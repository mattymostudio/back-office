"""Render a prepared invoice to print-ready HTML."""

from __future__ import annotations

import shutil
from pathlib import Path

from jinja2 import ChainableUndefined, Environment, FileSystemLoader

from .config import Workspace
from .model import load_invoice, prepare_invoice


def _env(ws: Workspace) -> Environment:
    return Environment(
        loader=FileSystemLoader(str(ws.template_dir())),
        undefined=ChainableUndefined,  # tolerant of optional client/invoice fields
        autoescape=True,
    )


def sync_forms(ws: Workspace) -> None:
    """Mirror forms/ into out/forms/ so W-9 links resolve from rendered HTML."""
    if not ws.forms_dir.exists():
        return
    out_forms = ws.out_dir / "forms"
    out_forms.mkdir(parents=True, exist_ok=True)
    for src in ws.forms_dir.iterdir():
        if src.is_file() and not src.name.startswith("."):
            dst = out_forms / src.name
            if not dst.exists() or src.stat().st_mtime > dst.stat().st_mtime:
                shutil.copy2(src, dst)


def render_html(ws: Workspace, invoice_path: Path) -> tuple[str, dict, list[str]]:
    """Render to an HTML string. Returns (html, prepared_invoice, warnings)."""
    studio, client, invoice_raw = load_invoice(ws, invoice_path)
    invoice, warnings = prepare_invoice(ws, studio, client, invoice_raw)
    template = _env(ws).get_template("invoice.html.j2")
    html = template.render(studio=studio, client=client, invoice=invoice)
    return html, invoice, warnings


def render_to_file(ws: Workspace, invoice_path: Path) -> tuple[Path, list[str]]:
    """Render and write out/<slug>/<number>.html. Returns (out_path, warnings)."""
    studio, client, invoice_raw = load_invoice(ws, invoice_path)
    slug = client.get("slug") or invoice_path.parent.name
    html, invoice, warnings = render_html(ws, invoice_path)

    out_subdir = ws.out_dir / slug
    out_subdir.mkdir(parents=True, exist_ok=True)
    out_path = out_subdir / f"{invoice['number']}.html"
    out_path.write_text(html)
    return out_path, warnings
