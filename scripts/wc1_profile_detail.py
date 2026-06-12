"""Fetch full WC1 entity profiles for specific referenceIds.

Usage:
    uv run python scripts/wc1_profile_detail.py
"""
from __future__ import annotations
import asyncio, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.services.lseg.client import LsegClient

_BASE = "https://api.risk.lseg.com/screening/v3"

# референсы из предыдущего скрининга
TARGETS = [
    ("e_tr_wco_43690",  "BABBAR KHALSA INTERNATIONAL (sanctions hit #1)"),
    ("e_tr_wco_7201419","BABBAR KHALSA INTERNATIONAL (sanctions hit #2)"),
    ("e_tr_wco_7876732","B&K SA"),
    ("e_tr_wco_8913230","BK"),
    ("e_tr_wco_9166842","ООО BRILLIANT КОНСАЛТИНГ"),
    ("e_tr_wco_815547", "KAVEH CUTTING TOOLS COMPANY"),
    ("e_tr_wci_6510867","Arman NURUSHEV (PEP INACTIVE)"),
    ("e_tr_wci_6166836","Arman ZAINUDDIN (PEP ACTIVE)"),
]


def _v(*path, obj, default="—"):
    for k in path:
        if not isinstance(obj, dict): return default
        obj = obj.get(k, default)
    return obj if obj not in (None, "", [], {}) else default


def _names(names_col) -> dict:
    if not isinstance(names_col, dict): return {}
    buckets = {}
    for n in names_col.get("nameDetails", []):
        t = n.get("type", "?")
        for d in n.get("details", []):
            if d.get("type") == "FULL_NAME" and d.get("value"):
                buckets.setdefault(t, []).append(d["value"])
    return buckets


def _dates(dates_col) -> dict:
    if not isinstance(dates_col, dict): return {}
    out = {}
    for d in dates_col.get("dateDetails", []):
        if d.get("value"):
            out[d.get("type","?")] = d["value"]
    return out


def _locs(locs_col) -> dict:
    if not isinstance(locs_col, dict): return {}
    out = {}
    for ld in locs_col.get("locationDetails", []):
        t = ld.get("type","?")
        c = _v("name", obj=ld.get("country",{}))
        region = next((d["value"] for d in ld.get("details",[]) if d.get("type")=="REGION" and d.get("value")), None)
        label = f"{region}, {c}" if region and c != "—" else (c or region or "—")
        out.setdefault(t, []).append(label)
    return out


def _ids(ids_col) -> list:
    if not isinstance(ids_col, dict): return []
    out = []
    for d in ids_col.get("identificationDetails", []):
        out.append({
            "type": d.get("type"),
            "name": d.get("name"),
            "value": d.get("value"),
            "country": _v("name", obj=d.get("issuingCountry",{})),
        })
    return out


def _fi(fi_obj) -> list:
    if not isinstance(fi_obj, dict): return []
    return [
        {"title": d.get("title"), "type": d.get("detailType"), "text": d.get("text")}
        for d in fi_obj.get("details", []) if d.get("text")
    ]


def _sources(sources_list) -> list:
    if not isinstance(sources_list, list): return []
    out = []
    for s in sources_list:
        if not isinstance(s, dict): continue
        name = s.get("name") or s.get("abbreviation") or s.get("identifier") or str(s)
        cat  = _v("category","name", obj=s.get("type",{}))
        status = s.get("providerSourceStatus","")
        label = name
        if cat and cat != "—": label += f"  [{cat}]"
        if status: label += f"  ({status})"
        out.append(label)
    return out


def _connections(conns_col) -> list:
    if not isinstance(conns_col, dict): return []
    out = []
    for a in conns_col.get("associates", []):
        if not isinstance(a, dict): continue
        n = a.get("name") or _v("nameDetails",0,"details",0,"value", obj=a)
        out.append(f"{n}  [{a.get('type','')}]  ({'ACTIVE' if a.get('isActive') else 'inactive'})")
    return out


def _record_dates(rdates) -> dict:
    if not isinstance(rdates, list): return {}
    return {d.get("type","?"): d.get("value","") for d in rdates if d.get("value")}


