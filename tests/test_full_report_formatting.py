"""Тесты детерминированной сборки отчёта (full_report) — facts-only, без LLM."""

from app.services.ai.full_report import (
    _assemble_report,
    _build_courts_section,
    _build_fact_snapshot,
    _build_individuals_section,
    _build_material_facts_block,
    _build_structure_section,
    _collect_court_rows,
    _collect_individual_flags,
    _contract_relevance_tier,
    _extract_case_role_by_parties,
    _should_skip_case_for_report,
)

PERSON = "НУРУШЕВ АРМАН ЖАКЫПБЕКОВИЧ"


def _row_with(**enriched):
    return {"id": "case-1", "company_name": 'ТОО "ВК ТЕХ"', "iin": "220840001616",
            "enriched_data": enriched}


# ─── Согласование роли в суде ───────────────────────────────────────────────

def test_role_reconciled_when_third_party_but_in_defendants():
    """Adata говорит «Третья сторона», но ФИО есть в ответчиках → расхождение."""
    case = {
        "role": "Третья сторона",
        "category": "Статья 73. Противоправные действия в сфере семейно-бытовых отношений",
        "defendants": [PERSON],
    }
    display = _extract_case_role_by_parties(case, PERSON)
    assert "Третья сторона" in display
    assert "в списке сторон" in display  # реконсиляция показана текстом
    assert "⚠️" not in display  # без эмодзи


def test_company_court_row_uses_reconciled_role():
    """Дело компании: роль в таблице сверяется со списком сторон, не сырое поле."""
    company = 'ТОО "ВК ТЕХ"'
    row = _row_with(enrichment={"courts": {"cases": [
        {"role": "Третья сторона", "category": "о взыскании недоимки",
         "date": "2017-06-23", "defendants": [company]},
    ]}})
    rows = _collect_court_rows(row)
    assert len(rows) == 1
    assert rows[0]["is_defendant"] is True
    assert rows[0]["has_role_discrepancy"] is True
    # В таблице — компактная пометка о сверке (полное пояснение в «Найденных фактах»).
    assert "сверить" in rows[0]["role_in_case"]
    assert "Ответчик" in rows[0]["role_in_case"]


# ─── Фильтр сводных строк ───────────────────────────────────────────────────

def test_summary_rows_filtered_from_courts():
    """«Сводка за 2025 · Г:0 У:0 А:1» — мусор, не показывается."""
    summary_case = {"category": "Сводка за 2025", "result": "Г:0 У:0 А:1 АППК:0", "date": "2025"}
    real_case = {"category": "Реальное дело", "role": "Ответчик", "date": "2024-01-01"}
    assert _should_skip_case_for_report(summary_case) is True
    assert _should_skip_case_for_report(real_case) is False

    row = _row_with(enrichment={"courts": {"cases": [summary_case, real_case]}})
    rows = _collect_court_rows(row)
    assert all("Сводка" not in r["category"] for r in rows)
    assert len(rows) == 1


# ─── Критические флаги физлиц ───────────────────────────────────────────────

INDIVIDUAL = {
    "individualProfiles": {
        "880101300123": {
            "basicFl": {"name": PERSON, "age": 45, "alive": True, "is_public_official": True},
            "reliabilityFl": {"terrorist": True, "ban_leaving": True, "ban_leaving_sum": 500000},
            "courtCaseFl": {"total_civil_count": 2, "total_criminal_count": 0, "total_administrative_count": 3},
        }
    }
}


def test_collect_individual_flags_parses_critical():
    flags = _collect_individual_flags(INDIVIDUAL)
    assert len(flags) == 1
    item = flags[0]
    assert "в списке террористов" in item["critical_flags"]
    assert any("запрет на выезд" in f for f in item["other_flags"])
    assert item["pep"] is True
    assert item["courts"]["admin"] == 3


def test_individual_flags_surface_in_snapshot_material_and_section():
    row = _row_with(**INDIVIDUAL)
    snapshot = _build_fact_snapshot(row)
    material = _build_material_facts_block(row)
    section = _build_individuals_section(row)
    for out in (snapshot, material, section):
        assert "в списке террористов" in out
    assert PERSON in section
    assert "ПДЛ" in section


# ─── Структура без судов ────────────────────────────────────────────────────

def test_structure_section_has_no_court_cases():
    row = _row_with(
        enrichment={"courts": {"cases": [
            {"role": "Ответчик", "category": "Какое-то дело", "date": "2024-01-01"},
        ]}, "companyInfo": {"director": PERSON}},
        beneficiary=[{"name": "ACME", "share": "55%"}],
    )
    section = _build_structure_section(row)
    assert "Какое-то дело" not in section
    assert "Судебные дела намеренно" not in section  # docstring не утекает
    assert "ACME" in section  # бенефициары остаются


# ─── Существенные факты: пусто → заглушка ────────────────────────────────────

