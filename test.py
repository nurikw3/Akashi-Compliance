# backend/auth.py
import hmac
import hashlib
import base64
from datetime import datetime, timezone
from dotenv import load_dotenv
import os
import json, httpx

load_dotenv()

API_KEY = os.getenv("LSEG_API_Key")
API_SECRET = os.getenv("LSEG_API_Secret")

def build_headers(method: str, path: str, body: bytes = b"") -> dict:
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    
    # Хэш тела запроса
    body_hash = hashlib.sha256(body).digest()
    body_b64 = base64.b64encode(body_hash).decode()
    
    # Строка для подписи
    msg = f"{timestamp}{method}{path}{body_b64}"
    
    # HMAC-SHA256
    signature = hmac.new(
        API_SECRET.encode(),
        msg.encode(),
        hashlib.sha256
    ).digest()
    sig_b64 = base64.b64encode(signature).decode()
    
    return {
        "Authorization": f'Credential={API_KEY}, SignedHeaders=date;(request-target);content-type;x-imfrom;content-sha256, Signature={sig_b64}',
        "Date": timestamp,
        "Content-Type": "application/json",
        "x-imfrom": API_KEY,
        "content-sha256": body_b64,
    }

async def screen_entity(org_name: str, reg_number: str):
    path = "/v1/cases"
    payload = {
        "entityType": "ORGANISATION",
        "name": org_name.strip().lower(),
        "groupId": "YOUR_GROUP_ID",
    }
    body = json.dumps(payload).encode()
    headers = build_headers("POST", path, body)

    async with httpx.AsyncClient(base_url="https://rms-world-check-one-api-pilot.thomsonreuters.com") as client:
        r = await client.post(path, content=body, headers=headers)
        r.raise_for_status()
        return r.json()

if __name__ == "__main__":
    import asyncio
    asyncio.run(screen_entity("KazDevOps ", "171040021791"))