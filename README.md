# Back Office

Plain-text invoicing that lives in a folder, not a SaaS dashboard. Your clients,
invoices, and business identity are YAML files; Back Office turns them into clean,
print-ready invoices and tracks what you're owed. Drive it from the terminal
(`backoffice`, or the short alias `bo`) — or point Claude at the folder and just
talk to it.

> **Not a terminal person?** Download this repo, open the folder with Claude, and
> say *"help me get started."* It installs the tool, sets up your details, and runs
> everything. See [GETTING_STARTED.md](GETTING_STARTED.md); the agent instructions
> live in [CLAUDE.md](CLAUDE.md).

## What it does

- **Read a contract → set up a client.** `ingest` pulls the parties, rate,
  payment terms, and subcontractor cap out of a PDF/MD/TXT contract (regex by
  default; optional Claude pass for messy ones).
- **Make invoices.** Auto-numbered, inheriting each client's default line items,
  with service periods and tax.
- **Pass-throughs.** Attach reimbursable expenses and subcontractor costs with
  their receipts; warns if you exceed a contractual cap.
- **Render.** Print-ready HTML or a headless PDF, themed to your brand color, with
  ACH/check details and W-9.
- **Quotes → invoices.** Send an estimate, then `accept` it to spin up the real
  invoice.
- **Recurring billing.** `cycle` generates this month's invoices for every
  retainer client; safe to re-run.
- **Know what you're owed.** `status` shows outstanding, overdue, and aging
  buckets; `mark` moves invoices through draft → sent → paid.
- **Year-end.** `summary` rolls up revenue per client, flags contractors who need
  a 1099-NEC, and totals expenses by category.

Everything is version-controllable and diffable, money math is exact decimals so
totals reproduce, and secrets (bank, EIN) stay in a gitignored file.

## Install

```bash
pipx install .        # or: make install   (falls back to a local venv)
backoffice init       # scaffold a workspace + a sample client/invoice
```

Needs Python 3.10+. Optional extras: `pip install '.[pdf]'` for headless PDF,
`'.[llm]'` for Claude-assisted contract reading.

## Try it

```bash
backoffice ingest contract.pdf                            # contract → client
backoffice new acme                                       # this month's invoice
backoffice expense --invoice acme/2026-001 --vendor OpenAI --amount 200
backoffice pdf acme/2026-001                              # print-ready PDF
backoffice mark NWS-2026-001-ACME paid --method ACH
backoffice status                                         # who owes you, and how late
```

Every command has a `--help`, and `bo` is shorthand for `backoffice`. Full
walkthrough: [GETTING_STARTED.md](GETTING_STARTED.md).

## Keeping secrets safe

Your real bank and tax-ID numbers go only in `studio.local.yml`, which is
gitignored. The bundled `examples/` dataset is fully synthetic (Northwind Studio
billing Acme Inc.), so the repo runs out of the box without exposing anyone's
numbers.

## License

MIT. Built by [Matty Mo Studio](https://themostfamousartist.com).
