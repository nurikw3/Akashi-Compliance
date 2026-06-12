"""Orchestration tests for the OSINT service.

No network and no real DB: the search client, the OpenAI client and ``app.models.db``
are all monkeypatched, so the whole query-gen → search → extract → validate →
persist flow runs against fakes.
"""
from __future__ import annotations

import json

import pytest

from app.core.config import settings
from app.models import db
from app.services.osint import service as osint
from app.services.osint.client import SearchHit

_REAL = "https://kursiv.media/news/realA"
_KNOWN = "https://lseg.example/known"


def _ready_row() -> dict:
    return {
        "id": "c1",
        "iin": "123456789012",
        "company_name": "ТОО Ромашка",
        "status": "ready",
        "enriched_data": {
            "enrichment": {
                "companyInfo": {
                    "fullName": "ТОО Ромашка",
                    "director": "Иванов Иван",
                    "address": "г. Алматы, ул. X",
                    "industry": "Строительство",
                },
                "affiliates": {"individuals": [{"name": "Петров Пётр", "role": "Учредитель"}]},
                "sanctions": {"isOnList": False, "lists": []},
                "statusFlags": [],
                "riskFlags": [],
            },
            "lseg": {
                "sanctions": {"matchedLists": ["OFAC"], "hits": []},
                "pep": {"individuals": []},
                "adverseMedia": {"articles": [{"headline": "Known", "url": _KNOWN}]},
            },
        },
    }


class _FakeDB:
    """Minimal stand-in for app.models.db with in-memory row state."""

    def __init__(self, row: dict) -> None:
        self.row = row

    def get_case(self, case_id: str):
        return self.row

    def update_case(self, case_id: str, **kwargs):
        if "enriched_data" in kwargs:
            self.row = {**self.row, "enriched_data": kwargs["enriched_data"]}


def _install_fake_db(monkeypatch, row: dict) -> _FakeDB:
    fake = _FakeDB(row)
    monkeypatch.setattr(db, "get_case", fake.get_case)
    monkeypatch.setattr(db, "update_case", fake.update_case)
    return fake


def _enable_osint(monkeypatch) -> None:
    monkeypatch.setattr(settings, "osint_enabled", True)
    monkeypatch.setattr(settings, "osint_search_api_key", "test-key")
    monkeypatch.setattr(settings, "osint_search_provider", "tavily")
    monkeypatch.setattr(settings, "openai_api_key", "test-openai")
    monkeypatch.setattr(settings, "openai_model", "gpt-test")
    monkeypatch.setattr(settings, "osint_max_results", 5)


# ── Fake OpenAI client (branches on the call's `name`) ──────────────────────


class _FakeMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeChoice:
    def __init__(self, content: str) -> None:
        self.message = _FakeMessage(content)


class _FakeResponse:
    def __init__(self, content: str) -> None:
        self.choices = [_FakeChoice(content)]


class _FakeCompletions:
    def __init__(self, responder) -> None:
        self._responder = responder

    async def create(self, **kwargs):
        return _FakeResponse(self._responder(kwargs))


class _FakeOpenAI:
    def __init__(self, responder) -> None:
        self.chat = type("_Chat", (), {"completions": _FakeCompletions(responder)})()


def _responder(kwargs: dict) -> str:
    name = kwargs.get("name", "")
    if name == "osint_query_gen":
        return json.dumps(
            {"queries": [{"q": "ТОО Ромашка коррупция", "subject": "ТОО Ромашка", "category": "corruption", "lang": "ru"}]}
        )
    if name == "osint_extract":
        return json.dumps(
            {
                "findings": [
                    # novel, citation present in search hits → kept
                    {"subject": "ТОО Ромашка", "subjectRole": "company", "category": "corruption",
                     "title": "Дело о коррупции", "summary": "Факт.", "sourceUrl": _REAL, "publishedDate": "2024-01-01"},
                    # hallucinated URL (not in hits) → dropped
                    {"subject": "ТОО Ромашка", "subjectRole": "company", "category": "sanctions",
                     "title": "Выдумка", "summary": "x", "sourceUrl": "https://fake.example/nope"},
                    # off-category → dropped
                    {"subject": "Иванов Иван", "subjectRole": "director", "category": "weather",
                     "title": "Погода", "summary": "x", "sourceUrl": "https://tengrinews.kz/x"},
                    # already in LSEG adverse media (known URL, but present in hits) → dropped as dup
                    {"subject": "ТОО Ромашка", "subjectRole": "company", "category": "sanctions",
                     "title": "Дубль LSEG", "summary": "x", "sourceUrl": _KNOWN},
                ]
            }
        )
    return "{}"


