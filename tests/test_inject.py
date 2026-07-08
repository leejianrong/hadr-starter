"""Deterministic narrative injection — keeps the model out of the HTML path."""
from __future__ import annotations

from scripts.inject import MARKER, inject


def test_replaces_marker():
    page = f"<div>a</div>{MARKER}<div>b</div>"
    out = inject(page, "A quake struck.")
    assert MARKER not in out
    assert "A quake struck." in out
    assert 'class="narrative"' in out


def test_escapes_html():
    out = inject(MARKER, "5 < 6 & <script>evil()</script>")
    assert "<script>" not in out
    assert "&lt;script&gt;" in out


def test_empty_narrative_is_noop():
    page = f"x{MARKER}y"
    assert inject(page, "   \n  ") == page


def test_missing_marker_is_noop():
    assert inject("no marker here", "prose") == "no marker here"


def test_paragraphs_split_on_blank_line():
    out = inject(MARKER, "First para.\n\nSecond para.")
    assert out.count("<p>") == 2
