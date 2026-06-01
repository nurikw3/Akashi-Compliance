"""Unified risk scoring engine.

Produces a 0–100 score from 7 weighted metrics sourced from Adata enrichment
and LSEG World-Check One data.

Metric weights (total = 100):
  1. International sanctions  — 35 pts  (LSEG WC1; Adata — только КЗ санкц./крит.)
  2. Court activity           — 20 pts  (Adata courts + LLM severity)
  3. Tax compliance           — 15 pts  (Adata taxes + налоговый риск Adata)
  4. Legal status             — 15 pts  (Adata operatingStatus + status flags)
  5. PEP screening            —  5 pts  (LSEG individuals)
  6. Adverse media            —  5 pts  (LSEG Media-Check)
  7. Affiliate risk           —  5 pts  (affiliate tree)
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

_ADATA_SANCTION_KEYWORDS = (
    "террор",
    "экстрем",
    "санкц",
    "розыск",
    "запрещ",
    "лжепредпр",
    "педофил",
    "банкрот",
)


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


def _adata_sanction_flags(enrichment: dict[str, Any]) -> list[str]:
    flags = list(enrichment.get("statusFlags") or []) + list(
        enrichment.get("riskFlags") or []
    )
    return [
        flag
        for flag in flags
        if any(word in flag.lower() for word in _ADATA_SANCTION_KEYWORDS)
    ]


def _tax_risk_degree_flags(enrichment: dict[str, Any]) -> list[str]:
    return [
        flag
        for flag in enrichment.get("riskFlags") or []
        if "налоговый риск" in flag.lower()
    ]


class RiskScorer:
    """Calculate risk score from enriched_data (Adata) + optional lseg section."""

    @staticmethod
    def _lseg_requires_high_risk(lseg: dict[str, Any]) -> bool:
        san = lseg.get("sanctions") or {}
        if not san.get("isFormalSanction"):
            return False
        for hit in san.get("hits") or []:
            if hit.get("isSanction"):
                return True
            if not hit.get("isMaterialMatch"):
                continue
            try:
                score = float(hit.get("matchScore") or 0)
            except (TypeError, ValueError):
                score = 0.0
            strength = (hit.get("matchStrength") or "").upper()
            if strength in ("STRONG", "EXACT") and score >= 85:
                return True
        return False

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

        if lseg and self._lseg_requires_high_risk(lseg):
            risk_level = "high"

        return ScoringResult(
            total_score=round(total, 1),
            risk_level=risk_level,
            breakdown=breakdown,
        )

    def _metric_sanctions(
        self, enrichment: dict[str, Any], lseg: dict[str, Any] | None
    ) -> MetricResult:
        max_pts = 35.0

        if lseg and lseg.get("screenedAt"):
            san = lseg.get("sanctions") or {}
            screened_as = lseg.get("screenedName") or "компания"
            hits = san.get("hits") or []
            formal = [h for h in hits if h.get("isSanction")]

            if formal:
                lists = san.get("matchedLists") or []
                label = ", ".join(lists[:3]) if lists else "международные списки"
                names = ", ".join(
                    (h.get("primaryName") or "") for h in formal[:2] if h.get("primaryName")
                )
                detail = f" ({names})" if names else ""
                return MetricResult(
                    metric="sanctions",
                    points=max_pts,
                    max_points=max_pts,
                    reason=f"LSEG WC1: формальные санкции — {label}{detail}",
                    source="lseg",
                )

            material = [h for h in hits if h.get("isMaterialMatch")]
            if material:
                names = ", ".join(
                    (h.get("primaryName") or h.get("submittedName") or "совпадение")
                    for h in material[:2]
                )
                return MetricResult(
                    metric="sanctions",
                    points=max_pts * 0.6,
                    max_points=max_pts,
                    reason=(
                        f"LSEG WC1: сильные совпадения по «{screened_as}» — "
                        f"проверить вручную ({names})"
                    ),
                    source="lseg",
                )

            weak_hits = [
                h
                for h in hits
                if not h.get("isSanction") and not h.get("isMaterialMatch")
            ]
            if weak_hits:
                weak = len(weak_hits)
                return MetricResult(
                    metric="sanctions",
                    points=0,
                    max_points=max_pts,
                    reason=(
                        f"LSEG WC1: санкций нет; {weak} слабых совпадений по названию "
                        f"(см. вкладку LSEG, не влияют на балл)"
                    ),
                    source="lseg",
                )

            kz_flags = _adata_sanction_flags(enrichment)
            if kz_flags:
                return MetricResult(
                    metric="sanctions",
                    points=max_pts * 0.5,
                    max_points=max_pts,
                    reason=(
                        "LSEG WC1: международных санкций нет. "
                        f"Adata — критические флаги КЗ: {', '.join(kz_flags[:2])}"
                    ),
                    source="adata",
                )

            return MetricResult(
                metric="sanctions",
                points=0,
                max_points=max_pts,
                reason=(
                    f"LSEG WC1 ({screened_as}): в международных санкционных "
                    "списках не значится"
                ),
                source="lseg",
            )

        kz_flags = _adata_sanction_flags(enrichment)
        if kz_flags:
            terror = any(
                any(w in f.lower() for w in ("террор", "экстрем", "terror"))
                for f in kz_flags
            )
            pts = max_pts if terror else max_pts * 0.5
            return MetricResult(
                metric="sanctions",
                points=pts,
                max_points=max_pts,
                reason=f"Adata — санкционные/критические флаги КЗ: {', '.join(kz_flags[:3])}",
                source="adata",
            )

        return MetricResult(
            metric="sanctions",
            points=0,
            max_points=max_pts,
            reason="Международные и КЗ санкционные списки: совпадений нет",
            source="adata",
        )

    def _metric_courts(self, enrichment: dict[str, Any]) -> MetricResult:
        max_pts = 20.0
        courts = enrichment.get("courts") or {}
        active = int(courts.get("activeCases") or 0)
        scope = courts.get("scope") or "company"
        note = courts.get("note") or ""

        if active == 0:
            return MetricResult(
                metric="courts",
                points=0,
                max_points=max_pts,
                reason="Активных судебных дел нет",
                source="adata",
            )

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
            pts = max_pts
        elif active > 5:
            pts = max_pts * 0.85
        elif has_enforcement:
            pts = max_pts * 0.75
        elif active > 1:
            pts = max_pts * 0.5
        else:
            pts = max_pts * 0.25

        scope_hint = f", объект: {scope}" if scope != "company" else ""
        note_hint = f". {note}" if note else ""
        return MetricResult(
            metric="courts",
            points=pts,
            max_points=max_pts,
            reason=f"Активных дел: {active}{scope_hint}"
            + (" (есть уголовные)" if has_criminal else "")
            + note_hint,
            source="adata",
        )

    def _metric_taxes(self, enrichment: dict[str, Any]) -> MetricResult:
        max_pts = 15.0
        taxes = enrichment.get("taxes") or {}
        debt = float(taxes.get("debt") or 0)
        status = (taxes.get("status") or "clean").lower()
        tax_risk_flags = _tax_risk_degree_flags(enrichment)

        pts = 0.0
        parts: list[str] = []

        if debt > 0:
            if status == "critical" or debt >= 10_000_000:
                pts = max(pts, max_pts)
                parts.append(f"задолженность {debt:,.0f} тг (критическая)".replace(",", " "))
            elif debt >= 1_000_000:
                pts = max(pts, max_pts * 0.7)
                parts.append(f"задолженность {debt:,.0f} тг".replace(",", " "))
            else:
                pts = max(pts, max_pts * 0.3)
                parts.append(f"задолженность {debt:,.0f} тг".replace(",", " "))

        if tax_risk_flags:
            degree_text = tax_risk_flags[0]
            lowered = degree_text.lower()
            if "высок" in lowered or "high" in lowered:
                pts = max(pts, max_pts * 0.55)
            elif "средн" in lowered or "medium" in lowered:
                pts = max(pts, max_pts * 0.25)
            elif "низк" in lowered or "low" in lowered:
                pts = max(pts, max_pts * 0.1)
            parts.append(degree_text)

        if pts == 0:
            return MetricResult(
                metric="taxes",
                points=0,
                max_points=max_pts,
                reason="Налоговая задолженность отсутствует, риск-фактор Adata в норме",
                source="adata",
            )

        return MetricResult(
            metric="taxes",
            points=min(max_pts, round(pts, 1)),
            max_points=max_pts,
            reason="; ".join(parts),
            source="adata",
        )

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
                metric="legal_status",
                points=max_pts,
                max_points=max_pts,
                reason=f"Компания ликвидирована или исключена: {status or status_flags[0]}",
                source="adata",
            )

        if any(w in status for w in suspended):
            return MetricResult(
                metric="legal_status",
                points=max_pts * 0.6,
                max_points=max_pts,
                reason=f"Деятельность приостановлена: {status}",
                source="adata",
            )

        financial = [f for f in status_flags if "финансов" in f.lower()]
        if financial:
            return MetricResult(
                metric="legal_status",
                points=max_pts * 0.35,
                max_points=max_pts,
                reason=f"Статусные флаги Adata: {', '.join(financial[:2])}",
                source="adata",
            )

        if status_flags:
            return MetricResult(
                metric="legal_status",
                points=max_pts * 0.2 * min(len(status_flags), 2),
                max_points=max_pts,
                reason=f"Статусные флаги: {', '.join(status_flags[:2])}",
                source="adata",
            )

        return MetricResult(
            metric="legal_status",
            points=0,
            max_points=max_pts,
            reason=f"Правовой статус: {status or 'действующая'}",
            source="adata",
        )

    def _metric_pep(self, lseg: dict[str, Any] | None) -> MetricResult:
        max_pts = 5.0
        if not lseg:
            return MetricResult(
                metric="pep",
                points=0,
                max_points=max_pts,
                reason="LSEG не подключён — PEP-скрининг не выполнен",
                source="none",
            )

        pep = lseg.get("pep") or {}
        if pep.get("isHit"):
            individuals = pep.get("individuals") or []
            names = [
                i.get("primaryName", "")
                for i in individuals[:2]
                if i.get("primaryName")
            ]
            return MetricResult(
                metric="pep",
                points=max_pts,
                max_points=max_pts,
                reason=f"PEP совпадение (руководство): {', '.join(names) or 'физлицо'}",
                source="lseg",
            )

        return MetricResult(
            metric="pep",
            points=0,
            max_points=max_pts,
            reason="PEP-совпадений по руководителю не обнаружено",
            source="lseg",
        )

    def _metric_adverse_media(self, lseg: dict[str, Any] | None) -> MetricResult:
        max_pts = 5.0
        if not lseg:
            return MetricResult(
                metric="adverse_media",
                points=0,
                max_points=max_pts,
                reason="LSEG не подключён — мониторинг СМИ не выполнен",
                source="none",
            )

        media = lseg.get("adverseMedia") or {}
        negative_count = int(media.get("negativeCount") or 0)

        if negative_count == 0:
            return MetricResult(
                metric="adverse_media",
                points=0,
                max_points=max_pts,
                reason="Негативных публикаций в Media-Check не найдено",
                source="lseg",
            )

        pts = max_pts if negative_count >= 3 else max_pts * (negative_count / 3)
        return MetricResult(
            metric="adverse_media",
            points=round(pts, 1),
            max_points=max_pts,
            reason=f"Негативных публикаций в СМИ: {negative_count}",
            source="lseg",
        )

    def _metric_affiliate_risk(
        self,
        enrichment: dict[str, Any],
        affiliate_tree: dict[str, Any] | None,
    ) -> MetricResult:
        max_pts = 5.0

        if affiliate_tree:
            nodes: list[dict] = affiliate_tree.get("nodes") or []
            high_risk_nodes = [
                n for n in nodes if n.get("riskLevel") == "high" and not n.get("main")
            ]
            if high_risk_nodes:
                names = [n.get("label", "") for n in high_risk_nodes[:2]]
                return MetricResult(
                    metric="affiliate_risk",
                    points=max_pts,
                    max_points=max_pts,
                    reason=f"Аффилиат с высоким риском: {', '.join(names)}",
                    source="affiliate_tree",
                )

        affiliates = enrichment.get("affiliates") or {}
        companies = affiliates.get("companies") or []
        if len(companies) > 10:
            return MetricResult(
                metric="affiliate_risk",
                points=max_pts * 0.4,
                max_points=max_pts,
                reason=f"Расширенная сеть связей: {len(companies)} аффилиатов",
                source="adata",
            )

        return MetricResult(
            metric="affiliate_risk",
            points=0,
            max_points=max_pts,
            reason="Аффилиатов с высоким риском не выявлено",
            source="adata",
        )
