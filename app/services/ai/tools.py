"""OpenAI tool definitions and executors for the compliance chat agent."""
from __future__ import annotations

import json
from typing import Any

from app.models import db

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_affiliate",
            "description": (
                "Поиск аффилированной компании или физлица по имени в базе данных. "
                "Возвращает данные досье: суды, налоги, риски, директора."
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
                    "name": {
                        "type": "string",
                        "description": "Имя для поиска санкций",
                    }
                },
                "required": ["name"],
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


def execute_tool(tool_name: str, arguments: dict[str, Any], current_case_id: str) -> str:
    """Execute a tool call and return result as JSON string."""

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
                    "riskLevel": row.get("risk_level"),
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
                "riskLevel": row.get("risk_level"),
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
