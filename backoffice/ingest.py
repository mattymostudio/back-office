"""Read a contract → scaffold clients/<slug>.yml.

Two extraction modes:

  • deterministic (default) — regex/keyword pass over the contract text. No
    dependencies beyond what's needed to read the file; works for everyone.
  • --llm (optional)        — Claude reads the contract and returns structured
    fields. Needs `pip install backoffice[llm]` + ANTHROPIC_API_KEY. Merged on
    top of the deterministic pass (LLM values win where present).

Either way the output is a client YAML you should eyeball before billing against
it — unknown fields are left as `[fill in]` placeholders (the invoice template
renders those in amber so they're obvious).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

import yaml

from .config import Workspace
from .money import to_money

# Default model for the optional LLM pass. Override with --model or
# BACKOFFICE_INGEST_MODEL. (Anthropic's most capable model; pick a cheaper one
# like claude-haiku-4-5 if you're ingesting many simple contracts.)
DEFAULT_LLM_MODEL = "claude-opus-4-8"

ENTITY_RE = re.compile(
    r"\b([A-Z][A-Za-z0-9&.,'\- ]+?(?:LLC|L\.L\.C\.|Inc\.?|Incorporated|Corp\.?|"
    r"Corporation|Ltd\.?|Limited|Company|Co\.|LP|L\.P\.|PLLC|PC))\b"
)


@dataclass
class Extraction:
    parties: list[str] = field(default_factory=list)
    client_legal_name: str | None = None
    dba: str | None = None
    payment_terms: str | None = None
    rate: Decimal | None = None
    rate_unit: str | None = None
    subcontractor_cap: Decimal | None = None
    term_start: str | None = None
    term_end: str | None = None
    reference: str | None = None
    notes: list[str] = field(default_factory=list)


# ── reading the contract ───────────────────────────────────────────

def read_contract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in (".md", ".markdown", ".txt"):
        return path.read_text(errors="ignore")
    if suffix == ".pdf":
        pdftotext = shutil.which("pdftotext")
        if pdftotext:
            with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tmp:
                tmp_path = tmp.name
            subprocess.run([pdftotext, "-layout", str(path), tmp_path], check=True)
            text = Path(tmp_path).read_text(errors="ignore")
            os.unlink(tmp_path)
            return text
        try:
            import pypdf  # noqa
            reader = pypdf.PdfReader(str(path))
            return "\n".join((p.extract_text() or "") for p in reader.pages)
        except Exception:
            raise SystemExit(
                "Reading PDFs needs either `pdftotext` (brew install poppler) or "
                "`pip install pypdf`. Or pass a .md/.txt contract instead."
            )
    raise SystemExit(f"Unsupported contract format: {suffix} (use .md, .txt, or .pdf)")


# ── deterministic extraction ───────────────────────────────────────

def _parse_amount(s: str) -> Decimal | None:
    m = re.search(r"\$\s*([\d,]+(?:\.\d{2})?)", s)
    if not m:
        return None
    try:
        return to_money(m.group(1).replace(",", ""))
    except Exception:
        return None


def deterministic_extract(text: str, studio_name: str | None) -> Extraction:
    ex = Extraction()
    flat = re.sub(r"\s+", " ", text)

    # Parties — legal entities, de-duped in first-seen order.
    seen: list[str] = []
    for m in ENTITY_RE.finditer(text):
        name = m.group(1).strip(" ,.")
        if name not in seen and len(name) < 80:
            seen.append(name)
    ex.parties = seen[:6]
    # Client = the first party that isn't us.
    studio_low = (studio_name or "").lower()
    for p in ex.parties:
        if studio_low and studio_low.split(",")[0] in p.lower():
            continue
        ex.client_legal_name = p
        break
    if not ex.client_legal_name and ex.parties:
        ex.client_legal_name = ex.parties[0]

    # Payment terms.
    if re.search(r"due upon receipt|upon receipt|net\s*0\b", flat, re.I):
        ex.payment_terms = "Net 0 (due upon receipt)"
    else:
        m = re.search(r"net\s*(\d{1,3})", flat, re.I)
        if m:
            ex.payment_terms = f"Net {m.group(1)}"

    # Rate — "$X per month" / "monthly retainer of $X" / "fee of $X".
    for pat in (
        r"\$\s*[\d,]+(?:\.\d{2})?\s*(?:/|per)\s*month",
        r"monthly (?:retainer|fee|rate)[^.$]*\$\s*[\d,]+(?:\.\d{2})?",
        r"(?:retainer|fee) of \$\s*[\d,]+(?:\.\d{2})?",
        r"\$\s*[\d,]+(?:\.\d{2})?\s*(?:/|per)\s*(?:hour|hr)",
    ):
        m = re.search(pat, flat, re.I)
        if m:
            ex.rate = _parse_amount(m.group(0))
            ex.rate_unit = "hour" if re.search(r"hour|hr", m.group(0), re.I) else "month"
            break

    # Subcontractor cap.
    m = re.search(r"subcontractor[^.]*?(\$\s*[\d,]+(?:\.\d{2})?)\s*(?:/|per)?\s*month", flat, re.I)
    if m:
        ex.subcontractor_cap = _parse_amount(m.group(1))

    # Term dates — "effective <date>" ... "through/until <date>".
    months = r"(?:January|February|March|April|May|June|July|August|September|October|November|December)"
    m = re.search(rf"effective[^.]*?({months}\s+\d{{1,2}},?\s+\d{{4}}|\d{{4}}-\d{{2}}-\d{{2}})", flat, re.I)
    if m:
        ex.term_start = m.group(1)
    m = re.search(rf"(?:through|until|expires?|ending)[^.]*?({months}\s+\d{{1,2}},?\s+\d{{4}}|\d{{4}}-\d{{2}}-\d{{2}})", flat, re.I)
    if m:
        ex.term_end = m.group(1)

    # Reference / title — first non-empty line, or an "...Agreement" phrase.
    first_lines = [ln.strip() for ln in text.splitlines() if ln.strip()][:8]
    for ln in first_lines:
        if re.search(r"agreement|statement of work|sow|contract|engagement", ln, re.I) and len(ln) < 90:
            ex.reference = ln.strip("# ").strip()
            break

    if not ex.client_legal_name:
        ex.notes.append("Could not identify the client entity — set client.legal_name by hand.")
    if not ex.payment_terms:
        ex.notes.append("No payment terms found — defaulting to Net 30.")
    if ex.rate is None:
        ex.notes.append("No rate found — set default_line_items[0].rate by hand.")
    return ex


# ── optional LLM extraction ────────────────────────────────────────

_LLM_SCHEMA = {
    "type": "object",
    "properties": {
        "client_legal_name": {"type": "string"},
        "dba": {"type": "string"},
        "payment_terms": {"type": "string"},
        "rate": {"type": "number"},
        "rate_unit": {"type": "string", "enum": ["month", "hour", "project", "year", "day"]},
        "subcontractor_cap": {"type": "number"},
        "term_start": {"type": "string"},
        "term_end": {"type": "string"},
        "reference": {"type": "string"},
    },
    "required": ["client_legal_name"],
    "additionalProperties": False,
}


def llm_extract(text: str, studio_name: str | None, model: str) -> Extraction:
    try:
        import anthropic
    except ImportError:
        raise SystemExit("LLM ingest needs the Anthropic SDK: pip install 'backoffice[llm]'")
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        raise SystemExit("Set ANTHROPIC_API_KEY to use --llm ingest.")

    client = anthropic.Anthropic()
    studio_line = f"The service provider (us) is '{studio_name}'. " if studio_name else ""
    prompt = (
        f"Extract billing setup fields from this consulting/services contract. "
        f"{studio_line}The CLIENT is the other party — the one being billed, not us. "
        f"Use null for anything not stated; do not guess. Return amounts as plain numbers.\n\n"
        f"--- CONTRACT ---\n{text[:60000]}"
    )
    resp = client.messages.create(
        model=model,
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
        output_config={"format": {"type": "json_schema", "schema": _LLM_SCHEMA}},
    )
    import json
    raw = next((b.text for b in resp.content if b.type == "text"), "{}")
    data = json.loads(raw)

    ex = Extraction()
    ex.client_legal_name = data.get("client_legal_name")
    ex.dba = data.get("dba")
    ex.payment_terms = data.get("payment_terms")
    ex.rate = to_money(data["rate"]) if data.get("rate") is not None else None
    ex.rate_unit = data.get("rate_unit")
    ex.subcontractor_cap = to_money(data["subcontractor_cap"]) if data.get("subcontractor_cap") is not None else None
    ex.term_start = data.get("term_start")
    ex.term_end = data.get("term_end")
    ex.reference = data.get("reference")
    ex.notes.append(f"LLM pass via {model}.")
    return ex


def _merge(base: Extraction, overlay: Extraction) -> Extraction:
    for f in ("client_legal_name", "dba", "payment_terms", "rate", "rate_unit",
              "subcontractor_cap", "term_start", "term_end", "reference"):
        v = getattr(overlay, f)
        if v not in (None, ""):
            setattr(base, f, v)
    base.notes.extend(overlay.notes)
    return base


# ── build the client YAML ──────────────────────────────────────────

def _slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return s or "client"


def build_client_yaml(ex: Extraction, slug: str, contract_rel: str) -> str:
    rate = float(ex.rate) if ex.rate is not None else "[fill in]"
    unit = ex.rate_unit or "month"
    client: dict = {
        "slug": slug,
        "client": {
            "legal_name": ex.client_legal_name or "[fill in client legal name]",
            "attn": "Accounts Payable",
            "email": "[fill in AP email]",
            "address": {
                "line1": "[fill in]", "city": "[fill in]",
                "state": "", "zip": "", "country": "USA",
            },
        },
        "contract": {
            "reference": ex.reference or "[fill in contract title]",
            "contract_ref": contract_rel,
            "payment_terms": ex.payment_terms or "Net 30",
        },
        "default_line_items": [{
            "description": f"{ex.reference or 'Services'} — recurring {unit}ly fee",
            "quantity": 1, "unit": unit, "rate": rate,
        }],
    }
    if ex.dba:
        client["client"]["dba"] = ex.dba
    if ex.subcontractor_cap is not None:
        client["contract"]["subcontractor_cap_per_month"] = float(ex.subcontractor_cap)
    if ex.term_start or ex.term_end:
        client["contract"]["term"] = {"start": ex.term_start or "[fill in]",
                                      "end": ex.term_end or "[fill in]"}

    header = "# Scaffolded by `backoffice ingest`. Review every field before billing.\n\n"
    return header + yaml.safe_dump(client, sort_keys=False, allow_unicode=True)


def ingest_contract(ws: Workspace, contract_path: Path, *, slug: str | None = None,
                    use_llm: bool = False, model: str | None = None,
                    force: bool = False) -> tuple[Path, Extraction]:
    text = read_contract_text(contract_path)
    studio_name = ws.studio().get("legal_name")

    ex = deterministic_extract(text, studio_name)
    if use_llm:
        model = model or os.environ.get("BACKOFFICE_INGEST_MODEL") or DEFAULT_LLM_MODEL
        ex = _merge(ex, llm_extract(text, studio_name, model))

    slug = slug or _slugify(ex.client_legal_name)
    ws.clients_dir.mkdir(parents=True, exist_ok=True)
    out_path = ws.clients_dir / f"{slug}.yml"
    if out_path.exists() and not force:
        raise SystemExit(f"{out_path} exists. Use --force to overwrite.")

    # Reference the contract relative to the workspace root if it lives inside it.
    try:
        contract_rel = str(contract_path.resolve().relative_to(ws.root))
    except ValueError:
        contract_rel = str(contract_path.resolve())

    out_path.write_text(build_client_yaml(ex, slug, contract_rel))
    return out_path, ex
