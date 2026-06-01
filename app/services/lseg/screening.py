from __future__ import annotations

from typing import Any

from app.services.company_display import is_placeholder_company_name

# WC1 fuzzy matches when the query was only a 12-digit BIN / "БИН …" string.
_BIN_QUERY_FALSE_POSITIVE_NAMES = (
    "BENEVOLENCE INTERNATIONAL",
    "BIN S.A",
    "BIN SP Z",
    "BANQUE ISLAMIQUE DU NIGER",
)


def filter_bin_query_false_positive_hits(
    hits: list[dict[str, Any]],
    *,
    screened_name: str,
    iin: str = "",
) -> list[dict[str, Any]]:
    """Drop obvious token matches caused by screening a BIN string instead of a legal name."""
    if not is_placeholder_company_name(screened_name, iin):
        return hits

    filtered: list[dict[str, Any]] = []
    for hit in hits:
        primary = (hit.get("primaryName") or "").upper()
        if any(token in primary for token in _BIN_QUERY_FALSE_POSITIVE_NAMES):
            continue
        strength = (hit.get("matchStrength") or "").upper()
        try:
            score = float(hit.get("matchScore") or 0)
        except (TypeError, ValueError):
            score = 0.0
        if strength not in ("STRONG", "EXACT") and score < 85:
            continue
        filtered.append(hit)
    return filtered
