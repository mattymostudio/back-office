.PHONY: help install setup test demo clean

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[1m%-10s\033[0m %s\n", $$1, $$2}'

install:  ## Install the `backoffice` command (pipx preferred, venv fallback)
	@pipx install . 2>/dev/null && echo "Installed via pipx — run: backoffice --version" || \
	( echo "pipx unavailable; using a local venv…" && \
	  python3 -m venv .venv && .venv/bin/pip install -q . && \
	  echo "Installed in .venv — run: .venv/bin/backoffice --version" )

setup: install  ## Install, then scaffold a workspace in this folder
	@( command -v backoffice >/dev/null && backoffice init ) || .venv/bin/backoffice init

test:  ## Run the test suite
	python3 -m pip install -q -e '.[dev]' && python3 -m pytest -q

demo:  ## Render the bundled example invoices
	BACKOFFICE_HOME=examples python3 -m backoffice render --all

clean:  ## Remove rendered output and caches
	rm -rf out examples/out .pytest_cache **/__pycache__ .venv *.egg-info
