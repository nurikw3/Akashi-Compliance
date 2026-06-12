"""OSINT web-search enrichment orchestration.

Supplements Adata / LSEG: generates targeted queries (company + director +
founders × 4 categories), searches the web, then a single LLM pass extracts only
novel findings (deduped against LSEG/Adata) with citations. A deterministic
post-filter kills hallucinated citations. Facts-only — no scores. Two LLM calls
total, all wrapped in one Langfuse trace.

Runs *after* the main enrichment + LSEG screen (so the dedup digest has their
facts) and writes ``enriched_data["osint"]`` while preserving every other key.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

from app.core.config import settings
from app.models import db
from app.services.ai.langfuse_setup import ai_trace, create_async_openai_client
from app.services.osint.client import SearchHit, get_search_client
from app.services.osint.mapper import (
    build_lseg_adata_digest,
    build_osint_section,
    lseg_adata_known_urls,
    validate_findings,
)
from app.services.osint.prompts import (
    CATEGORIES,
    EXTRACT_SYSTEM_PROMPT,
    QUERY_GEN_SYSTEM_PROMPT,
    _EXTRACT_FALLBACK,
    _QUERY_FALLBACK,
)
from app.services.verification_log import append_case_event

logger = logging.getLogger(__name__)

_MAX_FOUNDERS = 2
_MAX_QUERIES = 16
_SEARCH_CONCURRENCY = 3
_FOUNDER_ROLE_KEYWORDS = ("учред", "founder", "собственник", "участник", "бенефиц")
_PLACEHOLDER_NAMES = {"", "—", "-"}


def is_available() -> bool:
    """OSINT needs a search key *and* OpenAI (the two LLM passes are essential)."""
    return bool(
        settings.osint_enabled
        and settings.osint_search_api_key
        and settings.openai_api_key
    )


def _osint_model() -> str:
    """Model for OSINT's LLM passes; ``OSINT_MODEL`` overrides the global model."""
    return settings.osint_model or settings.openai_model


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _strip_code_fence(text: str) -> str:
    t = (text or "").strip()
    if t.startswith("```"):
        lines = t.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        t = "\n".join(lines).strip()
    return t


def _city_from_address(address: str) -> str:
    addr = (address or "").strip()
    if not addr or addr == "—":
        return ""
    # Adata addresses read "г. Алматы, ул. ..." — the leading chunk is the city.
    return addr.split(",")[0].strip()[:60]


def _build_subjects(enrichment: dict[str, Any], iin: str) -> list[dict[str, Any]]:
    """Company + director + up to two founders, each tagged with shared anchors."""
    info = enrichment.get("companyInfo") or {}
    company_name = str(info.get("fullName") or info.get("name") or "").strip()
    anchor = {
        "bin": iin,
        "company": company_name,
        "city": _city_from_address(str(info.get("address") or "")),
        "industry": str(info.get("industry") or "").strip(),
    }

    subjects: list[dict[str, Any]] = []
    seen: set[str] = set()

    if company_name and company_name not in (f"ИИН {iin}", "—"):
        subjects.append({"name": company_name, "role": "company", "anchor": anchor})
        seen.add(company_name.upper())

    director = str(info.get("director") or "").strip()
    if director and director not in _PLACEHOLDER_NAMES:
        subjects.append({"name": director, "role": "director", "anchor": anchor})
        seen.add(director.upper())

    founders_added = 0
    for person in (enrichment.get("affiliates") or {}).get("individuals") or []:
        name = str((person or {}).get("name") or "").strip()
        if not name or name.upper() in seen:
            continue
        role_txt = str(person.get("role") or "").lower()
        if any(kw in role_txt for kw in _FOUNDER_ROLE_KEYWORDS):
            subjects.append({"name": name, "role": "founder", "anchor": anchor})
            seen.add(name.upper())
            founders_added += 1
            if founders_added >= _MAX_FOUNDERS:
                break
    return subjects


