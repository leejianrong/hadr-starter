"""Offline reverse-geocode + onshore test (SPIKE-onshore-geocode).

Ray-casting point-in-polygon over vendored Natural Earth Admin-0 polygons — zero
runtime dependency. Serves both ISO3 normalization (blindspot #10: USGS gives only
lat/lon) and the `onshore` branch of the slice-1 threshold (ADR-0004). For V1,
"populated landmass" is approximated as "inside a country polygon"; the
population-distance refinement is deferred to a later slice.
"""
from __future__ import annotations

import json
from pathlib import Path

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "ne_110m_admin_0_countries.geojson"


def _polygons(geometry: dict) -> list:
    """Normalize Polygon / MultiPolygon into a list of polygons (each: list of rings)."""
    t = geometry.get("type")
    coords = geometry.get("coordinates", [])
    if t == "Polygon":
        return [coords]
    if t == "MultiPolygon":
        return list(coords)
    return []


def _point_in_ring(x: float, y: float, ring: list) -> bool:
    """Ray-casting crossing count for a single ring (x=lon, y=lat)."""
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def _point_in_polygon(x: float, y: float, rings: list) -> bool:
    """Even-odd rule across all rings (outer ring + any holes)."""
    inside = False
    for ring in rings:
        if _point_in_ring(x, y, ring):
            inside = not inside
    return inside


class Geo:
    """Loaded country polygons; answers iso3_for / is_onshore."""

    def __init__(self, path: Path | str = DATA_PATH):
        data = json.loads(Path(path).read_text())
        # list of (iso3, [polygon, ...]) where polygon = [ring, ...], ring = [[lon,lat], ...]
        self._countries: list[tuple[str, list]] = []
        for feat in data.get("features", []):
            iso3 = (feat.get("properties", {}) or {}).get("iso3") or ""
            polys = _polygons(feat.get("geometry") or {})
            if polys:
                self._countries.append((iso3, polys))

    def iso3_for(self, lat: float, lon: float) -> list[str]:
        """ISO3 codes whose polygon contains the point. Empty = offshore.

        Returns a *list* — border points can fall in more than one (CONTEXT).
        """
        hits: list[str] = []
        for iso3, polys in self._countries:
            if any(_point_in_polygon(lon, lat, poly) for poly in polys):
                if iso3 and iso3 not in hits:
                    hits.append(iso3)
        return hits

    def is_onshore(self, lat: float, lon: float) -> bool:
        for _iso3, polys in self._countries:
            if any(_point_in_polygon(lon, lat, poly) for poly in polys):
                return True
        return False
