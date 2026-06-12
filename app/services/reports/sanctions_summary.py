"""Deterministic, COMPACT, plain-Russian sanctions summary builder.

Designed for a non-technical compliance officer: one short card per entity,
every code/abbreviation decoded (see :mod:`glossary`). The rigid skeleton is
КТО · ЧТО · ГДЕ · КОГДА · ПОЧЕМУ but collapsed to a few readable lines.

Hard rules: NO recommendations, NO risk scoring, facts only. The optional
``reason`` is a plain-Russian restatement of World-Check ``furtherInformation``
(produced by :mod:`sanctions_narrative`), still facts-only.
"""
from __future__ import annotations

from typing import Any

from app.services.lseg.mapper import _extract_sanctioning_countries
from app.services.reports import glossary
from app.services.reports.sanctions_narrative import generate_sanction_narratives

_MAX_SUBJECTS = 40
_MAX_FI_BLOCKS = 6      # raw blocks kept for the LLM narrative
_MAX_KEY_REFS = 3       # recognizable IDs shown to the user


def _iso(value: Any) -> str:
    s = str(value or "").strip()
    return s[:10] if len(s) >= 10 and s[4:5] == "-" else s


def _sanctioning_countries(hit: dict) -> list[str]:
    existing = hit.get("sanctioningCountries")
    if isinstance(existing, list) and existing:
        return existing
    return _extract_sanctioning_countries(hit.get("sanctionLists") or [])


# узнаваемые идентификаторы → чистый русский ярлык (без технических названий)
_REF_LABELS = [
    ("OGRN", "ОГРН"),
    ("INN", "ИНН"),
    ("UN", "Номер ООН"),
    ("OFAC", "Номер OFAC"),
    ("EU", "Номер ЕС"),
]


def _key_refs(hit: dict) -> list[str]:
    """1–3 узнаваемых идентификатора с понятным ярлыком — без свалки номеров."""
    refs: list[str] = []
    seen_labels: set[str] = set()
    for d in hit.get("identifications") or []:
        if not isinstance(d, dict):
            continue
        typ = str(d.get("type") or "").upper()
        name = str(d.get("name") or "").upper()
        val = str(d.get("value") or "").strip()
        if not val:
            continue
        label = next((ru for code, ru in _REF_LABELS if code in typ or code in name), None)
        if label and label not in seen_labels:
            seen_labels.add(label)
            refs.append(f"{label}: {val}")
        if len(refs) >= _MAX_KEY_REFS:
            break
    return refs


def _where(hit: dict) -> str:
    countries: list[str] = []
    for loc in hit.get("locationDetails") or []:
        if isinstance(loc, dict):
            c = str(loc.get("countryName") or "").strip()
            if c and c != "Undetermined Geography" and c not in countries:
                countries.append(c)
    if not countries:
        for c in hit.get("countryNames") or []:
            c = str(c).strip()
            if c and c != "Undetermined Geography" and c not in countries:
                countries.append(c)
    return ", ".join(countries) if countries else "нет данных"


def _when(hit: dict) -> str:
    rd = hit.get("recordDates") or {}
    first = _iso(rd.get("INITIAL_PUBLISHED_DATE"))
    last = _iso(rd.get("LAST_PUBLISHED_DATE"))
    if first and last and first != last:
        return f"внесён {first}, обновлён {last}"
    if first:
        return f"внесён {first}"
    if last:
        return f"обновлён {last}"
    return "нет данных"


def _raw_further_info(hit: dict) -> list[dict]:
    out = []
    for d in hit.get("furtherInformation") or []:
        if isinstance(d, dict) and str(d.get("text") or "").strip():
            out.append({"type": str(d.get("type") or "").upper(), "text": " ".join(str(d["text"]).split())})
    return out[:_MAX_FI_BLOCKS]


