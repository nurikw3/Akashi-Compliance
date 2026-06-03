from app.services.ai.full_report import (
    _contract_relevance_tier,
    _extract_case_role_by_parties,
    _format_courts_section,
    _normalize_section_output,
)


def test_normalize_section_output_adds_takeaway_block():
    text = "Совпадений в санкционных списках не выявлено. Проверка завершена без инцидентов."
    normalized = _normalize_section_output("sanctions", text)

    assert "### Краткое сведение" in normalized
    assert "- Риск:" in normalized
    assert "- Следующее действие:" in normalized


def test_normalize_section_output_structures_plain_text():
    text = (
        "По структуре есть несколько сложных связей через директора и учредителей "
        "без прозрачного подтверждения конечных выгодоприобретателей. "
        "Требуется дополнительная проверка документов."
    )
    normalized = _normalize_section_output("structure", text)

    assert "### Ключевые наблюдения" in normalized
    assert normalized.count("- ") >= 3


def test_extract_case_role_marks_discrepancy_when_third_party_in_defendants():
    person = "НУРУШЕВ АРМАН ЖАКЫПБЕКОВИЧ"
    case = {
        "role": "Третья сторона",
        "category": "Статья 73. Противоправные действия в сфере семейно-бытовых отношений",
        "defendants": [person],
    }
    display = _extract_case_role_by_parties(case, person)
    assert "Третья сторона" in display
    assert "⚠️" in display
    assert (
        _contract_relevance_tier(
            case, person, person_role="Директор основной компании"
        )
        == "yellow"
    )


def test_courts_section_shows_discrepancy_in_table():
    person = "НУРУШЕВ АРМАН ЖАКЫПБЕКОВИЧ"
    row = {
        "company_name": "ТОО TEST",
        "enriched_data": {
            "enrichment": {"courts": {"cases": []}},
            "individualCourtsMeta": {
                "123456789012": {"name": person, "role": "Директор основной компании"},
            },
            "individualCourts": {
                "123456789012": [
                    {
                        "category": "Статья 73",
                        "role": "Третья сторона",
                        "defendants": [person],
                        "date": "2024-05-30",
                    },
                ]
            },
        },
    }
    section = _format_courts_section(row)
    assert "⚠️" in section
    assert "расхождение" in section.lower() or "списке" in section.lower()


def test_courts_section_red_flag_for_director_defendant_serious_category():
    row = {
        "company_name": "ТОО TEST",
        "enriched_data": {
            "enrichment": {"courts": {"cases": []}},
            "individualCourtsMeta": {
                "123456789012": {
                    "name": "НУРУШЕВ АРМАН ЖАКЫПБЕКОВИЧ",
                    "role": "Директор основной компании",
                }
            },
            "individualCourts": {
                "123456789012": [
                    {
                        "category": "Статья 73. Противоправные действия в сфере семейно-бытовых отношений",
                        "result": "Привлечен",
                        "date": "2025-01-11",
                        "role": "Ответчик",
                        "documents": [{"doc_link": "https://example/doc1"}],
                    }
                ]
            },
        },
    }

    section = _format_courts_section(row)

    assert "| Person/Entity | Роль в деле | Категория/статья |" in section
    assert "НУРУШЕВ АРМАН ЖАКЫПБЕКОВИЧ" in section
    assert "Ответчик" in section
    assert "### Вывод ИИ" in section
    assert "red flag" in section.lower()


def test_courts_section_yellow_for_tax_defendant_only():
    person = "НУРУШЕВ АРМАН ЖАКЫПБЕКОВИЧ"
    row = {
        "company_name": "ТОО TEST",
        "enriched_data": {
            "enrichment": {"courts": {"cases": []}},
            "individualCourtsMeta": {
                "123456789012": {
                    "name": person,
                    "role": "Директор основной компании",
                }
            },
            "individualCourts": {
                "123456789012": [
                    {
                        "category": "Взыскание налоговой задолженности",
                        "role": "Ответчик",
                        "date": "2017-06-23",
                    },
                    {
                        "category": "Статья 73. Противоправные действия",
                        "role": "Третья сторона",
                        "date": "2024-05-30",
                    },
                ]
            },
        },
    }
    section = _format_courts_section(row)
    assert "Третья сторона" not in section or "green" in section.lower()
    assert "Ответчик" in section


def test_courts_section_green_when_only_third_party():
    row = {
        "company_name": "ТОО TEST",
        "enriched_data": {
            "enrichment": {
                "courts": {
                    "cases": [
                        {
                            "type": "Гражданское дело",
                            "role": "Третья сторона",
                            "date": "2024-01-01",
                            "status": "Завершено",
                        }
                    ]
                }
            }
        },
    }

    section = _format_courts_section(row)

    assert "- Уровень риска: green" in section
    assert "Низкая релевантность к риску компании" in section
