"""AI jobs run in TaskIQ worker or inline fallback."""

from __future__ import annotations

import logging
from typing import Any

from app.models import db
from app.services.ai.service import AIService

logger = logging.getLogger(__name__)


async def generate_conclusion_for_case(case_id: str) -> None:
    row = db.get_case(case_id)
    if row is None or row.get("status") != "ready":
        return

    enriched = row.get("enriched_data") or {}
    enrichment = enriched.get("enrichment")
    assessment = enriched.get("assessment")
    if not enrichment or not assessment:
        return

    if row.get("conclusion"):
        return

    try:
        conclusion = await AIService().generate_conclusion(
            company_name=row["company_name"],
            enrichment=enrichment,
            assessment=assessment,
            iin=row["iin"],
            data_sources=enriched.get("dataSources"),
        )
        db.update_case(case_id, conclusion=conclusion)
        logger.info("AI conclusion saved for %s", case_id)
    except Exception:
        logger.exception("AI conclusion failed for %s", case_id)


async def chat_reply_for_case(case_id: str, user_message: str) -> dict[str, Any]:
    row = db.get_case(case_id)
    if row is None:
        raise ValueError("Case not found")

    history = [
        {"role": msg["role"], "content": msg["content"]}
        for msg in db.list_chat_messages(case_id)
        if msg["role"] in ("user", "assistant")
    ]
    prior_history = history
    if (
        history
        and history[-1]["role"] == "user"
        and history[-1]["content"].strip() == user_message.strip()
    ):
        prior_history = history[:-1]

    enriched = row.get("enriched_data") or {}
    reply, ai_mode = await AIService().chat_reply(
        company_name=row["company_name"],
        iin=row["iin"],
        message=user_message,
        enrichment=enriched.get("enrichment"),
        assessment=enriched.get("assessment"),
        conclusion=row.get("conclusion"),
        history=prior_history,
        data_sources=enriched.get("dataSources"),
    )
    assistant = db.add_chat_message(case_id=case_id, role="assistant", content=reply)
    return {"message": assistant, "aiMode": ai_mode}
