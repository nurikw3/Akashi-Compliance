"""Render the full facts-only dossier (Adata + LSEG) to PDF — same style as the
sanctions summary. Reuses the sanctions card renderer and styling primitives.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fpdf import FPDF
from fpdf.enums import XPos, YPos

from app.services.reports.sanctions_pdf import (
    _INK, _MUTED, _RED, _AMBER,
    _p, _kv, _rule,
    render_sanctions_section,
)

_FONT_DIR = Path(__file__).parent / "fonts"
_HEADER_BG = (38, 50, 70)
_SUBLABEL = (90, 90, 90)


_LINK = (40, 90, 200)


def _section_label(pdf: FPDF, text: str) -> None:
    """Маленький под-заголовок внутри секции."""
    pdf.ln(0.8)
    pdf.set_x(pdf.l_margin)
    pdf.set_font("DejaVu", "B", 8.5)
    pdf.set_text_color(*_SUBLABEL)
    pdf.multi_cell(0, 4.6, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_text_color(*_INK)


def _link(pdf: FPDF, label: str, url: str, *, size: float = 7.6, indent: str = "") -> None:
    """Кликабельная ссылка: `label: url` (url синим, кликабелен)."""
    if not url:
        return
    pdf.set_x(pdf.l_margin)
    pdf.set_font("DejaVu", "B", size)
    pdf.set_text_color(*_MUTED)
    lbl = f"{indent}{label} "
    lw = pdf.get_string_width(lbl) + 1
    pdf.cell(lw, 4.3, lbl, new_x=XPos.RIGHT, new_y=YPos.TOP)
    pdf.set_font("DejaVu", "", size)
    pdf.set_text_color(*_LINK)
    pdf.multi_cell(0, 4.3, url, new_x=XPos.LMARGIN, new_y=YPos.NEXT, link=url)
    pdf.set_text_color(*_INK)


class _DossierPDF(FPDF):
    def footer(self) -> None:  # noqa: D401
        self.set_y(-13)
        self.set_font("DejaVu", "", 7)
        self.set_text_color(*_MUTED)
        self.cell(0, 6, f"Только факты из источников Adata + LSEG World-Check One.  Стр. {self.page_no()}", align="C")


def _new() -> _DossierPDF:
    pdf = _DossierPDF(orientation="P", unit="mm", format="A4")
    pdf.add_font("DejaVu", "", str(_FONT_DIR / "DejaVuSans.ttf"))
    pdf.add_font("DejaVu", "B", str(_FONT_DIR / "DejaVuSans-Bold.ttf"))
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.set_margins(16, 14, 16)
    return pdf


def _section_header(pdf: FPDF, text: str) -> None:
    pdf.ln(2)
    pdf.set_x(pdf.l_margin)
    pdf.set_fill_color(*_HEADER_BG)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("DejaVu", "B", 11)
    pdf.cell(0, 7.5, "  " + text, fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_text_color(*_INK)
    pdf.ln(2)


def _render_title(pdf: FPDF, company: dict) -> None:
    pdf.set_font("DejaVu", "B", 17)
    pdf.set_text_color(*_INK)
    pdf.multi_cell(0, 9, "Досье по контрагенту")
    pdf.ln(0.5)
    pdf.set_font("DejaVu", "B", 12)
    pdf.multi_cell(0, 6, company.get("fullName", "—"))
    sub = []
    if company.get("bin"):
        sub.append(f"БИН {company['bin']}")
    if company.get("operatingStatus"):
        sub.append(company["operatingStatus"])
    if sub:
        _p(pdf, " · ".join(sub), size=8.5, color=_MUTED)
    _rule(pdf)


def _render_company(pdf: FPDF, c: dict) -> None:
    _section_header(pdf, "РЕКВИЗИТЫ")
    if c.get("registrationDate"):
        _kv(pdf, "Регистрация:", c["registrationDate"])
    if c.get("legalForm"):
        _kv(pdf, "Форма:", c["legalForm"] + (f" · {c['ownership']}" if c.get("ownership") else ""))
    if c.get("industry"):
        _kv(pdf, "Деятельность:", c["industry"] + (f" · сотрудников: {c['employees']}" if c.get("employees") else ""))
    if c.get("director"):
        _kv(pdf, "Руководитель:", c["director"])
    if c.get("address"):
        _kv(pdf, "Адрес:", c["address"])
    if c.get("bank"):
        _kv(pdf, "Банк:", c["bank"] + (f" · БИК {c['bik']}" if c.get("bik") else ""), size=8.5)
    if c.get("iik"):
        _kv(pdf, "ИИК:", c["iik"], size=8.5)
    _link(pdf, "Источник (Adata):", c.get("sourceLink", ""))
    _link(pdf, "Карточка директора:", c.get("directorUrl", ""))


def _render_taxes(pdf: FPDF, t: dict) -> None:
    _section_header(pdf, "НАЛОГИ")
    _kv(pdf, "Статус:", t.get("status", "—"))
    _kv(pdf, "Задолженность:", t.get("debt", "—"))
    _kv(pdf, "Всего уплачено:", t.get("totalPaid", "—") + (f" (последний платёж: {t['lastPayment']})" if t.get("lastPayment") else ""))
    if t.get("yearlyPayments"):
        _section_label(pdf, "По годам")
        for y in t["yearlyPayments"]:
            _kv(pdf, f"{y['year']}:", y["amount"], size=8.6)


def _render_sanctions(pdf: FPDF, summary: dict) -> None:
    _section_header(pdf, "САНКЦИИ И PEP")
    render_sanctions_section(pdf, summary, with_legend=True)


def _render_courts(pdf: FPDF, courts: dict) -> None:
    _section_header(pdf, "СУДЕБНЫЕ ДЕЛА")
    counts = []
    if courts.get("activeCases") is not None:
        counts.append(f"активных: {courts['activeCases']}")
    if courts.get("completedCases") is not None:
        counts.append(f"завершённых: {courts['completedCases']}")
    counts.append(f"сумма исков: {courts.get('totalAmount', '0 ₸')}")
    _kv(pdf, "Итого:", " · ".join(counts))
    if courts.get("note"):
        _p(pdf, courts["note"], size=8.4, color=_MUTED)
    items = courts.get("items") or []
    if items:
        _section_label(pdf, f"Дела {courts.get('scope', 'компании')} (по-человечески)")
        for it in items:
            _render_court_case(pdf, it)


def _render_court_case(pdf: FPDF, it: dict, *, compact: bool = False) -> None:
    """Одно судебное дело по-человечески: о чём · роль (+расхождение) · итог."""
    sz = 8.0 if compact else 8.8
    _p(pdf, f"● {it.get('date', '')} · {it.get('title', 'дело')}", size=sz, bold=True)
    if it.get("about"):
        _kv(pdf, "О чём:", it["about"], size=sz - 0.4)
    if it.get("role"):
        disc = any(w in it["role"].lower() for w in ("но фактически", "но на деле", "противореч", "расхожд"))
        _kv(pdf, "Роль:", it["role"], size=sz - 0.4, value_color=(_AMBER if disc else _INK))
    if it.get("outcome"):
        _kv(pdf, "Чем закончилось:", it["outcome"], size=sz - 0.4)
    tail = []
    if it.get("amount"):
        tail.append(f"сумма: {it['amount']}")
    if it.get("number"):
        tail.append(f"№ {it['number']}")
    if it.get("court"):
        tail.append(it["court"])
    if tail:
        _p(pdf, "   " + " · ".join(tail), size=7.4, color=_MUTED, h=4.0)
    if it.get("docLink"):
        _link(pdf, "Документ дела:", it["docLink"], indent="   ")
    pdf.ln(0.8)


def _render_affiliate_block(pdf: FPDF, it: dict) -> None:
    """Подробный блок по одному аффилиату — как мини-карточка компании."""
    kind = it.get("kind", "")
    bin_part = f", БИН/ИИН {it['bin']}" if it.get("bin") else ""
    status = it.get("operatingStatus")
    head = f"▸ {it['name']} ({kind}{bin_part})" + (f" — {status}" if status else "")
    accent = _RED if "НАЙДЕНО" in (it.get("sanctionStatus") or "") else _INK
    pdf.ln(0.6)
    _p(pdf, head, size=9, bold=True, color=accent)

    _kv(pdf, "Санкции:", it.get("sanctionStatus", "—"), size=8.2,
        value_color=(_RED if "НАЙДЕНО" in (it.get("sanctionStatus") or "") else _INK))

    if not it.get("enriched"):
        _p(pdf, "   Подробные данные (налоги, суды) по этому лицу не проверялись.",
           size=7.8, color=_MUTED, h=4.0)
        return

    tx = it.get("taxes")
    if tx:
        _kv(pdf, "Налоги:", f"{tx['status']}; задолженность: {tx['debt']}; уплачено: {tx['totalPaid']}", size=8.2)

    cc = it.get("companyCourts")
    if cc is not None:
        if cc.get("hasCases") or (cc.get("active") or cc.get("completed")):
            _kv(pdf, "Суды компании:", f"активных {cc.get('active', 0)}, завершённых {cc.get('completed', 0)}, сумма {cc.get('totalAmount', '0 ₸')}", size=8.2)
        else:
            _kv(pdf, "Суды компании:", "судебных дел нет", size=8.2)

    director = it.get("director")
    dcourts = it.get("directorCourtItems") or []
    if director:
        if dcourts:
            _kv(pdf, "Директор:", f"{director} — судебных дел: {len(dcourts)}", size=8.2)
            for dc in dcourts:
                _render_court_case(pdf, dc, compact=True)
        else:
            _kv(pdf, "Директор:", f"{director} — судебных дел нет", size=8.2)

    _link(pdf, "Источник (Adata):", it.get("sourceUrl", ""))
    if it.get("directorUrl"):
        _link(pdf, "Карточка директора:", it["directorUrl"])


def _render_affiliates(pdf: FPDF, a: dict) -> None:
    _section_header(pdf, "АФФИЛИАТЫ И СВЯЗАННЫЕ ЛИЦА")
    if a.get("intro"):
        _p(pdf, a["intro"], size=8.4, color=_MUTED)
    _kv(pdf, "Всего:", f"компаний {a.get('companiesCount', 0)}, физлиц {a.get('individualsCount', 0)}; "
                        f"проверено в санкц. списках: {a.get('screenedCount', 0)}")
    if a.get("sanctioned"):
        _section_label(pdf, "Найдены совпадения в санкционных списках")
        for s in a["sanctioned"]:
            _p(pdf, f"● {s['name']}" + (f" — {s['role']}" if s.get("role") else ""), size=8.6, bold=True, color=_RED)

    detailed = a.get("detailed") or []
    if detailed:
        _section_label(pdf, "Подробно по каждому связанному лицу")
        for it in detailed:
            _render_affiliate_block(pdf, it)


def render_dossier_pdf(dossier: dict[str, Any]) -> bytes:
    pdf = _new()
    pdf.add_page()

    _render_title(pdf, dossier.get("company") or {})
    _render_company(pdf, dossier.get("company") or {})
    if dossier.get("taxes"):
        _render_taxes(pdf, dossier["taxes"])
    _render_sanctions(pdf, dossier.get("sanctions") or {})
    if dossier.get("courts"):
        _render_courts(pdf, dossier["courts"])
    _render_affiliates(pdf, dossier.get("affiliates") or {})

    return bytes(pdf.output())
