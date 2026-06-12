"""Plain-Russian one-liner ("за что под санкциями") per sanctioned entity.

One batched LLM call rewrites the (English, verbose) World-Check
``furtherInformation`` into 1–2 plain Russian sentences a non-technical
compliance officer can read. Strict facts-only; deterministic fallback when
the LLM is unavailable so the report always renders.
"""
from __future__ import annotations

import json
import logging

from app.core.config import settings
from app.services.ai.langfuse_setup import ai_trace, create_async_openai_client

logger = logging.getLogger(__name__)

_SYSTEM = (
    "Ты — комплаенс-аналитик. Тебе дают записи World-Check, КОТОРЫЕ УЖЕ НАЙДЕНЫ "
    "в санкционных/наблюдательных списках. Перепиши КАЖДУЮ запись в 1–2 коротких "
    "предложениях на простом русском: за что и кем наложены санкции (или с чем "
    "связана запись). "
    "КРИТИЧНО: эти лица УЖЕ значатся в списках. НИКОГДА не пиши «санкции не наложены», "
    "«не под санкциями», «чисто» или отрицание — это будет фактической ошибкой. "
    "Используй поля sanctionType (тип санкций) и whoImposed, даже если подробного "
    "текста (details) нет. Если деталей мало — напиши кратко: «значится в санкционных/"
    "наблюдательных списках World-Check (тип: …), подробности в записи не раскрыты». "
    "ТОЛЬКО факты из данных. ЗАПРЕЩЕНО: рекомендации, советы, оценки риска, "
    "слова «рекомендуется/следует/высокий риск». Без воды, без англоязычных "
    "кодов и аббревиатур в ответе. Верни СТРОГО JSON-массив объектов "
    '{"id": <число>, "text": "<простой русский>"} в том же порядке.'
)

_MAX_FI_CHARS = 1400  # cap raw text per entity sent to the LLM


def _deterministic_fallback(entity: dict) -> str:
    """Без LLM: берём самый релевантный блок furtherInformation, иначе — тип/страну."""
    for block in entity.get("rawFurtherInfo") or []:
        if block.get("type") == "SANCTION" and block.get("text"):
            return str(block["text"])[:400]
    for block in entity.get("rawFurtherInfo") or []:
        if block.get("text"):
            return str(block["text"])[:400]
    country = entity.get("country") or ""
    return f"Запись в санкционных/наблюдательных списках World-Check{(' (' + country + ')') if country else ''}."


async def generate_sanction_narratives(entities: list[dict]) -> dict[int, str]:
    """Return {entity_index: plain_russian_text}. Never raises — falls back per entity."""
    fallbacks = {i: _deterministic_fallback(e) for i, e in enumerate(entities)}
    if not entities or not settings.openai_api_key:
        return fallbacks

    payload = []
    for i, e in enumerate(entities):
        raw = " ".join(
            f"[{b.get('type')}] {b.get('text')}"
            for b in (e.get("rawFurtherInfo") or [])
            if b.get("text")
        )[:_MAX_FI_CHARS]
        payload.append(
            {
                "id": i,
                "name": e.get("matchedName") or "",
                "country": e.get("country") or "",
                "onSanctionLists": True,  # запись уже найдена в списках — не отрицать
                "sanctionType": e.get("sanctionType") or [],
                "whoImposed": e.get("whoImposedRaw") or [],
                "details": raw or "подробного текста в записи нет",
            }
        )

    try:
        with ai_trace(name="sanction_narratives", iin=""):
            client = create_async_openai_client()
            resp = await client.chat.completions.create(
                name="sanction_narratives",
                model=settings.openai_model,
                messages=[
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                ],
                temperature=0.2,
            )
        content = (resp.choices[0].message.content or "").strip()
        # tolerate ```json fences
        if content.startswith("```"):
            content = content.strip("`")
            content = content[content.find("["):]
        parsed = json.loads(content)
        out = dict(fallbacks)
        for item in parsed:
            idx = int(item.get("id"))
            text = str(item.get("text") or "").strip()
            if 0 <= idx < len(entities) and text:
                out[idx] = text
        return out
    except Exception as exc:  # noqa: BLE001 - LLM is best-effort, never block the report
        logger.warning("sanction narrative LLM failed, using fallback: %s", exc)
        return fallbacks