def _confidence(hit: dict) -> dict:
    strength = str(hit.get("matchStrength") or "").upper()
    sf = str(hit.get("sfResult") or "").upper()
    score = hit.get("matchScore")
    note = ""
    if strength in ("MEDIUM", "WEAK") and sf != "MATCHED":
        note = "система нашла похожее имя, но не подтвердила по документам — нужна ручная проверка"
    return {
        "plain": glossary.MATCH_STRENGTH_PLAIN.get(strength, strength or "—"),
        "score": f"{score:.0f}%" if isinstance(score, (int, float)) else "",
        "note": note,
    }


def _build_subject(hit: dict, *, context: str) -> dict:
    sanction_lists = [s for s in (hit.get("sanctionLists") or []) if isinstance(s, str)]
    countries = _sanctioning_countries(hit)
    return {
        "context": context,
        "matchedName": str(hit.get("primaryName") or hit.get("submittedName") or "—"),
        "country": _where(hit),
        "isSanction": bool(hit.get("isSanction")),
        "isPep": bool(hit.get("isPep")),
        "confidence": _confidence(hit),
        "whoImposed": glossary.collapse_jurisdictions(countries),
        "whoImposedRaw": countries[:8],
        "sanctionType": glossary.classify_sanction_type(sanction_lists, hit.get("categories") or []),
        "when": _when(hit),
        "keyRefs": _key_refs(hit),
        "rawFurtherInfo": _raw_further_info(hit),
        "reasonFallback": "",   # filled below
        "reason": "",           # filled by narrative pass (or fallback)
        "sources": [
            {"title": str(l.get("title") or ""), "url": str(l.get("url") or "")}
            for l in (hit.get("sourceReferenceLinks") or [])
            if isinstance(l, dict) and l.get("url")
        ][:3],
    }


def _is_material(hit: dict) -> bool:
    return bool(hit.get("isSanction") or hit.get("isMaterialMatch") or hit.get("isPep"))


# Поля, действительно подтверждающие ЛИЧНОСТЬ (а не контекст):
#   SFCT_191 — DOCUMENT_ID (ИИН/БИН),  SFCT_2 — DATE_OF_BIRTH.
# Совпадение по стране (SFCT_3 COUNTRY, SFCT_5 NATIONALITY, SFCT_6 REGISTERED_COUNTRY,
# SFCT_192 DOC_COUNTRY) НЕ подтверждает — для любого казахстанского лица оно тривиально
# истинно и не отличает однофамильца.
_IDENTITY_SF_FIELDS = {"SFCT_191", "SFCT_2"}


def _document_check(hit: dict) -> str | None:
    """'MATCHED'/'NOT_MATCHED' если сверялся документ/ДР (SFCT_191/SFCT_2), иначе None.

    Игнорирует совпадения только по стране — они не подтверждают личность.
    """
    result: str | None = None
    for r in hit.get("secondaryFieldResults") or []:
        if not isinstance(r, dict):
            continue
        if str(r.get("typeId") or "").upper() in _IDENTITY_SF_FIELDS:
            fr = str(r.get("fieldResult") or "").upper()
            if fr == "MATCHED":
                return "MATCHED"
            if fr == "NOT_MATCHED":
                result = "NOT_MATCHED"
    return result


def _verification(hit: dict) -> str:
    """CONFIRMED / UNVERIFIED / FALSE_POSITIVE — подтверждено ли это тот самый объект.

    Подтверждено = точное/сильное совпадение по имени ИЛИ сверка ДОКУМЕНТА (ИИН/БИН)
    либо даты рождения. Совпадение только по стране НЕ считается подтверждением.
    Среднее/слабое имя без сверки документа = неподтверждено (вероятный однофамилец).

    Намеренно НЕ доверяет сохранённым ``verificationStatus``/``sfResult`` — они
    засчитывали совпадение по стране за подтверждение (баг мэппера).
    """
    strength = str(hit.get("matchStrength") or "").upper()
    doc = _document_check(hit)
    if doc == "MATCHED" or strength in ("EXACT", "STRONG"):
        return "CONFIRMED"
    if doc == "NOT_MATCHED":
        return "FALSE_POSITIVE"
    return "UNVERIFIED"


