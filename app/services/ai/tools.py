"""OpenAI tool definitions and executors for the compliance chat agent."""
from __future__ import annotations

import json
from typing import Any

from app.models import db
from app.services.ai.context import normalize_person_iin, resolve_individual_courts_key
from app.services.ai.court_roles import resolve_person_case_role

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_individual_courts",
            "description": (
                "Персональные судебные дела из individualCourts (Adata, кэш кейса). "
                "Без ИИН — дела директора основной компании. "
                "Не путать с enrichment.courts (суды юрлица)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "iin": {
                        "type": "string",
                        "description": "ИИН физлица (12 цифр); можно опустить для директора",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_affiliate",
            "description": (
                "Поиск аффилированной компании или физлица по имени в базе данных. "
                "Возвращает факты досье: суды, налоги, факторы (riskFlags Adata), директора."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Имя компании или физлица для поиска (частичное совпадение)",
                    }
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_case_detail",
            "description": (
                "Получить полные данные конкретного кейса по БИН или ИИН. "
                "Используй когда знаешь точный БИН аффилиата."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "bin_iin": {
                        "type": "string",
                        "description": "БИН или ИИН компании/физлица (12 цифр)",
                    }
                },
                "required": ["bin_iin"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_lseg_sanctions",
            "description": (
                "Поиск санкционных данных LSEG по имени компании или физлица. "
                "Ищет в lseg и lsegExtended полях всех кейсов."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Имя для поиска санкций"},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "traverse_affiliate_graph",
            "description": (
                "Обходит граф аффилиатов текущего кейса и возвращает факты по каждому узлу "
                "(санкции, суды, налоги, факторы). Используй для вопросов: "
                "'данные по аффилиатам', 'кто из связанных компаний под санкциями'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "max_depth": {
                        "type": "integer",
                        "description": "Глубина обхода графа (1=прямые связи, 2=через одно звено). По умолчанию 2.",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_by_director",
            "description": (
                "Найти все компании в базе где директор совпадает с именем. "
                "Используй для вопросов: 'в каких ещё компаниях директор X', "
                "'проверь все компании Нурушева', 'сеть связей по директору'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Имя или фамилия директора для поиска",
                    }
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compare_cases",
            "description": (
                "Сравнить два кейса по БИН/ИИН side-by-side по фактам: санкции, суды, налоги, статус. "
                "Используй для вопросов вида 'сравни с аффилиатом'. Возвращает факты по обоим, без оценок."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "bin_a": {"type": "string", "description": "БИН/ИИН первой компании"},
                    "bin_b": {"type": "string", "description": "БИН/ИИН второй компании"},
                },
                "required": ["bin_a", "bin_b"],
            },
        },
    },
]


def _summarize_enrichment(enriched: dict) -> dict:
    """Extract key fields for tool response (don't dump everything)."""
    enrichment = enriched.get("enrichment") or {}
    info = enrichment.get("companyInfo") or {}
    courts = enrichment.get("courts") or {}
    taxes = enrichment.get("taxes") or {}
    lseg = enriched.get("lseg") or {}

    return {
        "director": info.get("director"),
        "status": info.get("operatingStatus"),
        "industry": info.get("industry"),
        "riskFlags": enrichment.get("riskFlags") or [],
        "courts": {
            "activeCases": courts.get("activeCases", 0),
            "totalAmount": courts.get("totalAmount", 0),
            "cases": [
                {
                    "type": c.get("type"),
                    "date": c.get("date"),
                    "summary": (c.get("aiAnalysis") or {}).get("summary_ru") or c.get("status"),
                }
                for c in (courts.get("cases") or [])[:5]
            ],
        },
        "taxes": {
            "status": taxes.get("status"),
            "debt": taxes.get("debt", 0),
            "totalPaid": taxes.get("totalPaid"),
        },
        "lseg": {
            "sanctionsHit": (lseg.get("sanctions") or {}).get("isOnList", False),
            "pepHit": (lseg.get("pep") or {}).get("isHit", False),
            "matchedLists": (lseg.get("sanctions") or {}).get("matchedLists", []),
        },
    }


