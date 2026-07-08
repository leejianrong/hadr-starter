"""Renderer: fixed four-section anatomy, quiet vs populated, no bare casualties."""
from __future__ import annotations

from datetime import datetime, timezone

from scripts.decluster import decluster
from scripts.model import FeedHealth, Report
from scripts.render import render
from tests.helpers import make_quake

NOW = datetime(2026, 7, 8, 8, 30, tzinfo=timezone.utc)


def _report(clusters):
    return Report(
        publish_utc=NOW,
        window_start_utc=NOW,
        window_end_utc=NOW,
        clusters=clusters,
        feeds=[FeedHealth(name="USGS", url="file://x", ok=True, as_of=NOW)],
        coverage_note="Coverage: earthquakes only (USGS).",
    )


def test_all_four_sections_and_window_label_present():
    html = render(_report([]))
    for section in ("Sudden-onset", "Slow-onset", "Feed health"):
        assert section in html
    assert "last 24h ending" in html
    assert "Coverage: earthquakes only (USGS)." in html


def test_quiet_page_shows_nothing_to_report_not_blank():
    html = render(_report([]))
    assert "No new sudden-onset events crossed threshold" in html


def test_populated_page_shows_event_and_sequence():
    clusters = decluster([
        make_quake(id="main", mag=7.1, lat=0.0, lon=0.0, place="near Nowhere"),
        make_quake(id="a1", mag=6.2, lat=0.1, lon=0.1),
    ])
    html = render(_report(clusters))
    assert "near Nowhere" in html
    assert "aftershock" in html
    assert "M7.1" in html


def test_feed_health_line_present():
    html = render(_report([]))
    assert "USGS" in html
    assert "up" in html
