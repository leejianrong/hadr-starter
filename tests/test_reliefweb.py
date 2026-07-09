"""ReliefWeb adapter — RSS parsing traps, offline against the trimmed real fixture
captured 2026-07-08."""
from __future__ import annotations

from datetime import timezone
from pathlib import Path

from scripts import reliefweb
from scripts.model import parse_glide

RSS = (Path(__file__).parent / "fixtures" / "reliefweb_disasters_rss_sample.xml").read_text()


def _by_glide(ds):
    return {d.glide: d for d in ds}


def test_parses_all_items():
    ds = reliefweb.parse_rss(RSS)
    assert len(ds) == reliefweb.item_count(RSS) >= 5


def test_glide_and_iso3_from_glide_suffix():
    d = _by_glide(reliefweb.parse_rss(RSS))["EQ-2026-000093-VEN"]
    assert d.hazard_code == "EQ"
    assert d.iso3 == ("VEN",)          # ISO3 from the GLIDE suffix, not name-matched


def test_iso3_present_even_when_country_tag_absent():
    # The Philippines EQ+Tsunami item has no "Affected country" tag in the fixture;
    # ISO3 must still come from the GLIDE suffix.
    d = _by_glide(reliefweb.parse_rss(RSS))["EQ-2026-000083-PHL"]
    assert d.iso3 == ("PHL",)
    assert d.country_names == ()


def test_epidemics_are_captured():
    # ReliefWeb's whole point: hazards USGS/GDACS can't see.
    ds = reliefweb.parse_rss(RSS)
    assert any(d.hazard_code == "EP" for d in ds)


def test_pubdate_is_utc():
    d = reliefweb.parse_rss(RSS)[0]
    assert d.pub_date is not None and d.pub_date.tzinfo == timezone.utc


def test_summary_extracted_as_plain_text():
    d = reliefweb.parse_rss(RSS)[0]
    assert d.summary
    assert "<" not in d.summary and "&lt;" not in d.summary  # tags stripped/unescaped


def test_country_names_are_display_only_not_iso3():
    # Names carry political variants we deliberately do NOT string-match (blindspot #10).
    d = _by_glide(reliefweb.parse_rss(RSS))["EQ-2026-000093-VEN"]
    assert d.country_names == ("Venezuela (Bolivarian Republic of)",)
    assert d.iso3 == ("VEN",)          # the code stays clean


def test_glide_regex_shape():
    assert parse_glide("Glide: EQ-2026-000093-VEN") == ("EQ", "2026", "000093", "VEN")
    assert parse_glide("no glide here") is None
