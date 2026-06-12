"""Pure helpers for OSINT: dedup digest, deterministic validation, section build.

These functions never trust the LLM blindly — :func:`validate_findings` is the
anti-hallucination gate that keeps only citations that actually came back from
the search provider and recomputes the source domain from the URL.
"""
from __future__ import annotations

from typing import Any

from app.services.osint.client import domain_of
from app.services.osint.prompts import CATEGORIES

_VALID_ROLES = {"company", "director", "founder"}


def _normalize_url(url: str) -> str:
    return (url or "").strip().rstrip("/").lower()


def lseg_adata_known_urls(enriched: dict[str, Any]) -> set[str]:
    """Normalized URLs already surfaced by LSEG (so OSINT can drop duplicates)."""
    urls: set[str] = set()
    if not isinstance(enriched, dict):
        return urls
    lseg = enriched.get("lseg")
    if not isinstance(lseg, dict):
        return urls

    media = lseg.get("adverseMedia") or {}
    for art in media.get("articles") or []:
        url = str((art or {}).get("url") or "").strip()
        if url:
            urls.add(_normalize_url(url))

    for hit in (lseg.get("sanctions") or {}).get("hits") or []:
        for link in (hit or {}).get("sourceReferenceLinks") or []:
            url = str((link or {}).get("url") or "").strip()
            if url:
                urls.add(_normalize_url(url))
    return urls


def build_lseg_adata_digest(enriched: dict[str, Any]) -> dict[str, Any]:
    """Compact view of what LSEG/Adata already know, for the dedup LLM pass."""
    enriched = enriched if isinstance(enriched, dict) else {}
    lseg = enriched.get("lseg") if isinstance(enriched.get("lseg"), dict) else {}
    enrichment = (
        enriched.get("enrichment")
        if isinstance(enriched.get("enrichment"), dict)
        else {}
    )

    sanctions = lseg.get("sanctions") or {}
    pep = lseg.get("pep") or {}
    media = lseg.get("adverseMedia") or {}
    adata_sanctions = enrichment.get("sanctions") or {}

    return {
        "lsegSanctionLists": sanctions.get("matchedLists") or [],
        "lsegSanctionNames": [
            str((h or {}).get("primaryName") or "").strip()
            for h in (sanctions.get("hits") or [])
            if (h or {}).get("primaryName")
        ][:30],
        "lsegPepNames": [
            str((p or {}).get("primaryName") or "").strip()
            for p in (pep.get("individuals") or [])
            if (p or {}).get("primaryName")
        ][:30],
        "lsegMediaHeadlines": [
            str((a or {}).get("headline") or "").strip()
            for a in (media.get("articles") or [])
            if (a or {}).get("headline")
        ][:40],
        "adataSanctionLists": adata_sanctions.get("lists") or [],
        "adataStatusFlags": (enrichment.get("statusFlags") or [])[:20],
        "adataRiskFlags": (enrichment.get("riskFlags") or [])[:20],
    }


def validate_findings(
    findings: list[dict[str, Any]],
    *,
    allowed_urls: set[str],
    known_urls: set[str],
) -> list[dict[str, Any]]:
    """Deterministic post-filter (anti-hallucination + dedup + normalization).

    Drops any finding whose ``sourceUrl`` was not actually returned by search,
    or that LSEG already surfaced, or whose category is outside the four
    triggers. ``sourceName`` is always recomputed from the URL domain.
    """
    allowed_norm = {_normalize_url(u) for u in allowed_urls}
    known_norm = {_normalize_url(u) for u in known_urls}

    clean: list[dict[str, Any]] = []
    for f in findings or []:
        if not isinstance(f, dict):
            continue
        url = str(f.get("sourceUrl") or "").strip()
        if not url:
            continue
        norm = _normalize_url(url)
        if norm not in allowed_norm:
            continue  # hallucinated / not from this search
        if norm in known_norm:
            continue  # already covered by LSEG/Adata
        category = str(f.get("category") or "").strip()
        if category not in CATEGORIES:
            continue
        role = str(f.get("subjectRole") or "").strip()
        if role not in _VALID_ROLES:
            role = "company"
        clean.append(
            {
                "subject": str(f.get("subject") or "").strip(),
                "subjectRole": role,
                "category": category,
                "title": str(f.get("title") or "").strip(),
                "summary": str(f.get("summary") or "").strip(),
                "sourceUrl": url,
                "sourceName": domain_of(url),
                "publishedDate": str(f.get("publishedDate") or "").strip() or None,
                "dedupNote": "не найдено в LSEG/Adata",
            }
        )
    return clean


def build_osint_section(
    *,
    findings: list[dict[str, Any]],
    subjects: list[dict[str, Any]],
    queries_used: list[str],
    screened_at: str,
) -> dict[str, Any]:
    """Assemble the ``enriched_data["osint"]`` block (facts-only, no scores)."""
    sources = list(
        dict.fromkeys(f["sourceName"] for f in findings if f.get("sourceName"))
    )
    counts = {"company": 0, "director": 0, "founder": 0}
    for f in findings:
        role = f.get("subjectRole")
        if role in counts:
            counts[role] += 1
    return {
        "screenedAt": screened_at,
        "subjects": subjects,
        "queriesUsed": queries_used,
        "sources": sources,
        "findings": findings,
        "counts": counts,
    }
