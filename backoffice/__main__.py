"""Enables `python -m backoffice ...` — the zero-install run path.

After `pip install pyyaml jinja2`, you can drive the tool straight from the
unzipped folder without installing the package itself.
"""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
