"""V5 end-to-end: the slow-onset/ongoing section, the reached-ReliefWeb floor,
provenance stacking, and ReliefWeb change detection — through build_report."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from scripts import sitrep
from scripts.model import FeedHealth
from scripts.render import render
from scripts.sitrep import build_report
from tests.helpers import make_gdacs, make_reliefweb, raw_feed

NOW = datetime(2026, 7, 8, 12, 0, tzinfo=timezone.utc)
FIX = Path(__file__).parent / "fixtures"


class FakeGeo:
    def iso3_for(self, lat, lon):
        return ["XXX"]

    def is_onshore(self, lat, lon):
        return True


def _feed(name, ok=True):
    return FeedHealth(name=name, url=f"file://{name}", ok=ok, as_of=NOW, note="fixture")


def _build(gdacs_events=None, disasters=None, gprior=None, rprior=None):
    return build_report(
        raw_feed([]), "file://usgs", True, "", FakeGeo(), NOW, {},
        gdacs_events=gdacs_events or [], gdacs_feed=_feed("GDACS"), gdacs_prior=gprior or {},
        reliefweb_disasters=disasters or [], reliefweb_feed=_feed("ReliefWeb"),
        reliefweb_prior=rprior or {},
    )


def test_curated_disaster_appears_in_ongoing_window_exempt():
    # A disaster curated months ago (far outside the 24h window) still shows —
    # slow-onset is window-exempt (ADR-0004 branch 3 / R0.2).
    old = make_reliefweb(glide="EP-2026-000048-BGD", hazard_code="EP",
                         title="Bangladesh: Measles Outbreak",
                         pub_date=datetime(2026, 3, 1, tzinfo=timezone.utc))
    report, _ = _build(disasters=[old])
    assert len(report.ongoing) == 1
    assert report.ongoing[0].kind == "EP"
    assert report.items == []               # nothing sudden-onset
    html = render(report)
    assert "Measles" in html and "REACHED RELIEFWEB" in html


def test_reached_reliefweb_floor_shows_every_disaster():
    ds = [make_reliefweb(glide=f"FL-2026-00010{i}-XX{i}", title=f"Flood {i}")
          for i in range(3)]
    report, _ = _build(disasters=ds)
    assert len(report.ongoing) == 3         # all clear the floor, none filtered


def test_provenance_stacking_never_summed():
    # GDACS cyclone + ReliefWeb disaster with the SAME GLIDE → one stacked line.
    tc = make_gdacs(eventtype="TC", eventid=1, glide="TC-2026-000099-GUM",
                    name="Cyclone Bavi", peak_level="Red")
    d = make_reliefweb(glide="TC-2026-000099-GUM", title="Guam: Cyclone Bavi")
    report, _ = _build(gdacs_events=[tc], disasters=[d])

    assert len(report.items) == 1           # stacked onto the sudden-onset line
    assert report.ongoing == []
    it = report.items[0]
    assert it.gdacs is not None and it.reliefweb is not None
    assert it.independent is True           # independent orgs → real corroboration
    html = render(report)
    assert "never summed" in html
    assert "＋ ReliefWeb" in html


def test_reliefweb_new_then_quiet_across_runs():
    d = make_reliefweb(glide="EP-2026-000107-CAF", hazard_code="EP",
                       title="CAR: Cholera Outbreak")
    r1, res1 = _build(disasters=[d])
    assert r1.is_loud is True
    assert r1.ongoing[0].change == "NEW"

    rprior = {row.key: row for row in res1.reliefweb.next_rows}
    r2, _ = _build(disasters=[d], rprior=rprior)
    assert r2.ongoing[0].change is None
    assert r2.is_loud is False


def test_reliefweb_dropping_off_feed_is_not_a_retraction():
    # RSS shows only the latest ~20; a disaster leaving the feed aged out, it did
    # not end. There must be NO retraction (never infer 'ended' from absent).
    d = make_reliefweb(glide="FL-2026-000106-GEO", title="Georgia: Floods")
    _, res1 = _build(disasters=[d])
    rprior = {row.key: row for row in res1.reliefweb.next_rows}
    report, _ = _build(disasters=[], rprior=rprior)     # disaster gone from feed
    assert report.retractions == []
    assert report.ongoing == []


def test_full_coverage_note_and_three_feeds():
    report, _ = _build()
    assert [f.name for f in report.feeds] == ["USGS", "GDACS", "ReliefWeb"]
    assert "ReliefWeb curated disasters" in report.coverage_note
    html = render(report)
    assert "RSS mode" in html               # the loud RSS-limitation flag (coverage banner)


def test_cli_all_three_fixtures_end_to_end(tmp_path):
    """The full CLI path over the checked-in real fixtures: exit 0, ongoing section
    populated, and the RSS-mode feed-health flag on the page."""
    out = tmp_path / "dashboard.html"
    state = tmp_path / "state.sqlite3"
    rc = sitrep.main([
        "--fixture", str(FIX / "usgs_all_hour_sample.json"),
        "--gdacs-json-fixture", str(FIX / "gdacs_eventlist_sample.json"),
        "--reliefweb-fixture", str(FIX / "reliefweb_disasters_rss_sample.xml"),
        "--state", str(state), "--out", str(out), "--now", "2026-07-08T10:30",
    ])
    assert rc == 0
    html = out.read_text()
    assert "Slow-onset / ongoing" in html
    assert "REACHED RELIEFWEB" in html
    assert "RSS mode, no API" in html       # feed-health flag from the loader
    # Second run shares state → the ReliefWeb NEW flags clear (quiet on that axis).
    sitrep.main([
        "--fixture", str(FIX / "usgs_all_hour_sample.json"),
        "--reliefweb-fixture", str(FIX / "reliefweb_disasters_rss_sample.xml"),
        "--state", str(state), "--out", str(out), "--now", "2026-07-08T11:30",
    ])
    assert "newly curated onto ReliefWeb" not in out.read_text()
