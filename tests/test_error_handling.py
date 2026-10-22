"""Input errors stay actionable without hiding unrelated programming failures."""

import builtins
import shutil
import sys
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from backoffice import ingest, ledger, pdf
from backoffice.config import Workspace

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


@pytest.mark.parametrize("invoice", [
    "client: [\n",
    "- not a mapping\n",
    "client: acme\nnumber: INVALID\n",
    ("client: acme\nnumber: INVALID\nissue_date: 2026-06-01\n"
     "line_items:\n  - rate: invalid\n"),
])
def test_reconcile_reports_bad_invoice_and_keeps_valid_total(tmp_path, invoice):
    root = tmp_path / "workspace"
    shutil.copytree(EXAMPLES, root)
    (root / "invoices/acme/invalid.yml").write_text(invoice)

    records, drift = ledger.reconcile(Workspace(root))

    assert len(records) == 1
    assert records[0].number == "NWS-2026-001-ACME"
    assert records[0].total == Decimal("8120.00")
    assert len(drift) == 1
    assert drift[0].startswith("invalid.yml: failed to load (")


def test_reconcile_reports_unreadable_invoice(monkeypatch):
    def cannot_read(*_args):
        raise PermissionError("invoice is unreadable")

    monkeypatch.setattr(ledger, "load_invoice", cannot_read)
    _records, drift = ledger.reconcile(Workspace(EXAMPLES))
    assert drift == ["2026-001.yml: failed to load (invoice is unreadable)"]


def test_reconcile_does_not_hide_unexpected_error(monkeypatch):
    def unexpected_failure(*_args):
        raise RuntimeError("unexpected calculation failure")

    monkeypatch.setattr(ledger, "prepare_invoice", unexpected_failure)
    with pytest.raises(RuntimeError, match="unexpected calculation failure"):
        ledger.reconcile(Workspace(EXAMPLES))


@pytest.mark.parametrize("amount", ["$,,,", "$" + "9" * 40])
def test_parse_amount_rejects_invalid_decimal(amount):
    assert ingest._parse_amount(amount) is None


def test_parse_amount_preserves_exact_cents():
    assert ingest._parse_amount("Fee: $200.30") == Decimal("200.30")


def test_parse_amount_does_not_hide_unexpected_error(monkeypatch):
    def unexpected_failure(_value):
        raise RuntimeError("unexpected money failure")

    monkeypatch.setattr(ingest, "to_money", unexpected_failure)
    with pytest.raises(RuntimeError, match="unexpected money failure"):
        ingest._parse_amount("$200.30")


def test_pdf_contract_missing_dependency(monkeypatch, tmp_path):
    monkeypatch.setattr(ingest.shutil, "which", lambda _name: None)
    monkeypatch.setitem(sys.modules, "pypdf", None)
    with pytest.raises(SystemExit, match="pip install pypdf"):
        ingest.read_contract_text(tmp_path / "contract.pdf")


class PdfReadFailure(Exception):
    pass


class PdfDependencyFailure(Exception):
    pass


def test_pdf_contract_reads_all_pages(monkeypatch, tmp_path):
    monkeypatch.setattr(ingest.shutil, "which", lambda _name: None)
    reader = SimpleNamespace(pages=[
        SimpleNamespace(extract_text=lambda: "First page"),
        SimpleNamespace(extract_text=lambda: None),
        SimpleNamespace(extract_text=lambda: "Last page"),
    ])
    monkeypatch.setitem(sys.modules, "pypdf", SimpleNamespace(PdfReader=lambda _path: reader))
    assert ingest.read_contract_text(tmp_path / "contract.pdf") == "First page\n\nLast page"


@pytest.mark.parametrize("error", [
    PdfReadFailure("invalid PDF"),
    PdfDependencyFailure("encryption dependency missing"),
    OSError("cannot read PDF"),
    ValueError("invalid PDF value"),
])
def test_pdf_contract_expected_errors_keep_guidance(monkeypatch, tmp_path, error):
    def cannot_read(_path):
        raise error

    monkeypatch.setattr(ingest.shutil, "which", lambda _name: None)
    monkeypatch.setitem(sys.modules, "pypdf", SimpleNamespace(
        PdfReader=cannot_read,
        errors=SimpleNamespace(PyPdfError=PdfReadFailure, DependencyError=PdfDependencyFailure),
    ))
    with pytest.raises(SystemExit, match="pip install pypdf"):
        ingest.read_contract_text(tmp_path / "contract.pdf")


def test_pdf_contract_unexpected_errors_propagate(monkeypatch, tmp_path):
    def unexpected_failure(_path):
        raise RuntimeError("unexpected PDF failure")

    monkeypatch.setattr(ingest.shutil, "which", lambda _name: None)
    monkeypatch.setitem(sys.modules, "pypdf", SimpleNamespace(
        PdfReader=unexpected_failure,
        errors=SimpleNamespace(PyPdfError=PdfReadFailure, DependencyError=PdfDependencyFailure),
    ))
    with pytest.raises(RuntimeError, match="unexpected PDF failure"):
        ingest.read_contract_text(tmp_path / "contract.pdf")


@pytest.mark.parametrize("error", [ImportError("not installed"), OSError("native library missing")])
def test_weasyprint_missing_dependencies_keep_guidance(monkeypatch, error):
    real_import = builtins.__import__

    def import_without_weasyprint(name, *args, **kwargs):
        if name == "weasyprint":
            raise error
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", import_without_weasyprint)
    with pytest.raises(SystemExit, match="PDF export needs WeasyPrint"):
        pdf._require_weasyprint()


def test_weasyprint_unexpected_errors_propagate(monkeypatch):
    real_import = builtins.__import__

    def import_without_weasyprint(name, *args, **kwargs):
        if name == "weasyprint":
            raise RuntimeError("unexpected PDF import failure")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", import_without_weasyprint)
    with pytest.raises(RuntimeError, match="unexpected PDF import failure"):
        pdf._require_weasyprint()
