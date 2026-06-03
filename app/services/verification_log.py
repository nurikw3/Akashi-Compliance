from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.models import db


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _coerce_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _coerce_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def add_event_to_enriched(
    enriched: dict[str, Any] | None,
    *,
    provider: str,
    action: str,
    subject: dict[str, Any] | None = None,
    request: dict[str, Any] | None = None,
    outcome: dict[str, Any] | None = None,
    ts: str | None = None,
    max_events: int = 300,
) -> dict[str, Any]:
    """Append one verification log event into enriched_data dict.

    Keeps payload small: trims long strings, caps list length.
    """
    enriched = _coerce_dict(enriched)
    log = _coerce_list(enriched.get("verificationLog"))

    def _trim(value: Any, max_len: int = 400) -> Any:
        if isinstance(value, str):
            v = value.strip()
            return v if len(v) <= max_len else v[: max_len - 1] + "…"
        if isinstance(value, list):
            return value[:50]
        if isinstance(value, dict):
            # shallow-trim only
            out: dict[str, Any] = {}
            for k, v in list(value.items())[:50]:
                out[str(k)[:60]] = _trim(v, max_len=max_len)
            return out
        return value

    event: dict[str, Any] = {
        "ts": ts or _now_iso(),
        "provider": str(provider),
        "action": str(action),
    }
    if subject:
        event["subject"] = _trim(subject, max_len=200)
    if request:
        event["request"] = _trim(request, max_len=240)
    if outcome:
        event["outcome"] = _trim(outcome, max_len=240)

    log.append(event)
    if len(log) > max_events:
        log = log[-max_events:]
    enriched["verificationLog"] = log
    return enriched


def append_case_event(
    case_id: str,
    *,
    provider: str,
    action: str,
    subject: dict[str, Any] | None = None,
    request: dict[str, Any] | None = None,
    outcome: dict[str, Any] | None = None,
    ts: str | None = None,
) -> None:
    """Load case, append one event, and persist enriched_data."""
    row = db.get_case(case_id)
    if row is None:
        return
    enriched = row.get("enriched_data") or {}
    if not isinstance(enriched, dict):
        enriched = {}
    enriched = add_event_to_enriched(
        enriched,
        provider=provider,
        action=action,
        subject=subject,
        request=request,
        outcome=outcome,
        ts=ts,
    )
    db.update_case(case_id, enriched_data=enriched)

