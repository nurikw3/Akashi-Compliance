from __future__ import annotations

from enum import Enum

from app.services.enrichment.base import CompanyData


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RiskService:
    def calculate(self, data: CompanyData) -> RiskLevel:
        if data.in_sanctions_list and len(data.risk_flags) >= 2:
            return RiskLevel.HIGH

        score = len(data.status_flags) + len(data.risk_flags)
        if data.tax_debt and data.tax_debt > 1_000_000:
            score += 3
        elif data.tax_debt and data.tax_debt > 0:
            score += 1
        if data.court_cases and data.court_cases > 3:
            score += 2
        elif data.court_cases and data.court_cases > 0:
            score += 1
        status = (data.status or "").lower()
        if status in ("liquidated", "suspended", "ликвидирован", "приостановлен"):
            score += 4

        if score >= 5:
            return RiskLevel.HIGH
        if score >= 2:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW
