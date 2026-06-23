"""Tests for backoffice. Run with: pytest (or python -m pytest)."""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from backoffice.config import Workspace, deep_merge
from backoffice import ingest, ledger, scaffold
from backoffice.model import load_invoice, prepare_invoice
from backoffice.money import fmt_money, fmt_qty, fmt_date, to_money
from backoffice.render import render_html

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


@pytest.fixture
def ws():
    return Workspace(EXAMPLES)


# ── money ──────────────────────────────────────────────────────────

def test_money_rounding_half_up():
    assert fmt_money("1234.5") == "$1,234.50"
    assert fmt_money(Decimal("0.005")) == "$0.01"
    assert fmt_money(-50) == "-$50.00"

def test_money_currencies():
    assert fmt_money(1000, "EUR") == "€1,000.00"
    assert fmt_money(1000, "JPY") == "¥1,000"
    assert fmt_money(1000, "CHF") == "CHF 1,000.00"

def test_fmt_qty_and_date():
    assert fmt_qty(1) == "1"
    assert fmt_qty(Decimal("1.50")) == "1.5"
    assert fmt_date("2026-06-01") == "June 1, 2026"

def test_deep_merge():
    base = {"a": {"x": 1, "y": 2}, "b": 3}
    out = deep_merge(base, {"a": {"y": 9}, "c": 4})
    assert out == {"a": {"x": 1, "y": 9}, "b": 3, "c": 4}


# ── model / totals ─────────────────────────────────────────────────

def test_invoice_totals(ws):
    studio, client, raw = load_invoice(ws, EXAMPLES / "invoices/acme/2026-001.yml")
    prepared, warnings = prepare_invoice(ws, studio, client, raw)
    # 8000 retainer + 120 expense pass-through
    assert prepared["total"] == Decimal("8120.00")
    assert prepared["total_fmt"] == "$8,120.00"
    assert len(prepared["expenses"]) == 1

def test_render_html_contains_key_fields(ws):
    html, invoice, warnings = render_html(ws, EXAMPLES / "invoices/acme/2026-001.yml")
    assert "NWS-2026-001-ACME" in html
    assert "Acme Incorporated" in html
    assert "$8,120.00" in html
    assert "Northwind Studio, LLC" in html


# ── ledger / aging ─────────────────────────────────────────────────

def test_reconcile_and_aging(ws):
    records, drift = ledger.reconcile(ws)
    assert len(records) == 1
    rec = records[0]
    assert rec.number == "NWS-2026-001-ACME"
    assert rec.status == "sent"
    assert rec.outstanding is True
    # No drift: ledger amount (8120) matches computed total.
    assert drift == []

def test_aging_buckets(ws):
    records, _ = ledger.reconcile(ws)
    # due 2026-07-01; as of 2026-09-01 it's 62 days overdue → 61-90 bucket.
    s = ledger.summary(records, ref=date(2026, 9, 1))
    assert s["outstanding"] == Decimal("8120.00")
    assert s["overdue"] == Decimal("8120.00")
    assert s["aging"]["61-90"] == Decimal("8120.00")
    assert s["aging"]["current"] == Decimal("0")

def test_drift_detection(ws, tmp_path):
    # Copy the workspace, corrupt the ledger amount, expect drift.
    import shutil
    dst = tmp_path / "wsp"
    shutil.copytree(EXAMPLES, dst)
    led = dst / "_ledger.yml"
    led.write_text(led.read_text().replace("8120.00", "9999.00"))
    records, drift = ledger.reconcile(Workspace(dst))
    assert any("≠ computed" in d for d in drift)


# ── ingest (deterministic) ─────────────────────────────────────────

def test_deterministic_ingest():
    text = (EXAMPLES / "contracts/acme-msa.md").read_text()
    ex = ingest.deterministic_extract(text, studio_name="Northwind Studio, LLC")
    assert ex.client_legal_name == "Acme Incorporated"
    assert ex.payment_terms == "Net 30"
    assert ex.rate == Decimal("8000.00")
    assert ex.rate_unit == "month"
    assert ex.subcontractor_cap == Decimal("5000.00")

