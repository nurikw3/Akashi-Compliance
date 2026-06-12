"""Plain-Russian decoder for LSEG / sanctions jargon.

The end user is a non-technical compliance officer. Every code, abbreviation
and English keyword must be turned into plain Russian. Deterministic only —
no LLM, no recommendations.
"""
from __future__ import annotations

# ── PEP / статусы ────────────────────────────────────────────────────────────

PEP_PLAIN = "публично значимое лицо (политик, чиновник или связанные с ними лица)"

MATCH_STRENGTH_PLAIN = {
    "EXACT": "точное совпадение",
    "STRONG": "сильное совпадение",
    "MEDIUM": "среднее совпадение — требует ручной проверки",
    "WEAK": "слабое совпадение — вероятно, однофамилец",
}

VERIFICATION_PLAIN = {
    "CONFIRMED": "подтверждено",
    "UNVERIFIED": "не подтверждено по документам (возможен однофамилец)",
    "FALSE_POSITIVE": "по документам не совпало",
}

# ── расшифровка органов / списков (по первому токену названия списка) ─────────

AUTHORITY_PLAIN = {
    "OFAC": "Управление по иностранным активам Минфина США (OFAC)",
    "UKHMT": "Казначейство Великобритании",
    "UK": "Великобритания",
    "EU": "Евросоюз",
    "UN": "ООН (Совет Безопасности)",
    "BIS": "Минторг США — экспортный контроль (BIS)",
    "USA": "США",
    "US": "США",
    "DFAT": "МИД Австралии",
    "SECO": "Госсекретариат экономики Швейцарии",
    "AUSTRALIA": "Австралия",
    "SWITZERLAND": "Швейцария",
    "ISRAEL": "Израиль",
    "JAPAN": "Япония",
    "CANADA": "Канада",
    "RUSSIAN FEDERATION": "Россия",
}

# Приоритет вывода юрисдикций (ключевые — первыми, остальные сворачиваем в «+N»)
PRIORITY_JURISDICTIONS = [
    "United States", "США",
    "European Union", "Евросоюз", "ЕС",
    "United Kingdom", "Великобритания",
    "United Nations", "ООН",
    "Russia", "Россия",
]

# ── расшифровка ключевых кодов World-Check (что код ОЗНАЧАЕТ простыми словами)─

KEYWORD_PLAIN = {
    "INSAE-WC": "связан с лицом/компанией под санкциями (ЕС, США, Великобритания, ООН)",
    "INSAE-50-WC": "на 50% и более принадлежит лицу/компании под санкциями",
    "INSAE-50-OFAC-WC": "на 50% и более принадлежит компании под санкциями США (OFAC)",
    "INSAE-50-UKHMT-WC": "на 50% и более принадлежит лицу под санкциями Великобритании",
    "RSSRE-WC": "связан с российской компанией под секторальными санкциями (США/ЕС)",
    "RSSRE-50-WC": "на 50% и более принадлежит российской компании под секторальными санкциями США",
    "RUPTRE-WC": "связан с государственными структурами России (запрещённые операции)",
    "BIS-WC": "в списке аффилированных лиц Минторга США (экспортный контроль)",
    "SIE": "компания с государственным участием",
}

# ── типы санкций (простые ярлыки) ────────────────────────────────────────────


def classify_sanction_type(sanction_lists: list[str], categories: list[str]) -> list[str]:
    """Вернуть простые русские ярлыки типа санкций по названиям списков/категориям."""
    text = " ".join(sanction_lists + categories).upper()
    tags: list[str] = []

    implicit = "IMPLICIT" in text or "RELEVANT ENTITY" in text or "ASSOCIATED" in text
    rule_50 = "50%" in text or "50 OR MORE" in text or "INSAE-50" in text or "RSSRE-50" in text

    if rule_50:
        tags.append("косвенные — по структуре владения (правило 50%)")
    elif implicit:
        tags.append("косвенные (производные) — связь с санкционным лицом")
    else:
        tags.append("прямые санкции")

    if "SECTORAL" in text or "RSSRE" in text:
        tags.append("секторальные")
    if "BIS" in text or "EXPORT" in text or "INDUSTRY AND SECURITY" in text:
        tags.append("экспортный контроль")
    if "WMD" in text or "MASS DESTRUCTION" in text or "PROLIFERATION" in text:
        tags.append("оружие массового поражения")
    if "TERROR" in text:
        tags.append("терроризм")

    # де-дубликация с сохранением порядка
    seen: set[str] = set()
    out: list[str] = []
    for t in tags:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def collapse_jurisdictions(countries: list[str], *, keep: int = 4) -> str:
    """«США, ЕС, Великобритания, ООН и ещё 30 стран» — ключевые впереди, остальное в счётчик."""
    if not countries:
        return "нет данных"

    priority = [c for c in countries if c in PRIORITY_JURISDICTIONS]
    # нормализуем основные к коротким русским формам
    norm_map = {
        "United States": "США", "European Union": "ЕС", "United Kingdom": "Великобритания",
        "United Nations": "ООН", "Russia": "Россия", "International": "международные списки",
    }
    head: list[str] = []
    seen: set[str] = set()
    for c in priority + [c for c in countries if c not in priority]:
        label = norm_map.get(c, c)
        if label not in seen:
            seen.add(label)
            head.append(label)
        if len(head) >= keep:
            break

    rest = len(set(norm_map.get(c, c) for c in countries)) - len(head)
    base = ", ".join(head)
    if rest > 0:
        base += f" и ещё {rest} " + _plural_country(rest)
    return base


def _plural_country(n: int) -> str:
    if 11 <= n % 100 <= 14:
        return "стран"
    d = n % 10
    if d == 1:
        return "страна"
    if d in (2, 3, 4):
        return "страны"
    return "стран"


def decode_keyword(code: str) -> str | None:
    """Расшифровать код вида ``INTERNATIONAL - INSAE-WC - ...`` или просто ``INSAE-WC``."""
    token = code.upper()
    for key, plain in KEYWORD_PLAIN.items():
        if key in token:
            return plain
    return None