def _classify_court_case(case: dict, person_name: str = "") -> dict:
    """Объективное представление дела для чата — только факты, без оценки тяжести."""
    ai = case.get("aiAnalysis") or {}
    cat = str(case.get("category") or case.get("type") or "—")
    resolved = resolve_person_case_role(case, person_name)

    return {
        "category": cat,
        "role": resolved["display_role"],
        "adata_role": resolved["adata_role"],
        "party_list_role": resolved["party_list_role"],
        "role_discrepancy": resolved["has_discrepancy"],
        "date": case.get("date") or "—",
        "result": case.get("result") or case.get("status") or "—",
        "ai_summary": ai.get("summary_ru") or "",
    }


def execute_tool(tool_name: str, arguments: dict[str, Any], current_case_id: str) -> str:
    """Execute a tool call and return result as JSON string."""

    if tool_name == "get_individual_courts":
        iin_arg = str(arguments.get("iin") or "").strip() or None

        row = db.get_case(current_case_id)
        if not row:
            return json.dumps({"error": "Кейс не найден"})

        enriched = row.get("enriched_data") or {}
        enrichment = enriched.get("enrichment") or {}
        individual_courts = enriched.get("individualCourts") or {}
        meta = enriched.get("individualCourtsMeta") or {}

        storage_key = resolve_individual_courts_key(
            enriched, iin_arg, enrichment=enrichment
        )
        if not storage_key:
            hint = iin_arg or "директор"
            return json.dumps(
                {
                    "found": False,
                    "message": (
                        f"Персональные дела ({hint}) не найдены в individualCourts кейса. "
                        "Проверьте обогащение Adata."
                    ),
                }
            )

        iin = storage_key
        cases_raw = individual_courts.get(storage_key)
        if not isinstance(cases_raw, list):
            cases_raw = []

        if not cases_raw:
            return json.dumps(
                {
                    "found": False,
                    "iin": normalize_person_iin(storage_key) or storage_key,
                    "message": f"По ИИН {storage_key} в кейсе 0 дел (ключ есть, список пуст)",
                }
            )

        person_meta = meta.get(iin) if isinstance(meta.get(iin), dict) else {}
        person_name = str(person_meta.get("name") or iin)
        person_role = str(person_meta.get("role") or "")

        classified = [_classify_court_case(c, person_name) for c in cases_raw if isinstance(c, dict)]
        discrepancies = [c for c in classified if c.get("role_discrepancy")]

        return json.dumps(
            {
                "found": True,
                "person": person_name,
                "role_in_company": person_role,
                "total_cases": len(classified),
                "role_discrepancies": len(discrepancies),
                "cases": classified[:10],
            },
            ensure_ascii=False,
        )

    if tool_name == "search_affiliate":
        name = arguments.get("name", "")
        if not name:
            return json.dumps({"error": "Имя не указано"})

        rows = db.search_cases_by_name(name, limit=3)
        if not rows:
            current = db.get_case(current_case_id)
            if current:
                enriched = current.get("enriched_data") or {}
                tree = enriched.get("affiliateTree") or {}
                results = _search_in_tree(tree.get("root"), name)
                if results:
                    return json.dumps({"source": "affiliate_tree", "matches": results}, ensure_ascii=False)
            return json.dumps({"found": False, "message": f"Компания '{name}' не найдена в базе"})

        results = []
        for row in rows[:3]:
            enriched = row.get("enriched_data") or {}
            results.append(
                {
                    "name": row.get("company_name"),
                    "bin": row.get("iin"),
                    "data": _summarize_enrichment(enriched),
                }
            )
        return json.dumps({"found": True, "results": results}, ensure_ascii=False)

    if tool_name == "get_case_detail":
        bin_iin = arguments.get("bin_iin", "").strip()
        if not bin_iin:
            return json.dumps({"error": "БИН не указан"})

        row = db.find_case_by_iin(bin_iin)
        if not row:
            return json.dumps({"found": False, "message": f"Кейс с БИН {bin_iin} не найден"})

        enriched = row.get("enriched_data") or {}
        return json.dumps(
            {
                "found": True,
                "name": row.get("company_name"),
                "bin": row.get("iin"),
                "data": _summarize_enrichment(enriched),
                "lsegExtended": {
                    k: {
                        "name": v.get("name"),
                        "isOnSanctionList": v.get("isOnSanctionList"),
                        "sanctionLists": (v.get("sanctionLists") or [])[:3],
                    }
                    for k, v in (enriched.get("lsegExtended") or {}).items()
                },
            },
            ensure_ascii=False,
        )

    if tool_name == "search_lseg_sanctions":
        name = arguments.get("name", "").lower()
        if not name:
            return json.dumps({"error": "Имя не указано"})

        current = db.get_case(current_case_id)
        matches = []
        if current:
            enriched = current.get("enriched_data") or {}
            for key, entity in (enriched.get("lsegExtended") or {}).items():
                entity_name = str(entity.get("name") or key).lower()
                if name in entity_name or entity_name in name:
                    matches.append(
                        {
                            "name": entity.get("name"),
                            "isOnSanctionList": entity.get("isOnSanctionList"),
                            "sanctionLists": entity.get("sanctionLists") or [],
                            "hits": len(entity.get("hits") or []),
                        }
                    )

        return json.dumps({"matches": matches, "searchedIn": "lsegExtended"}, ensure_ascii=False)

    if tool_name == "traverse_affiliate_graph":
        max_depth = min(int(arguments.get("max_depth") or 2), 3)
        current = db.get_case(current_case_id)
        if not current:
            return json.dumps({"error": "Кейс не найден"})

        enriched = current.get("enriched_data") or {}
        tree = enriched.get("affiliateTree") or {}
        root = tree.get("root")
        if not root:
            return json.dumps({"found": False, "message": "Граф аффилиатов не построен для этого кейса"})

        nodes: list[dict] = []
        seen_bins: set[str] = set()

        def _walk(node: dict, depth: int) -> None:
            if depth > max_depth:
                return
            bin_val = str(node.get("iinBin") or "").strip()
            name_node = str(node.get("name") or "")
            role = str(node.get("role") or "")
            has_report = node.get("hasReport", False)

            entry: dict = {
                "name": name_node,
                "bin": bin_val,
                "role": role,
                "depth": depth,
                "has_report": has_report,
            }

            entry["node_type"] = str(node.get("type") or "")
            entry["enriched"] = False

            if has_report and bin_val and bin_val not in seen_bins:
                seen_bins.add(bin_val)
                row = db.find_case_by_iin(bin_val)
                if row:
                    aff_enriched = row.get("enriched_data") or {}
                    entry["data"] = _summarize_enrichment(aff_enriched)
                    entry["enriched"] = True
                    # Суды физлиц (директора аффилиата) — факт: количество дел
                    ind_courts = aff_enriched.get("individualCourts") or {}
                    ind_meta = aff_enriched.get("individualCourtsMeta") or {}
                    ind_summary: list[dict] = []
                    for iin_k, cases in ind_courts.items():
                        if not isinstance(cases, list) or not cases:
                            continue
                        pmeta = ind_meta.get(iin_k) if isinstance(ind_meta.get(iin_k), dict) else {}
                        pname = str(pmeta.get("name") or iin_k)
                        prole = str(pmeta.get("role") or "")
                        ind_summary.append({"person": pname, "role": prole, "court_cases": len(cases)})
                    if ind_summary:
                        entry["individual_courts"] = ind_summary

            nodes.append(entry)
            for child in node.get("children") or []:
                if isinstance(child, dict):
                    _walk(child, depth + 1)

        for child in root.get("children") or []:
            if isinstance(child, dict):
                _walk(child, 1)

        # Честный обход: показываем ТОЛЬКО реально загруженные данные. По узлам
        # без собственного отчёта суды/санкции/налоги НЕ проверены — пишем
        # «нет данных», а не 0, и подсказываем конкретное действие.
        NO_DATA = "нет данных (узел не обогащён)"

        enriched_nodes = [n for n in nodes if n["enriched"]]
        unenriched = [n for n in nodes if not n["enriched"]]
        unenriched_company_bins = [
            {"name": n["name"], "bin": n["bin"], "role": n["role"]}
            for n in unenriched
            if n.get("node_type") == "company" and len(n["bin"]) == 12
        ]

        sanctioned = [
            n for n in enriched_nodes
            if (n.get("data") or {}).get("lseg", {}).get("sanctionsHit")
        ]
        with_courts = [
            n for n in enriched_nodes
            if (n.get("data") or {}).get("courts", {}).get("activeCases", 0)
        ]

        full_traversal = len(unenriched) == 0 and len(enriched_nodes) > 0
        if full_traversal:
            message = (
                f"Граф обойдён полностью: данные есть по всем {len(nodes)} узлам."
            )
        elif enriched_nodes:
            message = (
                f"Полный обход графа невозможен: данные (суды/санкции/налоги) загружены "
                f"только по {len(enriched_nodes)} из {len(nodes)} узлов. По остальным "
                f"{len(unenriched)} узлам данных НЕТ — они не обогащены."
            )
        else:
            message = (
                f"Данных для обхода графа нет: ни по одному из {len(nodes)} узлов "
                f"суды/санкции/налоги не загружены (узлы не обогащены)."
            )

        how_to_complete = (
            "Чтобы проверить аффилиата, откройте его как отдельную проверку — кликните "
            "узел в графе аффилиатов (это запускает lookup по БИН: POST /lookup с iinBin "
            "и parentCaseId). После завершения проверки суды/санкции/налоги по узлу "
            "появятся в графе. Без этого данных по узлу нет."
        )

        return json.dumps(
            {
                "total_nodes": len(nodes),
                "enriched_nodes": len(enriched_nodes),
                "unenriched_nodes": len(unenriched),
                "full_traversal_possible": full_traversal,
                "message": message,
                "how_to_complete": None if full_traversal else how_to_complete,
                "unenriched_company_bins": unenriched_company_bins,
                "checked_facts": {
                    "sanctioned": [{"name": n["name"], "bin": n["bin"]} for n in sanctioned],
                    "with_active_courts": [
                        {
                            "name": n["name"],
                            "bin": n["bin"],
                            "active_courts": (n.get("data") or {}).get("courts", {}).get("activeCases", 0),
                        }
                        for n in with_courts
                    ],
                },
                "data_note": (
                    "ВАЖНО: значение «нет данных» означает, что узел НЕ проверялся, а НЕ "
                    "что проблем нет. В ответе пользователю явно раздели: (1) по каким узлам "
                    "данные ЕСТЬ и что именно в них найдено; (2) по каким узлам данных НЕТ "
                    "(перечисли их) — и подскажи открыть их через lookup (см. how_to_complete). "
                    "Запрещено писать «0 судов/санкций/налогов» по необогащённым узлам."
                ),
                "all_nodes": [
                    {
                        "name": n["name"],
                        "bin": n["bin"],
                        "role": n["role"],
                        "depth": n["depth"],
                        "node_type": n.get("node_type"),
                        "data_available": n["enriched"],
                        "active_courts": (
                            (n.get("data") or {}).get("courts", {}).get("activeCases", 0)
                            if n["enriched"] else NO_DATA
                        ),
                        "tax_debt": (
                            (n.get("data") or {}).get("taxes", {}).get("debt", 0)
                            if n["enriched"] else NO_DATA
                        ),
                        "sanctions": (
                            (n.get("data") or {}).get("lseg", {}).get("sanctionsHit", False)
                            if n["enriched"] else NO_DATA
                        ),
                        "pep": (
                            (n.get("data") or {}).get("lseg", {}).get("pepHit", False)
                            if n["enriched"] else NO_DATA
                        ),
                    }
                    for n in nodes
                ],
            },
            ensure_ascii=False,
        )

    if tool_name == "search_by_director":
        name = str(arguments.get("name") or "").strip()
        if not name:
            return json.dumps({"error": "Имя не указано"})

        rows = db.search_cases_by_director(name, limit=10)
        if not rows:
            return json.dumps({"found": False, "message": f"Компаний с директором '{name}' не найдено"})

        results = []
        for row in rows:
            if row.get("id") == current_case_id:
                continue
            aff_enriched = row.get("enriched_data") or {}
            enrichment = aff_enriched.get("enrichment") or {}
            info = enrichment.get("companyInfo") or {}
            courts = enrichment.get("courts") or {}
            taxes = enrichment.get("taxes") or {}
            lseg = aff_enriched.get("lseg") or {}
            results.append(
                {
                    "name": row.get("company_name"),
                    "bin": row.get("iin"),
                    "director": info.get("director") or "—",
                    "status": info.get("operatingStatus") or "—",
                    "active_courts": courts.get("activeCases", 0),
                    "tax_debt": (taxes.get("debt") or 0),
                    "sanctions": (lseg.get("sanctions") or {}).get("isOnList", False),
                    "pep": (lseg.get("pep") or {}).get("isHit", False),
                    "risk_flags": (enrichment.get("riskFlags") or [])[:3],
                }
            )

        return json.dumps(
            {
                "found": True,
                "director_query": name,
                "total": len(results),
                "companies": results,
            },
            ensure_ascii=False,
        )

    if tool_name == "compare_cases":
        bin_a = str(arguments.get("bin_a") or "").strip()
        bin_b = str(arguments.get("bin_b") or "").strip()
        if not bin_a or not bin_b:
            return json.dumps({"error": "Нужны оба БИН"})

        def _load(bin_val: str) -> dict | None:
            row = db.find_case_by_iin(bin_val)
            if not row:
                rows = db.search_cases_by_name(bin_val, limit=1)
                row = rows[0] if rows else None
            return row

        row_a = _load(bin_a)
        row_b = _load(bin_b)

        def _case_card(row: dict | None, label: str) -> dict:
            if not row:
                return {"label": label, "error": "не найден в базе"}
            aff_enriched = row.get("enriched_data") or {}
            enrichment = aff_enriched.get("enrichment") or {}
            info = enrichment.get("companyInfo") or {}
            courts = enrichment.get("courts") or {}
            taxes = enrichment.get("taxes") or {}
            lseg = aff_enriched.get("lseg") or {}
            assessment = aff_enriched.get("assessment") or {}
            flags = assessment.get("flags") or []
            ind_courts = aff_enriched.get("individualCourts") or {}
            total_ind = sum(len(v) for v in ind_courts.values() if isinstance(v, list))

            return {
                "label": label,
                "name": row.get("company_name"),
                "bin": row.get("iin"),
                "director": info.get("director") or "—",
                "status": info.get("operatingStatus") or "—",
                "sanctions_wc1": (lseg.get("sanctions") or {}).get("isOnList", False),
                "pep": (lseg.get("pep") or {}).get("isHit", False),
                "active_courts_company": courts.get("activeCases", 0),
                "individual_courts_total": total_ind,
                "tax_debt": taxes.get("debt") or 0,
                "tax_status": taxes.get("status") or "—",
                "risk_flags": [f.get("message") for f in flags[:4] if f.get("message")],
            }

        card_a = _case_card(row_a, bin_a)
        card_b = _case_card(row_b, bin_b)

        # Factual side-by-side: report each metric for both, no "who is riskier" verdict.
        def _facts(key: str) -> dict:
            return {"a": card_a.get(key), "b": card_b.get(key)}

        return json.dumps(
            {
                "comparison": [card_a, card_b],
                "facts": {
                    "sanctions_wc1": _facts("sanctions_wc1"),
                    "pep": _facts("pep"),
                    "active_courts_company": _facts("active_courts_company"),
                    "individual_courts_total": _facts("individual_courts_total"),
                    "tax_debt": _facts("tax_debt"),
                    "status": _facts("status"),
                },
            },
            ensure_ascii=False,
        )

    return json.dumps({"error": f"Unknown tool: {tool_name}"})


def _search_in_tree(node: dict | None, name: str) -> list[dict]:
    """Search affiliate tree for name match."""
    if not node:
        return []
    results = []
    node_name = str(node.get("name") or "").lower()
    if name.lower() in node_name:
        results.append(
            {
                "name": node.get("name"),
                "iinBin": node.get("iinBin"),
                "role": node.get("role"),
                "level": node.get("level"),
                "hasReport": node.get("hasReport", False),
            }
        )
    for child in node.get("children") or []:
        if isinstance(child, dict):
            results.extend(_search_in_tree(child, name))
    return results
