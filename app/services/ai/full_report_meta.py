"""Freshness and context-size metadata for sectional full reports."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.core.config import settings

# gpt-4o-mini — 128k context; sectional calls use a fraction per request.
FULL_REPORT_CONTEXT_WINDOW = 128_000

_SECTION_KEYS = ("sanctions", "courts", "structure", "summary")


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts or not isinstance(ts, str):
        return None
    try:
        normalized = ts.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        return None


def compute_full_report_staleness(enriched: dict[str, Any]) -> dict[str, Any]:
    """True when affiliate tree was rebuilt after the last saved full report."""
    tree = enriched.get("affiliateTree") or {}
    if not isinstance(tree, dict):
        tree = {}

    tree_status = tree.get("status")
    tree_built_at = tree.get("builtAt")
    report_generated_at = enriched.get("fullReportGeneratedAt")
    report_tree_snapshot = enriched.get("fullReportTreeBuiltAt")
    has_report = bool(enriched.get("fullReport"))
    nodes_count = tree.get("nodesCount") or 0

    base = {
        "stale": False,
        "reason": None,
        "message": None,
        "treeBuiltAt": tree_built_at,
        "reportGeneratedAt": report_generated_at,
        "reportTreeBuiltAt": report_tree_snapshot,
        "treeNodesCount": nodes_count,
        "treeStatus": tree_status,
    }

    if tree_status == "building":
        base["message"] = "Дерево связей сейчас перестраивается"
        return base

    if not has_report:
        base["reason"] = "no_report"
        if tree_status == "ready" and nodes_count:
            base["message"] = (
                f"Дерево готово ({nodes_count} узлов). Сгенерируйте отчёт, чтобы включить связи."
            )
        return base

    if not tree_built_at:
        return base

    reference = _parse_iso(report_tree_snapshot) or _parse_iso(report_generated_at)
    built = _parse_iso(tree_built_at)
    if built is None:
        return base

    if reference is None or built > reference:
        built_label = built.strftime("%d.%m.%Y %H:%M")
        report_label = (
            reference.strftime("%d.%m.%Y %H:%M") if reference else "—"
        )
        base["stale"] = True
        base["reason"] = "graph_updated"
        base["message"] = (
            f"Дерево связей обновлено ({built_label}), отчёт сформирован раньше ({report_label}). "
            "Пересоздайте отчёт, чтобы учесть новые узлы и аффилиатов."
        )
        return base

    return base


def estimate_full_report_context(row: dict[str, Any]) -> dict[str, Any] | None:
    """Размер ввода для единственного LLM-вызова (резюме).

    Отчёт собирается детерминированно из БД; LLM вызывается только для краткого
    резюме по блоку «Существенные факты» — и не вызывается, если их нет.
    """
    if row.get("status") != "ready":
        return None

    from app.services.ai.full_report import _build_material_facts_block

    enriched = row.get("enriched_data") or {}
    if not isinstance(enriched, dict) or not enriched.get("enrichment"):
        return None

    material = _build_material_facts_block(row)
    has_material = bool(
        material.strip()
        and not material.startswith("Существенных фактов не выявлено")
    )
    approx_input = (len(material) // 4) if has_material else 0
    section_calls = 1 if has_material else 0

    return {
        "model": settings.openai_model,
        "contextWindowTokens": FULL_REPORT_CONTEXT_WINDOW,
        "sectionCalls": section_calls,
        "approxTotalInputTokens": approx_input,
        "headroomTokens": max(0, FULL_REPORT_CONTEXT_WINDOW - approx_input),
        "sections": {},
        "note": (
            "Разделы собираются детерминированно из БД (без LLM). LLM вызывается "
            "только для краткого резюме по существенным фактам — или не вызывается, "
            "если их нет."
        ),
    }


def full_report_meta_for_row(row: dict[str, Any]) -> dict[str, Any]:
    enriched = row.get("enriched_data") or {}
    if not isinstance(enriched, dict):
        enriched = {}
    stale = compute_full_report_staleness(enriched)
    estimate = estimate_full_report_context(row)
    return {
        "fullReportStale": stale["stale"],
        "fullReportStaleReason": stale.get("reason"),
        "fullReportStaleMessage": stale.get("message"),
        "graphBuiltAt": stale.get("treeBuiltAt"),
        "fullReportContextEstimate": estimate,
    }
