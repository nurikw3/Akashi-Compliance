"""Plain-Russian explanation of court cases for a non-technical reader.

One batched LLM call turns each raw Adata court case into a human sentence:
о чём дело · роль человека (+ расхождение) · чем закончилось (выиграл/проиграл/
прекращено/исход не указан). Strict facts-only; deterministic fallback so the
dossier always renders.
"""
from __future__ import annotations

import json
import logging

from app.core.config import settings
from app.services.ai.langfuse_setup import ai_trace, create_async_openai_client

logger = logging.getLogger(__name__)

_SYSTEM = (
    "Ты — помощник, объясняешь судебные дела простым русским языком человеку без "
    "юридического образования. По каждому делу дай ТРИ коротких поля:\n"
    "1) about — о чём дело простыми словами (1 фраза, без статей и канцелярита);\n"
    "2) role — роль человека в деле простыми словами. Если указанная роль "
    "противоречит данным (например, role='Третья сторона', но человек — "
    "единственный участник дела о его правонарушении, или его ФИО в ответчиках), "
    "ОБЯЗАТЕЛЬНО отметь это: «указана как третья сторона, но фактически …»;\n"
    "3) outcome — чем закончилось простыми словами: выиграл / проиграл / "
    "оштрафован / прекращено / закрыто / ещё идёт / исход не указан. "
    "НЕ придумывай выигрыш или проигрыш, если данных нет — пиши «исход не указан».\n"
    "ТОЛЬКО факты из данных. Без советов, оценок риска и рекомендаций. "
    'Верни СТРОГО JSON-массив {"id": <num>, "about": "...", "role": "...", "outcome": "..."}.'
)


def _det_outcome(case: dict) -> str:
    res = str(case.get("result") or "").strip()
    status = str(case.get("status") or "").strip()
    if res and res.lower() not in ("дело не определено", "не определено", ""):
        return res
    if status:
        return status
    return "исход не указан"


def _det_role(case: dict) -> str:
    role = str(case.get("role") or "").strip()
    return role or "участник"


def _det_about(case: dict) -> str:
    cat = str(case.get("category") or "").strip()
    typ = str(case.get("type") or "дело").strip()
    if cat:
        # обрезаем длинную статью
        short = cat.split(".")[1].strip() if "." in cat and len(cat.split(".")) > 1 else cat
        return f"{typ}: {short[:120]}"
    return typ


def _fallback(case: dict) -> dict:
    return {"about": _det_about(case), "role": _det_role(case), "outcome": _det_outcome(case)}


async def explain_courts(cases: list[dict]) -> dict[int, dict]:
    """Return {index: {about, role, outcome}} in plain Russian. Never raises."""
    fallbacks = {i: _fallback(c) for i, c in enumerate(cases)}
    if not cases or not settings.openai_api_key:
        return fallbacks

    payload = []
    for i, c in enumerate(cases):
        payload.append({
            "id": i,
            "person": c.get("personName", ""),
            "type": c.get("type", ""),
            "category": str(c.get("category") or "")[:300],
            "declaredRole": c.get("role", ""),
            "status": c.get("status", ""),
            "result": c.get("result", ""),
            "defendants": c.get("defendants") or [],
            "plaintiffs": c.get("plaintiffs") or [],
            "participants": c.get("participants") or [],
        })

    try:
        with ai_trace(name="court_narratives", iin=""):
            client = create_async_openai_client()
            resp = await client.chat.completions.create(
                name="court_narratives",
                model=settings.openai_model,
                messages=[
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                ],
                temperature=0.2,
            )
        content = (resp.choices[0].message.content or "").strip()
        if content.startswith("```"):
            content = content.strip("`")
            content = content[content.find("["):]
        out = dict(fallbacks)
        for item in json.loads(content):
            idx = int(item.get("id"))
            if 0 <= idx < len(cases):
                out[idx] = {
                    "about": str(item.get("about") or fallbacks[idx]["about"]).strip(),
                    "role": str(item.get("role") or fallbacks[idx]["role"]).strip(),
                    "outcome": str(item.get("outcome") or fallbacks[idx]["outcome"]).strip(),
                }
        return out
    except Exception as exc:  # noqa: BLE001
        logger.warning("court narrative LLM failed, using fallback: %s", exc)
        return fallbacks
