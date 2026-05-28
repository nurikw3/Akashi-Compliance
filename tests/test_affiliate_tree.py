from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.affiliate_tree import (
    _level1_from_enrichment,
    build_affiliate_tree,
    normalize_bin,
)


def test_normalize_bin():
    assert normalize_bin("1710 4002 1791") == "171040021791"


def test_level1_from_enrichment_dedupes_main():
    enrichment = {
        "affiliates": {
            "companies": [
                {"name": "Child Co", "iinBin": "200940900060", "role": "Учредитель"},
                {"name": "Same as main", "iinBin": "171040021791", "role": "Дубль"},
            ],
            "individuals": [{"name": "Иванов", "iin": "900101300123", "role": "Учредитель"}],
        }
    }
    visited = {"171040021791"}
    children = _level1_from_enrichment(enrichment, main_bin="171040021791", visited=visited)
    assert len(children) == 2
    assert children[0]["iinBin"] == "200940900060"


@pytest.mark.asyncio
async def test_build_affiliate_tree_ready():
    case_id = "test-case-id"
    enrichment = {
        "affiliates": {
            "companies": [{"name": "L1 Co", "iinBin": "200940900060", "role": "Связь"}],
            "individuals": [],
        }
    }

    mock_row = {
        "company_name": 'ТОО "TEST"',
        "iin": "171040021791",
        "enriched_data": {"enrichment": enrichment},
    }

    mock_company = MagicMock()
    mock_company.name = "L1 Co Full"
    mock_company.related_companies = [
        {"name": "L2 Co", "iinBin": "300940900061", "role": "Дочерняя"}
    ]
    mock_company.founders = []

    with (
        patch("app.services.affiliate_tree.db.get_case", return_value=mock_row),
        patch("app.services.affiliate_tree.db.update_case") as update_mock,
        patch(
            "app.services.affiliate_tree.EnrichmentService"
        ) as service_cls,
    ):
        service_cls.return_value.enrich = AsyncMock(
            return_value=(mock_company, ["adata"], {})
        )
        await build_affiliate_tree(case_id)

    assert update_mock.called
    enriched = update_mock.call_args_list[-1].kwargs["enriched_data"]
    tree = enriched["affiliateTree"]
    assert tree["status"] == "ready"
    assert tree["root"]["children"][0]["children"]
