"""Headless PDF export via WeasyPrint (optional extra).

WeasyPrint is heavy (needs Pango/Cairo system libs), so it's an opt-in install:
`pip install backoffice[pdf]`. Without it, every rendered HTML still has a
Print / Save as PDF button — this just removes the manual step.
"""

from __future__ import annotations

from pathlib import Path

from .config import Workspace
from .render import render_html, sync_forms


def _require_weasyprint():
    try:
        from weasyprint import HTML  # noqa: F401
        return HTML
    except Exception as exc:  # ImportError or native-lib load failure
        raise SystemExit(
            "PDF export needs WeasyPrint, which isn't available.\n"
            "  Install:  pip install 'backoffice[pdf]'\n"
            "  macOS also needs:  brew install pango\n"
            "Until then, open the rendered HTML and use Print / Save as PDF.\n"
            f"(underlying error: {exc})"
        )


def render_pdf(ws: Workspace, invoice_path: Path) -> tuple[Path, list[str]]:
    """Render <number>.pdf next to the HTML in out/<slug>/. Returns (path, warnings)."""
    HTML = _require_weasyprint()
    sync_forms(ws)
    html, invoice, warnings = render_html(ws, invoice_path)

    slug = invoice.get("client") or invoice_path.parent.name
    out_subdir = ws.out_dir / slug
    out_subdir.mkdir(parents=True, exist_ok=True)
    out_path = out_subdir / f"{invoice['number']}.pdf"

    # base_url = the HTML's own directory so ../forms/<w9> links resolve.
    HTML(string=html, base_url=str(out_subdir) + "/").write_pdf(str(out_path))
    return out_path, warnings
