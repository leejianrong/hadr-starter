"""GDACS multi-hazard feed adapter — ingestion + normalization (RSS-first).

GDACS is EU/UN, multi-hazard (EQ/TC/FL/WF/VO/DR). One record is an *automated
impact alert* versioned over the event's life — not a physical event (USGS) or a
curated situation (ReliefWeb). Built RSS-first (ADR-0008): `parse_rss` is the
primary path, `parse_json` a drop-in upgrade with the same output type.

Every trap from `docs/feed-blindspots.md` (GDACS section) is handled here and only
here, so the rest of the pipeline sees a clean `GdacsEvent`:

- `istemporary`/`iscurrent` are the **strings** "true"/"false", not JSON booleans.
- JSON dates carry **no timezone designator** but are UTC; RSS uses RFC-822 GMT —
  two parsers (`from_gdacs_naive` / `from_rfc822` in `model`).
- The numeric `alertscore` is **not interchangeable between JSON and RSS**, so the
  canonical severity is the colour (`alertlevel`); the raw score is tagged with its
  `score_format` and never compared across formats.
- `alertlevel`/`alertscore` are the **peak** for the whole event; `episode*` are the
  current episode (can differ). We carry both, rank on peak.
- ISO3 comes from the `affectedcountries` **array** (a list — spans borders), not
  the comma-joined `country` string. RSS only carries a single `<gdacs:iso3>`.
- `severitydata` is per-hazard and unit-heterogeneous (EQ=M, TC=km/h, WF=ha, FL
  often 0) — carried as value+unit+text, never compared across types.
- The JSON list is hard-capped at 100 (rolling); the caller notes this on the page
  and never infers "event ended" from "absent" (that lives in the change-detector).

Live fetch lazy-imports `requests` so parsing stays offline-testable. GDACS has no
CORS for browsers (we fetch server-side), no key, no observed rate limit, default
UA fine — send gzip and log the final URL (CLAUDE.md #2).
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

from .geo import Geo
from .model import GdacsEvent, from_gdacs_naive, from_rfc822

FEED_URL_RSS = "https://www.gdacs.org/xml/rss.xml"
FEED_URL_JSON = "https://www.gdacs.org/gdacsapi/api/events/geteventlist/EVENTS4APP"

# The JSON event list is capped at 100 records, rolling (blindspot). Surfaced on the
# feed-health line so an aged-out-but-active event never reads as "ended".
JSON_LIST_CAP = 100

# RSS carries no per-item `source`; it is deterministic from the hazard type.
_SOURCE_BY_TYPE = {"EQ": "NEIC", "TC": "JTWC", "FL": "GLOFAS", "WF": "GWIS",
                   "VO": "TOULOUSE", "DR": "GDACS", "TS": "NEIC"}

_NS = {
    "gdacs": "http://www.gdacs.org",
    "geo": "http://www.w3.org/2003/01/geo/wgs84_pos#",
    "georss": "http://www.georss.org/georss",
}


def _as_bool(s: str | None) -> bool:
    """GDACS booleans arrive as the STRINGS 'true'/'false' — `x == True` fails."""
    return (s or "").strip().lower() == "true"


def _to_int(s, default=None):
    try:
        return int(str(s).strip())
    except (TypeError, ValueError):
        return default


def _to_float(s, default=0.0):
    try:
        return float(s)
    except (TypeError, ValueError):
        return default


# --------------------------------------------------------------------------- JSON

def fetch_json(url: str = FEED_URL_JSON, timeout: float = 30.0) -> tuple[dict, str]:
    """Fetch the JSON event list. Returns (raw_json, final_url_actually_fetched)."""
    import requests

    resp = requests.get(url, headers={"Accept-Encoding": "gzip"}, timeout=timeout)
    resp.raise_for_status()
    return resp.json(), resp.url


def parse_json(raw: dict, geo: Geo | None = None) -> list[GdacsEvent]:
    """Normalize the GeoJSON FeatureCollection (EVENTS4APP) into GdacsEvents."""
    out: list[GdacsEvent] = []
    for feat in raw.get("features", []):
        p = feat.get("properties") or {}
        geom = feat.get("geometry") or {}
        coords = geom.get("coordinates") or [0.0, 0.0]
        lon, lat = coords[0], coords[1]

        iso3 = tuple(
            c.get("iso3") for c in (p.get("affectedcountries") or []) if c.get("iso3")
        )
        if not iso3 and p.get("iso3"):        # fall back to the singular field
            iso3 = (p["iso3"],)

        sev = p.get("severitydata") or {}
        out.append(
            GdacsEvent(
                eventtype=p.get("eventtype") or "",
                eventid=_to_int(p.get("eventid"), 0),
                episodeid=_to_int(p.get("episodeid")),
                name=p.get("name") or "",
                glide=p.get("glide") or "",
                source=p.get("source") or _SOURCE_BY_TYPE.get(p.get("eventtype"), ""),
                source_id=str(p.get("sourceid") or ""),
                lat=lat,
                lon=lon,
                from_date=from_gdacs_naive(p.get("fromdate")),
                to_date=from_gdacs_naive(p.get("todate")),
                date_modified=from_gdacs_naive(p.get("datemodified")),
                peak_level=p.get("alertlevel") or "",
                episode_level=p.get("episodealertlevel") or "",
                peak_score=_to_float(p.get("alertscore")),
                episode_score=_to_float(p.get("episodealertscore")),
                score_format="json",
                is_current=_as_bool(p.get("iscurrent")),
                is_temporary=_as_bool(p.get("istemporary")),
                iso3=iso3,
                country=p.get("country") or "",
                severity_value=(sev.get("severity") if sev.get("severity") is not None
                                else None),
                severity_unit=sev.get("severityunit") or "",
                severity_text=sev.get("severitytext") or "",
                report_url=(p.get("url") or {}).get("report") or "",
            )
        )
    return out


def generated_json(raw: dict) -> str | None:
    """No standard generated stamp on EVENTS4APP; expose our note if present."""
    return (raw.get("metadata") or {}).get("note")


# ---------------------------------------------------------------------------- RSS

def fetch_rss(url: str = FEED_URL_RSS, timeout: float = 30.0) -> tuple[str, str]:
    """Fetch the RSS feed. Returns (xml_text, final_url_actually_fetched)."""
    import requests

    resp = requests.get(url, headers={"Accept-Encoding": "gzip"}, timeout=timeout)
    resp.raise_for_status()
    return resp.text, resp.url


def _txt(item: ET.Element, path: str) -> str | None:
    el = item.find(path, _NS)
    return el.text.strip() if el is not None and el.text else None


def parse_rss(xml_text: str, geo: Geo | None = None) -> list[GdacsEvent]:
    """Normalize the GDACS RSS feed into GdacsEvents.

    RSS is the primary path (ADR-0008). It has a wider window than the 100-capped
    JSON but loses the structured `affectedcountries` list, `source`, and `sourceid`
    (derived / left empty here) — a documented RSS-mode limitation.
    """
    root = ET.fromstring(xml_text.lstrip("﻿"))
    out: list[GdacsEvent] = []
    for item in root.iter("item"):
        etype = _txt(item, "gdacs:eventtype") or ""

        lat = _to_float(_txt(item, "geo:lat"), 0.0)
        lon = _to_float(_txt(item, "geo:long"), 0.0)
        if lat == 0.0 and lon == 0.0:
            pt = _txt(item, "georss:point")
            if pt and len(pt.split()) == 2:
                lat, lon = (float(v) for v in pt.split())

        sev_el = item.find("gdacs:severity", _NS)
        sev_unit = sev_el.get("unit", "") if sev_el is not None else ""
        sev_val = _to_float(sev_el.get("value"), None) if sev_el is not None else None
        sev_txt = (sev_el.text or "").strip() if sev_el is not None else ""

        iso3s = _txt(item, "gdacs:iso3") or ""
        out.append(
            GdacsEvent(
                eventtype=etype,
                eventid=_to_int(_txt(item, "gdacs:eventid"), 0),
                episodeid=_to_int(_txt(item, "gdacs:episodeid")),
                name=_txt(item, "gdacs:eventname") or "",
                glide=_txt(item, "gdacs:glide") or "",
                source=_SOURCE_BY_TYPE.get(etype, ""),     # RSS carries no per-item source
                source_id="",                              # not in RSS
                lat=lat,
                lon=lon,
                from_date=from_rfc822(_txt(item, "gdacs:fromdate")),
                to_date=from_rfc822(_txt(item, "gdacs:todate")),
                date_modified=from_rfc822(_txt(item, "gdacs:datemodified")),
                peak_level=_txt(item, "gdacs:alertlevel") or "",
                episode_level=_txt(item, "gdacs:episodealertlevel") or "",
                peak_score=_to_float(_txt(item, "gdacs:alertscore")),
                episode_score=_to_float(_txt(item, "gdacs:episodealertscore")),
                score_format="rss",     # NOT comparable to a JSON score (blindspot)
                is_current=_as_bool(_txt(item, "gdacs:iscurrent")),
                is_temporary=_as_bool(_txt(item, "gdacs:temporary")),
                iso3=(iso3s,) if iso3s else (),
                country=_txt(item, "gdacs:country") or "",
                severity_value=sev_val,
                severity_unit=sev_unit,
                severity_text=sev_txt,
                report_url=_txt(item, "link") or "",
            )
        )
    return out


def channel_pubdate(xml_text: str):
    """The RSS channel's own pubDate (UTC) — the feed-health 'as of'."""
    root = ET.fromstring(xml_text.lstrip("﻿"))
    chan = root.find("channel")
    if chan is None:
        return None
    el = chan.find("pubDate")
    return from_rfc822(el.text) if el is not None and el.text else None
