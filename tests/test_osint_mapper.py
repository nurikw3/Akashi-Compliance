"""Pure-function tests for OSINT mapper: validation, dedup, facts-only output."""
from __future__ import annotations

from app.services.osint.mapper import (
    build_lseg_adata_digest,
    build_osint_section,
    lseg_adata_known_urls,
    validate_findings,
)

_REAL = "https://kursiv.media/news/realA"
_KNOWN = "https://lseg.example/known-article"
_ALLOWED = {_REAL, _KNOWN, "https://tengrinews.kz/x"}


def _finding(url: str, *, category: str = "corruption", role: str = "company") -> dict:
    return {
        "subject": "ТОО Ромашка",
        "subjectRole": role,
        "category": category,
        "title": "Заголовок",
        "summary": "Факт.",
        "sourceUrl": url,
        "publishedDate": "2024-01-01",
    }


def test_validate_drops_hallucinated_citation() -> None:
    findings = [_finding("https://fake.example/not-from-search")]
    assert validate_findings(findings, allowed_urls=_ALLOWED, known_urls=set()) == []


def test_validate_keeps_novel_and_drops_lseg_known_url() -> None:
    findings = [_finding(_REAL), _finding(_KNOWN, category="sanctions")]
    out = validate_findings(findings, allowed_urls=_ALLOWED, known_urls={_KNOWN})
    assert len(out) == 1
    assert out[0]["sourceUrl"] == _REAL


def test_validate_drops_off_category() -> None:
    findings = [_finding("https://tengrinews.kz/x", category="weather")]
    assert validate_findings(findings, allowed_urls=_ALLOWED, known_urls=set()) == []


def test_validate_normalizes_trailing_slash_for_dedup() -> None:
    # LSEG stored the URL without a trailing slash; the finding has one.
    findings = [_finding(_KNOWN + "/")]
    assert validate_findings(findings, allowed_urls={_KNOWN + "/"}, known_urls={_KNOWN}) == []


def test_source_name_derived_from_url_not_llm() -> None:
    f = _finding(_REAL)
    f["sourceName"] = "totally-wrong.com"  # the LLM lied; we must overwrite it
    out = validate_findings([f], allowed_urls=_ALLOWED, known_urls=set())
    assert out[0]["sourceName"] == "kursiv.media"


def test_invalid_role_falls_back_to_company() -> None:
    out = validate_findings([_finding(_REAL, role="ceo")], allowed_urls=_ALLOWED, known_urls=set())
    assert out[0]["subjectRole"] == "company"


def test_facts_only_no_scores() -> None:
    findings = validate_findings([_finding(_REAL)], allowed_urls=_ALLOWED, known_urls=set())
    section = build_osint_section(
        findings=findings, subjects=[], queries_used=["q"], screened_at="2026-01-01T00:00:00Z"
    )
    forbidden = {"severity", "score", "risk", "recommendation", "flag", "criticality"}

    def _scan(obj: object) -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                assert k.lower() not in forbidden, f"forbidden key {k!r} in OSINT output"
                _scan(v)
        elif isinstance(obj, list):
            for item in obj:
                _scan(item)

    _scan(section)


def test_build_section_counts_and_sources() -> None:
    findings = [
        {"subjectRole": "company", "sourceName": "kursiv.media", "category": "corruption"},
        {"subjectRole": "director", "sourceName": "tengrinews.kz", "category": "reputation"},
        {"subjectRole": "company", "sourceName": "kursiv.media", "category": "sanctions"},
    ]
    section = build_osint_section(
        findings=findings, subjects=[], queries_used=[], screened_at="t"
    )
    assert section["counts"] == {"company": 2, "director": 1, "founder": 0}
    # sources are de-duplicated, order-preserving
    assert section["sources"] == ["kursiv.media", "tengrinews.kz"]


def test_lseg_adata_known_urls_collects_media_and_reference_links() -> None:
    enriched = {
        "lseg": {
            "adverseMedia": {"articles": [{"url": "https://a.example/x/"}]},
            "sanctions": {
                "hits": [{"sourceReferenceLinks": [{"url": "https://ofac.gov/sdn"}]}]
            },
        }
    }
    urls = lseg_adata_known_urls(enriched)
    assert "https://a.example/x" in urls  # normalized (trailing slash stripped)
    assert "https://ofac.gov/sdn" in urls


def test_build_lseg_adata_digest_shape() -> None:
    enriched = {
        "lseg": {
            "sanctions": {"matchedLists": ["OFAC"], "hits": [{"primaryName": "SOME CO"}]},
            "pep": {"individuals": [{"primaryName": "Иванов"}]},
            "adverseMedia": {"articles": [{"headline": "Scandal"}]},
        },
        "enrichment": {"sanctions": {"lists": ["КГД"]}, "statusFlags": ["s"], "riskFlags": ["r"]},
    }
    digest = build_lseg_adata_digest(enriched)
    assert digest["lsegSanctionLists"] == ["OFAC"]
    assert digest["lsegSanctionNames"] == ["SOME CO"]
    assert digest["lsegPepNames"] == ["Иванов"]
    assert digest["lsegMediaHeadlines"] == ["Scandal"]
    assert digest["adataSanctionLists"] == ["КГД"]
