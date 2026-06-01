from __future__ import annotations

import re
from typing import Any, Literal

from app.core.config import settings
from app.services.ai.context import build_case_context, build_short_context

AiMode = Literal["openai", "template"]

SYSTEM_PROMPT = """Ты — ИИ-агент комплаенс-офицера в Казахстане.

У тебя есть инструменты для поиска данных в базе:
- search_affiliate(name) — найти аффилиата по имени
- get_case_detail(bin_iin) — получить полное досье по БИН
- search_lseg_sanctions(name) — проверить санкции по имени

ПРАВИЛА:
1. Начинай с краткого контекста. Если нужны детали — используй инструменты.
2. Отвечай только на основе найденных данных. Не выдумывай.
3. Если данных нет — скажи честно.
4. Отвечай на русском языке, структурированно.
5. При вопросах об аффилиатах/санкциях ВСЕГДА используй инструменты.
"""


class AIService:
    def uses_openai(self) -> bool:
        return bool(settings.openai_api_key)

    async def generate_conclusion(
        self,
        *,
        company_name: str,
        enrichment: dict[str, Any],
        assessment: dict[str, Any],
        iin: str = "",
        data_sources: dict[str, str] | None = None,
    ) -> str:
        if settings.openai_api_key:
            try:
                return await self._openai_conclusion(
                    company_name, enrichment, assessment, iin=iin, data_sources=data_sources
                )
            except Exception:
                pass
        return self._template_conclusion(company_name, enrichment, assessment)

    async def chat_reply(
        self,
        *,
        case_id: str,
        company_name: str,
        iin: str,
        message: str,
        enrichment: dict[str, Any] | None,
        assessment: dict[str, Any] | None,
        conclusion: str | None,
        history: list[dict[str, str]] | None = None,
        data_sources: dict[str, str] | None = None,
        lseg: dict[str, Any] | None = None,
    ) -> tuple[str, AiMode]:
        context = build_short_context(
            company_name=company_name,
            iin=iin,
            enrichment=enrichment,
            assessment=assessment,
            lseg=lseg,
        )
        full_context = build_case_context(
            company_name=company_name,
            iin=iin,
            enrichment=enrichment,
            assessment=assessment,
            conclusion=conclusion,
            data_sources=data_sources,
        )

        if settings.openai_api_key:
            try:
                reply = await self._openai_chat(
                    company_name=company_name,
                    message=message,
                    context=context,
                    history=history or [],
                    case_id=case_id,
                )
                return reply, "openai"
            except Exception:
                pass

        return (
            self._template_chat(company_name, message, full_context, enrichment, assessment),
            "template",
        )

    def _template_conclusion(
        self,
        company_name: str,
        enrichment: dict[str, Any],
        assessment: dict[str, Any],
    ) -> str:
        risk_level = assessment.get("riskLevel", "low")
        risk_label = {"low": "низкий", "medium": "средний", "high": "высокий"}[risk_level]
        flags = assessment.get("flags") or []
        flags_text = "\n".join(f"- {f.get('message', '')}" for f in flags) or "- Существенных флагов не выявлено"
        taxes = enrichment.get("taxes", {})
        courts = enrichment.get("courts", {})
        sanctions = enrichment.get("sanctions", {})
        recommendations = assessment.get("recommendations") or []
        return f"""## Заключение по контрагенту «{company_name}»

**Общий вывод:** Уровень риска — {risk_label}. {assessment.get("summary", "")}

**Ключевые факты:**
- Налоговая задолженность: {taxes.get("debt", 0):,.0f} тг
- Активные судебные дела: {courts.get("activeCases", 0)}
- Факторы риска: {"да" if sanctions.get("isOnList") or enrichment.get("riskFlags") else "нет"}

**Риски:**
{flags_text}

**Рекомендация:** {recommendations[0] if recommendations else "Провести стандартную проверку."}
""".replace(",", " ")

    def _template_chat(
        self,
        company_name: str,
        message: str,
        context: str,
        enrichment: dict[str, Any] | None,
        assessment: dict[str, Any] | None,
    ) -> str:
        lower = message.lower()
        e = enrichment or {}
        aff = e.get("affiliates") or {}
        co_count = len(aff.get("companies") or [])
        pe_count = len(aff.get("individuals") or [])

        if not e and "обработ" not in lower:
            return (
                f"Досье по «{company_name}» ещё загружается. "
                "Дождитесь статуса «готово» или обновите проверку. "
                "Для ответов по данным Adata подключите OPENAI_API_KEY в .env."
            )

        if "служеб" in lower or "записк" in lower:
            risk = (assessment or {}).get("riskLevel", "—")
            summary = (assessment or {}).get("summary", "")
            return (
                f"## Служебная записка (черновик)\n\n"
                f"**Контрагент:** {company_name}\n"
                f"**Уровень риска:** {risk}\n\n"
                f"**Обоснование:** {summary}\n\n"
                f"**Прошу:** согласовать сотрудничество / установить лимит / запросить документы "
                f"(укажите сумму и срок в вопросе).\n\n"
                f"_Для полноценной генерации добавьте OPENAI_API_KEY._"
            )

        if "документ" in lower:
            docs = [
                "Справка об отсутствии налоговой задолженности",
                "Выписка / учредительные документы",
                "Финансовая отчётность за последний период",
            ]
            if (e.get("courts") or {}).get("activeCases", 0) > 0:
                docs.append("Пояснения по судебным делам")
            if e.get("riskFlags"):
                docs.append("Письменные пояснения по выявленным факторам риска")
            return "**Рекомендуемые документы:**\n" + "\n".join(f"- {d}" for d in docs)

        if "аффили" in lower or "связ" in lower or "учред" in lower:
            lines = [f"**Связи «{company_name}»:** {co_count} юрлиц, {pe_count} физлиц/учредителей."]
            for co in (aff.get("companies") or [])[:8]:
                lines.append(f"- {co.get('name')} (БИН {co.get('iinBin')}) — {co.get('role')}")
            for person in (aff.get("individuals") or [])[:5]:
                lines.append(f"- {person.get('name')} — {person.get('role')}")
            lines.append("\n_Подключите OPENAI_API_KEY для детального анализа сети._")
            return "\n".join(lines)

        if "налог" in lower or "задолж" in lower:
            taxes = e.get("taxes") or {}
            return (
                f"**Налоги {company_name}:** задолженность {taxes.get('debt', 0):,.0f} тг, "
                f"статус «{taxes.get('status', '—')}», "
                f"последний год отчислений: {taxes.get('lastPayment', '—')}."
            ).replace(",", " ")

        if "суд" in lower or "дел" in lower:
            courts = e.get("courts") or {}
            note = courts.get("note") or ""
            cases = courts.get("cases") or []
            text = (
                f"**Суды ({courts.get('scope', 'company')}):** активных ~{courts.get('activeCases', 0)}. "
                f"{note}"
            )
            if cases:
                text += "\n" + "\n".join(
                    f"- {c.get('date')}: {c.get('status')}" for c in cases[:5]
                )
            return text

        if "риск" in lower:
            flags = e.get("riskFlags") or []
            if flags:
                return "**Факторы риска:**\n" + "\n".join(f"- {f}" for f in flags[:12])
            return (assessment or {}).get("summary", "Существенных рисков не выявлено.")

        if "директор" in lower or "руковод" in lower:
            director = (e.get("companyInfo") or {}).get("director", "—")
            return f"**Руководитель:** {director}"

        # Extract a relevant snippet from full context
        keywords = [w for w in re.split(r"\W+", lower) if len(w) > 4][:3]
        for kw in keywords:
            if kw in context.lower():
                idx = context.lower().find(kw)
                snippet = context[max(0, idx - 80) : idx + 400].strip()
                return (
                    f"По вашему вопросу (режим без OpenAI, фрагмент досье):\n\n…{snippet}…\n\n"
                    f"Задайте более конкретный вопрос или добавьте OPENAI_API_KEY для полного анализа."
                )

        summary = (assessment or {}).get("summary", "См. вкладки «Данные» и «Заключение».")
        return (
            f"**{company_name}:** {summary}\n\n"
            "Я работаю в упрощённом режиме (без OpenAI). "
            "Уточните вопрос: риски, аффилиаты, налоги, суды, документы или служебная записка. "
            "Для свободного диалога по всему досье добавьте OPENAI_API_KEY в .env."
        )

    async def _openai_conclusion(
        self,
        company_name: str,
        enrichment: dict[str, Any],
        assessment: dict[str, Any],
        *,
        iin: str = "",
        data_sources: dict[str, str] | None = None,
    ) -> str:
        context = build_case_context(
            company_name=company_name,
            iin=iin,
            enrichment=enrichment,
            assessment=assessment,
            conclusion=None,
            data_sources=data_sources,
        )
        client = self._client()
        response = await client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"{context}\n\n"
                        "Составь итоговое заключение комплаенс-офицера: вывод, факты, риски, рекомендация."
                    ),
                },
            ],
            temperature=0.3,
        )
        return response.choices[0].message.content or self._template_conclusion(
            company_name, enrichment, assessment
        )

    async def _openai_chat(
        self,
        *,
        company_name: str,
        message: str,
        context: str,
        history: list[dict[str, str]],
        case_id: str,
    ) -> str:
        import json as _json

        from app.services.ai.tools import TOOLS, execute_tool

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"ДОСЬЕ (краткое):\n{context}"},
        ]

        for item in history[-6:]:
            role = item.get("role")
            content = (item.get("content") or "").strip()
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})

        messages.append({"role": "user", "content": message})

        client = self._client()

        for _ in range(3):
            response = await client.chat.completions.create(
                model=settings.openai_model,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
                max_tokens=1500,
                temperature=0.2,
            )

            choice = response.choices[0]

            if choice.finish_reason == "stop" or not choice.message.tool_calls:
                content = choice.message.content
                if not content:
                    raise ValueError("Empty OpenAI response")
                return content

            messages.append(choice.message)

            for tool_call in choice.message.tool_calls:
                try:
                    args = _json.loads(tool_call.function.arguments)
                except Exception:
                    args = {}

                result = execute_tool(tool_call.function.name, args, case_id)

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result,
                    }
                )

        response = await client.chat.completions.create(
            model=settings.openai_model,
            messages=messages,
            max_tokens=1500,
            temperature=0.2,
        )
        content = response.choices[0].message.content
        if not content:
            raise ValueError("Empty OpenAI response")
        return content

    def _client(self) -> Any:
        from openai import AsyncOpenAI

        client_kwargs: dict[str, Any] = {"api_key": settings.openai_api_key}
        if settings.openai_base_url:
            client_kwargs["base_url"] = settings.openai_base_url
        return AsyncOpenAI(**client_kwargs)
