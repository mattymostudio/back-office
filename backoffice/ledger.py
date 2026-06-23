"""Accounts-receivable: reconcile invoices with status, age the unpaid, mark paid.

The invoice YAML is the source of truth for *amounts*; `_ledger.yml` tracks
*status* (draft → issued → sent → paid → void) and payment metadata. `reconcile`
joins the two and flags drift so the ledger can't silently diverge from reality.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

import yaml

from .config import Workspace, load_yaml
from .model import find_all_invoices, load_invoice, prepare_invoice
from .money import coerce_date, fmt_money

OPEN_STATUSES = {"issued", "sent"}
CLOSED_STATUSES = {"paid", "void"}
ALL_STATUSES = ["draft", "issued", "sent", "paid", "void"]

AGING_BUCKETS = [
    ("current", 0, 0),      # not yet due
    ("1-30", 1, 30),
    ("31-60", 31, 60),
    ("61-90", 61, 90),
    ("90+", 91, 10**9),
]


@dataclass
class Record:
    number: str
    client: str
    doc_type: str = "invoice"
    issue_date: date | None = None
    due_date: date | None = None
    total: Decimal = Decimal("0")
    currency: str = "USD"
    status: str = "draft"
    sent_date: date | None = None
    paid_date: date | None = None
    method: str = ""
    on_disk: bool = False
    notes: str = ""
    warnings: list[str] = field(default_factory=list)

    @property
    def outstanding(self) -> bool:
        return self.status in OPEN_STATUSES

    def days_overdue(self, ref: date) -> int:
        if not self.due_date:
            return 0
        return (ref - self.due_date).days


def reconcile(ws: Workspace) -> tuple[list[Record], list[str]]:
    """Build the joined invoice+status view. Returns (records, drift_warnings)."""
    drift: list[str] = []
    ledger_rows = {str(r.get("number")): r for r in (load_yaml(ws.ledger_yml).get("invoices") or [])}
    seen: set[str] = set()
    records: list[Record] = []

    for path in find_all_invoices(ws):
        try:
            studio, client, raw = load_invoice(ws, path)
            prepared, warns = prepare_invoice(ws, studio, client, raw)
        except Exception as exc:  # malformed file shouldn't sink the whole report
            drift.append(f"{path.name}: failed to load ({exc})")
            continue
        if prepared.get("type") == "quote":
            continue  # quotes aren't receivables
        num = str(prepared["number"])
        seen.add(num)
        row = ledger_rows.get(num, {})
        rec = Record(
            number=num,
            client=prepared.get("client") or client.get("slug", ""),
            doc_type=prepared.get("type", "invoice"),
            issue_date=coerce_date(prepared.get("issue_date")),
            due_date=coerce_date(prepared.get("due_date")),
            total=prepared["total"],
            currency=prepared.get("currency", "USD"),
            status=str(row.get("status", "draft")),
            sent_date=coerce_date(row.get("sent_date")),
            paid_date=coerce_date(row.get("paid_date")),
            method=row.get("method", "") or "",
            on_disk=True,
            notes=row.get("notes", "") or "",
            warnings=warns,
        )
        if row and row.get("amount") not in (None, "") and Decimal(str(row["amount"])) != prepared["total"]:
            drift.append(f"{num}: ledger amount {fmt_money(row['amount'], rec.currency)} "
                         f"≠ computed {fmt_money(prepared['total'], rec.currency)}")
        records.append(rec)

    # Ledger rows with no file on disk (historical / pre-system / voided).
    for num, row in ledger_rows.items():
        if num in seen:
            continue
        records.append(Record(
            number=num, client=row.get("client", ""),
            issue_date=coerce_date(row.get("issue_date")),
            due_date=coerce_date(row.get("due_date")),
            total=Decimal(str(row.get("amount", 0) or 0)),
            status=str(row.get("status", "draft")),
            sent_date=coerce_date(row.get("sent_date")),
            paid_date=coerce_date(row.get("paid_date")),
            method=row.get("method", "") or "",
            on_disk=False, notes=row.get("notes", "") or "",
        ))

    records.sort(key=lambda r: (r.issue_date or date.min, r.number))
    return records, drift


def aging(records: list[Record], ref: date | None = None) -> dict:
    """Sum outstanding (issued/sent) invoices into aging buckets."""
    ref = ref or date.today()
    buckets = {name: Decimal("0") for name, _, _ in AGING_BUCKETS}
    for r in records:
        if not r.outstanding:
            continue
        d = r.days_overdue(ref)
        for name, lo, hi in AGING_BUCKETS:
            if name == "current" and d <= 0:
                buckets[name] += r.total
                break
            if lo <= d <= hi:
                buckets[name] += r.total
                break
    return buckets


def summary(records: list[Record], ref: date | None = None) -> dict:
    ref = ref or date.today()
    outstanding = sum((r.total for r in records if r.outstanding), Decimal("0"))
    paid = sum((r.total for r in records if r.status == "paid"), Decimal("0"))
    overdue = sum((r.total for r in records if r.outstanding and r.days_overdue(ref) > 0), Decimal("0"))
    by_status = {s: Decimal("0") for s in ALL_STATUSES}
    by_client: dict[str, Decimal] = {}
    for r in records:
        by_status[r.status] = by_status.get(r.status, Decimal("0")) + r.total
        if r.outstanding:
            by_client[r.client] = by_client.get(r.client, Decimal("0")) + r.total
    return {
        "outstanding": outstanding, "overdue": overdue, "paid": paid,
        "by_status": by_status, "by_client_outstanding": by_client,
        "aging": aging(records, ref),
    }


FORM_1099_THRESHOLD = Decimal("600")


def year_summary(ws: Workspace, year: int) -> dict:
    """Year-end roll-up: revenue by client, contractor 1099 totals, expenses by category."""
    records, _ = reconcile(ws)
    invoiced: dict[str, Decimal] = {}
    paid: dict[str, Decimal] = {}
    for r in records:
        if r.doc_type == "quote":
            continue
        if r.status != "void" and r.issue_date and r.issue_date.year == year:
            invoiced[r.client] = invoiced.get(r.client, Decimal("0")) + r.total
        if r.status == "paid":
            when = r.paid_date or r.issue_date
            if when and when.year == year:
                paid[r.client] = paid.get(r.client, Decimal("0")) + r.total

    # Contractor payments (1099-NEC: report what you paid each contractor).
    contractors: dict[str, Decimal] = {}
    if ws.contractors_dir.exists():
        for cpath in ws.contractors_dir.glob("*.yml"):
            data = load_yaml(cpath)
            d = coerce_date(data.get("date"))
            if not (d and d.year == year):
                continue
            amount = data.get("amount")
            if amount is None and data.get("hours") and data.get("rate"):
                amount = Decimal(str(data["hours"])) * Decimal(str(data["rate"]))
            name = (data.get("contractor") or {}).get("name", "Unknown")
            contractors[name] = contractors.get(name, Decimal("0")) + Decimal(str(amount or 0))

    # Pass-through expenses by category (handy for Schedule C).
    expenses: dict[str, Decimal] = {}
    if ws.expenses_dir.exists():
        for epath in ws.expenses_dir.glob("*.yml"):
            if epath.name.startswith("_"):
                continue
            data = load_yaml(epath)
            d = coerce_date(data.get("date"))
            if not (d and d.year == year):
                continue
            cat = data.get("category", "other")
            expenses[cat] = expenses.get(cat, Decimal("0")) + Decimal(str(data.get("amount", 0) or 0))

    return {
        "year": year,
        "invoiced": invoiced,
        "paid": paid,
        "total_invoiced": sum(invoiced.values(), Decimal("0")),
        "total_paid": sum(paid.values(), Decimal("0")),
        "contractors": contractors,
        "contractors_1099": {n: a for n, a in contractors.items() if a >= FORM_1099_THRESHOLD},
        "expenses": expenses,
    }


def mark(ws: Workspace, number: str, status: str, *, on: str | None = None,
         method: str = "") -> Record:
    """Set status + dates on a ledger row, creating it from the invoice if needed."""
    if status not in ALL_STATUSES:
        raise SystemExit(f"Unknown status '{status}'. One of: {', '.join(ALL_STATUSES)}")
    when = on or date.today().isoformat()

    ledger = load_yaml(ws.ledger_yml)
    rows = ledger.get("invoices") or []
    row = next((r for r in rows if str(r.get("number")) == number), None)
    if row is None:
        # Synthesize from the invoice on disk.
        recs, _ = reconcile(ws)
        src = next((r for r in recs if r.number == number), None)
        if src is None:
            raise SystemExit(f"Invoice '{number}' not found on disk or in the ledger.")
        row = {
            "number": number, "client": src.client,
            "issue_date": src.issue_date.isoformat() if src.issue_date else "",
            "due_date": src.due_date.isoformat() if src.due_date else "",
            "amount": float(src.total),
        }
        rows.append(row)

    row["status"] = status
    if status == "sent":
        row["sent_date"] = when
    elif status == "paid":
        row["paid_date"] = when
        if method:
            row["method"] = method
        if not row.get("sent_date"):
            row["sent_date"] = when

    ledger["invoices"] = rows
    header = ("# Back Office status ledger — managed by `backoffice mark`.\n"
              "# Statuses: draft | issued | sent | paid | void\n\n")
    ws.ledger_yml.write_text(header + yaml.safe_dump(ledger, sort_keys=False, allow_unicode=True))

    recs, _ = reconcile(ws)
    return next(r for r in recs if r.number == number)