def print_profile(ref_id: str, label: str, profile: dict) -> None:
    W = 72
    print(f"\n{'█'*W}")
    print(f"  {label}")
    print(f"  ref: {ref_id}")
    print(f"{'█'*W}")

    sep = "─"*W

    # ── record-level dates
    rdates = _record_dates(profile.get("recordDates", []))
    if rdates:
        print(f"\n  КОГДА (даты записи в WC)")
        print(f"  {sep}")
        labels = {
            "INITIAL_PUBLISHED_DATE": "Впервые внесён в базу WC",
            "LAST_PUBLISHED_DATE":    "Последнее обновление в WC",
        }
        for k, v in rdates.items():
            print(f"  {labels.get(k, k)}: {v}")

    # ── names
    name_buckets = _names(profile.get("names", {}))
    if name_buckets:
        print(f"\n  КТО (Имена)")
        print(f"  {sep}")
        lmap = {
            "PRIMARY":"Основное","AKA":"AKA","AKAENHANCED":"AKA+",
            "FKA":"FKA","DBA":"DBA","LANG_VARIATION":"Транслитерация",
            "NATIVE_AKA":"Родной алфавит","PREVIOUS":"Прежнее",
        }
        for t, vals in name_buckets.items():
            for v in vals:
                print(f"  [{lmap.get(t,t)}]  {v}")

    # ── entity dates (birth/death etc)
    edates = _dates(profile.get("dates", {}))
    if edates:
        print(f"\n  КОГДА (даты сущности)")
        print(f"  {sep}")
        for k,v in edates.items():
            print(f"  {k}: {v}")

    # ── geography
    locs = _locs(profile.get("locations", {}))
    if locs:
        print(f"\n  ГДЕ (Локации)")
        print(f"  {sep}")
        lmap2 = {
            "CITIZENSHIP":"Гражданство","COUNTRY_OF_RESIDENCE":"Страна проживания",
            "PLACE_OF_BIRTH":"Место рождения","REGISTEREDIN":"Страна регистрации",
            "VESSEL_FLAG":"Флаг","LOCATION":"Локация",
        }
        for t, vals in locs.items():
            for v in vals:
                print(f"  [{lmap2.get(t,t)}]  {v}")

    # ── identifications (санкционные номера и документы)
    ids = _ids(profile.get("identifications", {}))
    if ids:
        print(f"\n  ЧТО (Санкционные номера / Документы)")
        print(f"  {sep}")
        for d in ids:
            print(f"  [{d['type']}] {d['value']}  —  {d['name']}  (страна: {d['country']})")

    # ── sources (кто внёс / список)
    raw_sources = profile.get("sources", [])
    src_labels = _sources(raw_sources)
    if src_labels:
        print(f"\n  ЧТО (Источники / Санкционные списки)")
        print(f"  {sep}")
        for s in src_labels:
            print(f"  • {s}")

    # ── further information
    fi = _fi(profile.get("furtherInformation", {}))
    if fi:
        print(f"\n  FURTHER INFORMATION (комментарии аналитиков LSEG)")
        print(f"  {sep}")
        for item in fi:
            if item.get("title"):
                print(f"  ▶ {item['title']}  [{item.get('type','')}]")
            text = item.get("text","")
            # wrap at 68 chars
            line = "  "
            for word in text.split():
                if len(line)+len(word)+1 > 70:
                    print(line)
                    line = "  "+word+" "
                else:
                    line += word+" "
            if line.strip():
                print(line)

    # ── connections
    conns = _connections(profile.get("connections", {}))
    if conns:
        print(f"\n  СВЯЗИ (Connections)")
        print(f"  {sep}")
        for c in conns[:20]:
            print(f"  • {c}")

    # ── source reference links
    srl = profile.get("sourceReferenceLinks", {})
    if isinstance(srl, dict):
        links = srl.get("referenceLinks", [])
        if links:
            print(f"\n  ПЕРВОИСТОЧНИКИ (ссылки)")
            print(f"  {sep}")
            for lnk in links[:10]:
                print(f"  • {lnk.get('title','—')}  →  {lnk.get('url','—')}")


async def main():
    client = LsegClient()

    for ref_id, label in TARGETS:
        print(f"\n⟶ Загружаю профиль {ref_id} ({label})...")
        try:
            url = f"{_BASE}/references/records/{ref_id}"
            profile = await client._request("GET", url)
        except Exception as exc:
            print(f"   Ошибка: {exc}")
            continue

        print_profile(ref_id, label, profile)

        # raw dump для отладки (первые 1000 символов)
        raw_str = json.dumps(profile, ensure_ascii=False, indent=2)
        if len(raw_str) > 1200:
            raw_str = raw_str[:1200] + "\n... [обрезан]"
        print(f"\n  RAW (фрагмент):\n{raw_str}")


if __name__ == "__main__":
    asyncio.run(main())
