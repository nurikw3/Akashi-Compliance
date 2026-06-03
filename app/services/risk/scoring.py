"""Unified risk scoring engine (0–100).

Produces a compliance risk score from Adata enrichment, LSEG World-Check One,
and affiliate tree data.  Each metric maps to a real compliance concern and
carries a weight proportional to its regulatory significance.

Metric weights (total = 100)
────────────────────────────
  1. International sanctions   — 30 pts
     Source: LSEG WC1 (primary) / Adata (fallback КЗ-списки).
     Formal sanctions ↝ 30.  Material match (strong/exact ≥85) ↝ 18.
     KZ-only flags (терроризм, лжепредприятие) ↝ 15–30.
     Rationale: sanctions are the single strongest kill-deal signal per
     FATF/AML/CFT and Kazakhstan's FinMonitoring requirements.

  2. Court activity            — 20 pts
     Source: Adata enrichment.courts (company) + companyCourtCases/
     individualCourts (detailed).
     Criminal case ↝ 20.  Defendant in civil ↝ 10–16.  Third-party ↝ 2–6.
     Scales with active count.  LLM aiAnalysis.category used when available.
     Rationale: litigation is a core due-diligence signal; defendant status
     and criminal charges carry the highest weight.

  3. Tax compliance            — 15 pts
     Source: Adata taxes.debt, taxes.status, riskFactor (tax_risk_degree).
     Logarithmic scale: debt 50K→2, 500K→5, 1M→8, 5M→12, 10M+→15.
     tax_risk_degree from Adata adds up to 4 additional points (capped at 15).
     Rationale: tax arrears correlate with financial distress and regulatory
     enforcement; log-scale prevents small debts from over-scoring.

  4. PEP exposure              — 10 pts
     Source: LSEG PEP screening (individuals linked to entity).
     Any PEP hit ↝ 10.  No LSEG → 0 (cannot penalize without data).
     Rationale: PEP relationships trigger enhanced due diligence under FATF
     Recommendation 12 and KZ AML law (Article 5); previously under-weighted.

  5. Legal status              — 10 pts
     Source: Adata operatingStatus + statusFlags.
     Liquidated ↝ 10.  Suspended ↝ 6.  Financial-problem flags ↝ 3.5.
     Rationale: an inactive or bankrupt counterparty cannot fulfill obligations;
     weight reduced vs. prior version because liquidation is a blocker, not a
     graduated risk — the score signals "verify before proceeding".

  6. Adverse media             —  5 pts
     Source: LSEG Media-Check (negativeCount).
     ≥3 negative mentions ↝ 5.  Linear below 3.
     Rationale: media sentiment is a soft signal; confirms or amplifies other
     red flags rather than standing alone.

  7. Affiliate risk            — 10 pts
     Source: affiliate tree node risk levels + enriched affiliate profiles.
     High-risk affiliate ↝ 10.  Sanctioned affiliate (LSEG extended) ↝ 10.
     Many affiliates (>10) without high risk ↝ 3.
     Rationale: contagion risk from related entities is a key AML concern;
     previously under-weighted at 5 pts.

Risk levels:
  0–19   low       — standard procedure
  20–34  medium    — enhanced due diligence recommended
  35–49  high      — escalate to compliance committee
  50–100 critical  — likely deal-breaker; formal review required
  LSEG formal-sanction override → force "high" minimum.
"""
from __future__ import annotations

import math
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


def _log_debt_score(debt: float, max_pts: float) -> float:
    """Logarithmic mapping: 50K→2, 500K→5, 1M→8, 5M→12, 10M+→15."""
    if debt <= 0:
        return 0.0
    raw = max_pts * math.log10(max(debt, 1)) / math.log10(15_000_000)
    return min(max_pts, max(0, round(raw, 1)))


