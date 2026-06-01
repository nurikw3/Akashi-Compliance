"""LLM-based analysis of court case texts.

Classifies each court case from Adata into structured annotations:
  category: criminal | civil | administrative | enforcement
  severity: critical | high | medium | low
  outcome: convicted | pending | dismissed | unknown
  amount_kzt: extracted monetary amount or 0
  summary_ru: 1-2 sentence Russian summary
"""
from __future__ import annotations

import json
import logging
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """Ты — юридический аналитик по казахстанскому праву.
Проанализируй описание судебного дела и верни JSON строго следующей структуры (без markdown-обёртки):
{
  "category": "criminal" | "civil" | "administrative" | "enforcement",
  "severity": "critical" | "high" | "medium" | "low",
  "outcome": "convicted" | "pending" | "dismissed" | "unknown",
  "amount_kzt": <число или 0>,
  "summary_ru": "<1-2 предложения на русском>"
}

Правила классификации:
- criminal: уголовное дело, мошенничество, хищение, терроризм
- enforcement: исполнительное производство, взыскание задолженности
- administrative: административное правонарушение, штраф
- civil: гражданский спор, иск, контрактный спор
- severity critical: уголовное осуждение, сумма >50 млн тг или терроризм
- severity high: уголовное дело (не осуждён), сумма 10-50 млн тг
- severity medium: административные нарушения, сумма 1-10 млн тг
- severity low: мелкий спор, сумма <1 млн тг
Отвечай ТОЛЬКО валидным JSON без дополнительного текста."""

_FALLBACK = {
    "category": "civil",
    "severity": "medium",
    "outcome": "unknown",
    "amount_kzt": 0,
    "summary_ru": "Судебное дело (данных недостаточно для автоматической классификации).",
}


async def analyze_court_cases(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Add aiAnalysis field to each court case that lacks one. Returns updated list."""
    if not settings.openai_api_key or not cases:
        return cases

    updated: list[dict[str, Any]] = []
    for case in cases:
        if case.get("aiAnalysis"):
            updated.append(case)
            continue

        text = _case_to_text(case)
        if not text:
            updated.append(case)
            continue

        analysis = await _classify_single(text)
        updated.append({**case, "aiAnalysis": analysis})

    return updated


def _case_to_text(case: dict[str, Any]) -> str:
    parts: list[str] = []
    if case.get("type"):
        parts.append(str(case["type"]))
    if case.get("status"):
        parts.append(str(case["status"]))
    if case.get("date"):
        parts.append(f"дата: {case['date']}")
    if case.get("amount") and int(case.get("amount") or 0) > 0:
        parts.append(f"сумма: {case['amount']} тг")
    return " | ".join(parts)


async def _classify_single(text: str) -> dict[str, Any]:
    try:
        from openai import AsyncOpenAI

        client_kwargs: dict[str, Any] = {"api_key": settings.openai_api_key}
        if settings.openai_base_url:
            client_kwargs["base_url"] = settings.openai_base_url
        client = AsyncOpenAI(**client_kwargs)

        response = await client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            temperature=0.1,
            max_tokens=300,
        )
        raw = (response.choices[0].message.content or "").strip()
        return json.loads(raw)
    except Exception as exc:
        logger.debug("Court case LLM classification failed: %s", exc)
        return {**_FALLBACK}
