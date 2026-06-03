"""Langfuse tracing helpers for AI calls (OpenAI drop-in + trace context)."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Generator

from app.core.config import settings

logger = logging.getLogger(__name__)

_TRACE_SEED_PREFIX = "akashi:"


def langfuse_enabled() -> bool:
    return bool(settings.langfuse_secret_key and settings.langfuse_public_key)


def _trace_seed(iin: str, action: str) -> str:
    """Stable seed: one Langfuse trace per company IIN + action (chat, full_report, …)."""
    normalized_iin = (iin or "").strip()
    normalized_action = (action or "").strip() or "unknown"
    return f"{_TRACE_SEED_PREFIX}{normalized_iin}:{normalized_action}"


def iin_trace_id(iin: str, action: str = "") -> str:
    """Deterministic Langfuse trace id from company BIN/IIN and optional action."""
    if not (iin or "").strip() or not langfuse_enabled():
        return ""
    try:
        from langfuse import get_client

        return get_client().create_trace_id(seed=_trace_seed(iin, action))
    except Exception as exc:
        logger.debug("Langfuse create_trace_id failed: %s", exc)
        return ""


def create_async_openai_client() -> Any:
    """AsyncOpenAI client; uses Langfuse wrapper when credentials are configured."""
    client_kwargs: dict[str, Any] = {"api_key": settings.openai_api_key}
    if settings.openai_base_url:
        client_kwargs["base_url"] = settings.openai_base_url
    if langfuse_enabled():
        from langfuse.openai import AsyncOpenAI

        return AsyncOpenAI(**client_kwargs)
    from openai import AsyncOpenAI

    return AsyncOpenAI(**client_kwargs)


def flush_langfuse() -> None:
    if not langfuse_enabled():
        return
    try:
        from langfuse import get_client

        get_client().flush()
    except Exception as exc:
        logger.debug("Langfuse flush failed: %s", exc)


@contextmanager
def ai_trace(
    *,
    name: str,
    iin: str,
    case_id: str = "",
    extra_metadata: dict[str, Any] | None = None,
) -> Generator[None, None, None]:
    """Group nested OpenAI calls under one Langfuse trace keyed by company IIN."""
    normalized_iin = (iin or "").strip()
    if not langfuse_enabled() or not normalized_iin:
        yield
        return

    try:
        from langfuse import get_client, propagate_attributes

        lf = get_client()
        trace_id = lf.create_trace_id(seed=_trace_seed(normalized_iin, name))
        metadata: dict[str, Any] = {
            "iin": normalized_iin,
            "case_id": case_id,
            "action": name,
        }
        if extra_metadata:
            metadata.update(extra_metadata)

        with lf.start_as_current_observation(
            as_type="span",
            name=name,
            trace_context={"trace_id": trace_id},
        ):
            with propagate_attributes(
                user_id=normalized_iin,
                session_id=normalized_iin,
                metadata=metadata,
                trace_name=name,
            ):
                yield
        flush_langfuse()
    except Exception as exc:
        logger.warning("Langfuse trace %s skipped: %s", name, exc)
        yield
