"""Declustering (ADR-0001): mainshock + aftershocks collapse to one sequence."""
from __future__ import annotations

from datetime import timedelta

from scripts.decluster import decluster
from tests.helpers import T0, make_quake


def test_mainshock_plus_aftershocks_is_one_cluster():
    quakes = [
        make_quake(id="main", mag=7.1, lat=0.0, lon=0.0, time=T0),
        make_quake(id="a1", mag=6.2, lat=0.1, lon=0.1, time=T0 + timedelta(hours=1)),
        make_quake(id="a2", mag=5.0, lat=0.2, lon=0.0, time=T0 + timedelta(hours=2)),
        make_quake(id="a3", mag=4.5, lat=0.0, lon=0.2, time=T0 + timedelta(hours=3)),
    ]
    clusters = decluster(quakes)
    assert len(clusters) == 1
    c = clusters[0]
    assert c.mainshock.id == "main"
    assert c.count == 4
    assert c.largest_aftershock.mag == 6.2
    assert c.is_swarm is False


def test_distant_events_are_separate_clusters():
    quakes = [
        make_quake(id="jp", mag=6.0, lat=38.0, lon=142.0, time=T0),
        make_quake(id="cl", mag=6.1, lat=-33.0, lon=-72.0, time=T0),  # Chile — far away
    ]
    clusters = decluster(quakes)
    assert len(clusters) == 2


def test_swarm_has_no_dominant_mainshock():
    quakes = [
        make_quake(id="s1", mag=5.2, lat=0.0, lon=0.0, time=T0),
        make_quake(id="s2", mag=5.1, lat=0.05, lon=0.05, time=T0 + timedelta(minutes=30)),
        make_quake(id="s3", mag=5.0, lat=0.0, lon=0.05, time=T0 + timedelta(hours=1)),
    ]
    clusters = decluster(quakes)
    assert len(clusters) == 1
    assert clusters[0].is_swarm is True


def test_declustering_is_deterministic():
    quakes = [
        make_quake(id=f"q{i}", mag=5.0, lat=0.0, lon=0.0, time=T0) for i in range(5)
    ]
    a = decluster(list(quakes))
    b = decluster(list(reversed(quakes)))
    assert [c.mainshock.id for c in a] == [c.mainshock.id for c in b]
