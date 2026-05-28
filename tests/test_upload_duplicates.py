from __future__ import annotations

import pytest

from app.api.routes import cases as cases_routes
from app.api.routes.cases import _import_upload_item
from app.models import db


@pytest.fixture
def mock_enqueue(monkeypatch):
    async def _fake(case_id: str) -> dict:
        return {"mode": "test", "caseId": case_id}

    monkeypatch.setattr(cases_routes, "enqueue_case_pipeline", _fake)


@pytest.mark.asyncio
async def test_import_skip_existing_does_not_create_second_case(mock_enqueue):
    existing = db.create_case(company_name="First", iin="171040021794")
    action, api_case, job = await _import_upload_item(
        name="First Updated",
        iin_bin="171040021794",
        on_duplicate="skip",
    )
    assert action == "skipped"
    assert api_case["id"] == existing["id"]
    assert job is None


@pytest.mark.asyncio
async def test_import_refresh_reuses_case_and_enqueues(mock_enqueue):
    existing = db.create_case(company_name="First", iin="171040021795")
    action, api_case, job = await _import_upload_item(
        name="First Updated",
        iin_bin="171040021795",
        on_duplicate="refresh",
    )
    assert action == "refreshed"
    assert api_case["id"] == existing["id"]
    assert api_case["name"] == "First Updated"
    assert job is not None
    row = db.get_case(existing["id"])
    assert row is not None
    assert row["company_name"] == "First Updated"
    assert row["status"] == "pending"


@pytest.mark.asyncio
async def test_import_create_always_adds_new_row(mock_enqueue):
    first = db.create_case(company_name="First", iin="171040021796")
    action, api_case, job = await _import_upload_item(
        name="Second",
        iin_bin="171040021796",
        on_duplicate="create",
    )
    assert action == "created"
    assert job is not None
    assert api_case["id"] != first["id"]
