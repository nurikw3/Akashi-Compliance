from __future__ import annotations

from typing import Any

import httpx
import streamlit as st

from app.core.config import settings


st.set_page_config(page_title="Akashi Compliance", layout="wide")


def _request(method: str, path: str, **kwargs: Any) -> Any:
    url = f"{settings.api_base_url}{path}"
    with httpx.Client(timeout=120.0) as client:
        response = client.request(method, url, **kwargs)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            return response.json()
        return response.content


def _deep_search(value: Any, candidate_keys: set[str]) -> Any:
    if isinstance(value, dict):
        for key, nested_value in value.items():
            if key.lower() in candidate_keys:
                return nested_value
        for nested_value in value.values():
            found = _deep_search(nested_value, candidate_keys)
            if found not in (None, "", [], {}):
                return found
    elif isinstance(value, list):
        for nested_value in value:
            found = _deep_search(nested_value, candidate_keys)
            if found not in (None, "", [], {}):
                return found
    return None


def _show_status(status: str) -> None:
    color = "#1c7c1c" if status == "Совпадений не найдено" else "#b42318"
    st.markdown(
        f"""
        <div style="padding: 14px; border-radius: 10px; background: {color}; color: white; font-weight: 700;">
            {status}
        </div>
        """,
        unsafe_allow_html=True,
    )


def _show_audit(audit: dict[str, Any]) -> None:
    if audit.get("from_cache"):
        st.info("Показан исторический результат из кэша аудита.")
    else:
        st.success("Проверка выполнена через Adata и сохранена в историю.")

    _show_status(audit["status"])

    raw_result = audit["raw_result"]
    basic_payload = raw_result.get("basic", {})
    basic_data = basic_payload.get("data", basic_payload)

    company_name = _deep_search(
        basic_data,
        {
            "name",
            "name_ru",
            "short_name",
            "companyname",
            "organizationname",
            "full_name",
            "fullName",
        },
    )
    company_address = _deep_search(
        basic_data,
        {
            "address",
            "legal_addres",
            "legal_address",
            "legaladdress",
            "factaddress",
            "registeredaddress",
        },
    )
    company_status = _deep_search(
        basic_data,
        {
            "status",
            "company_status",
            "company_status_name",
            "companystatus",
            "active",
            "company_state",
        },
    )

    col1, col2, col3 = st.columns(3)
    col1.metric("Название", company_name or audit["organization_name"])
    col2.metric("Адрес", company_address or "Нет данных")
    col3.metric("Статус компании", company_status or "Нет данных")

    if audit["status"] == "Совпадения найдены":
        st.link_button(
            "Скачать отчёт",
            f"{settings.api_base_url}/api/audits/{audit['id']}/pdf",
            use_container_width=False,
        )

    st.subheader("Сырые ответы")
    with st.expander("basic", expanded=True):
        st.json(raw_result.get("basic", {}))
    with st.expander("riskfactor", expanded=True):
        st.json(raw_result.get("riskfactor", {}))
    with st.expander("trustworthy-extended", expanded=False):
        st.json(raw_result.get("trustworthy_extended", {}))


def _render_history() -> None:
    st.subheader("История проверок")
    try:
        history = _request("GET", "/api/audits/history")
    except httpx.HTTPError as exc:
        st.warning(f"Не удалось загрузить историю: {exc}")
        return

    if not history:
        st.caption("Пока нет сохраненных проверок.")
        return

    header = st.columns([2, 3, 2, 2, 2])
    header[0].markdown("**Дата**")
    header[1].markdown("**Название**")
    header[2].markdown("**БИН**")
    header[3].markdown("**Статус**")
    header[4].markdown("**Отчёт**")

    for item in history:
        row = st.columns([2, 3, 2, 2, 2])
        row[0].write(item["checked_at"])
        row[1].write(item["organization_name"])
        row[2].write(item["bin"])
        row[3].write(item["status"])
        if item["status"] == "Совпадения найдены":
            row[4].link_button(
                "Скачать PDF",
                f"{settings.api_base_url}/api/audits/{item['id']}/pdf",
                use_container_width=True,
            )
        else:
            row[4].caption("Не требуется")


st.title("Akashi Compliance")
st.caption("Поиск организации, кеш аудита, история проверок и локальный PDF-отчет.")

with st.form("audit-form"):
    organization_name = st.text_input("Название организации")
    bin_value = st.text_input("БИН", max_chars=12)
    submitted = st.form_submit_button("Запустить проверку")

if submitted:
    if not organization_name.strip() or not bin_value.strip():
        st.error("Заполните название организации и БИН.")
    else:
        try:
            with st.spinner("Выполняется проверка через кеш и Adata..."):
                st.session_state["latest_audit"] = _request(
                    "POST",
                    "/api/audits/run",
                    json={
                        "organization_name": organization_name,
                        "bin": bin_value,
                    },
                )
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text
            st.error(f"Backend вернул ошибку: {detail}")
        except httpx.HTTPError as exc:
            st.error(f"Не удалось связаться с backend: {exc}")

latest_audit = st.session_state.get("latest_audit")
if latest_audit:
    st.subheader("Результат проверки")
    _show_audit(latest_audit)

_render_history()
