"""Test factories — build Quakes, GDACS events, and USGS payloads concisely."""
from __future__ import annotations

from datetime import datetime, timezone

from scripts.model import GdacsEvent, Quake, ReliefWebDisaster

T0 = datetime(2026, 7, 8, 0, 0, tzinfo=timezone.utc)


def make_reliefweb(
    *,
    title="Somewhere: Floods - Jul 2026",
    url="https://reliefweb.int/disaster/fl-2026-000200-xxx",
    glide="FL-2026-000200-XXX",
    hazard_code=None,
    iso3=None,
    country_names=("Somewhere",),
    pub_date=T0,
    summary="Heavy rainfall caused flooding.",
) -> ReliefWebDisaster:
    code = hazard_code if hazard_code is not None else (glide[:2] if glide else "")
    iso = iso3 if iso3 is not None else ((glide[-3:],) if glide else ())
    return ReliefWebDisaster(
        title=title,
        url=url,
        glide=glide,
        hazard_code=code,
        iso3=iso,
        country_names=country_names,
        pub_date=pub_date,
        summary=summary,
    )


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


def make_gdacs(
    *,
    eventtype="EQ",
    eventid=1,
    episodeid=1,
    name="",
    glide="",
    source=None,
    source_id="",
    lat=0.0,
    lon=0.0,
    from_date=T0,
    peak_level="Orange",
    episode_level=None,
    peak_score=2.0,
    episode_score=2.0,
    score_format="json",
    is_current=True,
    is_temporary=False,
    iso3=("XXX",),
    country="Somewhere",
    severity_value=6.0,
    severity_unit="M",
    severity_text="Magnitude 6.0M",
) -> GdacsEvent:
    _src = source if source is not None else {
        "EQ": "NEIC", "TC": "JTWC", "FL": "GLOFAS", "WF": "GWIS"}.get(eventtype, "")
    return GdacsEvent(
        eventtype=eventtype,
        eventid=eventid,
        episodeid=episodeid,
        name=name or f"{eventtype} event",
        glide=glide,
        source=_src,
        source_id=source_id,
        lat=lat,
        lon=lon,
        from_date=from_date,
        to_date=from_date,
        date_modified=from_date,
        peak_level=peak_level,
        episode_level=episode_level if episode_level is not None else peak_level,
        peak_score=peak_score,
        episode_score=episode_score,
        score_format=score_format,
        is_current=is_current,
        is_temporary=is_temporary,
        iso3=iso3,
        country=country,
        severity_value=severity_value,
        severity_unit=severity_unit,
        severity_text=severity_text,
        report_url="https://www.gdacs.org/report.aspx",
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