async def _generate_queries(subjects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    user_payload = json.dumps(
        {"subjects": subjects, "categories": list(CATEGORIES)}, ensure_ascii=False
    )
    try:
        client = create_async_openai_client()
        response = await client.chat.completions.create(
            name="osint_query_gen",
            model=_osint_model(),
            messages=[
                {"role": "system", "content": QUERY_GEN_SYSTEM_PROMPT},
                {"role": "user", "content": user_payload},
            ],
            temperature=0.2,
            max_tokens=900,
        )
        raw = _strip_code_fence(response.choices[0].message.content or "")
        data = json.loads(raw)
    except Exception as exc:
        logger.warning("OSINT query generation failed: %s", exc)
        data = {**_QUERY_FALLBACK}

    queries: list[dict[str, Any]] = []
    for q in data.get("queries") or []:
        if not isinstance(q, dict):
            continue
        text = str(q.get("q") or "").strip()
        category = str(q.get("category") or "").strip()
        if not text or category not in CATEGORIES:
            continue
        queries.append(
            {
                "q": text,
                "subject": str(q.get("subject") or "").strip(),
                "category": category,
                "lang": str(q.get("lang") or "ru").strip() or "ru",
            }
        )
        if len(queries) >= _MAX_QUERIES:
            break
    return queries


async def _run_searches(queries: list[dict[str, Any]]) -> list[SearchHit]:
    client = get_search_client()
    if client is None:
        return []
    sem = asyncio.Semaphore(_SEARCH_CONCURRENCY)
    max_results = settings.osint_max_results

    async def _one(q: dict[str, Any]) -> list[SearchHit]:
        async with sem:
            await asyncio.sleep(0.2)  # gentle pacing, mirrors LSEG batch
            try:
                return await client.search(
                    q["q"], max_results=max_results, lang=q.get("lang")
                )
            except Exception as exc:
                logger.debug("OSINT search failed for %r: %s", q["q"], exc)
                return []

    results = await asyncio.gather(*[_one(q) for q in queries], return_exceptions=True)
    hits: list[SearchHit] = []
    for r in results:
        if isinstance(r, list):
            hits.extend(r)
    return _dedup_hits(hits)


def _dedup_hits(hits: list[SearchHit]) -> list[SearchHit]:
    seen: set[str] = set()
    out: list[SearchHit] = []
    for h in hits:
        key = h.url.strip().rstrip("/").lower()
        if key and key not in seen:
            seen.add(key)
            out.append(h)
    return out


async def _extract_findings(
    hits: list[SearchHit],
    digest: dict[str, Any],
    subjects: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    hits_payload = [
        {
            "title": h.title,
            "url": h.url,
            "snippet": h.snippet[:500],
            "publishedDate": h.published_date,
        }
        for h in hits
    ]
    user_payload = json.dumps(
        {"subjects": subjects, "webResults": hits_payload, "alreadyKnown": digest},
        ensure_ascii=False,
    )
    try:
        client = create_async_openai_client()
        response = await client.chat.completions.create(
            name="osint_extract",
            model=_osint_model(),
            messages=[
                {"role": "system", "content": EXTRACT_SYSTEM_PROMPT},
                {"role": "user", "content": user_payload},
            ],
            temperature=0.1,
            max_tokens=1800,
        )
        raw = _strip_code_fence(response.choices[0].message.content or "")
        data = json.loads(raw)
    except Exception as exc:
        logger.warning("OSINT extraction failed: %s", exc)
        data = {**_EXTRACT_FALLBACK}
    return data.get("findings") or []


def _persist(case_id: str, section: dict[str, Any] | None, *, status: str) -> None:
    """Re-read latest enriched_data and merge, preserving all sibling keys."""
    latest = db.get_case(case_id) or {}
    merged = latest.get("enriched_data") if isinstance(latest, dict) else {}
    merged = merged if isinstance(merged, dict) else {}
    if section is not None:
        merged["osint"] = section
    merged["osintStatus"] = status
    db.update_case(case_id, enriched_data=merged)


async def osint_screen(case_id: str, *, force: bool = False) -> bool:
    """Run OSINT enrichment for an already-enriched case. Returns True on success."""
    if not is_available():
        return False
    row = db.get_case(case_id)
    if row is None or row.get("status") != "ready":
        return False
    enriched = row.get("enriched_data")
    if not isinstance(enriched, dict):
        return False

    existing = enriched.get("osint")
    if not force and isinstance(existing, dict) and existing.get("screenedAt"):
        logger.debug("Skipping OSINT for %s — already screened (use force=True)", case_id)
        return True

    enrichment = enriched.get("enrichment") or {}
    iin = row["iin"]
    subjects = _build_subjects(enrichment, iin)

    if not subjects:
        section = build_osint_section(
            findings=[], subjects=[], queries_used=[], screened_at=_now_iso()
        )
        _persist(case_id, section, status="ready")
        return True

    try:
        with ai_trace(name="osint_screen", iin=iin, case_id=case_id):
            queries = await _generate_queries(subjects)
            hits: list[SearchHit] = []
            findings: list[dict[str, Any]] = []
            if queries:
                hits = await _run_searches(queries)
                if hits:
                    digest = build_lseg_adata_digest(enriched)
                    known_urls = lseg_adata_known_urls(enriched)
                    allowed_urls = {h.url for h in hits}
                    raw_findings = await _extract_findings(hits, digest, subjects)
                    findings = validate_findings(
                        raw_findings,
                        allowed_urls=allowed_urls,
                        known_urls=known_urls,
                    )

        section = build_osint_section(
            findings=findings,
            subjects=subjects,
            queries_used=[q["q"] for q in queries],
            screened_at=_now_iso(),
        )
        _persist(case_id, section, status="ready")
        append_case_event(
            case_id,
            provider="OSINT",
            action="screen",
            subject={"type": "BIN", "value": iin},
            request={
                "endpoint": settings.osint_search_provider,
                "queries": len(queries),
            },
            outcome={
                "status": "ok",
                "counts": {
                    "queries": len(queries),
                    "rawHits": len(hits),
                    "novelFindings": len(findings),
                },
            },
        )
        logger.info(
            "OSINT screen done for %s: %d queries, %d hits, %d novel findings",
            case_id,
            len(queries),
            len(hits),
            len(findings),
        )
        return True
    except Exception:
        logger.exception("OSINT screening failed for %s", case_id)
        _persist(case_id, None, status="error")
        append_case_event(
            case_id, provider="OSINT", action="screen", outcome={"status": "error"}
        )
        return False
