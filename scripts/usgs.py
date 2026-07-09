"""USGS earthquake feed adapter — ingestion + normalization.

The live fetch uses `requests` (imported lazily so parsing stays offline-testable
with no dependency). Parsing is pure. USGS is CDN-fronted: no User-Agent needed,
send `Accept-Encoding: gzip`, and don't poll faster than 60s (USGS #5).
"""
from __future__ import annotations

from .geo import Geo
from .model import Quake, from_ms

FEED_URL = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_day.geojson"
# all_week covers 7 days (a superset of all_day) — used for the Past-7-days context
# section; the 24h sudden-onset brief is sliced from it by event time.
FEED_URL_WEEK = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_week.geojson"


def fetch(url: str = FEED_URL_WEEK, timeout: float = 30.0) -> tuple[dict, str]:
    """Fetch the summary feed. Returns (raw_json, final_url_actually_fetched)."""
    import requests

    resp = requests.get(url, headers={"Accept-Encoding": "gzip"}, timeout=timeout)
    resp.raise_for_status()
    # resp.url is the URL after any redirects — the one we log (CLAUDE.md #2).
    return resp.json(), resp.url


def parse(raw: dict, geo: Geo | None = None) -> list[Quake]:
    """Normalize the GeoJSON FeatureCollection into Quakes.

    Filters to `type == "earthquake"` (the feed also carries quarry blasts, ice
    quakes, etc.). If a `geo` resolver is given, fills ISO3 + onshore.
    """
    quakes: list[Quake] = []
    for feat in raw.get("features", []):
        props = feat.get("properties") or {}
        if props.get("type") != "earthquake":
            continue
        geom = feat.get("geometry") or {}
        coords = geom.get("coordinates") or [0.0, 0.0, 0.0]
        lon = coords[0]
        lat = coords[1]
        depth = coords[2] if len(coords) > 2 else 0.0

        # `ids` is comma-delimited with leading/trailing commas — strip empties.
        ids = frozenset(s for s in (props.get("ids") or "").split(",") if s)

        iso3: tuple[str, ...] = ()
        onshore = False
        if geo is not None:
            iso3 = tuple(geo.iso3_for(lat, lon))
            onshore = geo.is_onshore(lat, lon)

        quakes.append(
            Quake(
                id=feat.get("id") or "",
                ids=ids,
                mag=props.get("mag"),
                mag_type=(props.get("magType") or None),
                place=props.get("place") or "",
                time=from_ms(props["time"]),
                updated=from_ms(props["updated"]),
                depth_km=depth,
                lon=lon,
                lat=lat,
                alert=(props.get("alert") or None),
                status=props.get("status") or "",
                sig=props.get("sig"),
                tsunami=props.get("tsunami") or 0,
                felt=props.get("felt"),
                title=props.get("title") or "",
                iso3=iso3,
                onshore=onshore,
            )
        )
    return quakes


def generated_ms(raw: dict) -> int | None:
    """The feed's own generation time (epoch ms), for the feed-health 'as of'."""
    return (raw.get("metadata") or {}).get("generated")
