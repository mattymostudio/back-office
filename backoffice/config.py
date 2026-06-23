"""Workspace discovery and config loading.

A *workspace* is a directory holding your billing data:

    studio.yml          identity + payment + branding  (committed; may hold placeholders)
    studio.local.yml    real bank / EIN / signer        (gitignored; overrides studio.yml)
    clients/            one <slug>.yml per client
    invoices/<slug>/    one <number>.yml per invoice
    expenses/           pass-through expenses
    contractors/        subcontractor pass-throughs
    receipts/           attached receipt / agreement PDFs
    forms/              W-9 and other downloadable forms
    contracts/          executed + draft contracts (read by `backoffice ingest`)
    templates/          optional workspace-level template override
    out/                rendered HTML (regenerated; gitignored)

Discovery order: $BACKOFFICE_HOME, then the nearest ancestor of the CWD that
contains a studio.yml, then the CWD itself.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml

PACKAGE_DIR = Path(__file__).resolve().parent
PACKAGE_TEMPLATES = PACKAGE_DIR / "templates"

DATA_DIRS = (
    "clients", "invoices", "quotes", "expenses", "contractors",
    "receipts", "forms", "contracts", "out",
)


def load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open() as f:
        return yaml.safe_load(f) or {}


def deep_merge(base: dict, overlay: dict) -> dict:
    """Recursively merge overlay onto base. Overlay scalars/lists win."""
    out = dict(base)
    for k, v in (overlay or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


class Workspace:
    def __init__(self, root: Path):
        self.root = root.resolve()

    # ── path accessors ─────────────────────────────────────────────
    @property
    def studio_yml(self) -> Path:
        return self.root / "studio.yml"

    @property
    def studio_local_yml(self) -> Path:
        return self.root / "studio.local.yml"

    @property
    def ledger_yml(self) -> Path:
        return self.root / "_ledger.yml"

    def dir(self, name: str) -> Path:
        return self.root / name

    @property
    def clients_dir(self) -> Path:
        return self.root / "clients"

    @property
    def invoices_dir(self) -> Path:
        return self.root / "invoices"

    @property
    def quotes_dir(self) -> Path:
        return self.root / "quotes"

    @property
    def expenses_dir(self) -> Path:
        return self.root / "expenses"

    @property
    def contractors_dir(self) -> Path:
        return self.root / "contractors"

    @property
    def receipts_dir(self) -> Path:
        return self.root / "receipts"

    @property
    def forms_dir(self) -> Path:
        return self.root / "forms"

    @property
    def contracts_dir(self) -> Path:
        return self.root / "contracts"

    @property
    def out_dir(self) -> Path:
        return self.root / "out"

    def template_dir(self) -> Path:
        """Workspace template override if present, else the packaged default."""
        local = self.root / "templates"
        if (local / "invoice.html.j2").exists():
            return local
        return PACKAGE_TEMPLATES

    # ── loading ────────────────────────────────────────────────────
    def studio(self) -> dict:
        """studio.yml merged with the gitignored studio.local.yml overlay."""
        return deep_merge(load_yaml(self.studio_yml), load_yaml(self.studio_local_yml))

    def client(self, slug: str) -> dict:
        path = self.clients_dir / f"{slug}.yml"
        if not path.exists():
            known = sorted(p.stem for p in self.clients_dir.glob("*.yml")) if self.clients_dir.exists() else []
            raise SystemExit(f"Client not found: {path}\nKnown clients: {known}")
        return load_yaml(path)

    # ── discovery / creation ───────────────────────────────────────
    @classmethod
    def discover(cls, start: Path | None = None) -> "Workspace":
        env = os.environ.get("BACKOFFICE_HOME")
        if env:
            return cls(Path(env))
        cur = (start or Path.cwd()).resolve()
        for cand in (cur, *cur.parents):
            if (cand / "studio.yml").exists():
                return cls(cand)
        return cls(cur)

    def exists(self) -> bool:
        return self.studio_yml.exists()
