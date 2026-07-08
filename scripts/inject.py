"""Deterministically inject the model's narrative prose into dashboard.html.

Keeps the model out of the HTML and number path (ADR-0005 / ADR-0002): the
narrator writes plain prose; this escapes it and drops it at the placeholder the
renderer left. Pure + offline; the only file I/O is in `main`.

    uv run python -m scripts.inject dashboard.html narrative.md
"""
from __future__ import annotations

import html
import sys
from pathlib import Path

MARKER = "<!--NARRATIVE-->"


def inject(page: str, narrative: str) -> str:
    """Replace the placeholder with an escaped prose block (no-op if empty/absent)."""
    text = narrative.strip()
    if not text or MARKER not in page:
        return page
    paras = "".join(
        f"<p>{html.escape(p.strip())}</p>"
        for p in text.split("\n\n")
        if p.strip()
    )
    block = f'<section class="narrative"><h2>What changed</h2>{paras}</section>'
    return page.replace(MARKER, block, 1)


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    page_path, narrative_path = Path(args[0]), Path(args[1])
    page_path.write_text(inject(page_path.read_text(), narrative_path.read_text()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
