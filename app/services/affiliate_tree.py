"""Build affiliate tree with configurable depth (default 2) via background Adata checks."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from app.core.config import settings
from app.models import db
from app.services.enrichment.mapper import build_assessment, company_data_to_enrichment
from app.services.enrichment.service import EnrichmentService
from app.services.risk.service import RiskService

logger = logging.getLogger(__name__)

TREE_DEPTH = 2
MAX_LEVEL1_COMPANY_PROBES = 15
MAX_CHILDREN_PER_NODE = 12


def normalize_bin(value: str | None) -> str:
    if not value:
        return ""
    return "".join(ch for ch in str(value) if ch.isdigit())


def _count_nodes(node: dict[str, Any]) -> int:
    return 1 + sum(_count_nodes(c) for c in node.get("children") or [])


def _empty_tree_meta() -> dict[str, Any]:
    return {
        "status": "pending",
        "depth": TREE_DEPTH,
        "nodesCount": 0,
        "checkedBins": [],
        "builtAt": None,
        "error": None,
        "root": None,
    }


def _merge_tree_into_enriched(
    enriched: dict[str, Any], tree_patch: dict[str, Any]
) -> dict[str, Any]:
    current = enriched.get("affiliateTree") or _empty_tree_meta()
    current.update(tree_patch)
    enriched["affiliateTree"] = current
    return enriched


def _save_enriched(case_id: str, enriched: dict[str, Any]) -> None:
    db.update_case(case_id, enriched_data=enriched)


def _snapshot_from_company_data(
    *,
    bin_val: str,
    name_hint: str,
    company_data: Any,
    data_sources: dict[str, str],
) -> dict[str, Any]:
    display_name = company_data.name or name_hint
    enrichment = company_data_to_enrichment(display_name or "", company_data)
    assessment = build_assessment(enrichment)
    risk = RiskService().calculate(company_data)
    assessment["riskLevel"] = risk.value
    return {
        "bin": bin_val,
        "name": display_name or name_hint,
        "enrichment": enrichment,
        "assessment": assessment,
        "dataSources": data_sources,
        "riskLevel": risk.value,
        "cachedAt": datetime.now(timezone.utc).isoformat(),
    }


def _apply_has_report_flags(
    node: dict[str, Any], node_cache: dict[str, Any], main_bin: str
) -> None:
    bin_val = normalize_bin(node.get("iinBin"))
    if bin_val and (bin_val == main_bin or bin_val in node_cache):
        node["hasReport"] = True
    for child in node.get("children") or []:
        _apply_has_report_flags(child, node_cache, main_bin)


def cache_snapshot(
    node_cache: dict[str, Any],
    bin_val: str,
    snapshot: dict[str, Any],
) -> None:
    if bin_val and len(bin_val) == 12:
        node_cache[bin_val] = snapshot


def _open_case_id(bin_val: str) -> str | None:
    if not bin_val or len(bin_val) != 12:
        return None
    existing = db.find_case_by_iin(bin_val)
    return existing["id"] if existing else None


def get_cached_node_report(
    case_row: dict[str, Any], bin_val: str
) -> dict[str, Any] | None:
    """Return instant report payload from nodeCache or main case row."""
    main_bin = normalize_bin(case_row.get("iin"))
    if bin_val == main_bin:
        enriched = case_row.get("enriched_data") or {}
        return {
            "source": "main",
            "bin": main_bin,
            "name": case_row.get("company_name"),
            "caseId": case_row["id"],
            "openCaseId": case_row["id"],
            "enrichment": enriched.get("enrichment"),
            "assessment": enriched.get("assessment"),
            "dataSources": enriched.get("dataSources"),
            "riskLevel": case_row.get("risk_level"),
            "conclusion": case_row.get("conclusion"),
        }

    enriched = case_row.get("enriched_data") or {}
    cached = (enriched.get("nodeCache") or {}).get(bin_val)
    if cached:
        return {
            "source": "cache",
            "caseId": case_row["id"],
            "openCaseId": _open_case_id(bin_val),
            **cached,
        }

    existing = db.find_case_by_iin(bin_val)
    if existing and existing.get("status") == "ready":
        existing_enriched = existing.get("enriched_data") or {}
        return {
            "source": "case",
            "bin": bin_val,
            "name": existing.get("company_name"),
            "caseId": existing["id"],
            "openCaseId": existing["id"],
            "enrichment": existing_enriched.get("enrichment"),
            "assessment": existing_enriched.get("assessment"),
            "dataSources": existing_enriched.get("dataSources"),
            "riskLevel": existing.get("risk_level"),
            "conclusion": existing.get("conclusion"),
        }
    return None


def _make_node(
    *,
    node_id: str,
    name: str,
    level: int,
    node_type: str,
    iin_bin: str = "",
    role: str = "",
    probe_error: str | None = None,
) -> dict[str, Any]:
    node: dict[str, Any] = {
        "id": node_id,
        "name": name or "—",
        "type": node_type,
        "level": level,
        "role": role,
        "children": [],
    }
    if iin_bin:
        node["iinBin"] = iin_bin
    if probe_error:
        node["probeError"] = probe_error
    return node


def _level1_from_enrichment(
    enrichment: dict[str, Any], *, main_bin: str, visited: set[str]
) -> list[dict[str, Any]]:
    affiliates = enrichment.get("affiliates") or {}
    children: list[dict[str, Any]] = []

    for index, company in enumerate(affiliates.get("companies") or []):
        name = (company.get("name") or "").strip()
        if not name:
            continue
        bin_val = normalize_bin(company.get("iinBin"))
        if bin_val and (bin_val == main_bin or bin_val in visited):
            continue
        if bin_val:
            visited.add(bin_val)
        node_id = f"l1-co-{bin_val or index}"
        children.append(
            _make_node(
                node_id=node_id,
                name=name,
                level=1,
                node_type="company",
                iin_bin=bin_val,
                role=company.get("role") or "Связанная компания",
            )
        )

    for index, person in enumerate(affiliates.get("individuals") or []):
        name = (person.get("name") or "").strip()
        if not name:
            continue
        iin = normalize_bin(person.get("iin"))
        key = iin or f"p{index}"
        if key in visited and iin:
            continue
        if iin:
            visited.add(iin)
        children.append(
            _make_node(
                node_id=f"l1-pe-{key}",
                name=name,
                level=1,
                node_type="person",
                iin_bin=iin,
                role=person.get("role") or "Физ. лицо",
            )
        )

    return children


def _affiliates_from_company_data(
    company_data: Any, *, parent_bin: str, visited: set[str], level: int
) -> list[dict[str, Any]]:
    children: list[dict[str, Any]] = []
    related = company_data.related_companies or []
    founders = company_data.founders or []

    for index, company in enumerate(related):
        if len(children) >= MAX_CHILDREN_PER_NODE:
            break
        name = (company.get("name") or "").strip()
        if not name:
            continue
        bin_val = normalize_bin(company.get("iinBin") or company.get("bin"))
        if not bin_val or len(bin_val) != 12:
            continue
        if bin_val == parent_bin or bin_val in visited:
            continue
        visited.add(bin_val)
        children.append(
            _make_node(
                node_id=f"l{level}-co-{bin_val}",
                name=name,
                level=level,
                node_type="company",
                iin_bin=bin_val,
                role=company.get("role") or "Связь",
            )
        )

    for index, person in enumerate(founders):
        if len(children) >= MAX_CHILDREN_PER_NODE:
            break
        name = (person.get("name") or "").strip()
        if not name:
            continue
        iin = normalize_bin(person.get("iin"))
        node_key = iin or f"f{index}"
        if iin and iin in visited:
            continue
        if iin:
            visited.add(iin)
        children.append(
            _make_node(
                node_id=f"l{level}-pe-{node_key}",
                name=name,
                level=level,
                node_type="person",
                iin_bin=iin,
                role=person.get("role") or "Учредитель",
            )
        )

    return children


async def _probe_bin(
    bin_val: str,
    name_hint: str,
    *,
    parent_bin: str,
    visited: set[str],
    level: int,
    semaphore: asyncio.Semaphore,
    node_cache: dict[str, Any],
) -> list[dict[str, Any]]:
    async with semaphore:
        service = EnrichmentService()
        try:
            company_data, _, data_sources = await service.enrich(bin_val)
            cache_snapshot(
                node_cache,
                bin_val,
                _snapshot_from_company_data(
                    bin_val=bin_val,
                    name_hint=name_hint,
                    company_data=company_data,
                    data_sources=data_sources,
                ),
            )
            return _affiliates_from_company_data(
                company_data,
                parent_bin=parent_bin,
                visited=visited,
                level=level,
            )
        except Exception as exc:
            logger.warning("Tree probe failed for BIN %s: %s", bin_val, exc)
            return [
                _make_node(
                    node_id=f"l{level}-err-{bin_val}",
                    name=f"{name_hint} (ошибка проверки)",
                    level=level,
                    node_type="company",
                    iin_bin=bin_val,
                    role="Не удалось загрузить связи",
                    probe_error=str(exc),
                )
            ]


async def build_affiliate_tree(case_id: str) -> None:
    """Background job: expand affiliate network to ``TREE_DEPTH`` levels."""
    row = db.get_case(case_id)
    if row is None:
        return

    enriched = row.get("enriched_data") or {}
    enrichment = enriched.get("enrichment")
    main_bin = normalize_bin(row["iin"])
    main_name = row["company_name"]

    if not enrichment or not main_bin:
        _save_enriched(
            case_id,
            _merge_tree_into_enriched(
                enriched,
                {
                    "status": "error",
                    "error": "Нет данных обогащения для построения дерева",
                    "builtAt": datetime.now(timezone.utc).isoformat(),
                },
            ),
        )
        return

    visited: set[str] = {main_bin}
    checked_bins: list[str] = [main_bin]
    node_cache: dict[str, Any] = dict(enriched.get("nodeCache") or {})

    assessment = enriched.get("assessment")
    if enrichment and assessment:
        cache_snapshot(
            node_cache,
            main_bin,
            {
                "bin": main_bin,
                "name": main_name,
                "enrichment": enrichment,
                "assessment": assessment,
                "dataSources": enriched.get("dataSources") or {},
                "riskLevel": row.get("risk_level"),
                "cachedAt": datetime.now(timezone.utc).isoformat(),
            },
        )
    enriched["nodeCache"] = node_cache

    enriched = _merge_tree_into_enriched(
        enriched,
        {
            "status": "building",
            "depth": TREE_DEPTH,
            "nodesCount": 1,
            "checkedBins": checked_bins,
            "error": None,
            "root": {
                "id": f"root-{main_bin}",
                "name": main_name,
                "iinBin": main_bin,
                "type": "main",
                "role": "Исследуемая компания",
                "level": 0,
                "children": [],
            },
        },
    )
    _save_enriched(case_id, enriched)

    root = enriched["affiliateTree"]["root"]
    root["children"] = _level1_from_enrichment(
        enrichment, main_bin=main_bin, visited=visited
    )
    root["hasReport"] = True
    _apply_has_report_flags(root, node_cache, main_bin)

    # Persist partial tree so UI can show level 1 while level 2 loads
    enriched["nodeCache"] = node_cache
    enriched = _merge_tree_into_enriched(
        enriched,
        {
            "nodesCount": _count_nodes(root),
            "checkedBins": list(visited),
            "root": root,
        },
    )
    _save_enriched(case_id, enriched)

    if TREE_DEPTH < 2:
        enriched = _merge_tree_into_enriched(
            enriched,
            {
                "status": "ready",
                "nodesCount": _count_nodes(root),
                "builtAt": datetime.now(timezone.utc).isoformat(),
                "root": root,
            },
        )
        _save_enriched(case_id, enriched)
        return

    level1_companies = [
        n
        for n in root["children"]
        if n.get("type") == "company" and normalize_bin(n.get("iinBin")) and len(normalize_bin(n.get("iinBin"))) == 12
    ][:MAX_LEVEL1_COMPANY_PROBES]

    semaphore = asyncio.Semaphore(max(1, settings.graph_probe_concurrency))

    async def expand_level1(node: dict[str, Any]) -> None:
        bin_val = normalize_bin(node.get("iinBin"))
        if not bin_val:
            return
        checked_bins.append(bin_val)
        children = await _probe_bin(
            bin_val,
            node.get("name") or "",
            parent_bin=bin_val,
            visited=visited,
            level=2,
            semaphore=semaphore,
            node_cache=node_cache,
        )
        node["children"] = children
        node["hasReport"] = bin_val in node_cache
        _apply_has_report_flags(node, node_cache, main_bin)

    try:
        await asyncio.gather(*[expand_level1(n) for n in level1_companies])
        _apply_has_report_flags(root, node_cache, main_bin)
        enriched["nodeCache"] = node_cache
        enriched = _merge_tree_into_enriched(
            enriched,
            {
                "status": "ready",
                "nodesCount": _count_nodes(root),
                "checkedBins": list(dict.fromkeys(checked_bins + list(visited))),
                "builtAt": datetime.now(timezone.utc).isoformat(),
                "root": root,
            },
        )
        _save_enriched(case_id, enriched)
    except Exception as exc:
        logger.exception("Affiliate tree build failed for %s", case_id)
        enriched["nodeCache"] = node_cache
        enriched = _merge_tree_into_enriched(
            enriched,
            {
                "status": "error",
                "error": str(exc),
                "nodesCount": _count_nodes(root),
                "builtAt": datetime.now(timezone.utc).isoformat(),
                "root": root,
            },
        )
        _save_enriched(case_id, enriched)
