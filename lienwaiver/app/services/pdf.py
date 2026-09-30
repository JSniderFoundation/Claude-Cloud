"""Render a waiver to PDF from the HTML template."""
from __future__ import annotations

import base64
import io
import re
from pathlib import Path

import qrcode
from jinja2 import Environment, FileSystemLoader, select_autoescape

from ..config import settings
from ..models import Waiver

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"
_env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=select_autoescape(["html"]))


def money(value) -> str:
    return f"${value:,.2f}"


def longdate(value) -> str:
    return value.strftime("%B %-d, %Y") if value else ""


_env.filters["money"] = money
_env.filters["longdate"] = longdate
_env.filters["shortdate"] = lambda d: d.strftime("%m/%d/%Y") if d else ""


def slug(text: str) -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-")
    return text[:60] or "x"


def qr_data_uri(url: str) -> str:
    img = qrcode.make(url, box_size=4, border=1)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def render_waiver_html(waiver: Waiver, company: dict[str, str], portal_url: str) -> str:
    template = _env.get_template("pdf/waiver.html")
    return template.render(w=waiver, vendor=waiver.vendor, project=waiver.project, company=company,
                           portal_url=portal_url, qr=qr_data_uri(portal_url) if portal_url else "")


def render_waiver_pdf(waiver: Waiver, company: dict[str, str], portal_url: str) -> bytes:
    from weasyprint import HTML

    html = render_waiver_html(waiver, company, portal_url)
    return HTML(string=html, base_url=str(TEMPLATE_DIR)).write_pdf()


def waiver_pdf_path(waiver: Waiver, kind: str) -> Path:
    """kind is 'unsigned' or 'signed'. Files are grouped by project then vendor so the folder is browsable."""
    folder = settings.pdf_dir / slug(waiver.project.name) / slug(waiver.vendor.name)
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{waiver.number}-{kind}.pdf"


def write_unsigned_pdf(waiver: Waiver, company: dict[str, str], portal_url: str) -> Path:
    path = waiver_pdf_path(waiver, "unsigned")
    path.write_bytes(render_waiver_pdf(waiver, company, portal_url))
    return path
