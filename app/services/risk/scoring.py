"""Unified risk scoring engine.

Produces a 0–100 score from 7 weighted metrics sourced from Adata enrichment
and LSEG World-Check One data. Replaces the two divergent models previously
living in risk/service.py and enrichment/mapper.py.

Metric weights (total = 100):
  1. International sanctions  — 35 pts  (LSEG WC1 + Adata flags)
  2. Court activity           — 20 pts  (Adata courts + LLM severity)
  3. Tax compliance           — 15 pts  (Adata taxes)
  4. Legal status             — 15 pts  (Adata operatingStatus)
  5. PEP screening            —  5 pts  (LSEG individuals)
  6. Adverse media            —  5 pts  (LSEG Media-Check)
  7. Affiliate risk           —  5 pts  (affiliate tree)
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class MetricResult:
    metric: str
    points: float
    max_points: float
    reason: str
    source: str


@dataclass
class ScoringResult:
    total_score: float
    risk_level: str
    breakdown: list[MetricResult]

    def breakdown_as_dicts(self) -> list[dict[str, Any]]:
        return [asdict(m) for m in self.breakdown]


class RiskScorer:
    """Calculate risk score from enriched_data (Adata) + optional lseg section."""

    def calculate(
        self,
        enrichment: dict[str, Any],
        lseg: dict[str, Any] | None = None,
        affiliate_tree: dict[str, Any] | None = None,
    ) -> ScoringResult:
        breakdown: list[MetricResult] = [
            self._metric_sanctions(enrichment, lseg),
            self._metric_courts(enrichment),
            self._metric_taxes(enrichment),
            self._metric_legal_status(enrichment),
            self._metric_pep(lseg),
            self._metric_adverse_media(lseg),
            self._metric_affiliate_risk(enrichment, affiliate_tree),
        ]

        total = sum(m.points for m in breakdown)
        total = min(100.0, total)

        if total >= 67:
            risk_level = "high"
        elif total >= 34:
            risk_level = "medium"
        else:
            risk_level = "low"

        return ScoringResult(
            total_score=round(total, 1),
            risk_level=risk_level,
            breakdown=breakdown,
        )

    # ── Metric 1: Sanctions (35 pts) ──────────────────────────────────────────

    def _metric_sanctions(
        self, enrichment: dict[str, Any], lseg: dict[str, Any] | None
    ) -> MetricResult:
        max_pts = 35.0

        # LSEG international sanctions take precedence
        if lseg:
            san = lseg.get("sanctions") or {}
            if san.get("isOnList"):
                lists = san.get("matchedLists") or []
                label = ", ".join(lists[:3]) if lists else "international watchlist"
                return MetricResult(
                    metric="sanctions",
                    points=max_pts,
                    max_points=max_pts,
                    reason=f"В санкционных списках: {label}",
                    source="lseg",
                )

        # Adata domestic flags
        sanctions = enrichment.get("sanctions") or {}
        risk_flags: list[str] = enrichment.get("riskFlags") or []

        if sanctions.get("isOnList"):
            all_flags = (sanctions.get("lists") or []) + risk_flags
            terror = any(
                w in f.lower() for f in all_flags
                for w in ("террор", "экстремизм", "terror")
            )
            pts = max_pts if terror else max_pts * 0.8
            return MetricResult(
                metric="sanctions",
                points=pts,
                max_points=max_pts,
                reason=f"КЗ санкционные флаги: {', '.join(risk_flags[:3])}",
                source="adata",
            )

        # Partial: severe risk flags without formal sanction listing
        severe = [
            f for f in risk_flags
            if any(w in f.lower() for w in ("террор", "банкрот", "розыск", "арест"))
        ]
        if severe:
            return MetricResult(
                metric="sanctions",
                points=max_pts * 0.4,
                max_points=max_pts,
                reason=f"Критические флаги риска: {', '.join(severe[:2])}",
                source="adata",
            )

        return MetricResult(
            metric="sanctions", points=0, max_points=max_pts,
            reason="Санкционных записей не обнаружено", source="adata",
        )

    # ── Metric 2: Court activity (20 pts) ────────────────────────────────────

    def _metric_courts(self, enrichment: dict[str, Any]) -> MetricResult:
        max_pts = 20.0
        courts = enrichment.get("courts") or {}
        active = int(courts.get("activeCases") or 0)

        if active == 0:
            return MetricResult(
                metric="courts", points=0, max_points=max_pts,
                reason="Активных судебных дел нет", source="adata",
            )

        # Check AI-classified severity in cases list
        cases_list: list[dict] = courts.get("cases") or []
        has_criminal = any(
            (c.get("aiAnalysis") or {}).get("category") == "criminal"
            for c in cases_list
        )
        has_enforcement = any(
            (c.get("aiAnalysis") or {}).get("category") == "enforcement"
            for c in cases_list
        )

        if has_criminal:
            pts = max_pts  # 20
        elif active > 5:
            pts = max_pts * 0.85
        elif has_enforcement:
            pts = max_pts * 0.75
        elif active > 1:
            pts = max_pts * 0.5
        else:
            pts = max_pts * 0.25

        return MetricResult(
            metric="courts",
            points=pts,
            max_points=max_pts,
            reason=f"Активных судебных дел: {active}"
            + (" (уголовные)" if has_criminal else ""),
            source="adata",
        )

    # ── Metric 3: Tax compliance (15 pts) ────────────────────────────────────

    def _metric_taxes(self, enrichment: dict[str, Any]) -> MetricResult:
        max_pts = 15.0
        taxes = enrichment.get("taxes") or {}
        debt = float(taxes.get("debt") or 0)
        status = (taxes.get("status") or "clean").lower()

        if debt == 0:
            return MetricResult(
                metric="taxes", points=0, max_points=max_pts,
                reason="Налоговых задолженностей нет", source="adata",
            )

        if status == "critical" or debt >= 10_000_000:
            pts = max_pts
            reason = f"Критическая налоговая задолженность: {debt:,.0f} тг"
        elif debt >= 1_000_000:
            pts = max_pts * 0.7
            reason = f"Значительная налоговая задолженность: {debt:,.0f} тг"
        else:
            pts = max_pts * 0.3
            reason = f"Налоговая задолженность: {debt:,.0f} тг"

        return MetricResult(
            metric="taxes", points=pts, max_points=max_pts,
            reason=reason.replace(",", " "), source="adata",
        )

    # ── Metric 4: Legal status (15 pts) ──────────────────────────────────────

    def _metric_legal_status(self, enrichment: dict[str, Any]) -> MetricResult:
        max_pts = 15.0
        info = enrichment.get("companyInfo") or {}
        status = (info.get("operatingStatus") or "").lower()
        status_flags: list[str] = enrichment.get("statusFlags") or []

        terminal = ("ликвидирован", "liquidated")
        suspended = ("приостановлен", "suspended", "временно приостановлена")

        if any(w in status for w in terminal) or any(
            any(w in f.lower() for w in terminal) for f in status_flags
        ):
            return MetricResult(
                metric="legal_status", points=max_pts, max_points=max_pts,
                reason=f"Компания ликвидирована: {status or ', '.join(status_flags[:1])}",
                source="adata",
            )

        if any(w in status for w in suspended):
            return MetricResult(
                metric="legal_status", points=max_pts * 0.6, max_points=max_pts,
                reason=f"Деятельность приостановлена: {status}",
                source="adata",
            )

        if status_flags:
            return MetricResult(
                metric="legal_status", points=max_pts * 0.4 * min(len(status_flags), 2) / 2,
                max_points=max_pts,
                reason=f"Статусные флаги: {', '.join(status_flags[:2])}",
                source="adata",
            )

        return MetricResult(
            metric="legal_status", points=0, max_points=max_pts,
            reason="Правовой статус в норме", source="adata",
        )

    # ── Metric 5: PEP screening (5 pts) ──────────────────────────────────────

    def _metric_pep(self, lseg: dict[str, Any] | None) -> MetricResult:
        max_pts = 5.0
        if not lseg:
            return MetricResult(
                metric="pep", points=0, max_points=max_pts,
                reason="LSEG не подключён — PEP-скрининг не выполнен", source="none",
            )

        pep = lseg.get("pep") or {}
        if pep.get("isHit"):
            individuals = pep.get("individuals") or []
            names = [i.get("primaryName", "") for i in individuals[:2] if i.get("primaryName")]
            return MetricResult(
                metric="pep", points=max_pts, max_points=max_pts,
                reason=f"PEP совпадение: {', '.join(names) or 'физическое лицо'}",
                source="lseg",
            )

        return MetricResult(
            metric="pep", points=0, max_points=max_pts,
            reason="PEP-совпадений не обнаружено", source="lseg",
        )

    # ── Metric 6: Adverse media (5 pts) ──────────────────────────────────────

    def _metric_adverse_media(self, lseg: dict[str, Any] | None) -> MetricResult:
        max_pts = 5.0
        if not lseg:
            return MetricResult(
                metric="adverse_media", points=0, max_points=max_pts,
                reason="LSEG не подключён — мониторинг СМИ не выполнен", source="none",
            )

        media = lseg.get("adverseMedia") or {}
        negative_count = int(media.get("negativeCount") or 0)

        if negative_count == 0:
            return MetricResult(
                metric="adverse_media", points=0, max_points=max_pts,
                reason="Негативных публикаций не обнаружено", source="lseg",
            )

        pts = max_pts if negative_count >= 3 else max_pts * (negative_count / 3)
        return MetricResult(
            metric="adverse_media",
            points=round(pts, 1),
            max_points=max_pts,
            reason=f"Негативных публикаций в СМИ: {negative_count}",
            source="lseg",
        )

    # ── Metric 7: Affiliate risk (5 pts) ─────────────────────────────────────

    def _metric_affiliate_risk(
        self,
        enrichment: dict[str, Any],
        affiliate_tree: dict[str, Any] | None,
    ) -> MetricResult:
        max_pts = 5.0

        # Check affiliate tree for high-risk nodes
        if affiliate_tree:
            nodes: list[dict] = affiliate_tree.get("nodes") or []
            high_risk_nodes = [
                n for n in nodes
                if n.get("riskLevel") == "high" and not n.get("main")
            ]
            if high_risk_nodes:
                names = [n.get("label", "") for n in high_risk_nodes[:2]]
                return MetricResult(
                    metric="affiliate_risk", points=max_pts, max_points=max_pts,
                    reason=f"Аффилиат с высоким риском: {', '.join(names)}",
                    source="affiliate_tree",
                )

        # Fallback: check enrichment affiliates count
        affiliates = enrichment.get("affiliates") or {}
        companies = affiliates.get("companies") or []
        if len(companies) > 10:
            return MetricResult(
                metric="affiliate_risk", points=max_pts * 0.4, max_points=max_pts,
                reason=f"Большое число аффилиатов: {len(companies)}",
                source="adata",
            )

        return MetricResult(
            metric="affiliate_risk", points=0, max_points=max_pts,
            reason="Аффилиатов с высоким риском не обнаружено", source="adata",
        )
