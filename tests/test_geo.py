"""Geo module: ray-casting point-in-polygon, ISO3 list, onshore (SPIKE-onshore-geocode)."""
from __future__ import annotations

import json

from scripts.geo import Geo

# A synthetic country: a square covering lon 0..10, lat 0..10.
SQUARE = {
    "type": "FeatureCollection",
    "features": [{
        "type": "Feature",
        "properties": {"iso3": "AAA", "name": "Squareland"},
        "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]]},
    }],
}


def _square_geo(tmp_path):
    p = tmp_path / "square.geojson"
    p.write_text(json.dumps(SQUARE))
    return Geo(p)


def test_point_inside_square_is_onshore(tmp_path):
    geo = _square_geo(tmp_path)
    assert geo.is_onshore(5, 5) is True
    assert geo.iso3_for(5, 5) == ["AAA"]


def test_point_outside_square_is_offshore(tmp_path):
    geo = _square_geo(tmp_path)
    assert geo.is_onshore(20, 20) is False
    assert geo.iso3_for(20, 20) == []


def test_point_just_outside_edge(tmp_path):
    geo = _square_geo(tmp_path)
    assert geo.is_onshore(5, 10.5) is False


def test_real_data_known_points():
    """Smoke test against the vendored Natural Earth data."""
    geo = Geo()
    assert "JPN" in geo.iso3_for(35.68, 139.69)   # Tokyo
    assert geo.is_onshore(0.0, -140.0) is False    # mid-Pacific