def _is_confirmed(hit: dict) -> bool:
    return _verification(hit) == "CONFIRMED"


def _hidden_reason(hit: dict) -> str:
    """Короткое человекочитаемое «почему скрыто» для неподтверждённого совпадения."""
    strength = str(hit.get("matchStrength") or "").upper()
    sname = {"MEDIUM": "среднее", "WEAK": "слабое"}.get(strength, (strength.lower() or "неточное"))
    doc = _document_check(hit)
    if doc == "NOT_MATCHED":
        return f"{sname} совпадение по имени; документ (ИИН/БИН) НЕ совпал — другой объект"
    sfr = hit.get("secondaryFieldResults") or []
    had_country = any(
        str(r.get("typeId")) in ("SFCT_3", "SFCT_5", "SFCT_6")
        for r in sfr if isinstance(r, dict)
    )
    if had_country:
        return f"{sname} совпадение по имени; совпала только страна, ИИН/БИН в записи LSEG отсутствует — сверить нельзя"
    return f"{sname} совпадение по имени; документ (ИИН/БИН) не сверялся"


def build_sanctions_summary(enriched: dict[str, Any]) -> dict[str, Any]:
    """Deterministic compact structure (sync). ``reason`` is the fallback text."""
    lseg = enriched.get("lseg") or {}
    lseg_extended = enriched.get("lsegExtended") or {}

    # Собираем все материальные совпадения как (контекст, хит), затем делим на
    # подтверждённые (показываем) и неподтверждённые (вероятные однофамильцы — прячем).
    material_pairs: list[tuple[str, dict]] = []

    for hit in (lseg.get("sanctions") or {}).get("hits") or []:
        if isinstance(hit, dict) and _is_material(hit):
            material_pairs.append(("Компания (прямая проверка)", hit))

    for hit in (lseg.get("pep") or {}).get("individuals") or []:
        if isinstance(hit, dict) and _is_material(hit):
            material_pairs.append(("Руководитель / связанное физлицо", hit))

    coverage: list[dict] = []
    for key, entity in lseg_extended.items():
        if not isinstance(entity, dict):
            continue
        ent_name = str(entity.get("name") or key)
        flagged = [h for h in (entity.get("hits") or []) if isinstance(h, dict) and _is_material(h)]
        confirmed_flagged = [h for h in flagged if _is_confirmed(h)]
        if confirmed_flagged:
            status = "под санкциями / совпадение"
        elif flagged:
            status = "только слабое совпадение (не подтверждено)"
        else:
            status = "чисто"
        coverage.append({"name": ent_name, "role": str(entity.get("role") or ""), "status": status})
        ctx = f"Связанное лицо: {ent_name}"
        role = str(entity.get("role") or "").strip()
        if role:
            ctx += f" ({role})"
        for hit in flagged:
            material_pairs.append((ctx, hit))

    confirmed_pairs = [(c, h) for c, h in material_pairs if _is_confirmed(h)]
    unverified_pairs = [(c, h) for c, h in material_pairs if not _is_confirmed(h)]

    subjects = [_build_subject(h, context=c) for c, h in confirmed_pairs][:_MAX_SUBJECTS]

    # Скрытые слабые совпадения — НЕ удаляем молча, отдаём счётчик + имена (честность).
    hidden = []
    for c, h in unverified_pairs:
        name = str(h.get("primaryName") or h.get("submittedName") or "—")
        score = h.get("matchScore")
        hidden.append({
            "name": name,
            "score": f"{score:.0f}%" if isinstance(score, (int, float)) else "",
            "reason": _hidden_reason(h),
        })

    # fill deterministic fallback reason now (LLM may overwrite later)
    from app.services.reports.sanctions_narrative import _deterministic_fallback
    for s in subjects:
        s["reasonFallback"] = _deterministic_fallback(s)
        s["reason"] = s["reasonFallback"]

    return {
        "meta": {
            "company": str(lseg.get("screenedName") or enriched.get("companyName") or "—"),
            "iin": str(lseg.get("screenedIin") or enriched.get("iin") or ""),
            "screenedAt": _iso(lseg.get("screenedAt")),
            "source": "LSEG World-Check One",
            "subjectCount": len(subjects),
        },
        "hidden": hidden,
        "legend": [
            ("PEP", glossary.PEP_PLAIN),
            ("Среднее совпадение", "система нашла похожее имя, но не подтвердила его по документам (ИИН/БИН) — нужна ручная проверка"),
            ("Косвенные санкции", "лицо само не в списке, но связано/принадлежит тем, кто под санкциями (например, правило 50%)"),
            ("Правило 50%", "компания на 50% и более принадлежит лицу под санкциями — ограничения распространяются и на неё"),
        ],
        "subjects": subjects,
        "coverage": coverage,
    }


