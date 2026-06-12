"""Ad-hoc WC1 deep screening script.

Usage:
    uv run python scripts/wc1_deep_screen.py 220840001616
"""
from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

# ── bootstrap project imports ─────────────────────────────────────────────────
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.lseg.client import LsegClient
from app.services.adata.client import run_parallel_checks


# ── helpers ───────────────────────────────────────────────────────────────────

def _val(obj: Any, *keys: str, default: Any = None) -> Any:
    for k in keys:
        if not isinstance(obj, dict):
            return default
        obj = obj.get(k, default)
    return obj


def _names_of_type(names: list[dict], name_type: str) -> list[str]:
    out = []
    for n in names:
        if n.get("type") != name_type:
            continue
        for d in n.get("details", []):
            if d.get("type") == "FULL_NAME":
                out.append(d.get("value", ""))
    return [v for v in out if v]


def _all_full_names(names: list[dict]) -> dict[str, list[str]]:
    buckets: dict[str, list[str]] = {}
    for n in names:
        ntype = n.get("type", "?")
        for d in n.get("details", []):
            if d.get("type") == "FULL_NAME" and d.get("value"):
                buckets.setdefault(ntype, []).append(d["value"])
    return buckets


def _locations(loc_details: list[dict]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for ld in loc_details:
        ltype = ld.get("type", "?")
        country = _val(ld, "country", "name")
        region = next(
            (d.get("value") for d in ld.get("details", []) if d.get("type") == "REGION"),
            None,
        )
        label = country or ""
        if region:
            label = f"{region}, {label}" if label else region
        if label:
            out.setdefault(ltype, []).append(label)
    return out


def _dates(date_details: list[dict]) -> dict[str, str]:
    return {
        d.get("type", "?"): d.get("value", "")
        for d in date_details
        if d.get("value")
    }


def _identifications(id_details: list[dict]) -> list[dict]:
    out = []
    for d in id_details:
        out.append({
            "type": d.get("type"),
            "value": d.get("value"),
            "issuer": d.get("issuer"),
            "country": _val(d, "issuingCountry", "name"),
            "issued": d.get("issueDate"),
            "expires": d.get("expiryDate"),
        })
    return out


def _further_info(fi: dict) -> list[dict]:
    return [
        {
            "title": d.get("title"),
            "type": d.get("detailType"),
            "text": d.get("text"),
        }
        for d in fi.get("details", [])
        if d.get("text")
    ]


def _source_categories(result: dict) -> list[str]:
    return result.get("sourceCategories", [])


def print_hit(idx: int, result: dict) -> None:
    sep = "─" * 70
    print(f"\n{'═' * 70}")
    print(f"  СОВПАДЕНИЕ #{idx + 1}")
    print(f"{'═' * 70}")

    # ── Match metadata
    print(f"  Match score:    {result.get('matchScore', '—')}")
    print(f"  Match strength: {result.get('matchStrength', '—')}")
    print(f"  Категории:      {', '.join(_source_categories(result)) or '—'}")
    print(f"  Тип записи:     {result.get('recordType', '—')}")
    print(f"  PEP статус:     {result.get('pepStatus', '—')}")
    print(f"  Reference ID:   {result.get('referenceId', '—')}")

    # ── Timestamps
    print(f"\n  {sep}")
    print("  КОГДА (Временные метки)")
    print(f"  {sep}")
    print(f"  Создана в WC:   {result.get('creationDate', '—')}")
    print(f"  Изменена в WC:  {result.get('modificationDate', '—')}")
    print(f"  Последний алерт:{result.get('lastAlertDate', '—')}")
    dates = _dates(_val(result, "dates", "dateDetails", default=[]))
    for dtype, dval in dates.items():
        print(f"  {dtype}: {dval}")

    # ── КТО — Names
    names_raw = result.get("names", [])
    name_buckets = _all_full_names(names_raw)
    print(f"\n  {sep}")
    print("  КТО (Имена и алиасы)")
    print(f"  {sep}")
    for ntype, nvals in name_buckets.items():
        label = {
            "PRIMARY": "Основное имя",
            "AKA": "Также известен как (AKA)",
            "AKAENHANCED": "AKA (расширенный)",
            "FKA": "Ранее известен как (FKA)",
            "DBA": "Торговое наименование (DBA)",
            "LANG_VARIATION": "Языковой вариант",
            "NATIVE_AKA": "Имя на родном языке",
            "PREVIOUS": "Прежнее имя",
        }.get(ntype, ntype)
        for v in nvals:
            print(f"  [{label}] {v}")

    # ── ГДЕ — Locations
    loc_details = _val(result, "locations", "locationDetails", default=[])
    locs = _locations(loc_details)
    if locs:
        print(f"\n  {sep}")
        print("  ГДЕ (Географическая привязка)")
        print(f"  {sep}")
        type_labels = {
            "CITIZENSHIP": "Гражданство",
            "COUNTRY_OF_RESIDENCE": "Страна проживания",
            "PLACE_OF_BIRTH": "Место рождения",
            "REGISTERED_IN": "Страна регистрации",
            "VESSEL_FLAG": "Флаг судна",
        }
        for ltype, lvals in locs.items():
            label = type_labels.get(ltype, ltype)
            for v in lvals:
                print(f"  [{label}] {v}")

    # ── Документы
    id_details = _val(result, "identifications", "identificationDetails", default=[])
    idents = _identifications(id_details)
    if idents:
        print(f"\n  {sep}")
        print("  ДОКУМЕНТЫ (Идентификаторы)")
        print(f"  {sep}")
        for doc in idents:
            parts = [f"[{doc['type']}] {doc['value'] or '—'}"]
            if doc.get("country"):
                parts.append(f"страна выдачи: {doc['country']}")
            if doc.get("issuer"):
                parts.append(f"орган: {doc['issuer']}")
            if doc.get("issued"):
                parts.append(f"выдан: {doc['issued']}")
            if doc.get("expires"):
                parts.append(f"действует до: {doc['expires']}")
            print(f"  {' | '.join(parts)}")

    # ── Further Information
    fi_raw = result.get("furtherInformation", {})
    fi_items = _further_info(fi_raw) if isinstance(fi_raw, dict) else []
    if fi_items:
        print(f"\n  {sep}")
        print("  FURTHER INFORMATION (Аналитический комментарий LSEG)")
        print(f"  {sep}")
        for item in fi_items:
            if item.get("title"):
                print(f"  Заголовок: {item['title']}  [{item.get('type', '')}]")
            # word-wrap text at ~65 chars
            text = item.get("text", "")
            words = text.split()
            line = "  "
            for word in words:
                if len(line) + len(word) + 1 > 70:
                    print(line)
                    line = "  " + word + " "
                else:
                    line += word + " "
            if line.strip():
                print(line)


async def main(bin_iin: str) -> None:
    print(f"\n{'█' * 70}")
    print(f"  WC1 ГЛУБОКИЙ СКРИНИНГ: {bin_iin}")
    print(f"{'█' * 70}\n")

    # ── Step 1: Adata — получить имя компании
    print("⟶ Шаг 1: Adata — обогащение по BIN...")
    company_name = ""
    director_name = ""
    try:
        raw = await run_parallel_checks(bin_iin)
        info_data = {}
        if isinstance(raw.get("info"), dict):
            info_data = raw["info"].get("data", {}) or {}
        basic_data = info_data.get("basic") or raw.get("basic", {}) or {}
        if isinstance(basic_data, dict):
            basic_data = basic_data.get("data", basic_data) or basic_data

        for key in ("name", "name_ru", "short_name", "fullname", "organizationname"):
            val = basic_data.get(key) or info_data.get(key)
            if val and isinstance(val, str) and val.strip():
                company_name = val.strip()
                break

        for key in ("fullname_director", "director", "head_name"):
            val = basic_data.get(key) or info_data.get(key)
            if val and isinstance(val, str) and val.strip():
                director_name = val.strip()
                break

        print(f"   Название компании: {company_name or '(не найдено)'}")
        print(f"   Директор:          {director_name or '(не найдено)'}")
    except Exception as exc:
        print(f"   Adata ошибка: {exc}")

    if not company_name:
        print("   Adata не вернул имя — скрининг будет по BIN-строке")
        company_name = bin_iin

    # ── Step 2: WC1 — скрининг организации
    client = LsegClient()

    # ── Build secondaryFields for KZ org (SFCT_193 omitted — causes 400 on WC1)
    org_secondary: list[dict] = [
        {"typeId": "SFCT_6",   "value": "KAZ"},       # REGISTERED_COUNTRY
        {"typeId": "SFCT_191", "value": bin_iin},      # DOCUMENT_ID = BIN
        {"typeId": "SFCT_192", "value": "KAZ"},        # DOCUMENT_ID_COUNTRY
    ]

    print(f"\n⟶ Шаг 2: WC1 — скрининг ORGANISATION [{company_name}] (+ BIN secondaryFields)...")
    try:
        case_resp = await client.screen_sync(company_name, "ORGANISATION", org_secondary)
        case_id = case_resp.get("caseSystemId", "")
        print(f"   case_system_id: {case_id}")
    except Exception as exc:
        print(f"   Ошибка screen_sync: {exc}")
        return

    results_data: dict = {}
    if case_id:
        print(f"\n⟶ Шаг 3: WC1 — получение результатов...")
        try:
            results_data = await client.get_results(case_id)
        except Exception as exc:
            print(f"   Ошибка get_results: {exc}")

    results: list[dict] = results_data.get("results", [])
    total = results_data.get("resultsCount", len(results))
    print(f"   Всего совпадений: {total}")

    # ── Step 3 (optional): screen director
    director_results: list[dict] = []
    if director_name:
        ind_secondary: list[dict] = [
            {"typeId": "SFCT_5", "value": "KAZ"},  # NATIONALITY
            {"typeId": "SFCT_3", "value": "KAZ"},  # COUNTRY_LOCATION
        ]
        print(f"\n⟶ Шаг 4: WC1 — скрининг INDIVIDUAL [{director_name}] (+ NATIONALITY=KAZ)...")
        try:
            dir_case = await client.screen_sync(director_name, "INDIVIDUAL", ind_secondary)
            dir_case_id = dir_case.get("caseSystemId", "")
            if dir_case_id:
                dir_res = await client.get_results(dir_case_id)
                director_results = dir_res.get("results", [])
                print(f"   Совпадений по директору: {len(director_results)}")
        except Exception as exc:
            print(f"   Ошибка скрининга директора: {exc}")

    # ── Print company hits
    if not results:
        print("\n  Совпадений по организации не найдено.")
    else:
        print(f"\n{'█' * 70}")
        print(f"  РЕЗУЛЬТАТЫ — ОРГАНИЗАЦИЯ ({len(results)} совпадений)")
        print(f"{'█' * 70}")
        for i, r in enumerate(results):
            print_hit(i, r)

    # ── Print director hits
    if director_results:
        print(f"\n{'█' * 70}")
        print(f"  РЕЗУЛЬТАТЫ — ДИРЕКТОР ({len(director_results)} совпадений)")
        print(f"{'█' * 70}")
        for i, r in enumerate(director_results):
            print_hit(i, r)

    # ── Raw dump (trimmed)
    print(f"\n{'█' * 70}")
    print("  RAW JSON (первые 5 результатов, обрезан до 8000 символов)")
    print(f"{'█' * 70}")
    dump = json.dumps(results[:5], ensure_ascii=False, indent=2)
    print(dump[:8000])
    if len(dump) > 8000:
        print("... [обрезан]")


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "220840001616"
    asyncio.run(main(target))
