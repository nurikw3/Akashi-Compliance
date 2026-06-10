"""Central glossary of abbreviations and compliance terms.

Used to auto-expand abbreviations in generated reports (and mirrored on the
frontend in ``lib/abbreviations.ts``). Keep the two in sync when editing.
"""

from __future__ import annotations

import re

# Canonical term -> full Russian definition. Ordered roughly by domain.
GLOSSARY: dict[str, str] = {
    # KZ business / legal
    "БИН": "Бизнес-идентификационный номер (12 цифр) юридического лица",
    "ИИН": "Индивидуальный идентификационный номер (12 цифр) физического лица",
    "ОПФ": "Организационно-правовая форма юридического лица",
    "ТОО": "Товарищество с ограниченной ответственностью",
    "АО": "Акционерное общество",
    "ИП": "Индивидуальный предприниматель",
    "КГД": "Комитет государственных доходов (налоговый орган РК)",
    "КФМ": "Комитет по финансовому мониторингу (финансовая разведка РК)",
    "УБО": "Конечный бенефициарный собственник (Ultimate Beneficial Owner)",
    "UBO": "Конечный бенефициарный собственник (Ultimate Beneficial Owner)",
    "ЧСИ": "Частный судебный исполнитель",
    "ИП (исполнительное)": "Исполнительное производство",
    # International sanctions / screening
    "LSEG": "London Stock Exchange Group — поставщик данных World-Check One",
    "WC1": "World-Check One — база санкций, PEP и негативных публикаций (LSEG)",
    "PEP": "Politically Exposed Person — публичное должностное лицо",
    "OFAC": "Office of Foreign Assets Control — орган санкций Минфина США",
    "SDN": "Specially Designated Nationals — санкционный список OFAC (США)",
    "HMT": "His Majesty's Treasury — орган санкций Великобритании",
    "EU": "European Union — санкционные списки Европейского союза",
    "UN": "United Nations — санкционные списки ООН",
    "СБ ООН": "Совет Безопасности ООН (санкционные списки)",
    "SECO": "State Secretariat for Economic Affairs — санкции Швейцарии",
    "FATF": "Financial Action Task Force — Группа разработки финансовых мер борьбы с отмыванием денег",
    "AML": "Anti-Money Laundering — противодействие отмыванию денег",
    "CFT": "Combating the Financing of Terrorism — противодействие финансированию терроризма",
    "ПОД/ФТ": "Противодействие отмыванию денег и финансированию терроризма",
    "KYC": "Know Your Customer — процедуры идентификации клиента",
    # Data sources / terms
    "Adata": "Adata.kz — источник данных по компаниям Казахстана",
    "Контроль и надзор": (
        "Сведения о государственном контроле и надзоре — проверки, предписания и "
        "надзорные меры государственных органов в отношении контрагента (по данным Adata)"
    ),
}


def define(term: str) -> str | None:
    """Return the full definition for an abbreviation/term, or None."""
    return GLOSSARY.get(term)


# Whole-word tokens (Latin/Cyrillic/digits). Slash and spaces are separators, so
# "LSEG/WC1" splits into "LSEG" and "WC1"; phrase terms are matched by substring.
_WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9]+")


def _is_phrase_term(term: str) -> bool:
    """True for terms that are not a single alphanumeric token (spaces, '/', parens)."""
    return _WORD_RE.fullmatch(term) is None


def abbreviations_in_text(text: str) -> list[str]:
    """Return glossary terms that appear in ``text`` (phrase + token match)."""
    if not text:
        return []
    found: list[str] = []
    seen: set[str] = set()

    # Phrase terms (e.g. "Контроль и надзор", "СБ ООН", "ПОД/ФТ").
    for term in GLOSSARY:
        if _is_phrase_term(term) and term in text and term not in seen:
            seen.add(term)
            found.append(term)

    tokens = set(_WORD_RE.findall(text))
    for term in GLOSSARY:
        if _is_phrase_term(term):
            continue
        if term in tokens and term not in seen:
            seen.add(term)
            found.append(term)
    return found


def glossary_legend_markdown(text: str, *, heading: str = "## Расшифровка сокращений") -> str:
    """Build a markdown legend of every glossary term used in ``text``.

    Returns an empty string when no known abbreviations are present.
    """
    terms = abbreviations_in_text(text)
    if not terms:
        return ""
    lines = [heading, ""]
    for term in terms:
        lines.append(f"- **{term}** — {GLOSSARY[term]}")
    return "\n".join(lines)
