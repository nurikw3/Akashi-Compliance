from app.services.ai.full_report import _format_courts_section, _normalize_section_output


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
                        "defendants": ["НУРУШЕВ АРМАН ЖАКЫПБЕКОВИЧ"],
                        "documents": [{"doc_link": "https://example/doc1"}],
                    }
                ]
            },
        },
    }

    section = _format_courts_section(row)

    assert "| Person/Entity | Роль в деле | Категория/статья |" in section
    assert "НУРУШЕВ АРМАН ЖАКЫПБЕКОВИЧ" in section
    assert "### Вердикт ИИ по судам" in section
    assert "- Уровень риска: red" in section
    assert "Прямая релевантность к компании" in section


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
