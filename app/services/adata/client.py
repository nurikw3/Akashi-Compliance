"""Adata.kz HTTP client.

Primary source (one start + poll cycle):
  GET {ADATA_BASE_URL}/info/{ADATA_TOKEN}?iinBin=...
  GET {ADATA_BASE_URL}/info/check/{ADATA_TOKEN}?token={jobToken}

Fallback endpoints (only when a field is missing from ``info`` ``data``):
  basic, riskfactor, trustworthy-extended, relation, courtcase

Report PDF uses ``/report/`` (unchanged).
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import httpx

from app.core.config import (
    normalize_adata_courtcase_base_url,
    normalize_adata_individual_base_url,
    settings,
)
from app.services.cache import ADATA_TTL, DIRECTOR_IIN_TTL, adata_key, get_cached, set_cached
from app.services.verification_log import append_case_event

logger = logging.getLogger(__name__)


class AdataError(Exception):
    pass


# Keys searched in nested info payloads (Kazakh API naming variants).
_NAME_KEYS = frozenset(
    {
        "name",
        "name_ru",
        "short_name",
        "companyname",
        "organizationname",
        "full_name",
        "fullname",
        "fullnamekz",
        "fullnameru",
    }
)
_DIRECTOR_KEYS = frozenset({"director", "head", "ceo", "manager", "head_name", "directorname"})
_STATUS_KEYS = frozenset(
    {
        "status",
        "company_status",
        "company_status_name",
        "companystatus",
        "company_state",
        "active",
    }
)
_ADDRESS_KEYS = frozenset(
    {
        "address",
        "legal_addres",
        "legal_address",
        "legaladdress",
        "factaddress",
        "registeredaddress",
        "jur_address",
    }
)
_TAX_DEBT_KEYS = frozenset(
    {"taxdebt", "tax_debt", "debt", "taxarrears", "tax_arrears", "sum", "amount"}
)
_SANCTION_KEYS = frozenset({"sanction", "sanctions", "inlist", "matched", "in_sanctions_list"})
_RELATION_KEYS = frozenset(
    {"affiliation_by_company", "affiliation_by_head", "affiliation_by_founder"}
)
_COURT_KEYS = frozenset(
    {
        "court_cases",
        "courtcases",
        "total_civil_count",
        "total_criminal_count",
        "courtcase",
    }
)
_RISK_BOOL_KEYS = frozenset(
    {
        "bankrupt",
        "tax_debt",
        "taxdebt",
        "inactive",
        "pseudo_company",
        "court_cases",
        "courtcases",
    }
)


def _check_url() -> str:
    base = settings.adata_base_url.rstrip("/")
    return f"{base}/info/check/{settings.adata_token}"


def _token_path(suffix: str) -> str:
    base = settings.adata_base_url.rstrip("/")
    return f"{base}/{suffix}/{settings.adata_token}"


def _courtcase_token_path() -> str:
    base = normalize_adata_courtcase_base_url(settings.adata_base_url)
    return f"{base}/{settings.adata_token}"


def deep_find(value: Any, keys: frozenset[str] | set[str]) -> Any:
    """Return the first non-empty value for any key in ``keys`` (case-insensitive)."""
    if isinstance(value, dict):
        for key, nested in value.items():
            if key.lower() in keys:
                if nested not in (None, "", [], {}):
                    return nested
        for nested in value.values():
            found = deep_find(nested, keys)
            if found not in (None, "", [], {}):
                return found
    elif isinstance(value, list):
        for nested in value:
            found = deep_find(nested, keys)
            if found not in (None, "", [], {}):
                return found
    return None


def info_has(value: Any, keys: frozenset[str] | set[str]) -> bool:
    return deep_find(value, keys) is not None


def _is_aggregate_court_year_row(row: dict[str, Any]) -> bool:
    """Yearly litigation summary row (not a single court case)."""
    if row.get("year") and any(
        row.get(k) is not None for k in ("civil_count", "criminal_count", "administrative_count")
    ):
        return True
    return False


def _is_detailed_court_case_row(row: dict[str, Any]) -> bool:
    """Single court case with number, parties, documents, or history."""
    if _is_aggregate_court_year_row(row):
        return False
    if row.get("number"):
        return True
    if row.get("court") or row.get("category") or row.get("documents") or row.get("history"):
        return True
    return False


def _court_cases_last_page(data: dict[str, Any]) -> int:
    last_page = (
        data.get("last_page")
        or data.get("lastPage")
        or data.get("total_pages")
        or data.get("totalPages")
    )
    try:
        return max(1, int(last_page)) if last_page is not None else 1
    except (TypeError, ValueError):
        return 1


async def _merge_company_info_court_pages(
    client: httpx.AsyncClient,
    job_token: str,
    data: dict[str, Any],
) -> dict[str, Any]:
    """Merge paginated ``court_cases`` from company info/check when present."""
    raw_cases = data.get("court_cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        return data
    if not any(_is_detailed_court_case_row(r) for r in raw_cases if isinstance(r, dict)):
        return data

    pages_total = _court_cases_last_page(data)
    if pages_total <= 1:
        return data

    check_url = _check_url()
    merged: list[Any] = list(raw_cases)
    for page in range(2, pages_total + 1):
        response = await client.get(check_url, params={"token": job_token, "page": page})
        response.raise_for_status()
        page_data = response.json().get("data")
        if isinstance(page_data, dict):
            merged.extend(page_data.get("court_cases") or [])

    return {**data, "court_cases": merged}


async def _poll(
    client: httpx.AsyncClient,
    job_token: str,
    *,
    attempts: int | None = None,
    delay: float | None = None,
) -> dict[str, Any]:
    attempts = attempts or settings.adata_poll_attempts
    delay = delay or settings.adata_poll_delay_seconds
    check_url = _check_url()
    for _ in range(attempts):
        await asyncio.sleep(delay)
        response = await client.get(check_url, params={"token": job_token})
        response.raise_for_status()
        data = response.json()
        if data.get("data") is not None:
            return data
    return {"error": "timeout"}


async def _get_endpoint(
    client: httpx.AsyncClient, path_suffix: str, bin_value: str
) -> dict[str, Any]:
    url = _token_path(path_suffix)
    response = await client.get(url, params={"iinBin": bin_value})
    response.raise_for_status()
    payload = response.json()
    if "token" not in payload:
        return payload
    return await _poll(client, payload["token"])


async def fetch_company_info(bin_value: str, *, case_id: str | None = None) -> dict[str, Any]:
    """Start company info job and poll until ``data`` is ready; return that object."""
    if not settings.adata_token:
        raise AdataError("ADATA_TOKEN is not configured")

    cache_key = adata_key("info", bin_value)
    cached = await get_cached(cache_key)
    if cached is not None:
        if case_id:
            append_case_event(
                case_id,
                provider="Adata",
                action="company_info (cached)",
                subject={"type": "BIN", "value": bin_value},
                request={"endpoint": "/company/info", "params": {"iinBin": bin_value}},
                outcome={"status": "ok", "cached": True},
            )
        return cached

    timeout = settings.adata_timeout_seconds
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(_token_path("info"), params={"iinBin": bin_value})
        response.raise_for_status()
        payload = response.json()
        if "token" not in payload:
            if isinstance(payload.get("data"), dict):
                if case_id:
                    append_case_event(
                        case_id,
                        provider="Adata",
                        action="company_info",
                        subject={"type": "BIN", "value": bin_value},
                        request={"endpoint": "/company/info", "params": {"iinBin": bin_value}},
                        outcome={"status": "ok", "cached": False, "meta": {"poll": False}},
                    )
                return payload["data"]
            raise AdataError("Company info start did not return a job token or data")

        result = await _poll(client, payload["token"])
        if result.get("error"):
            raise AdataError(f"Company info poll failed: {result['error']}")
        data = result.get("data")
        if not isinstance(data, dict):
            raise AdataError("Company info poll returned no data")
        data = await _merge_company_info_court_pages(client, payload["token"], data)
        await set_cached(cache_key, data, ADATA_TTL)
        if case_id:
            append_case_event(
                case_id,
                provider="Adata",
                action="company_info",
                subject={"type": "BIN", "value": bin_value},
                request={"endpoint": "/company/info → /company/info/check", "params": {"iinBin": bin_value}},
                outcome={"status": "ok", "cached": False, "meta": {"poll": True}},
            )
        return data


def _fallbacks_for_info(info_data: dict[str, Any]) -> list[str]:
    """Endpoint suffixes to call when ``info`` does not contain enough data."""
    from app.services.adata.info_mapper import info_has_structured_blocks

    if info_has_structured_blocks(info_data):
        needed: list[str] = []
        basic = info_data.get("basic") or {}
        if not (basic.get("short_name") or basic.get("name_ru")):
            needed.append("basic")
        status = info_data.get("status") or {}
        if status.get("tax_debt") is None and not info_data.get("riskFactor"):
            needed.append("riskfactor")
        if not info_data.get("riskFactor") and not info_has(info_data, _SANCTION_KEYS):
            needed.append("trustworthy-extended")
        diagram = info_data.get("connectedDiagram") or {}
        if not any(
            diagram.get(k)
            for k in ("affiliation_by_company", "affiliation_by_head", "affiliation_by_founder")
        ):
            needed.append("relation")
        from app.services.adata.info_mapper import _litigation_totals

        lit = info_data.get("litigation") or {}
        risk = info_data.get("riskFactor") or {}
        head_lit = (risk.get("head") or {}).get("litigation") if isinstance(risk, dict) else {}
        if _litigation_totals(lit) + _litigation_totals(head_lit) == 0:
            needed.append("courtcase")
        return needed

    needed = []
    if not info_has(info_data, _NAME_KEYS) and not info_has(info_data, _DIRECTOR_KEYS):
        needed.append("basic")
    if not info_has(info_data, _TAX_DEBT_KEYS) and not info_has(info_data, _RISK_BOOL_KEYS):
        needed.append("riskfactor")
    if not info_has(info_data, _SANCTION_KEYS):
        needed.append("trustworthy-extended")
    if not info_has(info_data, _RELATION_KEYS):
        needed.append("relation")
    if not info_has(info_data, _COURT_KEYS):
        needed.append("courtcase")
    return needed


async def get_basic(client: httpx.AsyncClient, bin_value: str) -> dict[str, Any]:
    return await _get_endpoint(client, "basic", bin_value)


async def get_riskfactor(client: httpx.AsyncClient, bin_value: str) -> dict[str, Any]:
    return await _get_endpoint(client, "riskfactor", bin_value)


async def get_sanctions(client: httpx.AsyncClient, bin_value: str) -> dict[str, Any]:
    return await _get_endpoint(client, "trustworthy-extended", bin_value)


async def get_courtcase(client: httpx.AsyncClient, bin_value: str) -> dict[str, Any]:
    url = _courtcase_token_path()
    response = await client.get(url, params={"iinBin": bin_value})
    response.raise_for_status()
    payload = response.json()
    if "token" not in payload:
        return payload
    return await _poll(client, payload["token"])


async def get_relation(client: httpx.AsyncClient, bin_value: str) -> dict[str, Any]:
    url = _token_path("relation")
    response = await client.get(url, params={"iinBin": bin_value})
    response.raise_for_status()
    payload = response.json()
    if not payload.get("success", True) and "token" not in payload:
        return payload
    if "token" not in payload:
        return payload
    return await _poll(client, payload["token"])


_RAW_KEYS = {
    "basic": "basic",
    "riskfactor": "riskfactor",
    "trustworthy-extended": "sanctions",
    "relation": "relation",
    "courtcase": "courtcase",
}


async def _fetch_fallback(
    client: httpx.AsyncClient, suffix: str, bin_value: str
) -> dict[str, Any]:
    if suffix == "basic":
        return await get_basic(client, bin_value)
    if suffix == "riskfactor":
        return await get_riskfactor(client, bin_value)
    if suffix == "trustworthy-extended":
        return await get_sanctions(client, bin_value)
    if suffix == "relation":
        return await get_relation(client, bin_value)
    if suffix == "courtcase":
        return await get_courtcase(client, bin_value)
    raise AdataError(f"Unknown fallback endpoint: {suffix}")


async def run_parallel_checks(bin_value: str, *, case_id: str | None = None) -> dict[str, Any]:
    """Fetch company info first, then optional fallback endpoints for missing fields."""
    if not settings.adata_token:
        raise AdataError("ADATA_TOKEN is not configured")

    result: dict[str, Any] = {}
    info_data: dict[str, Any] = {}

    try:
        info_data = await fetch_company_info(bin_value, case_id=case_id)
        result["info"] = {"success": True, "data": info_data}
    except Exception as exc:
        logger.info(
            "Adata company info failed for BIN %s: %s",
            bin_value,
            exc,
        )
        if case_id:
            append_case_event(
                case_id,
                provider="Adata",
                action="company_info",
                subject={"type": "BIN", "value": bin_value},
                request={"endpoint": "/company/info", "params": {"iinBin": bin_value}},
                outcome={"status": "error", "cached": False, "message": str(exc)[:200]},
            )
        result["info"] = {"error": str(exc)}

    fallbacks = _fallbacks_for_info(info_data) if info_data else list(_RAW_KEYS.keys())
    if case_id:
        append_case_event(
            case_id,
            provider="Adata",
            action="fallbacks_selected",
            subject={"type": "BIN", "value": bin_value},
            request={"endpoint": "fallbacks_for_info"},
            outcome={"status": "ok", "counts": {"fallbacks": len(fallbacks)}, "meta": {"endpoints": fallbacks}},
        )

    timeout = settings.adata_timeout_seconds
    async with httpx.AsyncClient(timeout=timeout) as client:
        if fallbacks:

            async def _run_one(suffix: str) -> tuple[str, Any]:
                try:
                    return suffix, await _fetch_fallback(client, suffix, bin_value)
                except Exception as exc:
                    logger.info(
                        "Adata %s failed for BIN %s: %s",
                        suffix,
                        bin_value,
                        exc,
                    )
                    return suffix, exc

            pairs = await asyncio.gather(*[_run_one(s) for s in fallbacks])
            for suffix, value in pairs:
                raw_key = _RAW_KEYS[suffix]
                if isinstance(value, Exception):
                    result[raw_key] = {"error": str(value), "source": raw_key}
                    endpoint = "/courtcase" if suffix == "courtcase" else f"/company/{suffix}"
                    if case_id:
                        append_case_event(
                            case_id,
                            provider="Adata",
                            action=f"fallback:{suffix}",
                            subject={"type": "BIN", "value": bin_value},
                            request={"endpoint": endpoint, "params": {"iinBin": bin_value}},
                            outcome={"status": "error", "cached": False, "message": str(value)[:200]},
                        )
                else:
                    result[raw_key] = value
                    endpoint = "/courtcase" if suffix == "courtcase" else f"/company/{suffix}"
                    if case_id:
                        append_case_event(
                            case_id,
                            provider="Adata",
                            action=f"fallback:{suffix}",
                            subject={"type": "BIN", "value": bin_value},
                            request={"endpoint": endpoint, "params": {"iinBin": bin_value}},
                            outcome={"status": "ok", "cached": False},
                        )

    return result


async def fetch_pdf_report_url(iin: str) -> str:
    """Return Adata PDF download URL (report token + poll info/check for ``data.location``)."""
    if not settings.adata_token:
        raise AdataError("ADATA_TOKEN is not configured")

    report_url = _token_path("report")
    check_url = _check_url()
    timeout = max(settings.adata_timeout_seconds, 35.0)

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(report_url, params={"iinBin": iin})
        response.raise_for_status()
        data = response.json()
        if not data.get("success"):
            raise AdataError(f"Report init failed: {data}")
        job_token = data.get("token")
        if not job_token:
            raise AdataError("No token in report response")

        for _ in range(10):
            await asyncio.sleep(3)
            check = await client.get(check_url, params={"token": job_token})
            check.raise_for_status()
            result = check.json()
            location = (result.get("data") or {}).get("location")
            if location:
                return str(location)

    raise AdataError("PDF report generation timeout after 30s")


async def download_company_report(bin_value: str, out_path: Path) -> Path:
    """Download Adata PDF to *out_path* (uses :func:`fetch_pdf_report_url`)."""
    pdf_url = await fetch_pdf_report_url(bin_value)
    timeout = max(settings.adata_timeout_seconds, 35.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(pdf_url, follow_redirects=True)
        response.raise_for_status()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(response.content)
        return out_path


# ---------------------------------------------------------------------------
# Helpers for new endpoints
# ---------------------------------------------------------------------------


def _relation_scheme_check_url() -> str:
    base = settings.adata_base_url.rstrip("/")
    return f"{base}/relation-scheme/check/{settings.adata_token}"


async def _poll_with_url(
    client: httpx.AsyncClient,
    job_token: str,
    check_url: str,
    *,
    attempts: int | None = None,
    delay: float | None = None,
) -> dict[str, Any]:
    """Like ``_poll`` but accepts an explicit *check_url* instead of the default info/check."""
    attempts = attempts or settings.adata_poll_attempts
    delay = delay or settings.adata_poll_delay_seconds
    for _ in range(attempts):
        await asyncio.sleep(delay)
        response = await client.get(check_url, params={"token": job_token})
        response.raise_for_status()
        data = response.json()
        if data.get("data") is not None:
            return data
    return {"error": "timeout"}


def _normalize_iin_digits(value: Any) -> str | None:
    if value is None:
        return None
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    if len(digits) == 12:
        return digits
    return None


_DIRECTOR_IIN_KEYS = frozenset(
    {"head_biin", "director_iin", "head_iin", "head_biin_formatted", "head_bin_formatted"}
)


def _extract_director_iin_from_basic_payload(payload: dict[str, Any]) -> str | None:
    """Extract 12-digit director IIN from basic endpoint or nested basic blocks."""
    blocks: list[dict[str, Any]] = []
    if isinstance(payload, dict):
        blocks.append(payload)
        data = payload.get("data")
        if isinstance(data, dict):
            blocks.append(data)
            nested_basic = data.get("basic")
            if isinstance(nested_basic, dict):
                blocks.append(nested_basic)
        basic = payload.get("basic")
        if isinstance(basic, dict):
            blocks.append(basic)

    for block in blocks:
        for key in _DIRECTOR_IIN_KEYS:
            iin = _normalize_iin_digits(block.get(key))
            if iin:
                return iin

    found = deep_find(payload, _DIRECTOR_IIN_KEYS)
    return _normalize_iin_digits(found)


def _individual_api_base() -> str:
    return normalize_adata_individual_base_url(settings.adata_base_url)


def _individual_token_path(suffix: str) -> str:
    base = _individual_api_base().rstrip("/")
    return f"{base}/{suffix}/{settings.adata_token}"


def _individual_info_check_url() -> str:
    return _individual_token_path("info/check")


async def fetch_individual_info(
    iin: str, *, case_id: str | None = None
) -> dict[str, Any]:
    """Return individual profile from ``/api/individual/info``, cached 12h.

    Response includes basicFl (name, birth, alive, is_public_official),
    reliabilityFl (terrorist, enforcement_debt, etc.), courtCaseFl, affiliationFl.
    """
    cache_key = adata_key("individual_info", iin)
    cached = await get_cached(cache_key)
    if cached is not None:
        if case_id:
            append_case_event(
                case_id,
                provider="Adata",
                action="individual_info (cached)",
                subject={"type": "IIN", "value": iin},
                request={"endpoint": "/individual/info", "params": {"iinBin": iin}},
                outcome={"status": "ok", "cached": True},
            )
        return cached

    if not settings.adata_token:
        return {}

    try:
        timeout = settings.adata_timeout_seconds
        check_url = _individual_info_check_url()
        async with httpx.AsyncClient(timeout=timeout) as client:
            url = _individual_token_path("info")
            response = await client.get(url, params={"iinBin": iin})
            response.raise_for_status()
            payload = response.json()
            if not payload.get("success", True) and "token" not in payload:
                logger.warning("individual info init failed for IIN %s: %s", iin, payload.get("message") or payload)
                return {}
            job_token = payload.get("token")
            if not job_token:
                data = payload.get("data")
                if isinstance(data, dict):
                    await set_cached(cache_key, data, ADATA_TTL)
                    return data
                return {}

            attempts = settings.adata_poll_attempts
            delay = settings.adata_poll_delay_seconds
            for _ in range(attempts):
                await asyncio.sleep(delay)
                check = await client.get(check_url, params={"token": job_token})
                check.raise_for_status()
                result = check.json()
                data = result.get("data")
                if isinstance(data, dict) and data.get("basicFl"):
                    await set_cached(cache_key, data, ADATA_TTL)
                    if case_id:
                        append_case_event(
                            case_id,
                            provider="Adata",
                            action="individual_info",
                            subject={"type": "IIN", "value": iin},
                            request={"endpoint": "/individual/info → /individual/info/check", "params": {"iinBin": iin}},
                            outcome={"status": "ok", "cached": False},
                        )
                    return data

            return {}
    except Exception as exc:
        logger.warning("fetch_individual_info failed for IIN %s: %s", iin, exc)
        if case_id:
            append_case_event(
                case_id,
                provider="Adata",
                action="individual_info",
                subject={"type": "IIN", "value": iin},
                request={"endpoint": "/individual/info", "params": {"iinBin": iin}},
                outcome={"status": "error", "cached": False, "message": str(exc)[:200]},
            )
        return {}


def _normalize_court_documents(docs_raw: Any) -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    if not isinstance(docs_raw, list):
        return documents
    for doc in docs_raw:
        if not isinstance(doc, dict):
            continue
        file_name = doc.get("file_name") or doc.get("fileName")
        doc_link = doc.get("doc_link") or doc.get("docLink")
        if file_name or doc_link:
            documents.append(
                {
                    "file_name": str(file_name) if file_name else None,
                    "doc_link": str(doc_link) if doc_link else None,
                }
            )
    return documents


def _normalize_individual_court_case(raw: dict[str, Any]) -> dict[str, Any]:
    history: list[dict[str, Any]] = []
    for event in raw.get("history") or []:
        if not isinstance(event, dict):
            continue
        history.append(
            {
                "event_date": event.get("event_date") or event.get("eventDate"),
                "name": event.get("name"),
                "documents": _normalize_court_documents(event.get("documents")),
            }
        )

    case_documents = _normalize_court_documents(raw.get("documents"))
    defendants = list(raw.get("defendants") or [])
    plaintiffs = list(raw.get("plaintiffs") or [])
    participants: list[str] = []
    sides = raw.get("sides")
    if isinstance(sides, list):
        participants = [str(s) for s in sides if s]
    # Do not map generic ``sides`` to defendants — that breaks role (третья сторона vs ответчик).

    return {
        "number": raw.get("number"),
        "result": raw.get("result") or raw.get("court_case_result"),
        "type": raw.get("type"),
        "date": raw.get("date"),
        "court": raw.get("court"),
        "category": raw.get("category"),
        "judge": raw.get("judge"),
        "status": raw.get("status"),
        "role": raw.get("role"),
        "defendants": defendants,
        "plaintiffs": plaintiffs,
        "participants": participants,
        "documents": case_documents,
        "history": history,
    }


async def fetch_director_iin(bin_value: str, *, case_id: str | None = None) -> str | None:
    """Return director IIN from ``/company/basic/``, cached 24h."""
    cache_key = adata_key("director_iin", bin_value)
    cached = await get_cached(cache_key)
    if cached is not None:
        if case_id:
            append_case_event(
                case_id,
                provider="Adata",
                action="director_iin (cached)",
                subject={"type": "BIN", "value": bin_value},
                request={"endpoint": "/company/basic", "params": {"iinBin": bin_value}},
                outcome={"status": "ok", "cached": True},
            )
        return _normalize_iin_digits(cached.get("director_iin"))

    if not settings.adata_token:
        return None

    try:
        timeout = settings.adata_timeout_seconds
        async with httpx.AsyncClient(timeout=timeout) as client:
            basic_payload = await get_basic(client, bin_value)
        director_iin = _extract_director_iin_from_basic_payload(basic_payload)
        if director_iin:
            await set_cached(cache_key, {"director_iin": director_iin}, DIRECTOR_IIN_TTL)
        if case_id:
            append_case_event(
                case_id,
                provider="Adata",
                action="director_iin",
                subject={"type": "BIN", "value": bin_value},
                request={"endpoint": "/company/basic", "params": {"iinBin": bin_value}},
                outcome={"status": "ok", "cached": False, "counts": {"directorIinFound": bool(director_iin)}},
            )
        return director_iin
    except Exception as exc:
        logger.warning("fetch_director_iin failed for BIN %s: %s", bin_value, exc)
        if case_id:
            append_case_event(
                case_id,
                provider="Adata",
                action="director_iin",
                subject={"type": "BIN", "value": bin_value},
                request={"endpoint": "/company/basic", "params": {"iinBin": bin_value}},
                outcome={"status": "error", "cached": False, "message": str(exc)[:200]},
            )
        return None


async def _poll_individual_court_cases(
    client: httpx.AsyncClient,
    job_token: str,
    check_url: str,
) -> list[dict[str, Any]]:
    """Poll individual/info/check until ``court_cases`` is present; merge all pages."""
    attempts = settings.adata_poll_attempts
    delay = settings.adata_poll_delay_seconds
    ready_data: dict[str, Any] | None = None
    for _ in range(attempts):
        await asyncio.sleep(delay)
        check = await client.get(check_url, params={"token": job_token, "page": 1})
        check.raise_for_status()
        result = check.json()
        data = result.get("data")
        if isinstance(data, dict) and "court_cases" in data:
            ready_data = data
            break

    if ready_data is None:
        return []

    raw_cases: list[Any] = list(ready_data.get("court_cases") or [])
    total_pages = ready_data.get("total_pages") or ready_data.get("totalPages")
    try:
        pages_total = int(total_pages) if total_pages is not None else 1
    except (TypeError, ValueError):
        pages_total = 1

    for page in range(2, max(pages_total, 1) + 1):
        check = await client.get(check_url, params={"token": job_token, "page": page})
        check.raise_for_status()
        page_data = check.json().get("data")
        if isinstance(page_data, dict):
            raw_cases.extend(page_data.get("court_cases") or [])

    return [
        _normalize_individual_court_case(row) for row in raw_cases if isinstance(row, dict)
    ]


async def fetch_individual_court_cases(
    iin: str, *, case_id: str | None = None
) -> list[dict[str, Any]]:
    """Return individual court cases with document links, cached 12h."""
    cache_key = adata_key("individual_courts", iin)
    cached = await get_cached(cache_key)
    if cached is not None:
        if case_id:
            cases_cached = cached.get("cases")
            count = len(cases_cached) if isinstance(cases_cached, list) else 0
            append_case_event(
                case_id,
                provider="Adata",
                action="individual_courts (cached)",
                subject={"type": "IIN", "value": iin},
                request={"endpoint": "/individual/court-case/details", "params": {"iinBin": iin}},
                outcome={"status": "ok", "cached": True, "counts": {"cases": count}},
            )
        cases = cached.get("cases")
        return cases if isinstance(cases, list) else []

    if not settings.adata_token:
        return []

    try:
        timeout = settings.adata_timeout_seconds
        check_url = _individual_info_check_url()
        async with httpx.AsyncClient(timeout=timeout) as client:
            url = _individual_token_path("court-case/details")
            response = await client.get(url, params={"iinBin": iin})
            response.raise_for_status()
            payload = response.json()
            if not payload.get("success", True) and "token" not in payload:
                logger.warning(
                    "individual court-case init failed for IIN %s: %s",
                    iin,
                    payload.get("message") or payload,
                )
                if case_id:
                    append_case_event(
                        case_id,
                        provider="Adata",
                        action="individual_courts",
                        subject={"type": "IIN", "value": iin},
                        request={"endpoint": "/individual/court-case/details", "params": {"iinBin": iin}},
                        outcome={
                            "status": "error",
                            "cached": False,
                            "message": str(payload.get("message") or "init_failed")[:200],
                        },
                    )
                return []
            job_token = payload.get("token")
            if not job_token:
                return []

            cases = await _poll_individual_court_cases(client, job_token, check_url)
            await set_cached(cache_key, {"cases": cases}, ADATA_TTL)
            if case_id:
                docs = 0
                for c in cases:
                    if isinstance(c, dict):
                        docs += len(c.get("documents") or [])
                        for h in c.get("history") or []:
                            if isinstance(h, dict):
                                docs += len(h.get("documents") or [])
                append_case_event(
                    case_id,
                    provider="Adata",
                    action="individual_courts",
                    subject={"type": "IIN", "value": iin},
                    request={
                        "endpoint": "/individual/court-case/details → /individual/info/check",
                        "params": {"iinBin": iin},
                    },
                    outcome={"status": "ok", "cached": False, "counts": {"cases": len(cases), "docs": docs}},
                )
            return cases
    except Exception as exc:
        logger.warning("fetch_individual_court_cases failed for IIN %s: %s", iin, exc)
        if case_id:
            append_case_event(
                case_id,
                provider="Adata",
                action="individual_courts",
                subject={"type": "IIN", "value": iin},
                request={"endpoint": "/individual/court-case/details", "params": {"iinBin": iin}},
                outcome={"status": "error", "cached": False, "message": str(exc)[:200]},
            )
        return []


async def fetch_company_court_cases(
    bin_value: str, *, case_id: str | None = None
) -> list[dict[str, Any]]:
    """Return company court cases from ``/api/courtcase``, cached 12h.

    Same detailed format as individual courts (number, documents, history).
    Init: GET /api/courtcase/{token}?iinBin=BIN → job token.
    Poll: GET /api/company/info/check/{token}?token=… → paginated court_cases.
    """
    cache_key = adata_key("company_courts", bin_value)
    cached = await get_cached(cache_key)
    if cached is not None:
        if case_id:
            cases_cached = cached.get("cases")
            count = len(cases_cached) if isinstance(cases_cached, list) else 0
            append_case_event(
                case_id,
                provider="Adata",
                action="company_courts (cached)",
                subject={"type": "BIN", "value": bin_value},
                request={"endpoint": "/courtcase", "params": {"iinBin": bin_value}},
                outcome={"status": "ok", "cached": True, "counts": {"cases": count}},
            )
        cases = cached.get("cases")
        return cases if isinstance(cases, list) else []

    if not settings.adata_token:
        return []

    try:
        timeout = settings.adata_timeout_seconds
        check_url = _check_url()
        async with httpx.AsyncClient(timeout=timeout) as client:
            url = _courtcase_token_path()
            response = await client.get(url, params={"iinBin": bin_value})
            response.raise_for_status()
            payload = response.json()
            if not payload.get("success", True) and "token" not in payload:
                logger.warning(
                    "company court-case init failed for BIN %s: %s",
                    bin_value,
                    payload.get("message") or payload,
                )
                if case_id:
                    append_case_event(
                        case_id,
                        provider="Adata",
                        action="company_courts",
                        subject={"type": "BIN", "value": bin_value},
                        request={"endpoint": "/courtcase", "params": {"iinBin": bin_value}},
                        outcome={
                            "status": "error",
                            "cached": False,
                            "message": str(payload.get("message") or "init_failed")[:200],
                        },
                    )
                return []
            job_token = payload.get("token")
            if not job_token:
                return []

            cases = await _poll_company_court_cases(client, job_token, check_url)
            await set_cached(cache_key, {"cases": cases}, ADATA_TTL)
            if case_id:
                docs = 0
                for c in cases:
                    if isinstance(c, dict):
                        docs += len(c.get("documents") or [])
                        for h in c.get("history") or []:
                            if isinstance(h, dict):
                                docs += len(h.get("documents") or [])
                append_case_event(
                    case_id,
                    provider="Adata",
                    action="company_courts",
                    subject={"type": "BIN", "value": bin_value},
                    request={
                        "endpoint": "/courtcase → /company/info/check",
                        "params": {"iinBin": bin_value},
                    },
                    outcome={"status": "ok", "cached": False, "counts": {"cases": len(cases), "docs": docs}},
                )
            return cases
    except Exception as exc:
        logger.warning("fetch_company_court_cases failed for BIN %s: %s", bin_value, exc)
        if case_id:
            append_case_event(
                case_id,
                provider="Adata",
                action="company_courts",
                subject={"type": "BIN", "value": bin_value},
                request={"endpoint": "/courtcase", "params": {"iinBin": bin_value}},
                outcome={"status": "error", "cached": False, "message": str(exc)[:200]},
            )
        return []


async def _poll_company_court_cases(
    client: httpx.AsyncClient,
    job_token: str,
    check_url: str,
) -> list[dict[str, Any]]:
    """Poll company info/check for courtcase results; merge all pages."""
    attempts = settings.adata_poll_attempts
    delay = settings.adata_poll_delay_seconds
    ready_data: dict[str, Any] | None = None
    for _ in range(attempts):
        await asyncio.sleep(delay)
        check = await client.get(check_url, params={"token": job_token, "page": 1})
        check.raise_for_status()
        result = check.json()
        data = result.get("data")
        if isinstance(data, dict) and "court_cases" in data:
            ready_data = data
            break

    if ready_data is None:
        return []

    raw_cases: list[Any] = list(ready_data.get("court_cases") or [])
    last_page = ready_data.get("last_page") or ready_data.get("total_pages") or 1
    try:
        pages_total = max(1, int(last_page))
    except (TypeError, ValueError):
        pages_total = 1

    for page in range(2, pages_total + 1):
        check = await client.get(check_url, params={"token": job_token, "page": page})
        check.raise_for_status()
        page_data = check.json().get("data")
        if isinstance(page_data, dict):
            raw_cases.extend(page_data.get("court_cases") or [])

    return [
        _normalize_individual_court_case(row) for row in raw_cases if isinstance(row, dict)
    ]


# ---------------------------------------------------------------------------
# New public endpoints (trustworthy-plus, beneficiary, non-resident, relation)
# ---------------------------------------------------------------------------


async def fetch_trustworthy_plus(iin: str, *, case_id: str | None = None) -> dict[str, Any]:
    """Return trustworthy-plus compliance data for *iin*, with 12-hour Redis cache."""
    cache_key = adata_key("trustworthy", iin)
    cached = await get_cached(cache_key)
    if cached is not None:
        if case_id:
            append_case_event(
                case_id,
                provider="Adata",
                action="trustworthy_plus (cached)",
                subject={"type": "BIN", "value": iin},
                request={"endpoint": "/company/trustworthy-plus", "params": {"iinBin": iin}},
                outcome={"status": "ok", "cached": True},
            )
        return cached

    try:
        timeout = settings.adata_timeout_seconds
        async with httpx.AsyncClient(timeout=timeout) as client:
            url = _token_path("trustworthy-plus")
            response = await client.get(url, params={"iinBin": iin})
            response.raise_for_status()
            payload = response.json()
            if "token" not in payload:
                return {}
            result = await _poll(client, payload["token"])
            if result.get("error"):
                return {}
            data = result.get("data")
            if not isinstance(data, dict):
                return {}
            await set_cached(cache_key, data, ADATA_TTL)
            if case_id:
                append_case_event(
                    case_id,
                    provider="Adata",
                    action="trustworthy_plus",
                    subject={"type": "BIN", "value": iin},
                    request={"endpoint": "/company/trustworthy-plus → /company/info/check", "params": {"iinBin": iin}},
                    outcome={"status": "ok", "cached": False},
                )
            return data
    except Exception as exc:
        logger.warning("fetch_trustworthy_plus failed for IIN %s: %s", iin, exc)
        if case_id:
            append_case_event(
                case_id,
                provider="Adata",
                action="trustworthy_plus",
                subject={"type": "BIN", "value": iin},
                request={"endpoint": "/company/trustworthy-plus", "params": {"iinBin": iin}},
                outcome={"status": "error", "cached": False, "message": str(exc)[:200]},
            )
        return {}


async def fetch_beneficiary(iin: str, *, case_id: str | None = None) -> list[dict[str, Any]]:
    """Return beneficiary list for *iin*, with 12-hour Redis cache."""
    cache_key = adata_key("beneficiary", iin)
    cached = await get_cached(cache_key)
    if cached is not None:
        if case_id:
            items_cached = cached.get("items")
            count = len(items_cached) if isinstance(items_cached, list) else 0
            append_case_event(
                case_id,
                provider="Adata",
                action="beneficiary (cached)",
                subject={"type": "BIN", "value": iin},
                request={"endpoint": "/relation-scheme/beneficiary", "params": {"iinBin": iin}},
                outcome={"status": "ok", "cached": True, "counts": {"items": count}},
            )
        return cached.get("items", [])  # type: ignore[return-value]

    try:
        timeout = settings.adata_timeout_seconds
        check_url = _relation_scheme_check_url()
        async with httpx.AsyncClient(timeout=timeout) as client:
            url = _token_path("relation-scheme/beneficiary")
            response = await client.get(url, params={"iinBin": iin})
            response.raise_for_status()
            payload = response.json()
            if "token" not in payload:
                return []
            result = await _poll_with_url(client, payload["token"], check_url)
            if result.get("error"):
                return []
            data = result.get("data")
            items: list[dict[str, Any]] = data if isinstance(data, list) else []
            await set_cached(cache_key, {"items": items}, ADATA_TTL)
            if case_id:
                append_case_event(
                    case_id,
                    provider="Adata",
                    action="beneficiary",
                    subject={"type": "BIN", "value": iin},
                    request={
                        "endpoint": "/relation-scheme/beneficiary → /relation-scheme/check",
                        "params": {"iinBin": iin},
                    },
                    outcome={"status": "ok", "cached": False, "counts": {"items": len(items)}},
                )
            return items
    except Exception as exc:
        logger.warning("fetch_beneficiary failed for IIN %s: %s", iin, exc)
        if case_id:
            append_case_event(
                case_id,
                provider="Adata",
                action="beneficiary",
                subject={"type": "BIN", "value": iin},
                request={"endpoint": "/relation-scheme/beneficiary", "params": {"iinBin": iin}},
                outcome={"status": "error", "cached": False, "message": str(exc)[:200]},
            )
        return []


async def fetch_non_resident_affiliations(
    iin: str, *, case_id: str | None = None
) -> dict[str, Any]:
    """Return non-resident affiliation data for *iin*, with 12-hour Redis cache."""
    cache_key = adata_key("nonresident", iin)
    cached = await get_cached(cache_key)
    if cached is not None:
        if case_id:
            count = 0
            if isinstance(cached, dict):
                count = len(cached.get("data") or [])
            append_case_event(
                case_id,
                provider="Adata",
                action="non_residents (cached)",
                subject={"type": "BIN", "value": iin},
                request={"endpoint": "/relation-scheme/affiliation-non-resident", "params": {"iinBin": iin}},
                outcome={"status": "ok", "cached": True, "counts": {"items": count}},
            )
        return cached

    _default: dict[str, Any] = {"hasNonResidentFromAll": False, "data": []}
    try:
        timeout = settings.adata_timeout_seconds
        check_url = _relation_scheme_check_url()
        async with httpx.AsyncClient(timeout=timeout) as client:
            url = _token_path("relation-scheme/affiliation-non-resident")
            response = await client.get(url, params={"iinBin": iin})
            response.raise_for_status()
            payload = response.json()
            if "token" not in payload:
                return _default
            result = await _poll_with_url(client, payload["token"], check_url)
            if result.get("error"):
                return _default
            data = result.get("data")
            if not isinstance(data, dict):
                return _default
            await set_cached(cache_key, data, ADATA_TTL)
            if case_id:
                count = len((data.get("data") or [])) if isinstance(data, dict) else 0
                append_case_event(
                    case_id,
                    provider="Adata",
                    action="non_residents",
                    subject={"type": "BIN", "value": iin},
                    request={
                        "endpoint": "/relation-scheme/affiliation-non-resident → /relation-scheme/check",
                        "params": {"iinBin": iin},
                    },
                    outcome={"status": "ok", "cached": False, "counts": {"items": count}},
                )
            return data
    except Exception as exc:
        logger.warning("fetch_non_resident_affiliations failed for IIN %s: %s", iin, exc)
        if case_id:
            append_case_event(
                case_id,
                provider="Adata",
                action="non_residents",
                subject={"type": "BIN", "value": iin},
                request={"endpoint": "/relation-scheme/affiliation-non-resident", "params": {"iinBin": iin}},
                outcome={"status": "error", "cached": False, "message": str(exc)[:200]},
            )
        return _default


async def fetch_relation_extended(iin: str, *, case_id: str | None = None) -> dict[str, Any]:
    """Return extended relation/affiliation data for *iin*, with 12-hour Redis cache."""
    cache_key = adata_key("relation", iin)
    cached = await get_cached(cache_key)
    if cached is not None:
        if case_id:
            head = cached.get("affiliation_by_head") if isinstance(cached, dict) else None
            founder = cached.get("affiliation_by_founder") if isinstance(cached, dict) else None
            head_count = len(head or []) if isinstance(head, list) else 0
            founder_count = len(founder or []) if isinstance(founder, list) else 0
            append_case_event(
                case_id,
                provider="Adata",
                action="relation_extended (cached)",
                subject={"type": "BIN", "value": iin},
                request={"endpoint": "/company/relation", "params": {"iinBin": iin}},
                outcome={"status": "ok", "cached": True, "counts": {"byHead": head_count, "byFounder": founder_count}},
            )
        return cached

    try:
        timeout = settings.adata_timeout_seconds
        async with httpx.AsyncClient(timeout=timeout) as client:
            url = _token_path("relation")
            response = await client.get(url, params={"iinBin": iin})
            response.raise_for_status()
            payload = response.json()
            if "token" not in payload:
                return {}
            result = await _poll(client, payload["token"])
            if result.get("error"):
                return {}
            data = result.get("data")
            if not isinstance(data, dict):
                return {}
            await set_cached(cache_key, data, ADATA_TTL)
            if case_id:
                by_head = data.get("affiliation_by_head") or data.get("affiliationByHead") or []
                by_founder = data.get("affiliation_by_founder") or data.get("affiliationByFounder") or []
                head_count = len(by_head) if isinstance(by_head, list) else 0
                founder_count = len(by_founder) if isinstance(by_founder, list) else 0
                append_case_event(
                    case_id,
                    provider="Adata",
                    action="relation_extended",
                    subject={"type": "BIN", "value": iin},
                    request={"endpoint": "/company/relation → /company/info/check", "params": {"iinBin": iin}},
                    outcome={"status": "ok", "cached": False, "counts": {"byHead": head_count, "byFounder": founder_count}},
                )
            return data
    except Exception as exc:
        logger.warning("fetch_relation_extended failed for IIN %s: %s", iin, exc)
        if case_id:
            append_case_event(
                case_id,
                provider="Adata",
                action="relation_extended",
                subject={"type": "BIN", "value": iin},
                request={"endpoint": "/company/relation", "params": {"iinBin": iin}},
                outcome={"status": "error", "cached": False, "message": str(exc)[:200]},
            )
        return {}
