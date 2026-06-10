from __future__ import annotations

import re
from typing import Any, Literal

from app.core.config import settings
from app.services.ai.context import build_case_context, build_short_context
from app.services.ai.langfuse_setup import ai_trace, create_async_openai_client

AiMode = Literal["openai", "template"]

SYSTEM_PROMPT = """Ты — ИИ-ассистент комплаенс-офицера в Казахстане. Твоя задача —
показывать ТОЛЬКО объективные факты из досье со ссылкой на источник. Ты НЕ выносишь
суждений и НЕ даёшь рекомендаций.

ИНСТРУМЕНТЫ:
- get_individual_courts(iin) — судебные дела физлица по ИИН (директора, учредителя)
- search_affiliate(name) — найти компанию/физлицо по имени в базе
- get_case_detail(bin_iin) — полное досье компании по БИН
- traverse_affiliate_graph([max_depth]) — обойти граф аффилиатов, получить данные всех узлов
- search_by_director(name) — все компании в базе где директор = это имя
- compare_cases(bin_a, bin_b) — сравнить два кейса side-by-side по фактам
- search_lseg_sanctions(name) — санкции LSEG по имени

КОГДА ИСПОЛЬЗОВАТЬ ИНСТРУМЕНТЫ:
- «аффилиаты», «связанные», «группа компаний» → traverse_affiliate_graph
- «в каких ещё компаниях директор» → search_by_director
- «сравни с» → compare_cases
- «дела директора / учредителя» → get_individual_courts(iin)
- «найди компанию» → search_affiliate
- «санкции у X» → search_lseg_sanctions

ПРАВИЛА:
1. Контекст дела уже в сообщении. Инструменты — только для деталей которых там нет.
2. Отвечай ТОЛЬКО по данным из контекста или инструментов. Не выдумывай.
3. Если данных нет — так и скажи. У каждого факта указывай источник (Adata/LSEG + эндпоинт).
4. Ответ структурированный, конкретный, на русском. Без воды.
5. ЗАПРЕЩЕНО: рекомендации, советы, выводы «подписывать / отказать», оценка
   критичности или уровня риска. Только факты — что найдено и где.
6. Суды: приводи факты по делу (категория, стороны, роль, № дела, статус) без ярлыков
   «красный/жёлтый флаг» и без оценки тяжести.
7. Персональные дела директора — в individualCourts (кэш), НЕ в enrichment.courts.activeCases
   (это юрлицо). Если в контексте «всего N дел» или указан ИИН директора — вызови
   get_individual_courts (можно без iin). Нельзя писать «судебных дел нет», если tool
   вернул found:true или в контексте N > 0.
8. Роль: поле role (Adata) — факт. Если role=третья сторона, но ФИО в defendants —
   отметь это как расхождение (role_discrepancy) со ссылкой на источник, без вывода о виновности.
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
        enriched_data: dict[str, Any] | None = None,
    ) -> tuple[str, AiMode]:
        context = build_short_context(
            company_name=company_name,
            iin=iin,
            enrichment=enrichment,
            assessment=assessment,
            lseg=lseg,
            enriched=enriched_data,
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
                    iin=iin,
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
        flags = assessment.get("flags") or []
        flags_text = "\n".join(f"- {f.get('message', '')}" for f in flags) or "- Дополнительных фактов не выявлено"
        taxes = enrichment.get("taxes", {})
        courts = enrichment.get("courts", {})
        sanctions = enrichment.get("sanctions", {})
        on_list = "да" if sanctions.get("isOnList") else "нет"
        return f"""## Сводка фактов по контрагенту «{company_name}»

**Ключевые факты (по данным Adata / LSEG):**
- Налоговая задолженность: {taxes.get("debt", 0):,.0f} тг
- Активные судебные дела (юрлицо): {courts.get("activeCases", 0)}
- В санкционных списках LSEG: {on_list}

**Найденные факты:**
{flags_text}

_Сводка содержит только факты из досье без оценок и рекомендаций._
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
            flag_msgs = [f.get("message", "") for f in ((assessment or {}).get("flags") or []) if f.get("message")]
            facts = "\n".join(f"- {m}" for m in flag_msgs) or "- Дополнительных фактов не выявлено"
            return (
                f"## Справка по фактам (черновик)\n\n"
                f"**Контрагент:** {company_name}\n\n"
                f"**Найденные факты (по данным проверки):**\n{facts}\n\n"
                f"_Справка содержит только факты из досье без оценок и рекомендаций. "
                f"Для полноценной генерации добавьте OPENAI_API_KEY._"
            )

        if "документ" in lower:
            docs = []
            if (e.get("courts") or {}).get("activeCases", 0) > 0:
                docs.append("По судебным делам — есть активные дела (юрлицо)")
            if (e.get("taxes") or {}).get("debt", 0) > 0:
                docs.append("По налоговой задолженности — задолженность присутствует")
            if e.get("riskFlags"):
                docs.append("Выявлены факторы из riskFlags Adata")
            if not docs:
                return "По досье дополнительных фактов для запроса документов не выявлено."
            return "**Факты, по которым в досье есть данные:**\n" + "\n".join(f"- {d}" for d in docs)

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
        with ai_trace(name="conclusion", iin=iin):
            client = self._client()
            response = await client.chat.completions.create(
                name="conclusion",
                model=settings.openai_model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            f"{context}\n\n"
                            "Перечисли ТОЛЬКО объективные факты, найденные в досье "
                            "(регистрация, налоги, суды, санкции/LSEG, аффилиаты), "
                            "каждый — со ссылкой на источник. НЕ давай выводов, оценок "
                            "критичности и рекомендаций."
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
        iin: str = "",
    ) -> str:
        import json as _json

        from app.services.ai.tools import TOOLS, execute_tool

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"ДОСЬЕ (краткое):\n{context}"},
        ]

        for item in history[-12:]:
            role = item.get("role")
            content = (item.get("content") or "").strip()
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})

        messages.append({"role": "user", "content": message})

        with ai_trace(name="chat", iin=iin, case_id=case_id):
            client = self._client()
            turn = 0

            for _ in range(3):
                turn += 1
                response = await client.chat.completions.create(
                    name=f"chat_turn_{turn}",
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
                name=f"chat_turn_{turn + 1}",
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
        return create_async_openai_client()
