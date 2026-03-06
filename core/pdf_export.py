"""
Generate PDF reports for dashboard submissions and their click metadata.
"""
import io
import re
from django.utils import timezone as django_tz

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak,
)


def _sanitize(s, max_len=200):
    """Make string safe for PDF and truncate if needed."""
    if s is None:
        return "—"
    s = str(s).strip()
    s = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', s)
    return (s[:max_len] + '…') if len(s) > max_len else s or "—"


def _format_geo(click):
    g = getattr(click, 'geo_location', None) or {}
    parts = [
        g.get('city'),
        g.get('region'),
        g.get('country'),
    ]
    parts = [p for p in parts if p]
    result = ", ".join(parts) if parts else "—"
    if g.get('isp'):
        result += f" · {_sanitize(g.get('isp'), 80)}"
    return result or "—"


def _format_browser(click):
    b = getattr(click, 'browser', None) or {}
    name = b.get('name') or "—"
    ver = b.get('version', '')
    if ver:
        name += f" {ver}"
    return _sanitize(name, 100)


def _format_device(click):
    d = getattr(click, 'device', None) or {}
    parts = [
        d.get('type'),
        d.get('os'),
        d.get('platform'),
        d.get('memory'),
    ]
    parts = [p for p in parts if p]
    return _sanitize(", ".join(parts), 120) if parts else "—"


def _format_screen(click):
    s = getattr(click, 'screen', None) or {}
    res = s.get('resolution')
    vp = s.get('viewport')
    if res or vp:
        return _sanitize(f"{res or '—'} · {vp or '—'}", 80)
    return "—"


def build_submissions_pdf(submissions):
    """
    Build a PDF containing the given submissions and their click metadata.
    submissions: list of Submission instances with prefetched click_metadata.
    Returns: bytes of the PDF.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=20 * mm,
        leftMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        name='CustomTitle',
        parent=styles['Heading1'],
        fontSize=16,
        spaceAfter=6,
    )
    heading_style = styles['Heading2']
    body_style = styles['Normal']
    story = []

    story.append(Paragraph("Techtronix Solutions LLC", title_style))
    story.append(Paragraph("Submission(s) Export", styles['Heading3']))
    generated = django_tz.now().strftime("%Y-%m-%d %H:%M UTC")
    story.append(Paragraph(f"Generated: {generated}", body_style))
    story.append(Spacer(1, 8 * mm))

    for sub in submissions:
        story.append(Paragraph(f"Submission: {_sanitize(sub.name, 100)}", heading_style))
        story.append(Spacer(1, 3 * mm))

        sub_data = [
            ["Name", _sanitize(sub.name)],
            ["Phone", _sanitize(sub.phone)],
            ["Email", _sanitize(sub.email)],
            ["Address", _sanitize(sub.address)],
            ["City", _sanitize(sub.city)],
            ["Zip", _sanitize(sub.zip_code)],
            ["Country", _sanitize(sub.country)],
            ["Submitted", sub.created_at.strftime("%Y-%m-%d %H:%M") if sub.created_at else "—"],
        ]
        t = Table(sub_data, colWidths=[25 * mm, 140 * mm])
        t.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        story.append(t)
        story.append(Spacer(1, 5 * mm))

        rel = getattr(sub, 'click_metadata', None)
        clicks = list(rel.all()) if rel else []
        if clicks:
            story.append(Spacer(1, 2 * mm))
            for click in clicks:
                ts = click.timestamp.strftime("%Y-%m-%d %H:%M") if getattr(click, 'timestamp', None) else "—"
                story.append(Paragraph(ts, body_style))
                click_data = [
                    ["IP", _sanitize(str(click.ip_address) if click.ip_address else "—")],
                    ["Geo", _format_geo(click)],
                    ["Browser", _format_browser(click)],
                    ["Device", _format_device(click)],
                    ["Screen", _format_screen(click)],
                ]
                ct = Table(click_data, colWidths=[28 * mm, 137 * mm])
                ct.setStyle(TableStyle([
                    ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, -1), 8),
                    ('GRID', (0, 0), (-1, -1), 0.25, colors.lightgrey),
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ]))
                story.append(ct)
                story.append(Spacer(1, 3 * mm))
        else:
            story.append(Spacer(1, 2 * mm))

        if sub is not submissions[-1]:
            story.append(PageBreak())

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()
