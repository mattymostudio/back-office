# Getting started

Three ways in, easiest first.

## 1. Point Claude at it (no terminal knowledge needed)

1. **Download** this repo as a ZIP and unzip it somewhere (e.g. your Desktop).
2. **Open the folder with Claude** — in Claude Code (`cd` into it and run
   `claude`), or any Claude that can see this folder.
3. **Say "help me get started."** Claude reads [`CLAUDE.md`](CLAUDE.md), installs
   the tool, asks you a few questions (your business name, address, bank, tax
   ID), and sets everything up. Then you just talk to it:
   - *"Set up a new client from this contract"* (drag in a PDF)
   - *"Invoice Acme for last month and make a PDF"*
   - *"Mark invoice NWS-2026-002 as paid by ACH"*
   - *"Who owes me money?"* / *"How much did I make this year?"*

That's the whole pitch: your invoices are plain files in a folder, and Claude is
the front desk.

## 2. Use it yourself from the terminal

```bash
pipx install .        # or: make install   (falls back to a local venv)
backoffice init       # scaffolds studio.yml + a sample client + invoice
# edit studio.yml (your details) and studio.local.yml (bank/EIN — stays private)
backoffice render acme/2026-001 --open
```

Then see [`README.md`](README.md) for the full command list, or run
`backoffice --help`.

## 3. Just look at the example first

```bash
make demo             # renders the bundled Northwind → Acme sample to out/
```

Open `examples/out/acme/NWS-2026-001-ACME.html` to see what an invoice looks like
before committing to anything.

---

**One thing to remember:** your real bank and tax-ID numbers live in
`studio.local.yml`, which is never committed to Git. Everything else is safe to
version-control, back up, and diff like any other text.
