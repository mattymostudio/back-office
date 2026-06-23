# Operating Back Office (for Claude)

You are helping someone run **Back Office**, a plain-text invoicing tool, from
this folder. They may not be technical — your job is to run the commands for
them. Read this file, then drive the tool through the terminal. Explain what you
did in plain language; don't make them read YAML unless they want to.

**Golden rule:** all billing data is plain YAML files in this folder. Real bank
and tax-ID numbers go **only** in `studio.local.yml`, which is gitignored. Never
put them in `studio.yml`.

---

## First: make sure the tool runs

Check whether the `backoffice` command exists (`backoffice --version`). If not,
install it — try these in order and stop at the first that works. (`bo` is a
shorter alias for `backoffice` once installed — use whichever you like.)

1. `pipx install .` — cleanest; puts `backoffice` on the PATH.
2. `make install` — does the pipx-or-venv dance for you.
3. Venv fallback: `python3 -m venv .venv && .venv/bin/pip install .` — then call
   the tool as `.venv/bin/backoffice` everywhere below.
4. Zero-install fallback (needs only PyYAML + Jinja2):
   `python3 -m pip install --user pyyaml jinja2`, then run the tool as
   `python3 -m backoffice` instead of `backoffice`.

If a command later errors with "No module named weasyprint" or "needs the
Anthropic SDK", that's an **optional** feature — install the extra it names
(`pip install 'backoffice[pdf]'` or `'backoffice[llm]'`) or use the documented
fallback (browser Print-to-PDF; deterministic ingest).

---

## First-time setup interview

If there's no `studio.yml` yet, run `backoffice init`, then fill in who they are.
Ask for these and edit `studio.yml`:

- **Legal name** of their business (e.g. "Jane Doe Design, LLC") and a short name
- **Mailing address**, **phone**, **email**, **website**
- **Who signs** invoices (name + title)
- **Brand accent color** (a hex like `#1f6f5c`) and optional font — optional, looks nicer
- **Invoice number prefix** (e.g. their initials) under `numbering.prefix`

Then handle secrets separately: copy `studio.local.example.yml` to
`studio.local.yml` and fill in their **bank ACH details** and **EIN/Tax ID**.
Tell them this file stays on their machine and is never committed. Do **not**
print these values back in chat.

When done, render the sample invoice so they see it working:
`backoffice render acme/2026-001 --open` (or open `out/acme/...html` and Print →
Save as PDF).

---

## Everyday tasks → what to run

| They say… | You run |
|---|---|
| "Set up a new client" (from a contract) | `backoffice ingest path/to/contract.pdf` — then open `clients/<slug>.yml`, fill any `[fill in]` blanks with them, confirm the rate/terms are right |
| "Set up a new client" (no contract) | Copy `clients/acme.yml` to `clients/<slug>.yml` and fill it in with them |
| "Invoice <client> for last month" | `backoffice new <slug> --service-period <start>..<end>`, then edit line items if needed, then `backoffice render <slug>/<file>` |
| "Add an expense to that invoice" | `backoffice expense --invoice <slug>/<file> --vendor "…" --amount N --date YYYY-MM-DD --receipt path` |
| "Add a subcontractor" | `backoffice contractor --invoice <slug>/<file> --name "…" --amount N --date YYYY-MM-DD` |
| "Send me a quote/estimate" | `backoffice quote <slug>` → edit → `backoffice render <slug>/q-<file>` |
| "They accepted the quote" | `backoffice accept <slug>/q-<file>` (makes a real invoice) |
| "Run this month's recurring invoices" | `backoffice cycle` (bills every client marked `recurring: true`) |
| "Make a PDF" | `backoffice pdf <slug>/<file>` (or open the HTML and Print → Save as PDF) |
| "I emailed it" | `backoffice mark <NUMBER> sent` |
| "They paid" | `backoffice mark <NUMBER> paid --method ACH` |
| "Who owes me money?" | `backoffice status` |
| "How much did I make this year / who needs a 1099?" | `backoffice summary` |

Invoice/quote references are `<client-slug>/<filename-without-.yml>` (e.g.
`acme/2026-002`). Invoice **numbers** (e.g. `NWS-2026-002-ACME`) are what `mark`
and `summary` use — `status` shows both.

---

## Guardrails

- **Marking `sent` or `paid` is a real-world claim.** Confirm with the person
  before you run it, and don't invent a payment that didn't happen.
- **After `ingest`, always review the generated client file together.** It's a
  best-effort read of a contract. Anything it couldn't find is `[fill in]`. Get
  the rate, payment terms, and legal name right before billing against it.
- **Never print or echo bank/EIN/SSN values in chat.** Edit `studio.local.yml`
  silently and confirm "done" instead.
- **Don't guess dollar amounts.** If you don't know a rate or expense, ask.
- When they're ready to back things up: `git init` here. The included
  `.gitignore` keeps `studio.local.yml` and their live data out of Git by
  default — point that out so secrets don't get pushed.
- After a batch of changes, you can re-render everything with
  `backoffice render --all` and sanity-check with `backoffice status`.

---

## Where things live

```
studio.yml          their identity, branding, numbering   (safe to commit)
studio.local.yml    bank + EIN                              (gitignored — secret)
clients/<slug>.yml  one per client (terms, default line items, `recurring:`)
invoices/<slug>/    one YAML per invoice
quotes/<slug>/      estimates (q-…); become invoices via `accept`
expenses/ contractors/ receipts/   pass-throughs + their receipts
contracts/          contracts you can `ingest`
forms/              their W-9 etc.
out/                rendered HTML/PDF (regenerated; gitignored)
_ledger.yml         invoice status: draft → issued → sent → paid → void
```

Full human docs are in `README.md`. The command list is `backoffice --help`.