class RiskScorer:
    """Calculate 0-100 risk score from enriched_data + optional LSEG + tree."""

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
            self._metric_pep(lseg),
            self._metric_legal_status(enrichment),
            self._metric_adverse_media(lseg),
            self._metric_affiliate_risk(enrichment, affiliate_tree),
        ]

        total = min(100.0, sum(m.points for m in breakdown))

        if total >= 50:
            risk_level = "critical"
        elif total >= 35:
            risk_level = "high"
        elif total >= 20:
            risk_level = "medium"
        else:
            risk_level = "low"

        if lseg and self._lseg_requires_high_risk(lseg):
            if risk_level in ("low", "medium"):
                risk_level = "high"

        return ScoringResult(
            total_score=round(total, 1),
            risk_level=risk_level,
            breakdown=breakdown,
        )

    # ── 1. Sanctions (30 pts) ────────────────────────────────────────────

    def _metric_sanctions(
        self, enrichment: dict[str, Any], lseg: dict[str, Any] | None
    ) -> MetricResult:
        max_pts = 30.0

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
                return MetricResult(
                    metric="sanctions",
                    points=0,
                    max_points=max_pts,
                    reason=(
                        f"LSEG WC1: санкций нет; {len(weak_hits)} слабых совпадений "
                        f"(не влияют на балл)"
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

    # ── 2. Courts (20 pts) ───────────────────────────────────────────────

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
        defendant_count = sum(
            1 for c in cases_list
            if str(c.get("role") or "").lower() in ("ответчик", "defendant")
        )

        if has_criminal:
            pts = max_pts
            detail = "уголовные дела"
        elif defendant_count >= 3:
            pts = max_pts * 0.8
            detail = f"ответчик в {defendant_count} делах"
        elif active > 5:
            pts = max_pts * 0.75
            detail = f"много дел ({active})"
        elif has_enforcement:
            pts = max_pts * 0.65
            detail = "исполнительное производство"
        elif defendant_count >= 1:
            pts = max_pts * 0.5
            detail = f"ответчик в {defendant_count} деле(ах)"
        elif active > 1:
            pts = max_pts * 0.3
            detail = f"третья сторона / истец, {active} дел"
        else:
            pts = max_pts * 0.15
            detail = "третья сторона / истец, 1 дело"

        scope_hint = f", объект: {scope}" if scope != "company" else ""
        note_hint = f". {note}" if note else ""
        return MetricResult(
            metric="courts",
            points=round(pts, 1),
            max_points=max_pts,
            reason=f"Активных дел: {active} ({detail}{scope_hint}){note_hint}",
            source="adata",
        )

    # ── 3. Taxes (15 pts) ────────────────────────────────────────────────

    def _metric_taxes(self, enrichment: dict[str, Any]) -> MetricResult:
        max_pts = 15.0
        taxes = enrichment.get("taxes") or {}
        debt = float(taxes.get("debt") or 0)
        tax_risk_flags = _tax_risk_degree_flags(enrichment)

        debt_pts = _log_debt_score(debt, max_pts)

        degree_pts = 0.0
        if tax_risk_flags:
            lowered = tax_risk_flags[0].lower()
            if "высок" in lowered or "high" in lowered:
                degree_pts = 4.0
            elif "средн" in lowered or "medium" in lowered:
                degree_pts = 2.0
            elif "низк" in lowered or "low" in lowered:
                degree_pts = 0.5

        pts = min(max_pts, debt_pts + degree_pts)

        if pts == 0:
            return MetricResult(
                metric="taxes",
                points=0,
                max_points=max_pts,
                reason="Налоговая задолженность отсутствует, риск-фактор Adata в норме",
                source="adata",
            )

        parts: list[str] = []
        if debt > 0:
            parts.append(f"задолженность {debt:,.0f} тг ({debt_pts:.0f} б.)".replace(",", " "))
        if tax_risk_flags:
            parts.append(f"{tax_risk_flags[0]} (+{degree_pts:.0f} б.)")

        return MetricResult(
            metric="taxes",
            points=round(pts, 1),
            max_points=max_pts,
            reason="; ".join(parts),
            source="adata",
        )

    # ── 4. PEP exposure (10 pts) ─────────────────────────────────────────

    def _metric_pep(self, lseg: dict[str, Any] | None) -> MetricResult:
        max_pts = 10.0
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

    # ── 5. Legal status (10 pts) ─────────────────────────────────────────

    def _metric_legal_status(self, enrichment: dict[str, Any]) -> MetricResult:
        max_pts = 10.0
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

    # ── 6. Adverse media (5 pts) ─────────────────────────────────────────

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

    # ── 7. Affiliate risk (10 pts) ───────────────────────────────────────

    def _metric_affiliate_risk(
        self,
        enrichment: dict[str, Any],
        affiliate_tree: dict[str, Any] | None,
    ) -> MetricResult:
        max_pts = 10.0

        if affiliate_tree:
            nodes: list[dict] = affiliate_tree.get("nodes") or []
            high_risk_nodes = [
                n for n in nodes if n.get("riskLevel") == "high" and not n.get("main")
            ]
            sanctioned_nodes = [
                n for n in nodes if n.get("isSanctioned") and not n.get("main")
            ]

            if sanctioned_nodes:
                names = [n.get("label", "") for n in sanctioned_nodes[:2]]
                return MetricResult(
                    metric="affiliate_risk",
                    points=max_pts,
                    max_points=max_pts,
                    reason=f"Санкционный аффилиат: {', '.join(names)}",
                    source="affiliate_tree",
                )

            if high_risk_nodes:
                names = [n.get("label", "") for n in high_risk_nodes[:2]]
                pts = max_pts if len(high_risk_nodes) >= 2 else max_pts * 0.7
                return MetricResult(
                    metric="affiliate_risk",
                    points=pts,
                    max_points=max_pts,
                    reason=f"Аффилиат с высоким риском: {', '.join(names)}",
                    source="affiliate_tree",
                )

        affiliates = enrichment.get("affiliates") or {}
        companies = affiliates.get("companies") or []
        if len(companies) > 10:
            return MetricResult(
                metric="affiliate_risk",
                points=max_pts * 0.3,
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
