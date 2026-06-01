"""LSEG World-Check One v3 HTTP client.

Supports two authentication modes:
- HMAC (primary): signs every request with api-key / api-secret
- OAuth Bearer (fallback): exchanges service-account-uuid / service-account-password for a JWT

The mode is selected automatically based on which credentials are configured.
If both are present, HMAC is preferred (no extra token round-trip).
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac as _hmac
import base64
import json as _json
import logging
import time
from datetime import datetime, timezone
from email.utils import formatdate
from typing import Any
from urllib.parse import urlparse

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_BASE = "https://api.risk.lseg.com"
_GATEWAY_HOST = "api.risk.lseg.com"
_GATEWAY_PATH = "/screening/v3/"
_TOKEN_URL = f"{_BASE}/auth/oauth2/v1/token"
_SCREEN_URL = f"{_BASE}/screening/v3"


def _rfc7231_date() -> str:
    """Return current time as RFC 7231 / HTTP-date string (required by HMAC)."""
    return formatdate(usegmt=True)


def _hmac_signature(secret: str, data_to_sign: str) -> str:
    key = secret.encode("utf-8")
    msg = data_to_sign.encode("utf-8")
    sig = _hmac.new(key, msg, hashlib.sha256).digest()
    return base64.b64encode(sig).decode("utf-8")


def _build_hmac_headers(
    method: str,
    path: str,
    date: str,
    body: bytes | None = None,
) -> dict[str, str]:
    """Build HMAC-signed Authorization + Date headers per LSEG WC1 v3 spec."""
    api_key = settings.lseg_client_id
    api_secret = settings.lseg_client_secret

    # Strip the gateway prefix from the path for signing (query string already excluded)
    relative = path.replace(_GATEWAY_PATH.rstrip("/"), "").lstrip("/")
    request_target = f"{method.lower()} {_GATEWAY_PATH}{relative}"

    if body:
        content_type = "application/json"
        content_length = str(len(body))
        body_str = body.decode("utf-8")
        data_to_sign = (
            f"(request-target): {request_target}\n"
            f"host: {_GATEWAY_HOST}\n"
            f"date: {date}\n"
            f"content-type: {content_type}\n"
            f"content-length: {content_length}\n"
            f"{body_str}"
        )
        sig = _hmac_signature(api_secret, data_to_sign)
        logger.debug("HMAC sign (body):\n%s", data_to_sign)
        auth = (
            f'Signature keyId="{api_key}",algorithm="hmac-sha256",'
            f'headers="(request-target) host date content-type content-length",'
            f'signature="{sig}"'
        )
        return {
            "Authorization": auth,
            "Date": date,
            "Content-Type": content_type,
            "Content-Length": content_length,
        }
    else:
        data_to_sign = (
            f"(request-target): {request_target}\n"
            f"host: {_GATEWAY_HOST}\n"
            f"date: {date}"
        )
        sig = _hmac_signature(api_secret, data_to_sign)
        logger.debug("HMAC sign (no body):\n%s", data_to_sign)
        auth = (
            f'Signature keyId="{api_key}",algorithm="hmac-sha256",'
            f'headers="(request-target) host date",'
            f'signature="{sig}"'
        )
        return {
            "Authorization": auth,
            "Date": date,
        }


class LsegClient:
    def __init__(self) -> None:
        self._token: str | None = None
        self._token_expires: float = 0.0
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Auth helpers
    # ------------------------------------------------------------------

    def _use_hmac(self) -> bool:
        """True when HMAC mode should be used (api-key + api-secret configured)."""
        # HMAC uses the same CLIENT_ID / CLIENT_SECRET env vars as OAuth but
        # interprets them as api-key / api-secret.  We always prefer HMAC.
        return bool(settings.lseg_client_id and settings.lseg_client_secret)

    async def _get_token(self) -> str:
        """Obtain/cache OAuth2 Bearer token (only used in non-HMAC mode)."""
        async with self._lock:
            if self._token and time.monotonic() < self._token_expires - 30:
                return self._token
            date = _rfc7231_date()
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    _TOKEN_URL,
                    auth=(settings.lseg_client_id, settings.lseg_client_secret),
                    headers={"Date": date},
                )
                resp.raise_for_status()
                data = resp.json()
                self._token = data["access_token"]
                self._token_expires = time.monotonic() + int(data.get("expires_in", 3600))
                logger.info("LSEG OAuth2 token refreshed (expires_in=%s)", data.get("expires_in"))
                return self._token

    async def _request(
        self,
        method: str,
        url: str,
        payload: dict | None = None,
        timeout: int = 60,
    ) -> dict[str, Any]:
        """Execute an authenticated request using HMAC or OAuth."""
        parsed = urlparse(url)
        # For HMAC signing use only the path (no query string), per WC1 v3 spec
        signing_path = parsed.path
        full_url = url  # send request to full URL with query params

        body_bytes: bytes | None = None
        if payload is not None:
            body_bytes = _json.dumps(payload, separators=(",", ":")).encode("utf-8")

        date = _rfc7231_date()

        if self._use_hmac():
            headers = _build_hmac_headers(method, signing_path, date, body_bytes)
        else:
            token = await self._get_token()
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Date": date,
            }

        async with httpx.AsyncClient(timeout=timeout) as client:
            req_kwargs: dict[str, Any] = {"headers": headers}
            if body_bytes is not None:
                req_kwargs["content"] = body_bytes
            resp = await client.request(method, full_url, **req_kwargs)
            logger.debug("LSEG %s %s → %s", method, url, resp.status_code)
            if resp.status_code >= 400:
                logger.error("LSEG error %s: %s", resp.status_code, resp.text[:300])
            resp.raise_for_status()
            return resp.json()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def screen_sync(self, name: str, entity_type: str) -> dict[str, Any]:
        """Create a WC1 case and screen it synchronously. Returns full case object."""
        payload: dict[str, Any] = {
            "groupId": settings.lseg_group_id,
            "entityType": entity_type,
            "providerTypes": ["WATCHLIST"],
            "name": name,
            "nameTransposition": False,
            "secondaryFields": [],
            "customFields": [],
        }
        return await self._request("POST", f"{_SCREEN_URL}/cases?screen=SYNC", payload)

    async def get_results(self, case_system_id: str) -> dict[str, Any]:
        """Retrieve screening results (watchlist hits) for a case."""
        return await self._request("POST", f"{_SCREEN_URL}/cases/{case_system_id}/results", {})

    async def get_media_check(self, case_system_id: str) -> dict[str, Any]:
        """Retrieve adverse media articles for a case."""
        payload = {
            "baseFilter": {"smartFilter": True, "reviewRequiredArticles": True},
            "sort": {"columnName": "publicationDate", "order": "DESCENDING"},
            "pagination": {"itemsPerPage": 10, "pageReference": None},
        }
        return await self._request("POST", f"{_SCREEN_URL}/cases/{case_system_id}/media-check/results", payload)

    async def get_rating(self, case_system_id: str) -> dict[str, Any]:
        """Get the risk rating for a screened case."""
        return await self._request("GET", f"{_SCREEN_URL}/cases/{case_system_id}/rating")
