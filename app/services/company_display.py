from __future__ import annotations

import re
from typing import Any

_PLACEHOLDER_NAME = re.compile(r"^(бин|иин)\s*\d{12}$", re.IGNORECASE)


def is_placeholder_company_name(name: str, iin: str) -> bool:
    cleaned = (name or "").strip()
    if not cleaned:
        return True
    if _PLACEHOLDER_NAME.match(cleaned):
        return True
    digits = re.sub(r"\D", "", cleaned)
    return digits == iin and len(digits) == 12


def resolve_company_display_name(
    company_name: str,
    iin: str,
    enrichment: dict[str, Any] | None = None,
) -> str:
    info = (enrichment or {}).get("companyInfo") or {}
    from_enrichment = (info.get("fullName") or "").strip()
    if from_enrichment and from_enrichment not in ("—", "-"):
        if is_placeholder_company_name(company_name, iin):
            return from_enrichment
    cleaned = (company_name or "").strip()
    if cleaned and not is_placeholder_company_name(cleaned, iin):
        return cleaned
    return from_enrichment or cleaned or f"БИН {iin}"
