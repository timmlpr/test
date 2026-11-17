"""PDF rendering with reportlab (letters and reports)."""
from __future__ import annotations

import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.core.clock import utcnow
from app.settings import brand

_styles = getSampleStyleSheet()
BODY = ParagraphStyle("body", parent=_styles["BodyText"], fontName="Helvetica", fontSize=10.5, leading=15)
SMALL = ParagraphStyle("small", parent=BODY, fontSize=8.5, textColor=colors.HexColor("#555555"))
H1 = ParagraphStyle("h1", parent=_styles["Heading1"], fontName="Helvetica-Bold", fontSize=18, textColor=colors.HexColor("#1e3a8a"))
H2 = ParagraphStyle("h2", parent=_styles["Heading2"], fontName="Helvetica-Bold", fontSize=13, textColor=colors.HexColor("#1e3a8a"))


def _esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#777777"))
    canvas.drawString(20 * mm, 12 * mm, f"{brand()['name']} · {utcnow():%d.%m.%Y} · Seite {doc.page}")
    canvas.restoreState()


def letter_pdf(subject: str, body: str, disclaimer: str) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=25 * mm, rightMargin=20 * mm, topMargin=25 * mm, bottomMargin=20 * mm,
                            title=subject)
    story = [Paragraph(f"<b>{_esc(subject)}</b>", BODY), Spacer(1, 6 * mm)]
    for para in body.split("\n\n"):
        story.append(Paragraph(_esc(para).replace("\n", "<br/>"), BODY))
        story.append(Spacer(1, 3 * mm))
    story += [Spacer(1, 8 * mm), Paragraph(_esc(disclaimer), SMALL)]
    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()


def report_pdf(data: dict) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=20 * mm, bottomMargin=20 * mm,
                            title=f"{brand()['name']} Privatsphäre-Report")
    s = data["summary"]
    story = [Paragraph(f"{brand()['name']} – Dein Privatsphäre-Report", H1),
             Paragraph(f"Version {data['version']} · erstellt am {data['created_at'][:10]}", SMALL), Spacer(1, 5 * mm),
             Paragraph("Zusammenfassung", H2),
             Paragraph(f"Risiko-Wert: <b>{s['score']}/100</b> ({ {'green': 'grün', 'yellow': 'gelb', 'red': 'rot'}[s['light']] }). "
                       f"{s['total']} Funde, davon {s['high']} mit hohem Risiko, {s['breaches']} Datenlecks.", BODY), Spacer(1, 3 * mm)]
    rows = [["Faktor", "Punkte"]] + [[k, str(v)] for k, v in s["factors"].items()]
    t = Table(rows, colWidths=[90 * mm, 30 * mm])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dbeafe")), ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                           ("FONTSIZE", (0, 0), (-1, -1), 9), ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1"))]))
    story += [t, Spacer(1, 5 * mm), Paragraph("Lösch-Plan (nach Wirkung sortiert)", H2)]
    for i, a in enumerate(data["plan"], 1):
        story.append(Paragraph(f"{i}. {_esc(a['title'])} – senkt den Wert um ca. {a['impact']} Punkte", BODY))
    story += [Spacer(1, 5 * mm), Paragraph("Alle Funde", H2)]
    rows = [["Risiko", "Quelle", "Fund", "Datum"]]
    for f in data["findings"]:
        rows.append([f["risk"], f["source"], Paragraph(_esc(f["title"]) + (f"<br/><font size=7>{_esc(f['url'] or '')}</font>"), SMALL),
                     (f["found_at"] or "")[:10]])
    t = Table(rows, colWidths=[18 * mm, 28 * mm, 100 * mm, 24 * mm], repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dbeafe")), ("FONTSIZE", (0, 0), (-1, -1), 8),
                           ("VALIGN", (0, 0), (-1, -1), "TOP"), ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1"))]))
    story += [t, Spacer(1, 6 * mm),
              Paragraph("Funde mit dem Hinweis „nicht sicher zuordenbar“ können namensgleiche andere Personen betreffen. "
                        "Dieser Report ist keine Rechtsberatung.", SMALL)]
    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()
