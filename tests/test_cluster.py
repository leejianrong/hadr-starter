"""Cross-feed confidence ladder + join (SPIKE-cross-feed-confidence / ADR-0001)."""
from __future__ import annotations

from datetime import timedelta

from scripts.cluster import attach_reliefweb, confidence, eq_identity_link, join
from scripts.decluster import decluster
from tests.helpers import T0, make_gdacs, make_quake, make_reliefweb


def _cluster(**kw):
    return decluster([make_quake(**kw)])[0]


# --- the earthquake identity link (checked first, definitional) ---

def test_identity_link_matches_embedded_usgs_id():
    q = make_quake(id="us7000abcd", ids=["us7000abcd", "nc1234"])
    g = make_gdacs(eventtype="EQ", source="NEIC", source_id="us7000abcd")
    assert eq_identity_link(g, q) is True


def test_identity_link_requires_neic_source():
    q = make_quake(id="us7000abcd", ids=["us7000abcd"])
    g = make_gdacs(eventtype="EQ", source="JTWC", source_id="us7000abcd")
    assert eq_identity_link(g, q) is False


def test_confidence_certain_on_identity_link():
    c = _cluster(id="us7000abcd", ids=["us7000abcd"], lat=10.0, lon=20.0)
    g = make_gdacs(source_id="us7000abcd", lat=10.0, lon=20.0)
    assert confidence(g, c) == "certain"


# --- the tolerance box (when no id is embedded) ---

def test_confidence_high_when_all_dims_tight():
    c = _cluster(lat=0.0, lon=0.0, mag=6.0, mag_type="mww", time=T0)
    g = make_gdacs(source_id="", lat=0.1, lon=0.1, severity_value=6.1,
                   from_date=T0 + timedelta(minutes=1))
    assert confidence(g, c) == "high"


def test_confidence_medium_when_loose():
    c = _cluster(lat=0.0, lon=0.0, mag=6.0, mag_type="mww", time=T0)
    g = make_gdacs(source_id="", lat=0.7, lon=0.0, severity_value=6.8,   # ~78 km, 0.8 M
                   from_date=T0 + timedelta(minutes=40))
    assert confidence(g, c) == "medium"


def test_confidence_low_when_only_partial():
    c = _cluster(lat=0.0, lon=0.0, mag=6.0, mag_type="mww", time=T0)
    g = make_gdacs(source_id="", lat=0.1, lon=0.1, severity_value=6.0,   # close in space
                   from_date=T0 + timedelta(hours=6))                    # but 6h apart
    assert confidence(g, c) == "low"


def test_non_earthquake_never_joins_a_quake_cluster():
    c = _cluster(lat=0.0, lon=0.0)
    flood = make_gdacs(eventtype="FL", source_id="", lat=0.0, lon=0.0)
    assert confidence(flood, c) is None


# --- join behaviour per level (A3-Q5) ---

def test_join_merges_identity_to_one_line_not_double_counted():
    c = _cluster(id="us7000abcd", ids=["us7000abcd"], lat=10.0, lon=20.0, place="Elsewhere")
    g = make_gdacs(source_id="us7000abcd", lat=10.0, lon=20.0, peak_level="Orange")
    items = join([c], [g])
    assert len(items) == 1                       # ONE line, never two
    it = items[0]
    assert it.eq is not None and it.gdacs is not None
    assert it.confidence == "certain"
    assert it.independent is False               # same NEIC reading — no corroboration
    assert it.alert == "orange"                  # loudest colour across the merge


def test_join_medium_labels_but_merges():
    c = _cluster(lat=0.0, lon=0.0, mag=6.0, mag_type="mww", time=T0)
    g = make_gdacs(source_id="", lat=0.7, lon=0.0, severity_value=6.8,
                   from_date=T0 + timedelta(minutes=40))
    items = join([c], [g])
    assert len(items) == 1
    assert items[0].confidence == "medium"


def test_join_low_confidence_cross_links_never_merges():
    c = _cluster(lat=0.0, lon=0.0, mag=6.0, mag_type="mww", time=T0, place="Quaketown")
    g = make_gdacs(source_id="", lat=0.1, lon=0.1, severity_value=6.0,
                   from_date=T0 + timedelta(hours=6), name="Distant EQ")
    items = join([c], [g])
    assert len(items) == 2                       # kept SEPARATE
    eq_item = next(i for i in items if i.eq is not None)
    gd_item = next(i for i in items if i.eq is None)
    assert gd_item.gdacs is not None and gd_item.eq is None
    assert any("possibly related" in x for x in eq_item.cross_links)
    assert any("possibly related" in x for x in gd_item.cross_links)


def test_join_non_eq_hazards_stand_alone():
    tc = make_gdacs(eventtype="TC", source_id="", name="Cyclone X", peak_level="Red")
    items = join([], [tc])
    assert len(items) == 1
    assert items[0].kind == "TC" and items[0].eq is None
    assert items[0].sources == ["GDACS·JTWC"]


# --- ReliefWeb: GLIDE stacking vs ongoing (V5) ---

def test_reliefweb_stacks_onto_matching_glide():
    tc = make_gdacs(eventtype="TC", eventid=1, glide="TC-2026-000099-GUM",
                    name="Cyclone Bavi", peak_level="Red")
    items = join([], [tc])
    disaster = make_reliefweb(glide="TC-2026-000099-GUM", title="Guam: Cyclone Bavi")
    ongoing = attach_reliefweb(items, [disaster])

    assert ongoing == []                       # stacked, not a separate ongoing line
    assert items[0].reliefweb is disaster
    assert "ReliefWeb" in items[0].sources
    assert items[0].independent is True         # GDACS & ReliefWeb are independent orgs


def test_reliefweb_without_match_becomes_ongoing():
    disaster = make_reliefweb(glide="EP-2026-000107-CAF", hazard_code="EP",
                              title="CAR: Cholera Outbreak")
    ongoing = attach_reliefweb([], [disaster])
    assert len(ongoing) == 1
    assert ongoing[0].kind == "EP" and ongoing[0].reliefweb is disaster
    assert ongoing[0].sources == ["ReliefWeb"]


def test_reliefweb_no_glide_never_stacks():
    tc = make_gdacs(eventtype="TC", eventid=1, glide="TC-2026-000099-GUM", peak_level="Red")
    items = join([], [tc])
    disaster = make_reliefweb(glide="", hazard_code="FL", title="Some flood")
    ongoing = attach_reliefweb(items, [disaster])
    assert len(ongoing) == 1                    # no GLIDE → cannot stack
    assert items[0].reliefweb is None
