"""V4 end-to-end: multi-hazard ranking, the EQ identity merge, GDACS threshold and
change detection — through build_report (the testable core), offline."""
from __future__ import annotations

from datetime import datetime, timezone

from scripts import severity
from scripts.model import FeedHealth
from scripts.render import render
from scripts.sitrep import build_report
from tests.helpers import make_gdacs, raw_feature, raw_feed

NOW = datetime(2026, 7, 8, 12, 0, tzinfo=timezone.utc)


class FakeGeo:
    def iso3_for(self, lat, lon):
        return ["XXX"]

    def is_onshore(self, lat, lon):
        return True


class OffshoreGeo:
    """USGS coarse-polygon reverse-geocode misses a coastal point → offshore."""

    def iso3_for(self, lat, lon):
        return []

    def is_onshore(self, lat, lon):
        return False


def _ms(y, mo, d, h=0):
    return int(datetime(y, mo, d, h, tzinfo=timezone.utc).timestamp() * 1000)


def _feed(ok=True):
    return FeedHealth(name="GDACS", url="file://gdacs", ok=ok, as_of=NOW, note="fixture")


def _build(usgs_feed, gdacs_events, prior=None, gprior=None, gfeed=None):
    return build_report(
        usgs_feed, "file://usgs", True, "", FakeGeo(), NOW, prior or {},
        gdacs_events=gdacs_events, gdacs_feed=gfeed or _feed(), gdacs_prior=gprior or {},
    )


# --- multi-hazard ranking + threshold ---

def test_green_gdacs_noise_is_filtered_orange_plus_shown():
    events = [
        make_gdacs(eventtype="WF", eventid=1, peak_level="Green", peak_score=1.0),
        make_gdacs(eventtype="TC", eventid=2, peak_level="Red", peak_score=3.0,
                   name="Cyclone Big"),
        make_gdacs(eventtype="FL", eventid=3, peak_level="Orange", peak_score=2.0,
                   name="Flood Mid"),
    ]
    report, _ = _build(raw_feed([]), events)
    kinds = [it.kind for it in report.items]
    assert "WF" not in kinds                      # green wildfire = noise, filtered
    assert kinds == ["TC", "FL"]                   # ranked Red above Orange


def test_cyclone_ranks_above_a_yellow_earthquake():
    usgs = raw_feed([raw_feature(eid="q", mag=6.5, time_ms=_ms(2026, 7, 8, 6),
                                 alert="yellow")])
    events = [make_gdacs(eventtype="TC", eventid=9, peak_level="Red", name="Cyclone")]
    report, _ = _build(usgs, events)
    assert report.items[0].kind == "TC"           # Red beats a yellow quake


# --- the earthquake identity merge (the headline DoD item) ---

def test_gdacs_eq_and_usgs_eq_merge_to_one_line():
    # Both independently pass threshold; the GDACS-EQ embeds the USGS id → ONE line.
    usgs = raw_feed([raw_feature(eid="us7000zzz", ids=",us7000zzz,", mag=6.6,
                                 mag_type="mww", time_ms=_ms(2026, 7, 8, 6),
                                 lat=10.0, lon=20.0, alert="orange")])
    g = make_gdacs(eventtype="EQ", eventid=555, source="NEIC", source_id="us7000zzz",
                   lat=10.0, lon=20.0, peak_level="Orange",
                   from_date=datetime(2026, 7, 8, 6, tzinfo=timezone.utc))
    report, _ = _build(usgs, [g])

    eq_items = [it for it in report.items if it.kind == "EQ"]
    assert len(eq_items) == 1                     # not double-counted
    it = eq_items[0]
    assert it.eq is not None and it.gdacs is not None
    assert it.confidence == "certain"
    assert it.independent is False
    assert "USGS" in it.sources and any("GDACS" in s for s in it.sources)

    html = render(report)
    assert "not independent corroboration" in html


def test_merged_eq_borrows_gdacs_country_when_usgs_offshore():
    # USGS placed offshore (empty iso3 via FakeGeo? no — raw_feature has no geo here,
    # so iso3 is empty → offshore). The merged GDACS side carries an ISO3.
    usgs = raw_feed([raw_feature(eid="us7000off", ids=",us7000off,", mag=6.6,
                                 mag_type="mww", time_ms=_ms(2026, 7, 8, 6),
                                 lat=-6.3, lon=149.5, alert="orange",
                                 place="120 km S of Kandrian")])
    g = make_gdacs(eventtype="EQ", eventid=42, source="NEIC", source_id="us7000off",
                   lat=-6.3, lon=149.5, iso3=("PNG",), peak_level="Orange",
                   from_date=datetime(2026, 7, 8, 6, tzinfo=timezone.utc))
    # build_report parses USGS with the real Geo (offshore for this coastal point).
    report = build_report(usgs, "file://usgs", True, "", OffshoreGeo(), NOW, {},
                          gdacs_events=[g], gdacs_feed=_feed(), gdacs_prior={})[0]
    html = render(report)
    assert "PNG" in html
    assert "country via GDACS" in html
    assert "(offshore)" not in html


def test_low_confidence_eq_pair_is_cross_linked_not_merged():
    usgs = raw_feed([raw_feature(eid="usA", ids=",usA,", mag=6.2, mag_type="mww",
                                 time_ms=_ms(2026, 7, 8, 6), lat=0.0, lon=0.0,
                                 alert="orange", place="Quaketown")])
    # No embedded id, close in space but 6h apart → low confidence.
    g = make_gdacs(eventtype="EQ", eventid=777, source="NEIC", source_id="",
                   lat=0.1, lon=0.1, severity_value=6.2, peak_level="Orange",
                   from_date=datetime(2026, 7, 8, 0, tzinfo=timezone.utc), name="Other EQ")
    report, _ = _build(usgs, [g])
    assert len([it for it in report.items if it.kind == "EQ"]) == 2   # kept separate
    html = render(report)
    assert "possibly related" in html


# --- GDACS change detection over persisted state ---

def test_gdacs_new_then_quiet_across_runs():
    events = [make_gdacs(eventtype="TC", eventid=42, peak_level="Red", name="Cyclone")]
    r1, res1 = _build(raw_feed([]), events)
    assert r1.is_loud is True
    assert r1.items[0].change == "NEW"

    gprior = {row.key: row for row in res1.gdacs.next_rows}
    r2, _ = _build(raw_feed([]), events, gprior=gprior)
    assert r2.items[0].change is None
    assert r2.is_loud is False


def test_gdacs_escalation_is_revised_and_loud():
    before = [make_gdacs(eventtype="FL", eventid=7, peak_level="Orange", name="Flood")]
    r1, res1 = _build(raw_feed([]), before)
    gprior = {row.key: row for row in res1.gdacs.next_rows}

    after = [make_gdacs(eventtype="FL", eventid=7, peak_level="Red", name="Flood")]
    r2, _ = _build(raw_feed([]), after, gprior=gprior)
    assert r2.items[0].change == "REVISED"
    assert "escalated" in r2.items[0].change_reason
    assert r2.is_loud is True


def test_gdacs_feed_health_line_and_coverage():
    report, _ = _build(raw_feed([]), [])
    names = [f.name for f in report.feeds]
    assert names == ["USGS", "GDACS"]
    assert "GDACS multi-hazard" in report.coverage_note


def test_gdacs_threshold_boundary():
    assert severity.gdacs_passes_threshold(make_gdacs(peak_level="Orange")) is True
    assert severity.gdacs_passes_threshold(make_gdacs(peak_level="Red")) is True
    assert severity.gdacs_passes_threshold(make_gdacs(peak_level="Green")) is False
