"""Test factories — build Quakes and USGS payloads concisely."""
from __future__ import annotations

from datetime import datetime, timezone

from scripts.model import Quake

T0 = datetime(2026, 7, 8, 0, 0, tzinfo=timezone.utc)


def make_quake(
    *,
    id="q1",
    ids=None,
    mag=5.0,
    mag_type="mww",
    alert=None,
    depth_km=10.0,
    onshore=True,
    lat=0.0,
    lon=0.0,
    sig=100,
    time=T0,
    place="somewhere",
    status="reviewed",
) -> Quake:
    return Quake(
        id=id,
        ids=frozenset(ids or [id]),
        mag=mag,
        mag_type=mag_type,
        place=place,
        time=time,
        updated=time,
        depth_km=depth_km,
        lon=lon,
        lat=lat,
        alert=alert,
        status=status,
        sig=sig,
        tsunami=0,
        felt=None,
        title="",
        iso3=("XXX",) if onshore else (),
        onshore=onshore,
    )


def raw_feature(*, mag=6.0, type="earthquake", time_ms=1783497600000, updated_ms=None,
                ids=",a,b,", alert=None, depth=10.0, lon=0.0, lat=0.0, sig=100,
                mag_type="mww", eid="e1", place="somewhere"):
    return {
        "type": "Feature",
        "id": eid,
        "properties": {
            "mag": mag, "magType": mag_type, "place": place, "time": time_ms,
            "updated": updated_ms or time_ms, "alert": alert, "status": "reviewed",
            "tsunami": 0, "sig": sig, "ids": ids, "type": type, "title": place,
        },
        "geometry": {"type": "Point", "coordinates": [lon, lat, depth]},
    }


def raw_feed(features, generated_ms=1783497600000):
    return {"type": "FeatureCollection",
            "metadata": {"generated": generated_ms, "count": len(features)},
            "features": features}
