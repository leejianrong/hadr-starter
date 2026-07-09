"""GDACS adapter — the parsing traps from docs/feed-blindspots.md, offline against
the trimmed real RSS/JSON fixtures captured 2026-07-08."""
from __future__ import annotations

import json
from datetime import timezone
from pathlib import Path

from scripts import gdacs

FIX = Path(__file__).parent / "fixtures"
RSS = (FIX / "gdacs_rss_sample.xml").read_text()
JSON_RAW = json.loads((FIX / "gdacs_eventlist_sample.json").read_text())


def _by_key(events):
    return {e.key: e for e in events}


# --- JSON adapter ---

def test_json_parses_all_hazard_types():
    events = gdacs.parse_json(JSON_RAW)
    kinds = {e.eventtype for e in events}
    assert {"EQ", "TC", "FL", "WF"} <= kinds


def test_string_booleans_become_real_bools():
    # istemporary/iscurrent arrive as the strings "true"/"false" (blindspot).
    e = gdacs.parse_json(JSON_RAW)[0]
    assert isinstance(e.is_current, bool)
    assert isinstance(e.is_temporary, bool)


def test_json_naive_datetime_attached_as_utc():
    # "2026-07-08T09:50:23" has no tz designator but IS UTC.
    e = _by_key(gdacs.parse_json(JSON_RAW))["EQ1550772"]
    assert e.from_date.tzinfo == timezone.utc
    assert (e.from_date.year, e.from_date.month, e.from_date.day) == (2026, 7, 8)


def test_affectedcountries_is_a_list_not_the_country_string():
    # The TC spans borders; iso3 must come from affectedcountries[], not `country`.
    tc = _by_key(gdacs.parse_json(JSON_RAW))["TC1001279"]
    assert len(tc.iso3) >= 2
    assert "JPN" in tc.iso3 and "CHN" in tc.iso3


def test_per_hazard_severity_units_are_heterogeneous():
    ev = _by_key(gdacs.parse_json(JSON_RAW))
    assert ev["EQ1550772"].severity_unit == "M"
    assert ev["TC1001279"].severity_unit == "km/h"
    assert any(e.severity_unit == "ha" for e in ev.values())  # wildfire burned area


def test_eq_source_is_neic():
    eq = _by_key(gdacs.parse_json(JSON_RAW))["EQ1550772"]
    assert eq.source == "NEIC"


def test_json_cap_note_surfaced():
    assert gdacs.generated_json(JSON_RAW) is not None
    assert gdacs.JSON_LIST_CAP == 100


# --- RSS adapter (the primary path) ---

def test_rss_parses_and_attaches_utc_from_rfc822():
    events = gdacs.parse_rss(RSS)
    assert events
    e = events[0]
    assert e.from_date.tzinfo == timezone.utc


def test_rss_source_derived_from_hazard_type():
    # RSS carries no per-item <source>; it's deterministic from the type.
    ev = _by_key(gdacs.parse_rss(RSS))
    assert ev["EQ1550772"].source == "NEIC"
    assert all(e.source == "GWIS" for e in ev.values() if e.eventtype == "WF")


def test_channel_pubdate_is_utc():
    dt = gdacs.channel_pubdate(RSS)
    assert dt is not None and dt.tzinfo == timezone.utc


def test_alertscore_not_interchangeable_but_colour_is_stable():
    # THE trap: the same event EQ1550772 has a different raw `alertscore` in JSON vs
    # RSS (peak score 1.0 vs 0.0), so we never compare raw scores across formats —
    # but the alert COLOUR (our canonical severity axis) is identical.
    j = _by_key(gdacs.parse_json(JSON_RAW))["EQ1550772"]
    r = _by_key(gdacs.parse_rss(RSS))["EQ1550772"]
    assert j.score_format == "json" and r.score_format == "rss"
    assert j.peak_score != r.peak_score          # raw scores differ across feeds
    assert j.peak_level == r.peak_level           # colour is stable → rank on this
    assert j.alert == r.alert
