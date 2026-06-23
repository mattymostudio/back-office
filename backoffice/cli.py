"""backoffice — command-line entry point.

    backoffice init                     scaffold a workspace here
    backoffice new <client>             scaffold the next invoice
    backoffice quote <client>           scaffold an estimate
    backoffice accept <quote>           turn an accepted quote into an invoice
    backoffice cycle                    generate monthly invoices for recurring clients
    backoffice expense --invoice ...    attach a pass-through expense
    backoffice contractor --invoice ... attach a subcontractor
    backoffice render [<inv>|--all]     render invoice(s) to HTML
    backoffice pdf <inv>                render straight to PDF (needs [pdf] extra)
    backoffice ingest <contract>        read a contract → client YAML
    backoffice status                   accounts-receivable overview
    backoffice summary [<year>]         year-end revenue / 1099 / expense roll-up
    backoffice mark <number> <status>   set draft/issued/sent/paid/void
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from . import __version__, ingest as ingest_mod, ledger as ledger_mod, scaffold
from .config import Workspace
from .model import find_all_invoices
from .money import fmt_money

GREEN, DIM, BOLD, YELLOW, RESET = "\033[32m", "\033[2m", "\033[1m", "\033[33m", "\033[0m"


def _ws() -> Workspace:
    return Workspace.discover()


def _need_ws(ws: Workspace) -> None:
    if not ws.exists():
        raise SystemExit("No workspace here (studio.yml not found). Run `backoffice init` first.")


# ── commands ───────────────────────────────────────────────────────

def cmd_init(args) -> int:
    ws = Workspace(Path(args.dir).resolve()) if args.dir else _ws()
    written = scaffold.init_workspace(ws, force=args.force)
    print(f"{GREEN}✓{RESET} workspace at {ws.root}")
    for p in written:
        print(f"  + {p.relative_to(ws.root)}")
    print(f"\nNext: edit studio.yml, then `backoffice render acme/2026-001` "
          f"(or open the rendered HTML).")
    print(f"{DIM}Put real bank/EIN in studio.local.yml (copy studio.local.example.yml).{RESET}")
    return 0


def cmd_new(args, doc_type="invoice") -> int:
    ws = _ws(); _need_ws(ws)
    path = scaffold.new_invoice(
        ws, args.client, issue_date=args.issue_date, due_date=args.due_date,
        service_period=args.service_period, number=args.number,
        payment_terms=args.payment_terms, notes=args.notes, doc_type=doc_type)
    rel = path.relative_to(ws.root)
    print(f"{GREEN}✓{RESET} {path.stem}  →  {rel}")
    stub = f"{args.client}/{path.stem}"
    print(f"  edit it, then: {BOLD}backoffice render {stub}{RESET}")
    return 0


def cmd_expense(args) -> int:
    ws = _ws(); _need_ws(ws)
    inv, fname = scaffold.add_expense(
        ws, invoice=args.invoice, vendor=args.vendor, amount=args.amount,
        date_=args.date, description=args.description, category=args.category,
        receipt=args.receipt, client=args.client, pre_approved=args.pre_approved,
        pre_approval_ref=args.pre_approval_ref, notes=args.notes)
    print(f"{GREEN}✓{RESET} expense   expenses/{fname}  (${args.amount} — {args.vendor})")
    if not args.no_render:
        out, warns = _render_one(ws, inv)
        _print_render(ws, out, warns)
    return 0


def cmd_contractor(args) -> int:
    ws = _ws(); _need_ws(ws)
    inv, fname = scaffold.add_contractor(
        ws, invoice=args.invoice, name=args.name, role=args.role, email=args.email,
        amount=args.amount, hours=args.hours, rate=args.rate, date_=args.date,
        description=args.description, client=args.client, pre_approved=args.pre_approved,
        pre_approval_ref=args.pre_approval_ref, agreement=args.agreement,
        contractor_invoice=args.contractor_invoice, notes=args.notes)
    print(f"{GREEN}✓{RESET} contractor  contractors/{fname}  ({args.name})")
    if not args.no_render:
        out, warns = _render_one(ws, inv)
        _print_render(ws, out, warns)
    return 0


def _render_one(ws, invoice_path):
    from .render import render_to_file, sync_forms
    sync_forms(ws)
    return render_to_file(ws, invoice_path)


def _print_render(ws, out, warns):
    print(f"{GREEN}✓{RESET} render    {out.relative_to(ws.root)}")
    for w in warns:
        print(f"  {YELLOW}⚠{RESET}  {w}", file=sys.stderr)


def cmd_render(args) -> int:
    ws = _ws(); _need_ws(ws)
    from .render import render_to_file, sync_forms
    if args.all:
        paths = find_all_invoices(ws)
    else:
        if not args.invoice:
            raise SystemExit("Pass an invoice (e.g. acme/2026-001) or --all.")
        paths = [scaffold.resolve_invoice(ws, args.invoice)]
    if not paths:
        raise SystemExit("No invoices found.")
    sync_forms(ws)
    any_done = False
    for p in paths:
        out, warns = render_to_file(ws, p)
        _print_render(ws, out, warns)
        any_done = True
    if args.open and any_done:
        import subprocess
        subprocess.run(["open", str(out)], check=False)
    return 0


def cmd_pdf(args) -> int:
    ws = _ws(); _need_ws(ws)
    from .pdf import render_pdf
    p = scaffold.resolve_invoice(ws, args.invoice)
    out, warns = render_pdf(ws, p)
    print(f"{GREEN}✓{RESET} pdf       {out.relative_to(ws.root)}")
    for w in warns:
        print(f"  {YELLOW}⚠{RESET}  {w}", file=sys.stderr)
    if args.open:
        import subprocess
        subprocess.run(["open", str(out)], check=False)
    return 0


def cmd_ingest(args) -> int:
    ws = _ws(); _need_ws(ws)
    out, ex = ingest_mod.ingest_contract(
        ws, Path(args.contract).expanduser(), slug=args.slug,
        use_llm=args.llm, model=args.model, force=args.force)
    print(f"{GREEN}✓{RESET} client    {out.relative_to(ws.root)}")
    print(f"  party     {ex.client_legal_name or '—'}")
    print(f"  terms     {ex.payment_terms or '—'}")
    print(f"  rate      {fmt_money(ex.rate) if ex.rate is not None else '—'}"
          f"{('/' + ex.rate_unit) if ex.rate and ex.rate_unit else ''}")
    if ex.subcontractor_cap is not None:
        print(f"  sub cap   {fmt_money(ex.subcontractor_cap)}/month")
    for n in ex.notes:
        print(f"  {DIM}· {n}{RESET}")
    print(f"\n  {BOLD}Review {out.relative_to(ws.root)} before billing{RESET} — [fill in] fields need you.")
    return 0


def cmd_accept(args) -> int:
    ws = _ws(); _need_ws(ws)
    path, src = scaffold.accept_quote(
        ws, args.quote, issue_date=args.issue_date, due_date=args.due_date,
        number=args.number, payment_terms=args.payment_terms)
    print(f"{GREEN}✓{RESET} accepted  {src} → {BOLD}{path.stem}{RESET}  ({path.relative_to(ws.root)})")
    print(f"  render: {BOLD}backoffice render {path.parent.name}/{path.stem}{RESET}")
    return 0


def cmd_cycle(args) -> int:
    ws = _ws(); _need_ws(ws)
    results = scaffold.run_cycle(ws, month=args.month, issue_date=args.issue_date)
    if not results:
        print("No recurring clients found. Add `recurring: true` to a client file.")
        return 0
    created = [r for r in results if r["status"] == "created"]
    for r in created:
        print(f"{GREEN}✓{RESET} created   {r['slug']}/{r['ref']}")
    for r in (r for r in results if r["status"] == "skipped"):
        print(f"{DIM}· skipped   {r['slug']}/{r['ref']} (already billed this month){RESET}")
    if created and not args.no_render:
        from .render import render_to_file, sync_forms
        sync_forms(ws)
        for r in created:
            out, warns = render_to_file(ws, r["path"])
            _print_render(ws, out, warns)
    return 0


def cmd_summary(args) -> int:
    ws = _ws(); _need_ws(ws)
    year = args.year or date.today().year
    s = ledger_mod.year_summary(ws, year)
    print(f"{BOLD}{year} year-end summary{RESET}")
    print(f"  invoiced      {fmt_money(s['total_invoiced'])}")
    print(f"  collected     {fmt_money(s['total_paid'])}")
    if s["paid"]:
        print(f"\n  {DIM}revenue collected by client{RESET}")
        for c, amt in sorted(s["paid"].items(), key=lambda kv: -kv[1]):
            print(f"    {c:<22}{fmt_money(amt):>14}")
    if s["contractors"]:
        print(f"\n  {DIM}contractor payments (1099-NEC flagged at ≥ $600){RESET}")
        for n, amt in sorted(s["contractors"].items(), key=lambda kv: -kv[1]):
            flag = f"  {YELLOW}● 1099-NEC{RESET}" if n in s["contractors_1099"] else ""
            print(f"    {n:<22}{fmt_money(amt):>14}{flag}")
    if s["expenses"]:
        print(f"\n  {DIM}pass-through expenses by category{RESET}")
        for c, amt in sorted(s["expenses"].items(), key=lambda kv: -kv[1]):
            print(f"    {c:<22}{fmt_money(amt):>14}")
    return 0


def cmd_status(args) -> int:
    ws = _ws(); _need_ws(ws)
    records, drift = ledger_mod.reconcile(ws)
    ref = date.today()
    s = ledger_mod.summary(records, ref)

    if not records:
        print("No invoices yet.")
        return 0

    print(f"{BOLD}Accounts receivable{RESET}  ({ref.isoformat()})")
    print(f"  outstanding   {fmt_money(s['outstanding'])}"
          f"   ({fmt_money(s['overdue'])} overdue)")
    print(f"  paid          {fmt_money(s['paid'])}")

    aging = s["aging"]
    if s["outstanding"] > 0:
        cells = "   ".join(f"{name} {fmt_money(aging[name])}" for name, _, _ in ledger_mod.AGING_BUCKETS)
        print(f"  aging         {cells}")

    print(f"\n  {DIM}{'number':<24}{'client':<12}{'status':<8}{'due':<12}{'total':>12}{RESET}")
    for r in records:
        flag = ""
        if r.outstanding and r.days_overdue(ref) > 0:
            flag = f" {YELLOW}● {r.days_overdue(ref)}d overdue{RESET}"
        due = r.due_date.isoformat() if r.due_date else "—"
        print(f"  {r.number:<24}{r.client:<12}{r.status:<8}{due:<12}"
              f"{fmt_money(r.total, r.currency):>12}{flag}")

    for d in drift:
        print(f"  {YELLOW}⚠{RESET}  {d}", file=sys.stderr)
    return 0


def cmd_mark(args) -> int:
    ws = _ws(); _need_ws(ws)
    rec = ledger_mod.mark(ws, args.number, args.status, on=args.date, method=args.method)
    when = ""
    if args.status == "sent" and rec.sent_date:
        when = f" on {rec.sent_date.isoformat()}"
    elif args.status == "paid" and rec.paid_date:
        when = f" on {rec.paid_date.isoformat()}" + (f" via {rec.method}" if rec.method else "")
    print(f"{GREEN}✓{RESET} {rec.number} → {BOLD}{rec.status}{RESET}{when}")
    return 0


# ── parser ─────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="backoffice", description="Plain-text invoicing from YAML.")
    p.add_argument("--version", action="version", version=f"backoffice {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("init", help="scaffold a workspace in the current directory")
    pi.add_argument("--dir", help="target directory (default: here)")
    pi.add_argument("--force", action="store_true", help="write missing pieces into an existing workspace")
    pi.set_defaults(func=cmd_init)

    for name, dt, helptext in (("new", "invoice", "scaffold the next invoice"),
                               ("quote", "quote", "scaffold an estimate/quote")):
        pn = sub.add_parser(name, help=helptext)
        pn.add_argument("client", help="client slug (clients/<slug>.yml)")
        pn.add_argument("--issue-date", help="YYYY-MM-DD (default: today)")
        pn.add_argument("--due-date", help="YYYY-MM-DD (default: from terms)")
        pn.add_argument("--service-period", help="YYYY-MM-DD..YYYY-MM-DD")
        pn.add_argument("--number", help="override the auto-number")
        pn.add_argument("--payment-terms", help="e.g. 'Net 0', 'Net 30'")
        pn.add_argument("--notes", help="free-text notes")
        pn.set_defaults(func=lambda a, dt=dt: cmd_new(a, dt))

    pe = sub.add_parser("expense", help="attach a pass-through expense + receipt")
    pe.add_argument("--invoice", required=True, help="<slug>/<file> or path")
    pe.add_argument("--vendor", required=True)
    pe.add_argument("--amount", required=True)
    pe.add_argument("--date", default=date.today().isoformat())
    pe.add_argument("--description", default="")
    pe.add_argument("--category", default="software",
                    choices=["software", "api-credits", "travel", "hardware", "other"])
    pe.add_argument("--receipt")
    pe.add_argument("--client")
    pe.add_argument("--pre-approved", action="store_true")
    pe.add_argument("--pre-approval-ref", default="")
    pe.add_argument("--notes", default="")
    pe.add_argument("--no-render", action="store_true")
    pe.set_defaults(func=cmd_expense)

    pc = sub.add_parser("contractor", help="attach a subcontractor pass-through")
    pc.add_argument("--invoice", required=True)
    pc.add_argument("--name", required=True)
    pc.add_argument("--role", default="")
    pc.add_argument("--email", default="")
    pc.add_argument("--amount", type=float)
    pc.add_argument("--hours", type=float)
    pc.add_argument("--rate", type=float)
    pc.add_argument("--date", default=date.today().isoformat())
    pc.add_argument("--description", default="")
    pc.add_argument("--client")
    pc.add_argument("--pre-approved", action="store_true")
    pc.add_argument("--pre-approval-ref", default="")
    pc.add_argument("--agreement")
    pc.add_argument("--contractor-invoice", dest="contractor_invoice")
    pc.add_argument("--notes", default="")
    pc.add_argument("--no-render", action="store_true")
    pc.set_defaults(func=cmd_contractor)

    pa = sub.add_parser("accept", help="convert an accepted quote into an invoice")
    pa.add_argument("quote", help="quote ref: <slug>/<file> or number")
    pa.add_argument("--issue-date", help="YYYY-MM-DD (default: today)")
    pa.add_argument("--due-date", help="YYYY-MM-DD (default: from terms)")
    pa.add_argument("--number", help="override the auto-number")
    pa.add_argument("--payment-terms")
    pa.set_defaults(func=cmd_accept)

    pcy = sub.add_parser("cycle", help="generate this month's invoices for recurring clients")
    pcy.add_argument("--month", help="YYYY-MM (default: current month)")
    pcy.add_argument("--issue-date", help="YYYY-MM-DD (default: today)")
    pcy.add_argument("--no-render", action="store_true")
    pcy.set_defaults(func=cmd_cycle)

    psm = sub.add_parser("summary", help="year-end revenue, 1099, and expense roll-up")
    psm.add_argument("year", nargs="?", type=int, help="year (default: this year)")
    psm.set_defaults(func=cmd_summary)

    pr = sub.add_parser("render", help="render invoice(s) to HTML")
    pr.add_argument("invoice", nargs="?", help="<slug>/<file> (omit with --all)")
    pr.add_argument("--all", action="store_true")
    pr.add_argument("--open", action="store_true", help="open the result (macOS)")
    pr.set_defaults(func=cmd_render)

    pp = sub.add_parser("pdf", help="render straight to PDF (needs backoffice[pdf])")
    pp.add_argument("invoice")
    pp.add_argument("--open", action="store_true")
    pp.set_defaults(func=cmd_pdf)

    pg = sub.add_parser("ingest", help="read a contract → clients/<slug>.yml")
    pg.add_argument("contract", help="path to a .md/.txt/.pdf contract")
    pg.add_argument("--slug", help="client slug (default: derived from the party name)")
    pg.add_argument("--llm", action="store_true", help="use Claude for messy contracts (needs [llm] extra + API key)")
    pg.add_argument("--model", help=f"override the LLM model (default: {ingest_mod.DEFAULT_LLM_MODEL})")
    pg.add_argument("--force", action="store_true")
    pg.set_defaults(func=cmd_ingest)

    ps = sub.add_parser("status", help="accounts-receivable overview")
    ps.set_defaults(func=cmd_status)

    pm = sub.add_parser("mark", help="set an invoice's status")
    pm.add_argument("number", help="invoice number")
    pm.add_argument("status", choices=ledger_mod.ALL_STATUSES)
    pm.add_argument("--date", help="YYYY-MM-DD (default: today)")
    pm.add_argument("--method", default="", help="for 'paid': ACH | check | wire")
    pm.set_defaults(func=cmd_mark)

    return p


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
