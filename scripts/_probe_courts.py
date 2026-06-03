import asyncio
import json

import httpx

from app.core.config import settings
from app.services.adata.client import _check_url, _token_path, _is_detailed_court_case_row

# CORE 24/7 has no cases; try a BIN likely to have litigation if provided via env.
import os
BIN = os.getenv("PROBE_BIN", "171040021791")


async def poll(client, check_url, token, page=1):
    for _ in range(15):
        await asyncio.sleep(2)
        cr = await client.get(check_url, params={"token": token, "page": page})
        cr.raise_for_status()
        j = cr.json()
        if j.get("data") is not None:
            return j["data"]
    return None


async def main() -> None:
    print("BIN:", BIN, "base:", settings.adata_base_url)
    async with httpx.AsyncClient(timeout=40) as client:
        url = _token_path("court-case/details")
        print("GET", url)
        r = await client.get(url, params={"iinBin": BIN})
        print("init status:", r.status_code)
        try:
            payload = r.json()
        except Exception:
            print("non-json:", r.text[:300]); return
        print("init keys:", list(payload.keys()), "msg:", payload.get("message"))
        token = payload.get("token")
        if not token:
            print("no token -> body:", json.dumps(payload, ensure_ascii=False)[:400]); return
        data = await poll(client, _check_url(), token, page=1)
    if not isinstance(data, dict):
        print("NO DATA dict; type=", type(data)); return
    print("detail data keys:", sorted(data.keys()))
    cc = data.get("court_cases")
    print("court_cases type:", type(cc), "len:", len(cc) if isinstance(cc, list) else "-")
    if isinstance(cc, list) and cc:
        first = cc[0]
        print("row0 keys:", sorted(first.keys()) if isinstance(first, dict) else type(first))
        print("is_detailed(row0):", _is_detailed_court_case_row(first) if isinstance(first, dict) else "n/a")
        print("row0:", json.dumps(first, ensure_ascii=False)[:700])


asyncio.run(main())