def test_ingest_writes_client_yaml(tmp_path):
    import shutil
    ws = Workspace(tmp_path)
    (tmp_path / "studio.yml").write_text("legal_name: Northwind Studio, LLC\n")
    shutil.copytree(EXAMPLES / "contracts", tmp_path / "contracts")
    out, ex = ingest.ingest_contract(ws, tmp_path / "contracts/acme-msa.md")
    assert out.exists()
    assert out.name == "acme-incorporated.yml"
    text = out.read_text()
    assert "Acme Incorporated" in text
    assert "8000" in text


# ── scaffold numbering ─────────────────────────────────────────────

def test_next_number(ws):
    # examples has NWS-2026-001-ACME → next for acme is 002.
    assert scaffold.next_number(ws, 2026, "acme") == "NWS-2026-002-ACME"

def test_quote_numbering_separate_from_invoices(ws):
    assert scaffold.next_number(ws, 2026, "acme", "quote") == "NWS-Q-2026-001-ACME"


# ── new features: quote→invoice, cycle, year-end summary ───────────

def _seed(tmp_path):
    """Copy the examples workspace to a writable temp dir."""
    import shutil
    dst = tmp_path / "wsp"
    shutil.copytree(EXAMPLES, dst)
    return Workspace(dst)

def test_quote_then_accept(tmp_path):
    ws = _seed(tmp_path)
    qpath = scaffold.new_invoice(ws, "acme", doc_type="quote",
                                 service_period="2026-07-01..2026-07-31")
    assert qpath.parent == ws.quotes_dir / "acme"          # quotes live apart
    assert qpath.name == "q-2026-001.yml"                  # distinct from invoice names
    assert "NWS-Q-2026-001-ACME" in qpath.read_text()
    inv_path, src = scaffold.accept_quote(ws, f"acme/{qpath.stem}")
    assert src == "NWS-Q-2026-001-ACME"
    assert inv_path.parent == ws.invoices_dir / "acme"     # accepted → real invoice
    text = inv_path.read_text()
    assert "Converted from quote" in text
    assert "2026-07-01" in text                            # service period carried over

def test_quotes_excluded_from_ar(tmp_path):
    ws = _seed(tmp_path)
    scaffold.new_invoice(ws, "acme", doc_type="quote")
    records, _ = ledger.reconcile(ws)
    assert all(r.doc_type != "quote" for r in records)     # no quotes in receivables

def test_cycle_creates_and_is_idempotent(tmp_path):
    ws = _seed(tmp_path)
    # May 2026 is already billed (invoice covers 2026-05-01) → skipped.
    skipped = scaffold.run_cycle(ws, month="2026-05")
    assert skipped and skipped[0]["status"] == "skipped"
    # A fresh month creates one.
    created = scaffold.run_cycle(ws, month="2026-09")
    assert any(r["status"] == "created" and r["slug"] == "acme" for r in created)
    # Running it again is a no-op.
    again = scaffold.run_cycle(ws, month="2026-09")
    assert all(r["status"] == "skipped" for r in again)

def test_year_summary(tmp_path):
    ws = _seed(tmp_path)
    # Add a paid invoice + a contractor payment in 2026.
    ledger.mark(ws, "NWS-2026-001-ACME", "paid", on="2026-07-02", method="ACH")
    scaffold.add_contractor(ws, invoice="acme/2026-001", name="Jordan Lee",
                            role="Design", amount=1500, date_="2026-05-20",
                            description="Brand work")
    s = ledger.year_summary(ws, 2026)
    # 8000 retainer + 120 expense + 1500 contractor, now all on the paid invoice.
    assert s["total_paid"] == Decimal("9620.00")
    assert s["contractors"]["Jordan Lee"] == Decimal("1500")
    assert "Jordan Lee" in s["contractors_1099"]            # ≥ $600
    assert s["expenses"].get("software") == Decimal("120.00")