def build_sanctions_markdown(summary: dict[str, Any]) -> str:
    """Render the compact readable summary as markdown for the full report section."""
    subjects = summary.get("subjects") or []
    coverage = summary.get("coverage") or []
    hidden = summary.get("hidden") or []
    lines: list[str] = ["### Найденные факты\n"]

    if not subjects:
        lines.append("- Подтверждённых санкционных совпадений не обнаружено.")
    else:
        legend = "; ".join(f"**{t}** — {d}" for t, d in (summary.get("legend") or [])[:4])
        if legend:
            lines.append(f"> {legend}\n")
        for s in subjects:
            country = s.get("country") or ""
            head = s.get("matchedName", "—") + (f" ({country})" if country and country != "нет данных" else "")
            lines.append(f"#### {head}")
            lines.append(f"- **Связь:** {s.get('context', '—')}")
            conf = s.get("confidence", {})
            conf_line = conf.get("plain", "—") + (f" ({conf['score']})" if conf.get("score") else "")
            lines.append(f"- **Совпадение:** {conf_line}")
            if s.get("reason"):
                lines.append(f"- **За что:** {s['reason']}")
            lines.append(f"- **Кто ввёл:** {s.get('whoImposed', 'нет данных')}")
            if s.get("sanctionType"):
                lines.append(f"- **Тип:** {'; '.join(s['sanctionType'])}")
            lines.append(f"- **Когда:** {s.get('when', 'нет данных')}")
            lines.append("")

    if coverage:
        flagged = [c["name"] for c in coverage if "под санкциями" in c.get("status", "")]
        clean = [c["name"] for c in coverage if "под санкциями" not in c.get("status", "")]
        parts = []
        if flagged:
            parts.append("под санкциями/совпадение: " + ", ".join(flagged))
        if clean:
            parts.append("чисто: " + ", ".join(clean))
        if parts:
            lines.append("**Проверенные связанные лица:** " + " · ".join(parts))

    if hidden:
        lines.append(
            f"\n**Скрыто как вероятные однофамильцы (не подтверждено по документам): {len(hidden)}**"
        )
        for h in hidden[:10]:
            score = f" {h['score']}" if h.get("score") else ""
            lines.append(f"- _{h['name']}{score} — {h.get('reason', 'не подтверждено')}_")

    return "\n".join(lines).strip()


async def build_readable_summary(enriched: dict[str, Any]) -> dict[str, Any]:
    """Async: build the compact summary + plain-Russian ``reason`` via one LLM call."""
    summary = build_sanctions_summary(enriched)
    subjects = summary["subjects"]
    if subjects:
        narratives = await generate_sanction_narratives(subjects)
        for i, s in enumerate(subjects):
            text = narratives.get(i)
            if text:
                s["reason"] = text
    return summary
