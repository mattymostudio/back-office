"""Invoice assembly: load YAML, fold in pass-throughs, compute totals.

Kept presentation-free so the same prepared invoice can drive HTML, PDF, or a
plain-text report. Returns (rendered_dict, warnings); warnings are non-fatal
sanity checks (client mismatch, out-of-period item, subcontractor cap).
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from .config import Workspace, load_yaml
from .money import coerce_date, fmt_date, fmt_money, fmt_qty, to_money


# ── loading ────────────────────────────────────────────────────────

def load_invoice(ws: Workspace, invoice_path: Path) -> tuple[dict, dict, dict]:
    invoice = load_yaml(invoice_path)
    slug = invoice.get("client") or invoice_path.parent.name
    client = ws.client(slug)
    studio = ws.studio()
    return studio, client, invoice


def currency_of(invoice: dict, client: dict, studio: dict) -> str:
    return (
        invoice.get("currency")
        or client.get("currency")
        or studio.get("payment", {}).get("currency")
        or "USD"
    ).upper()


# ── pass-through includes ──────────────────────────────────────────

def _load_includes(ws: Workspace, invoice: dict, client_slug: str,
                   warnings: list[str]) -> tuple[list[dict], list[dict]]:
    expenses: list[dict] = []
    for fname in invoice.get("include_expenses") or []:
        path = ws.expenses_dir / fname
        if not path.exists():
            warnings.append(f"include_expenses: file not found — {fname}")
            continue
        data = load_yaml(path)
        _validate_include(data, fname, client_slug, invoice, "expense", warnings)
        expenses.append(_expense_to_line_item(data, fname))

    contractors: list[dict] = []
    for fname in invoice.get("include_contractors") or []:
        path = ws.contractors_dir / fname
        if not path.exists():
            warnings.append(f"include_contractors: file not found — {fname}")
            continue
        data = load_yaml(path)
        _validate_include(data, fname, client_slug, invoice, "contractor", warnings)
        contractors.append(_contractor_to_line_item(data, fname))

    return expenses, contractors


def _validate_include(data: dict, fname: str, client_slug: str, invoice: dict,
                      kind: str, warnings: list[str]) -> None:
    if not data.get("billable", True):
        warnings.append(f"{kind} {fname} is marked billable=false — included anyway")
    inc_client = data.get("client")
    if inc_client and inc_client != client_slug:
        warnings.append(f"{kind} {fname} tagged for client '{inc_client}' but invoice is for '{client_slug}'")
    period = invoice.get("service_period") or {}
    if period.get("start") and period.get("end") and data.get("date"):
        d, start, end = coerce_date(data["date"]), coerce_date(period["start"]), coerce_date(period["end"])
        if d and start and end and not (start <= d <= end):
            warnings.append(f"{kind} {fname} dated {d.isoformat()} is outside service period "
                            f"{start.isoformat()}–{end.isoformat()}")
    if data.get("amount") is None and not (data.get("hours") and data.get("rate")):
        warnings.append(f"{kind} {fname} has no amount (and no hours×rate) — will render as 0")


def _expense_to_line_item(exp: dict, source_file: str) -> dict:
    receipt_tag = "receipt attached" if exp.get("receipt") else "receipt missing"
    sub_parts = [exp.get("category", "expense")]
    if exp.get("date"):
        d = coerce_date(exp["date"])
        if d:
            sub_parts.append(d.isoformat())
    sub_parts.append(receipt_tag)
    return {
        "description": f"{exp.get('vendor', 'Vendor')} — {exp.get('description', '')}".strip(" —"),
        "sub": " · ".join(p for p in sub_parts if p),
        "quantity": 1,
        "unit": "",
        "rate": exp.get("amount", 0),
        "_source": source_file,
    }


def _contractor_to_line_item(c: dict, source_file: str) -> dict:
    contractor = c.get("contractor", {})
    name = contractor.get("name", "Contractor")
    role = contractor.get("role", "")
    amount = c.get("amount")
    if amount is None and c.get("hours") and c.get("rate"):
        amount = Decimal(str(c["hours"])) * Decimal(str(c["rate"]))
    receipt_tag = "contractor invoice attached" if c.get("contractor_invoice") else "contractor invoice missing"
    sub_parts = []
    if c.get("date"):
        d = coerce_date(c["date"])
        if d:
            sub_parts.append(d.isoformat())
    if c.get("hours") and c.get("rate"):
        sub_parts.append(f"{c['hours']}h × {fmt_money(c['rate'])}/h")
    sub_parts.append(receipt_tag)
    desc = f"{name}" + (f" ({role})" if role else "") + (f" — {c['description']}" if c.get("description") else "")
    return {
        "description": desc,
        "sub": " · ".join(sub_parts),
        "quantity": 1,
        "unit": "",
        "rate": amount or 0,
        "_source": source_file,
    }


# ── computation ────────────────────────────────────────────────────

def compute_amount(item: dict) -> Decimal:
    qty = Decimal(str(item.get("quantity", 1)))
    rate = Decimal(str(item.get("rate", 0)))
    return to_money(qty * rate)


def decorate_item(item: dict, currency: str) -> dict:
    amount = compute_amount(item)
    return {
        "sub": None,
        "unit": None,
        **item,
        "amount": amount,
        "amount_fmt": fmt_money(amount, currency),
        "quantity_fmt": fmt_qty(item.get("quantity", 1)),
        "rate_fmt": fmt_money(item.get("rate", 0), currency),
    }


def prepare_invoice(ws: Workspace, studio: dict, client: dict, invoice: dict) -> tuple[dict, list[str]]:
    """Return (render-ready invoice dict, warnings)."""
    warnings: list[str] = []
    client_slug = client.get("slug", "")
    currency = currency_of(invoice, client, studio)

    inc_expenses, inc_contractors = _load_includes(ws, invoice, client_slug, warnings)

    line_items_raw = invoice.get("line_items") or client.get("default_line_items") or []
    subs_raw = list(invoice.get("subcontractors") or []) + inc_contractors
    exps_raw = list(invoice.get("expenses") or []) + inc_expenses

    line_items = [decorate_item(i, currency) for i in line_items_raw]
    subcontractors = [decorate_item(i, currency) for i in subs_raw]
    expenses = [decorate_item(i, currency) for i in exps_raw]

    cap = client.get("contract", {}).get("subcontractor_cap_per_month")
    if cap and subcontractors:
        total_sub = sum((i["amount"] for i in subcontractors), Decimal("0"))
        if total_sub > Decimal(str(cap)):
            warnings.append(
                f"Subcontractor pass-through {fmt_money(total_sub, currency)} exceeds "
                f"contractual cap of {fmt_money(cap, currency)}/month"
            )

    subtotal = sum((i["amount"] for i in line_items + subcontractors + expenses), Decimal("0"))

    tax = invoice.get("tax")
    tax_amount = Decimal("0")
    if tax and tax.get("rate_pct"):
        tax_amount = to_money(subtotal * Decimal(str(tax["rate_pct"])) / Decimal("100"))
    total = subtotal + tax_amount

    payment_terms = (
        invoice.get("payment_terms")
        or client.get("contract", {}).get("payment_terms")
        or studio.get("payment", {}).get("default_terms")
        or "Net 30"
    )

    period = invoice.get("service_period") or {}
    if period and not period.get("label") and period.get("start") and period.get("end"):
        period = {**period, "label": f"{fmt_date(period['start'])} – {fmt_date(period['end'])}"}

    bill_to = invoice.get("bill_to") or client.get("client", {})

    doc_type = invoice.get("type", "invoice").lower()  # "invoice" or "quote"

    rendered = {
        **invoice,
        "type": doc_type,
        "doc_title": "Estimate" if doc_type == "quote" else "Invoice",
        "currency": currency,
        "line_items": line_items,
        "subcontractors": subcontractors,
        "expenses": expenses,
        "subtotal": subtotal,
        "subtotal_fmt": fmt_money(subtotal, currency),
        "tax": tax,
        "tax_amount": tax_amount,
        "tax_amount_fmt": fmt_money(tax_amount, currency),
        "total": total,
        "total_fmt": fmt_money(total, currency),
        "payment_terms": payment_terms,
        "issue_date_fmt": fmt_date(invoice["issue_date"]),
        "due_date_fmt": fmt_date(invoice.get("due_date")),
        "service_period": period or None,
        "bill_to": bill_to,
    }
    return rendered, warnings


def find_all_invoices(ws: Workspace) -> list[Path]:
    if not ws.invoices_dir.exists():
        return []
    return sorted(ws.invoices_dir.rglob("*.yml"))