def test_material_facts_empty_returns_placeholder():
    row = _row_with(
        enrichment={"sanctions": {"isOnList": False}, "taxes": {"status": "clean", "debt": 0}},
        lseg={"sanctions": {"isOnList": False, "hits": []}, "pep": {"isHit": False}},
    )
    material = _build_material_facts_block(row)
    assert material.startswith("Существенных фактов не выявлено")


# ─── Язык: только русский, без эмодзи/англицизмов ───────────────────────────

def test_assembled_report_is_russian_only():
    row = _row_with(
        enrichment={"companyInfo": {"director": PERSON, "operatingStatus": "Действующее"},
                    "taxes": {"status": "clean", "debt": 0}, "sanctions": {"isOnList": False}},
        lseg={"sanctions": {"isOnList": False, "hits": []}, "pep": {"isHit": False}},
        lsegExtended={"k1": {"name": "ACME", "role": "учредитель", "country": "RU",
                             "isOnSanctionList": True, "hits": []}},
        **INDIVIDUAL,
    )
    report = _assemble_report(row, "")
    for bad in ("🔴", "⚠️", "watchlist", "[RED]", "[YELLOW]"):
        assert bad not in report, f"артефакт '{bad}' попал в отчёт"
    # все ключевые разделы на месте
    for heading in ("## Снимок", "## Существенные факты", "## 1. Санкционный анализ",
                    "## 2. Судебные дела", "## 3. Структура", "## 4. Физические лица",
                    "## Карта покрытия данных"):
        assert heading in report, f"нет раздела {heading}"


def test_criminal_conviction_surfaces_even_as_third_party():
    """Обвинительный приговор по мошенничеству (роль «Третья сторона») должен
    попадать и в таблицу, и в существенные факты — это не «шум»."""
    name = "САТЫБАЛДИЕВ КАБЫЛБЕК"
    row = _row_with(
        individualCourts={"111111111111": [
            {"category": "Статья 190. Мошенничество", "role": "Третья сторона",
             "result": "обвинительный приговор", "date": "2018-01-01", "number": "7550"},
        ]},
        individualCourtsMeta={"111111111111": {"name": name, "role": "учредитель"}},
    )
    rows = _collect_court_rows(row)
    assert any(r["is_serious"] for r in rows), "приговор не помечен как серьёзный"
    assert len(rows) == 1, "приговор отфильтрован как шум"
    material = _build_material_facts_block(row)
    assert "Мошенничество" in material
    assert "обвинительный приговор" in material


def test_main_company_not_listed_as_its_own_related_party():
    row = _row_with(
        enrichment={"companyInfo": {}, "sanctions": {"isOnList": False}},
        lseg={"sanctions": {"isOnList": False, "hits": []}, "pep": {"isHit": False}},
        lsegExtended={
            "220840001616": {"name": 'ТОО "ВК ТЕХ"', "isOnSanctionList": False,
                             "hits": [{"primaryName": "X"}]},
            "k2": {"name": "ACME", "isOnSanctionList": True, "hits": []},
        },
    )
    snapshot = _build_fact_snapshot(row)
    # компания не считается своим «связанным лицом»: только ACME → 1 из 1
    assert "1 из 1" in snapshot


def test_affiliate_profiles_and_registry_flags_surface():
    """affiliateProfiles (суды/налоги L1) и trustworthyPlus (массовый адрес) видны."""
    row = _row_with(
        enrichment={"companyInfo": {}, "sanctions": {"isOnList": False}},
        affiliateTree={"status": "ok", "nodesCount": 2, "root": {"children": [
            {"iinBin": "130840004730", "name": "ПК АСЕМ-ТАУ", "role": "Учредитель"},
        ]}},
        affiliateProfiles={
            "130840004730": {
                "director": "МУСИНА Г.", "courts": {"activeCases": 5, "completedCases": 0},
                "taxes": {"status": "debt", "debt": 15268}, "riskFlags": ["Налоговый риск: средняя"],
                "operatingStatus": "действующая",
            },
        },
        trustworthyPlus={"mass_address": 276, "rehabilitation_proceedings": False},
    )
    snapshot = _build_fact_snapshot(row)
    material = _build_material_facts_block(row)
    structure = _build_structure_section(row)

    # аффилиатские суды/долг — в снимке, фактах и структуре
    for out in (snapshot, material, structure):
        assert "АСЕМ-ТАУ" in out or "массовый адрес" in out
    assert "активных судебных дел 5" in material
    assert "15 268" in material  # налоговый долг аффилиата
    assert "массовый адрес регистрации (276" in material
    assert "Профили аффилиатов" in structure
    # двойного пробела в налоговой строке профиля нет
    assert "задолженность  долг" not in structure


def test_contract_relevance_tier_still_classifies():
    case = {
        "role": "Третья сторона",
        "category": "Статья 73. Противоправные действия в сфере семейно-бытовых отношений",
        "defendants": [PERSON],
    }
    assert _contract_relevance_tier(case, PERSON, person_role="Директор") == "yellow"
