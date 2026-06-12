"""Render the COMPACT plain-Russian sanctions summary to PDF (fpdf2 + DejaVuSans).

One short card per entity, every term decoded. No verdicts/recommendations.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fpdf import FPDF
from fpdf.enums import XPos, YPos

_FONT_DIR = Path(__file__).parent / "fonts"
_INK = (33, 33, 33)
_MUTED = (110, 110, 110)
_RULE = (220, 220, 220)
_RED = (150, 30, 30)
_AMBER = (150, 100, 10)
_BAND = (245, 245, 247)
_LEGEND_BG = (247, 249, 252)


class _PDF(FPDF):
    def footer(self) -> None:  # noqa: D401
        self.set_y(-13)
        self.set_font("DejaVu", "", 7)
        self.set_text_color(*_MUTED)
        self.cell(0, 6, f"Только факты из источников LSEG World-Check One.  Стр. {self.page_no()}", align="C")


def _new_pdf() -> _PDF:
    pdf = _PDF(orientation="P", unit="mm", format="A4")
    pdf.add_font("DejaVu", "", str(_FONT_DIR / "DejaVuSans.ttf"))
    pdf.add_font("DejaVu", "B", str(_FONT_DIR / "DejaVuSans-Bold.ttf"))
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.set_margins(16, 14, 16)
    return pdf


def _p(pdf: FPDF, text: str, *, size: float = 9, bold: bool = False,
       color: tuple = _INK, h: float = 4.6) -> None:
    pdf.set_x(pdf.l_margin)
    pdf.set_font("DejaVu", "B" if bold else "", size)
    pdf.set_text_color(*color)
    pdf.multi_cell(0, h, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)


def _kv(pdf: FPDF, label: str, value: str, *, size: float = 9,
        value_color: tuple = _INK) -> None:
    pdf.set_x(pdf.l_margin)
    pdf.set_font("DejaVu", "B", size)
    pdf.set_text_color(*_INK)
    lw = pdf.get_string_width(label + " ") + 1
    pdf.cell(lw, 4.8, label, new_x=XPos.RIGHT, new_y=YPos.TOP)
    pdf.set_font("DejaVu", "", size)
    pdf.set_text_color(*value_color)
    pdf.multi_cell(0, 4.8, value, new_x=XPos.LMARGIN, new_y=YPos.NEXT)


def _rule(pdf: FPDF) -> None:
    pdf.ln(1.5)
    pdf.set_draw_color(*_RULE)
    pdf.set_line_width(0.2)
    y = pdf.get_y()
    pdf.line(pdf.l_margin, y, pdf.w - pdf.r_margin, y)
    pdf.ln(2.5)


def _render_meta(pdf: FPDF, meta: dict[str, Any]) -> None:
    pdf.set_font("DejaVu", "B", 17)
    pdf.set_text_color(*_INK)
    pdf.multi_cell(0, 9, "Санкционная проверка")
    pdf.ln(0.5)
    _kv(pdf, "Контрагент:", meta.get("company") or "—", size=10.5)
    line = []
    if meta.get("iin"):
        line.append(f"БИН/ИИН {meta['iin']}")
    if meta.get("screenedAt"):
        line.append(f"проверка {meta['screenedAt']}")
    line.append(meta.get("source") or "LSEG World-Check One")
    _p(pdf, " · ".join(line), size=8.5, color=_MUTED)


def _render_legend(pdf: FPDF, legend: list) -> None:
    if not legend:
        return
    pdf.ln(1)
    x0, y0 = pdf.l_margin, pdf.get_y()
    pdf.set_fill_color(*_LEGEND_BG)
    pdf.set_font("DejaVu", "B", 8.5)
    pdf.set_text_color(*_INK)
    pdf.set_x(x0 + 2)
    pdf.multi_cell(pdf.epw - 4, 5, "Пояснение терминов", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    for term, desc in legend:
        pdf.set_x(x0 + 2)
        pdf.set_font("DejaVu", "B", 8)
        pdf.set_text_color(*_INK)
        lw = pdf.get_string_width(term + " — ") + 1
        pdf.cell(lw, 4.4, f"{term} — ", new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.set_font("DejaVu", "", 8)
        pdf.set_text_color(*_MUTED)
        pdf.multi_cell(pdf.epw - 4 - lw, 4.4, desc, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    y1 = pdf.get_y()
    pdf.set_draw_color(225, 230, 238)
    pdf.set_line_width(0.2)
    pdf.rect(x0, y0 - 1, pdf.epw, y1 - y0 + 2)
    pdf.ln(3)


def _render_subject(pdf: FPDF, idx: int, s: dict[str, Any]) -> None:
    is_sanction = s.get("isSanction")
    accent = _RED if is_sanction else _AMBER
    dot = "●"

    # header band: marker + name + country
    pdf.set_fill_color(*_BAND)
    pdf.set_x(pdf.l_margin)
    pdf.set_font("DejaVu", "B", 10.5)
    pdf.set_text_color(*accent)
    name = s.get("matchedName", "—")
    country = s.get("country") or ""
    head = f"{dot} {idx}. {name}" + (f"  ({country})" if country and country != "нет данных" else "")
    pdf.multi_cell(0, 6.6, head, fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(0.8)

    _kv(pdf, "Связь:", s.get("context", "—"), size=8.8, value_color=_MUTED)

    conf = s.get("confidence", {})
    conf_line = conf.get("plain", "—")
    if conf.get("score"):
        conf_line += f" ({conf['score']})"
    _kv(pdf, "Совпадение:", conf_line)
    if conf.get("note"):
        _p(pdf, conf["note"], size=8, color=_AMBER, h=4.2)

    # ── ПОЧЕМУ (центральное, простым языком)
    if s.get("reason"):
        _kv(pdf, "За что:", s["reason"])

    # ── КТО ВВЁЛ
    _kv(pdf, "Кто ввёл:", s.get("whoImposed", "нет данных"))

    # ── ТИП
    types = s.get("sanctionType") or []
    if types:
        _kv(pdf, "Тип:", "; ".join(types))

    # ── КОГДА
    _kv(pdf, "Когда:", s.get("when", "нет данных"))

    # ── идентификаторы (узнаваемые, 1-3)
    if s.get("keyRefs"):
        _kv(pdf, "Идентификаторы:", "; ".join(s["keyRefs"]), size=8.4, value_color=_MUTED)

    # ── первоисточники (ссылки на официальные документы)
    for src in (s.get("sources") or [])[:3]:
        url = src.get("url") if isinstance(src, dict) else None
        if not url:
            continue
        pdf.set_x(pdf.l_margin)
        pdf.set_font("DejaVu", "B", 7.6)
        pdf.set_text_color(*_MUTED)
        lbl = "Первоисточник "
        pdf.cell(pdf.get_string_width(lbl) + 1, 4.3, lbl, new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.set_font("DejaVu", "", 7.6)
        pdf.set_text_color(40, 90, 200)
        pdf.multi_cell(0, 4.3, str(url), new_x=XPos.LMARGIN, new_y=YPos.NEXT, link=str(url))
        pdf.set_text_color(*_INK)

    _rule(pdf)


def _render_coverage(pdf: FPDF, coverage: list[dict]) -> None:
    if not coverage:
        return
    pdf.set_font("DejaVu", "B", 10)
    pdf.set_text_color(*_INK)
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(0, 5.5, "Проверенные связанные лица", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(0.5)
    for c in coverage:
        flagged = "под санкциями" in c.get("status", "")
        marker = "●" if flagged else "○"
        meta = ", ".join(p for p in (c.get("role"),) if p)
        line = f"{marker} {c.get('name', '—')}" + (f" ({meta})" if meta else "") + f" — {c.get('status', '—')}"
        _p(pdf, line, size=8.4, color=(_RED if flagged else _MUTED))


def render_sanctions_section(pdf: FPDF, summary: dict[str, Any], *, with_legend: bool = True) -> None:
    """Render the sanctions body (legend + cards + coverage + hidden) onto an existing PDF.

    Reused by both the standalone sanctions PDF and the full dossier PDF.
    """
    if with_legend:
        _render_legend(pdf, summary.get("legend") or [])
        _rule(pdf)

    subjects = summary.get("subjects") or []
    if not subjects:
        _p(pdf, "Подтверждённых санкционных совпадений не обнаружено.", size=10)
    else:
        for i, s in enumerate(subjects, start=1):
            _render_subject(pdf, i, s)

    _render_coverage(pdf, summary.get("coverage") or [])

    hidden = summary.get("hidden") or []
    if hidden:
        pdf.ln(2)
        _p(pdf,
           f"Скрыто как вероятные однофамильцы (не подтверждено по документам): {len(hidden)}",
           size=8.2, bold=True, color=_MUTED, h=4.2)
        for h in hidden[:10]:
            score = f" {h['score']}" if h.get("score") else ""
            _p(pdf, f"○ {h['name']}{score} — {h.get('reason', 'не подтверждено')}",
               size=7.8, color=_MUTED, h=4.0)


def render_sanctions_pdf(summary: dict[str, Any]) -> bytes:
    pdf = _new_pdf()
    pdf.add_page()
    _render_meta(pdf, summary.get("meta", {}))
    render_sanctions_section(pdf, summary)
    return bytes(pdf.output())
