from __future__ import annotations

import logging
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)
from app.services.adata.client import deep_find, info_has, run_parallel_checks
from app.services.adata.info_mapper import info_has_structured_blocks, map_info_data
from app.services.adata.client import _SANCTION_KEYS
from app.services.enrichment.base import BaseProvider, CompanyData
from app.services.enrichment.person import normalize_person_name
# Re-export for legacy audit routes that import from this module.
from app.services.adata.client import (  # noqa: F401
    AdataError,
    download_company_report,
)


class AdataProvider(BaseProvider):
    name = "adata"

    def is_available(self) -> bool:
        return bool(settings.adata_token.strip())

    def _deep_get(self, value: Any, keys: set[str] | frozenset[str]) -> Any:
        return deep_find(value, keys)

    def _info_data(self, raw: dict[str, Any]) -> dict[str, Any]:
        info_payload = raw.get("info", {})
        if not isinstance(info_payload, dict):
            return {}
        data = info_payload.get("data", info_payload)
        return data if isinstance(data, dict) else {}

    def _section_payload(
        self, raw: dict[str, Any], key: str, *, info_data: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Prefer nested block inside info, then dedicated fallback key."""
        info = info_data if info_data is not None else self._info_data(raw)
        if isinstance(info.get(key), dict):
            return info[key]
        dedicated = raw.get(key, {})
        if not isinstance(dedicated, dict):
            return {}
        return dedicated.get("data", dedicated) if isinstance(dedicated, dict) else {}

    def _parse_courtcase(self, courtcase_payload: dict[str, Any]) -> tuple[
        int | None,
        list[dict[str, Any]],
        dict[str, int],
        list[dict[str, Any]],
    ]:
        data = courtcase_payload.get("data")
        if not isinstance(data, dict):
            data = courtcase_payload if isinstance(courtcase_payload, dict) else {}

        if not data:
            return None, [], {}, []

        totals = {
            "civil": int(data.get("total_civil_count") or 0),
            "criminal": int(data.get("total_criminal_count") or 0),
            "administrative": int(data.get("total_administrative_count") or 0),
            "appk": int(data.get("total_appk_count") or 0),
        }
        total_count = sum(totals.values())

        years_raw = data.get("court_cases") or data.get("courtcases") or []
        years: list[dict[str, Any]] = []
        cases_for_ui: list[dict[str, Any]] = []

        for row in years_raw:
            if not isinstance(row, dict):
                continue
            year = str(row.get("year", ""))
            civil = int(row.get("civil_count") or 0)
            criminal = int(row.get("criminal_count") or 0)
            administrative = int(row.get("administrative_count") or 0)
            appk = int(row.get("appk_count") or 0)
            year_total = civil + criminal + administrative + appk
            years.append(
                {
                    "year": year,
                    "civil_count": civil,
                    "criminal_count": criminal,
                    "administrative_count": administrative,
                    "appk_count": appk,
                }
            )
            if year_total > 0:
                cases_for_ui.append(
                    {
                        "type": f"Сводка за {year}",
                        "amount": 0,
                        "date": year,
                        "status": (
                            f"Г:{civil} У:{criminal} А:{administrative} АППК:{appk}"
                        ),
                    }
                )

        active: int | None = total_count if total_count else None
        if years:
            recent = sorted(years, key=lambda y: y.get("year", ""), reverse=True)[:3]
            recent_sum = sum(
                y["civil_count"]
                + y["criminal_count"]
                + y["administrative_count"]
                + y["appk_count"]
                for y in recent
            )
            if recent_sum:
                active = recent_sum

        return active, years, totals, cases_for_ui

    def _parse_relation(
        self, relation_data: dict[str, Any]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        related: list[dict[str, Any]] = []
        founders: list[dict[str, Any]] = []

        for item in relation_data.get("affiliation_by_company") or []:
            if not isinstance(item, dict):
                continue
            related.append(
                {
                    "name": item.get("name", "—"),
                    "iinBin": item.get("bin") or item.get("bin_formatted", ""),
                    "role": item.get("type", "Связанная компания"),
                }
            )

        by_head = relation_data.get("affiliation_by_head") or {}
        if isinstance(by_head, dict):
            for item in by_head.get("companies") or []:
                if not isinstance(item, dict):
                    continue
                related.append(
                    {
                        "name": item.get("name", "—"),
                        "iinBin": item.get("bin") or item.get("bin_formatted", ""),
                        "role": f"Связь с руководителем ({by_head.get('head_name', '')})",
                    }
                )

        for founder_block in relation_data.get("affiliation_by_founder") or []:
            if not isinstance(founder_block, dict):
                continue
            founders.append(
                {
                    "name": founder_block.get("founder_name", "—"),
                    "iin": founder_block.get("founder_biin")
                    or founder_block.get("founder_biin_formatted", ""),
                    "role": "Учредитель",
                }
            )
            for item in founder_block.get("companies") or []:
                if not isinstance(item, dict):
                    continue
                related.append(
                    {
                        "name": item.get("name", "—"),
                        "iinBin": item.get("bin") or item.get("bin_formatted", ""),
                        "role": "Компания учредителя",
                    }
                )

        return related, founders

    def _court_from_info(self, info_data: dict[str, Any]) -> tuple[
        int | None,
        list[dict[str, Any]],
        dict[str, int],
        list[dict[str, Any]],
        bool,
    ]:
        nested = info_data.get("courtcase") or info_data.get("court_case")
        if isinstance(nested, dict):
            payload = {"data": nested} if "data" not in nested else nested
            active, years, totals, ui = self._parse_courtcase(payload)
            if active is not None or years:
                return active, years, totals, ui, True

        if info_has(info_data, frozenset({"court_cases", "courtcases"})):
            active, years, totals, ui = self._parse_courtcase({"data": info_data})
            if active is not None or years:
                return active, years, totals, ui, True

        count = self._deep_get(
            info_data,
            {"courtcases", "court_cases", "casescount", "cases_count", "total_civil_count"},
        )
        if count is not None:
            try:
                return int(count), [], {}, [], True
            except (TypeError, ValueError):
                pass
        return None, [], {}, [], False

    def _build_section_sources(
        self,
        raw: dict[str, Any],
        *,
        has_company: bool,
        has_tax: bool,
        has_courts: bool,
        courts_stub: bool,
        has_sanctions: bool,
        has_affiliates: bool,
    ) -> dict[str, str]:
        info_ok = isinstance(raw.get("info"), dict) and raw["info"].get("data") is not None

        def _from(endpoint_key: str, field_ok: bool) -> str:
            if field_ok and (
                info_ok
                or (
                    isinstance(raw.get(endpoint_key), dict)
                    and raw[endpoint_key].get("data") is not None
                    and not raw[endpoint_key].get("error")
                )
            ):
                return "adata"
            return "none"

        courts = "none" if courts_stub else _from("courtcase", has_courts)
        return {
            "companyInfo": _from("basic", has_company),
            "taxes": _from("riskfactor", has_tax),
            "courts": courts,
            "sanctions": _from("sanctions", has_sanctions),
            "affiliates": _from("relation", has_affiliates),
            "graph": _from("relation", has_affiliates),
            "assessment": "none",
            "conclusion": "none",
        }

    def _map_raw(self, iin: str, raw: dict[str, Any], company_name: str) -> CompanyData:
        info_data = self._info_data(raw)

        if info_data and info_has_structured_blocks(info_data):
            mapped = map_info_data(
                iin, info_data, company_name=company_name, raw=raw
            )
            company = CompanyData(**{k: mapped[k] for k in CompanyData.model_fields if k in mapped})
            company.section_sources = mapped["section_sources"]
            # Merge trustworthy-extended sanctions if present in fallbacks
            sanctions_data = self._section_payload(raw, "sanctions", info_data=info_data)
            if sanctions_data and self._deep_get(
                sanctions_data, {"sanction", "sanctions", "inlist", "matched"}
            ):
                company.in_sanctions_list = True
                company.section_sources["sanctions"] = "adata"
                raw["_section_sources"]["sanctions"] = "adata"
            return company

        search_roots = [info_data] if info_data else []

        basic_data = self._section_payload(raw, "basic", info_data=info_data)
        if basic_data:
            search_roots.append(basic_data)

        risk_inner = self._section_payload(raw, "riskfactor", info_data=info_data)
        if risk_inner:
            search_roots.append(risk_inner)

        def _pick(keys: set[str]) -> Any:
            for root in search_roots:
                found = self._deep_get(root, keys)
                if found not in (None, "", [], {}):
                    return found
            return None

        name = _pick(
            {
                "name",
                "name_ru",
                "short_name",
                "companyname",
                "organizationname",
                "full_name",
                "fullname",
                "fullnameru",
            }
        )
        director = None
        if basic_data:
            director = normalize_person_name(
                basic_data.get("fullname_director") or basic_data.get("director")
            )
        if not director and info_data:
            basic_block = info_data.get("basic")
            if isinstance(basic_block, dict):
                director = normalize_person_name(
                    basic_block.get("fullname_director") or basic_block.get("director")
                )
        if not director:
            director = normalize_person_name(
                _pick({"head_name", "directorname", "ceo", "manager", "head"})
            )
        status = _pick(
            {
                "status",
                "company_status",
                "company_status_name",
                "companystatus",
                "company_state",
                "active",
            }
        )
        address = _pick(
            {
                "address",
                "legal_addres",
                "legal_address",
                "legaladdress",
                "factaddress",
                "registeredaddress",
                "jur_address",
            }
        )
        registration_date = _pick(
            {"registration_date", "regdate", "date_reg", "registerdate", "reg_date"}
        )
        employees_raw = _pick({"employees", "employeescount", "employee_count", "workers"})
        industry = _pick({"industry", "oked", "activity", "activity_name", "main_activity"})

        tax_debt = _pick({"taxdebt", "tax_debt", "debt", "taxarrears", "tax_arrears"})
        risk_court_cases = _pick({"courtcases", "court_cases", "casescount", "cases_count"})

        court_active, court_years, court_totals, court_ui_cases, courts_from_info = (
            self._court_from_info(info_data)
        )
        courts_source = "adata" if courts_from_info else "none"

        courtcase_payload = raw.get("courtcase", {})
        if not courts_from_info and isinstance(courtcase_payload, dict):
            if courtcase_payload.get("data"):
                court_active, court_years, court_totals, court_ui_cases = self._parse_courtcase(
                    courtcase_payload
                )
                courts_source = "adata"
            elif courtcase_payload.get("error"):
                courts_source = "none"

        if court_active is None and risk_court_cases is not None:
            try:
                court_active = int(risk_court_cases)
                if courts_source == "none":
                    courts_source = "adata"
            except (TypeError, ValueError):
                pass

        sanctions_data = self._section_payload(
            raw, "trustworthy_extended", info_data=info_data
        ) or self._section_payload(raw, "sanctions", info_data=info_data)
        sanctions_from_info = bool(info_data and info_has(info_data, _SANCTION_KEYS))
        in_sanctions = bool(
            self._deep_get(sanctions_data, {"sanction", "sanctions", "inlist", "matched"})
        )
        if sanctions_from_info:
            flag = self._deep_get(
                info_data, {"sanction", "sanctions", "inlist", "matched", "in_sanctions_list"}
            )
            in_sanctions = bool(flag) if flag is not None else False

        relation_data = self._section_payload(raw, "relation", info_data=info_data)
        if not relation_data and info_data:
            diagram = info_data.get("connectedDiagram")
            if isinstance(diagram, dict):
                relation_data = diagram
            else:
                relation_data = {
                    k: info_data[k]
                    for k in (
                        "affiliation_by_company",
                        "affiliation_by_head",
                        "affiliation_by_founder",
                    )
                    if k in info_data
                }
        related, founders = self._parse_relation(relation_data)

        employees: int | None = None
        if employees_raw is not None:
            try:
                employees = int(employees_raw)
            except (TypeError, ValueError):
                pass

        raw["_courts_source"] = courts_source
        raw["_court_ui_cases"] = court_ui_cases
        raw["_court_totals"] = court_totals

        has_company = bool(name or director or status or address)
        has_tax = tax_debt is not None
        has_courts = courts_source == "adata" and (
            court_active is not None or bool(court_years)
        )
        has_sanctions = sanctions_from_info or bool(sanctions_data)
        has_affiliates = bool(related or founders)

        section_sources = self._build_section_sources(
            raw,
            has_company=has_company,
            has_tax=has_tax,
            has_courts=has_courts,
            courts_stub=courts_source == "none",
            has_sanctions=has_sanctions,
            has_affiliates=has_affiliates,
        )
        raw["_section_sources"] = section_sources

        company = CompanyData(
            iin=iin,
            name=str(name) if name else (company_name or None),
            status=str(status) if status else None,
            tax_debt=float(tax_debt) if tax_debt is not None else None,
            court_cases=court_active,
            court_cases_years=court_years,
            court_totals=court_totals,
            in_sanctions_list=in_sanctions,
            director=director,
            address=str(address) if address else None,
            registration_date=str(registration_date) if registration_date else None,
            employees=employees,
            industry=str(industry) if industry else None,
            founders=founders,
            related_companies=related,
            raw=raw,
        )
        company.section_sources = section_sources
        company.section_sources["courts"] = courts_source
        return company

    async def check(self, iin: str) -> CompanyData | None:
        if not self.is_available():
            return None
        try:
            raw = await run_parallel_checks(iin)
            info_ok = isinstance(raw.get("info"), dict) and raw["info"].get("data") is not None
            any_data = info_ok or any(
                isinstance(section, dict) and section.get("data") is not None
                for key, section in raw.items()
                if key != "info"
            )
            if not any_data:
                info_err = raw.get("info", {}).get("error") if isinstance(raw.get("info"), dict) else None
                logger.info(
                    "Adata returned no usable data for BIN %s%s",
                    iin,
                    f": {info_err}" if info_err else "",
                )
                return None
            return self._map_raw(iin, raw, "")
        except Exception as exc:
            logger.info("Adata enrichment failed for BIN %s: %s", iin, exc)
            if settings.suppress_enrichment_errors:
                return None
            raise
