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

from app.core.config import settings

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


async def fetch_company_info(bin_value: str) -> dict[str, Any]:
    """Start company info job and poll until ``data`` is ready; return that object."""
    if not settings.adata_token:
        raise AdataError("ADATA_TOKEN is not configured")

    timeout = settings.adata_timeout_seconds
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(_token_path("info"), params={"iinBin": bin_value})
        response.raise_for_status()
        payload = response.json()
        if "token" not in payload:
            if isinstance(payload.get("data"), dict):
                return payload["data"]
            raise AdataError("Company info start did not return a job token or data")

        result = await _poll(client, payload["token"])
        if result.get("error"):
            raise AdataError(f"Company info poll failed: {result['error']}")
        data = result.get("data")
        if not isinstance(data, dict):
            raise AdataError("Company info poll returned no data")
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
        lit = info_data.get("litigation") or {}
        risk = info_data.get("riskFactor") or {}
        head_lit = (risk.get("head") or {}).get("litigation") if isinstance(risk, dict) else {}
        if not lit.get("court_cases") and not (head_lit or {}).get("court_cases"):
            if not any(
                int((lit or {}).get(k) or 0)
                + int((head_lit or {}).get(k) or 0)
                for k in (
                    "total_civil_count",
                    "total_criminal_count",
                    "total_administrative_count",
                )
            ):
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
    return await _get_endpoint(client, "courtcase", bin_value)


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


async def run_parallel_checks(bin_value: str) -> dict[str, Any]:
    """Fetch company info first, then optional fallback endpoints for missing fields."""
    if not settings.adata_token:
        raise AdataError("ADATA_TOKEN is not configured")

    result: dict[str, Any] = {}
    info_data: dict[str, Any] = {}

    try:
        info_data = await fetch_company_info(bin_value)
        result["info"] = {"success": True, "data": info_data}
    except Exception as exc:
        logger.info(
            "Adata company info failed for BIN %s: %s",
            bin_value,
            exc,
        )
        result["info"] = {"error": str(exc)}

    fallbacks = _fallbacks_for_info(info_data) if info_data else list(_RAW_KEYS.keys())

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
                else:
                    result[raw_key] = value

    return result


async def download_company_report(bin_value: str, out_path: Path) -> Path:
    if not settings.adata_token:
        raise AdataError("ADATA_TOKEN is not configured")

    url = _token_path("report")
    timeout = settings.adata_timeout_seconds
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(url, params={"iinBin": bin_value})
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")

        if "pdf" in content_type or response.content[:4] == b"%PDF":
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(response.content)
            return out_path

        try:
            payload = response.json()
        except Exception as exc:
            raise AdataError(f"Unexpected report response: {exc}") from exc

        inner_url = (
            payload.get("url")
            or payload.get("link")
            or payload.get("pdfUrl")
            or payload.get("pdf_url")
        )
        if inner_url:
            r2 = await client.get(inner_url)
            r2.raise_for_status()
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(r2.content)
            return out_path

        if "token" in payload:
            polled = await _poll(client, payload["token"], attempts=15, delay=3.0)
            data = polled.get("data") or {}
            polled_url = data.get("url") or data.get("pdfUrl")
            if polled_url:
                r3 = await client.get(polled_url)
                r3.raise_for_status()
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_bytes(r3.content)
                return out_path

        raise AdataError("Could not download PDF report from Adata")
