# Back Office

**Plain-text, Git-friendly invoicing.** Read a contract, render a print-ready
invoice or PDF, and track what you're owed — with your billing data as
version-controllable YAML instead of a SaaS silo.

Built for freelancers, consultants, and small studios who'd rather `git commit`
their invoices than rent another dashboard.

> **Not a terminal person?** Download this repo as a ZIP, open the folder with
> Claude, and say *"help me get started."* Claude installs the tool, sets up your
> details, and runs everything for you — see [GETTING_STARTED.md](GETTING_STARTED.md).
> The agent instructions live in [CLAUDE.md](CLAUDE.md).

```
$ backoffice ingest msa.pdf          # contract → client setup
$ backoffice new acme                # scaffold the month's invoice
$ backoffice expense --invoice acme/2026-001 --vendor OpenAI --amount 200 --receipt ~/r.pdf
$ backoffice pdf acme/2026-001       # print-ready PDF
$ backoffice mark NWS-2026-001-ACME paid --method ACH
$ backoffice status                  # who owes you what, and how late
```

---

## Why

Invoicing tools are either a heavy SaaS subscription or a Word template you
copy-paste and fat-finger. Back Office is the middle path: your studio identity,
clients, and invoices are small YAML files. A renderer turns them into a clean,
print-optimized invoice. A ledger tracks status and ages your receivables. Every
number is computed in Python with exact decimal math, so totals are reproducible
and diffable. Because it's just files, it lives in your own repo, backs up with
everything else, and never holds your data hostage.

## Install

```bash
pipx install backoffice          # or: pip install backoffice
backoffice init                  # scaffold a workspace in the current dir
```

Optional extras:

```bash
pip install 'backoffice[pdf]'    # headless PDF export (WeasyPrint; macOS: brew install pango)
pip install 'backoffice[llm]'    # contract reading via Claude (needs ANTHROPIC_API_KEY)
```

Core needs only Python 3.10+, PyYAML, and Jinja2. Every command is also available
as the shorter alias `bo` (e.g. `bo status`).

## Quickstart

```bash
backoffice init                              # creates studio.yml + a sample Acme client + first invoice
# edit studio.yml — your name, address, branding, numbering
backoffice render acme/2026-001 --open       # render to out/acme/<number>.html, open it
```

Open the HTML and **Print → Save as PDF**, or run `backoffice pdf acme/2026-001`
for a headless export.

## Workspace layout

```
studio.yml            your identity, payment info, branding   (safe to commit)
studio.local.yml      real bank / EIN / SSN                    (gitignored)
clients/<slug>.yml    one per client: terms, address, default line items, recurring flag
invoices/<slug>/      one YAML per invoice; inherits client defaults
quotes/<slug>/        estimates (q-…); become invoices via `backoffice accept`
expenses/             pass-through expenses (with receipts)
contractors/          subcontractor pass-throughs
receipts/             attached receipt / agreement PDFs
forms/                your W-9 and other downloadable forms
contracts/            executed + draft contracts (read by `backoffice ingest`)
out/                  rendered HTML/PDF (regenerated; gitignored)
_ledger.yml           invoice status: draft → issued → sent → paid → void
```

## Commands

| Command | Does |
|---|---|
| `backoffice init` | Scaffold a fresh workspace with a sample client + invoice |
| `backoffice ingest <contract>` | Read a `.pdf`/`.md`/`.txt` contract → `clients/<slug>.yml` |
| `backoffice new <client>` | Scaffold the next sequential invoice |
| `backoffice quote <client>` | Scaffold an estimate (renders as "Estimate", no bank details) |
| `backoffice accept <quote>` | Convert an accepted quote into a real invoice |
| `backoffice cycle` | Generate this month's invoices for every `recurring: true` client |
| `backoffice expense --invoice … --vendor … --amount … --receipt …` | Attach a pass-through expense + receipt, re-render |
| `backoffice contractor --invoice … --name … --amount …` | Attach a subcontractor pass-through |
| `backoffice render <inv>` / `--all` | Render invoice(s) to HTML |
| `backoffice pdf <inv>` | Render straight to PDF (needs `[pdf]` extra) |
| `backoffice status` | Accounts-receivable overview: outstanding, overdue, aging buckets |
| `backoffice summary [<year>]` | Year-end roll-up: revenue by client, 1099-NEC contractor totals, expenses by category |
| `backoffice mark <number> sent\|paid\|void` | Update status + payment metadata |

## Reading contracts

`backoffice ingest` extracts the billing setup — parties, rate, payment terms,
subcontractor cap, term dates — and writes a `clients/<slug>.yml` for you to
review:

```bash
backoffice ingest contracts/acme-msa.pdf            # deterministic, no API key
backoffice ingest contracts/messy.pdf --llm         # Claude reads tricky contracts
```

The deterministic pass works for everyone with no dependencies beyond a PDF text
extractor. The optional `--llm` flag uses Claude for contracts the regex pass
can't parse cleanly. Either way, **review the generated file before billing** —
anything it couldn't find is left as a `[fill in]` placeholder (rendered in amber
on the invoice so it's obvious).

## Branding

Theme every invoice from `studio.yml` without touching the template:

```yaml
branding:
  accent: "#1f6f5c"        # headings, totals, the print button
  font: 'Georgia, serif'   # any CSS font stack
numbering:
  prefix: NWS              # invoices become NWS-2026-001-CLIENT
```

Want a fully custom layout? Drop a `templates/invoice.html.j2` in your workspace
and it overrides the built-in one.

## Recurring billing & quotes

Mark a client `recurring: true` and `backoffice cycle` will generate its invoice
for the current month (`--month YYYY-MM` for a specific one). It's idempotent —
a client already billed for that month is skipped — so it's safe to run on a
schedule or by hand.

Send an estimate with `backoffice quote <client>`; it renders as "Estimate" with
no bank details. When the client says yes, `backoffice accept <slug>/q-<file>`
copies the line items into a real, sequentially-numbered invoice.

## Year-end

`backoffice summary` rolls up the year: revenue invoiced and collected per
client, total paid to each subcontractor with **1099-NEC** flags at the $600
threshold, and pass-through expenses by category for your Schedule C.

## Keeping secrets out of Git

This is the one thing to get right. `backoffice init` writes a `.gitignore` that
keeps `studio.local.yml` (and, by default, your live data dirs) out of version
control. Put your **bank routing/account numbers and EIN in `studio.local.yml`**,
never in `studio.yml`. The example `examples/` dataset ships with synthetic data
(Northwind Studio billing Acme Inc.) so the repo renders out of the box without
exposing anyone's real numbers.

## Development

```bash
pip install -e '.[dev]'
python -m pytest -q
BACKOFFICE_HOME=examples backoffice render --all   # smoke-test against demo data
```

## License

MIT. Built by [Matty Mo Studio](https://themostfamousartist.com).
