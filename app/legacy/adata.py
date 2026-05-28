from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import httpx

from app.core.config import settings


class AdataError(RuntimeError):
    pass


async def _poll(client: httpx.AsyncClient, job_token: str, label: str) -> dict[str, Any]:
    check_url = f"{settings.adata_base_url.rstrip('/')}/info/check/{settings.adata_token}"
    for _ in range(settings.adata_poll_attempts):
        await asyncio.sleep(settings.adata_poll_delay_seconds)
        response = await client.get(check_url, params={"token": job_token})
        response.raise_for_status()
        data = response.json()
        if data.get("data") is not None:
            return data
    raise AdataError(f"{label} polling timed out")


async def _fetch(client: httpx.AsyncClient, endpoint: str, bin_value: str) -> dict[str, Any]:
    url = f"{settings.adata_base_url.rstrip('/')}/{endpoint}/{settings.adata_token}"
    response = await client.get(url, params={"iinBin": bin_value})
    response.raise_for_status()
    payload = response.json()
    if "token" not in payload:
        return payload
    return await _poll(client, payload["token"], endpoint)


async def run_parallel_checks(bin_value: str) -> dict[str, Any]:
    if not settings.adata_token:
        raise AdataError("ADATA_TOKEN is not configured")

    timeout = httpx.Timeout(settings.adata_timeout_seconds)
    async with httpx.AsyncClient(timeout=timeout) as client:
        basic, riskfactor, trustworthy = await asyncio.gather(
            _fetch(client, "basic", bin_value),
            _fetch(client, "riskfactor", bin_value),
            _fetch(client, "trustworthy-extended", bin_value),
        )
    return {
        "basic": basic,
        "riskfactor": riskfactor,
        "trustworthy_extended": trustworthy,
    }


async def download_company_report(bin_value: str, out_path: Path) -> Path:
    if not settings.adata_token:
        raise AdataError("ADATA_TOKEN is not configured")

    url = f"{settings.adata_base_url.rstrip('/')}/report/{settings.adata_token}"
    timeout = httpx.Timeout(settings.adata_timeout_seconds)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(url, params={"iinBin": bin_value})
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        if "pdf" in content_type or response.content[:4] == b"%PDF":
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(response.content)
            return out_path

        payload = response.json()
        download_url = (
            payload.get("url")
            or payload.get("link")
            or payload.get("pdfUrl")
            or payload.get("pdf_url")
        )
        if download_url:
            pdf_response = await client.get(download_url)
            pdf_response.raise_for_status()
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(pdf_response.content)
            return out_path

        if "token" in payload:
            result = await _poll(client, payload["token"], "PDF")
            inner_url = (result.get("data") or {}).get("url") or (result.get("data") or {}).get("pdfUrl")
            if inner_url:
                pdf_response = await client.get(inner_url)
                pdf_response.raise_for_status()
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_bytes(pdf_response.content)
                return out_path

    raise AdataError("Could not download PDF report from Adata")