class _FakeSearch:
    def __init__(self, hits: list[SearchHit]) -> None:
        self._hits = hits

    async def search(self, query: str, *, max_results: int, lang=None):
        return self._hits


def _install_fakes(monkeypatch) -> None:
    monkeypatch.setattr(osint, "create_async_openai_client", lambda: _FakeOpenAI(_responder))
    hits = [
        SearchHit(title="Real", url=_REAL, snippet="..."),
        SearchHit(title="Other", url="https://tengrinews.kz/x", snippet="..."),
        SearchHit(title="Known-in-hits", url=_KNOWN, snippet="..."),
    ]
    monkeypatch.setattr(osint, "get_search_client", lambda: _FakeSearch(hits))


# ── Tests ───────────────────────────────────────────────────────────────────


def test_is_available_gating(monkeypatch):
    _enable_osint(monkeypatch)
    assert osint.is_available() is True
    monkeypatch.setattr(settings, "osint_enabled", False)
    assert osint.is_available() is False
    monkeypatch.setattr(settings, "osint_enabled", True)
    monkeypatch.setattr(settings, "osint_search_api_key", "")
    assert osint.is_available() is False
    monkeypatch.setattr(settings, "osint_search_api_key", "k")
    monkeypatch.setattr(settings, "openai_api_key", "")
    assert osint.is_available() is False


@pytest.mark.asyncio
async def test_osint_screen_end_to_end_dedup_and_validate(monkeypatch):
    _enable_osint(monkeypatch)
    _install_fakes(monkeypatch)
    fake = _install_fake_db(monkeypatch, _ready_row())

    ok = await osint.osint_screen("c1", force=True)
    assert ok is True

    osint_section = fake.row["enriched_data"]["osint"]
    findings = osint_section["findings"]
    # Only the novel, non-hallucinated, on-category, non-dup finding survives.
    assert len(findings) == 1
    assert findings[0]["category"] == "corruption"
    assert findings[0]["sourceUrl"] == _REAL
    assert findings[0]["sourceName"] == "kursiv.media"
    assert fake.row["enriched_data"]["osintStatus"] == "ready"
    # Facts-only: no scoring keys anywhere in the persisted section.
    assert "severity" not in findings[0] and "score" not in findings[0]


@pytest.mark.asyncio
async def test_osint_screen_idempotent_without_force(monkeypatch):
    _enable_osint(monkeypatch)

    def _boom():
        raise AssertionError("LLM/search must not be called when already screened")

    monkeypatch.setattr(osint, "create_async_openai_client", _boom)
    monkeypatch.setattr(osint, "get_search_client", _boom)

    row = _ready_row()
    row["enriched_data"]["osint"] = {"screenedAt": "2024-01-01T00:00:00Z", "findings": []}
    _install_fake_db(monkeypatch, row)

    ok = await osint.osint_screen("c1", force=False)
    assert ok is True


@pytest.mark.asyncio
async def test_osint_screen_requires_ready_status(monkeypatch):
    _enable_osint(monkeypatch)
    _install_fakes(monkeypatch)
    row = _ready_row()
    row["status"] = "enriching"
    _install_fake_db(monkeypatch, row)
    assert await osint.osint_screen("c1") is False


@pytest.mark.asyncio
async def test_osint_screen_returns_false_when_disabled(monkeypatch):
    monkeypatch.setattr(settings, "osint_enabled", False)
    assert await osint.osint_screen("c1") is False
