from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from docx import Document

from app.services.import_parser import parse_docx_bytes, preview_import_rows

SAMPLE_DOCX = Path("/Users/nurasyk/Downloads/контрагенты_wi!th bin.docx")
TEST_2_BIN_DOCX = Path("/Users/nurasyk/Downloads/TEST_2_BIN.docx")


@pytest.mark.skipif(not SAMPLE_DOCX.is_file(), reason="Sample docx not available")
def test_sample_docx_parses_kazakh_companies() -> None:
    content = SAMPLE_DOCX.read_bytes()
    items = parse_docx_bytes(content)
    rows = preview_import_rows(items)

    assert len(items) >= 10
    valid = [row for row in rows if row["valid"]]
    assert len(valid) >= 10
    assert any("AIX FM LIMITED" in row["name"] for row in valid)
    assert all(len(row["iinBin"]) == 12 for row in valid)


def test_paragraph_line_extracts_name_and_bin() -> None:
    from app.services.import_parser import _row_from_cells

    row = _row_from_cells(
        ['AIX - ЧАСТНАЯ КОМПАНИЯ AIX FM LIMITED - 191040900016']
    )
    assert row is not None
    assert row["iinBin"] == "191040900016"
    assert "AIX FM LIMITED" in row["name"]


@pytest.mark.skipif(not TEST_2_BIN_DOCX.is_file(), reason="TEST_2_BIN.docx not available")
def test_test_2_bin_docx_parses_valid_rows() -> None:
    content = TEST_2_BIN_DOCX.read_bytes()
    items = parse_docx_bytes(content)
    rows = preview_import_rows(items)

    assert len(items) >= 2
    valid = [row for row in rows if row["valid"]]
    assert len(valid) >= 2
    assert any("AIX FM LIMITED" in row["name"] for row in valid)
    assert any("CORE 24/7" in row["name"] for row in valid)


def test_single_column_table_does_not_treat_company_name_as_header() -> None:
    """Rows containing «компания» must not be mistaken for a header row."""
    doc = Document()
    table = doc.add_table(rows=2, cols=1)
    table.rows[0].cells[0].text = (
        "AIX - ЧАСТНАЯ КОМПАНИЯ AIX FM LIMITED - 191040900016"
    )
    table.rows[1].cells[0].text = 'KazDevOps - ТОО "CORE 24/7" - 171040021791'
    buf = BytesIO()
    doc.save(buf)

    items = parse_docx_bytes(buf.getvalue())
    rows = preview_import_rows(items)
    valid = [row for row in rows if row["valid"]]

    assert len(valid) == 2
    assert valid[0]["iinBin"] == "191040900016"
    assert valid[1]["iinBin"] == "171040021791"
