"""USGS parsing/normalization — epoch-ms, ids set, type filter."""
from __future__ import annotations

import json
from datetime import timezone
from pathlib import Path

from scripts.usgs import generated_ms, parse
from tests.helpers import raw_feature, raw_feed

FIXTURE = Path(__file__).parent / "fixtures" / "usgs_all_hour_sample.json"


def test_filters_non_earthquakes():
    feed = raw_feed([
        raw_feature(eid="eq", type="earthquake"),
        raw_feature(eid="blast", type="quarry blast"),
        raw_feature(eid="ice", type="ice quake"),
    ])
    quakes = parse(feed)
    assert [q.id for q in quakes] == ["eq"]


def test_epoch_ms_parsed_as_utc():
    feed = raw_feed([raw_feature(eid="eq", time_ms=1783497600000)])
    q = parse(feed)[0]
    assert q.time.tzinfo == timezone.utc
    assert q.time.year == 2026


def test_ids_split_strips_empty_leading_trailing():
    feed = raw_feed([raw_feature(eid="eq", ids=",ci123,us456,")])
    q = parse(feed)[0]
    assert q.ids == frozenset({"ci123", "us456"})


def test_coordinates_lon_lat_depth():
    feed = raw_feed([raw_feature(eid="eq", lon=141.8, lat=40.4, depth=55.0)])
    q = parse(feed)[0]
    assert (q.lon, q.lat, q.depth_km) == (141.8, 40.4, 55.0)


def test_real_fixture_parses():
    raw = json.loads(FIXTURE.read_text())
    quakes = parse(raw)  # no geo — offline, still parses
    assert len(quakes) >= 1
    assert all(q.time.tzinfo == timezone.utc for q in quakes)
    assert generated_ms(raw) is not None
