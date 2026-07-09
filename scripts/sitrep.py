"""Orchestrator — USGS earthquakes → dashboard.html (V1 + V2).

Deterministic pipeline (no model, no schedule — those are V3):
fetch → normalize → decluster → threshold → detect change vs persisted state →
render. The page is regenerated every run (the timestamp is the heartbeat); the
change-detector decides what is loud. Run it:

    uv run python -m scripts.sitrep                 # live fetch → dashboard.html
    uv run python -m scripts.sitrep --fixture F     # offline, from a saved payload
    uv run python -m scripts.sitrep --state S       # choose the state DB path
"""
from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import changes, cluster, gdacs, render, severity, usgs
from . import decluster as dc
from .geo import Geo
from .model import FeedHealth, GdacsEvent, Report, ReportItem, from_ms
from .state import DEFAULT_PATH, GdacsStateRow, StateRow, StateStore

WINDOW_HOURS = 24
COVERAGE_USGS_ONLY = (
    "Coverage: earthquakes only (USGS). No flood/cyclone/epidemic/conflict "
    "monitoring yet. Onshore is approximated as inside a country polygon."
)
COVERAGE_MULTIHAZARD = (
    "Coverage: earthquakes (USGS) + GDACS multi-hazard (cyclone/flood/wildfire/"
    "volcano). No epidemic/conflict monitoring yet (ReliefWeb arrives next). "
    "Onshore is approximated as inside a country polygon."
)
log = logging.getLogger("sitrep")


def build_report(
    raw: dict, final_url: str, feed_ok: bool, feed_note: str, geo: Geo,
    now_utc: datetime, prior: dict[str, StateRow],
    gdacs_events: list[GdacsEvent] | None = None,
    gdacs_feed: FeedHealth | None = None,
    gdacs_prior: dict[str, GdacsStateRow] | None = None,
) -> tuple[Report, changes.DetectResult]:
    """Pure pipeline over already-fetched payloads — the testable core.

    USGS is passed as raw JSON; GDACS is passed as *parsed* events (the RSS-first /
    JSON drop-in boundary lives in `gdacs.py`, so this stays format-agnostic).
    Returns the Report and the USGS DetectResult; the GDACS pass (when run) hangs
    off `result.gdacs` so V1–V3's 2-tuple unpacking is unchanged.
    """
    window_start = now_utc - timedelta(hours=WINDOW_HOURS)
    quakes = usgs.parse(raw, geo=geo)
    in_window = [q for q in quakes if window_start <= q.time <= now_utc]

    clusters = dc.decluster(in_window)
    kept = [c for c in clusters if severity.passes_threshold(c.mainshock)]
    kept.sort(key=severity.cluster_sort_key, reverse=True)

    result = changes.detect(prior, kept, feed_ok=feed_ok, now=now_utc)

    gen = usgs.generated_ms(raw)
    as_of = from_ms(gen) if gen else (now_utc if feed_ok else None)
    usgs_feed = FeedHealth(name="USGS", url=final_url, ok=feed_ok, as_of=as_of,
                           note=feed_note)

    feeds = [usgs_feed]
    retractions = list(result.retractions)
    is_loud = result.is_loud
    gdacs_result: changes.GdacsDetectResult | None = None
    coverage = COVERAGE_USGS_ONLY

    # --- GDACS multi-hazard + the cross-feed join (V4) ---
    kept_gdacs: list[GdacsEvent] = []
    if gdacs_feed is not None:
        coverage = COVERAGE_MULTIHAZARD
        feeds.append(gdacs_feed)
        gprior = gdacs_prior or {}
        # Window on CURRENCY, not onset. Cyclones/floods/wildfires run for days: a
        # Red cyclone that began a week ago is still the top of today's report while
        # `iscurrent` holds. Windowing those out on onset time would be the "infer
        # 'ended' from age" error (GDACS #cap / ADR-0007). Non-current alerts fall
        # back to the 24h onset window so a stale record doesn't linger forever.
        windowed = [
            e for e in (gdacs_events or [])
            if e.is_current
            or (e.from_date is not None and window_start <= e.from_date <= now_utc)
        ]
        kept_gdacs = [e for e in windowed if severity.gdacs_passes_threshold(e)]
        gdacs_result = changes.detect_gdacs(
            gprior, kept_gdacs, feed_ok=gdacs_feed.ok, now=now_utc
        )
        retractions.extend(gdacs_result.retractions)
        is_loud = is_loud or gdacs_result.is_loud

    items = cluster.join(result.clusters, kept_gdacs)
    _annotate_changes(items, gdacs_result)
    items.sort(key=severity.item_sort_key, reverse=True)

    result.gdacs = gdacs_result
    report = Report(
        publish_utc=now_utc,
        window_start_utc=window_start,
        window_end_utc=now_utc,
        clusters=result.clusters,
        feeds=feeds,
        coverage_note=coverage,
        items=items,
        retractions=retractions,
        is_loud=is_loud,
    )
    return report, result


def _annotate_changes(items: list[ReportItem],
                      gdacs_result: changes.GdacsDetectResult | None) -> None:
    """Carry change flags onto the unified items. The USGS side already annotated
    its clusters; here we copy those through and fill in the GDACS side."""
    gchanges = gdacs_result.changes if gdacs_result else {}
    for it in items:
        if it.eq is not None:
            it.change, it.change_reason = it.eq.change, it.eq.change_reason
            # A merged, USGS-quiet line can still be loud on the GDACS side.
            if not it.change and it.gdacs is not None:
                flag, reason = gchanges.get(it.gdacs.key, (None, ""))
                it.change, it.change_reason = flag, reason
        elif it.gdacs is not None:
            it.change, it.change_reason = gchanges.get(it.gdacs.key, (None, ""))


def _brief_change(it: ReportItem) -> dict:
    """One loud item as facts for the narrator — no numbers it can't see (ADR-0002)."""
    entry: dict = {
        "kind": it.kind,
        "iso3": list(it.eq.mainshock.iso3 if it.eq else (it.gdacs.iso3 if it.gdacs else ())),
        "alert": it.alert,
        "change": it.change,
        "reason": it.change_reason,
        "sources": it.sources,
        "confidence": it.confidence,
        "independent": it.independent,
        "cross_links": it.cross_links,
    }
    if it.eq is not None:
        c = it.eq
        entry.update(
            place=c.mainshock.place,
            mag=c.mainshock.mag,
            mag_type=c.mainshock.mag_type,
            depth_km=c.mainshock.depth_km,
            aftershocks=len(c.aftershocks),
            swarm=c.is_swarm,
        )
    if it.gdacs is not None:
        g = it.gdacs
        entry.update(
            place=entry.get("place") or g.name or g.country,
            name=g.name,
            severity=g.severity_text,   # per-hazard text, never a summed figure
            gdacs_source=g.source,
        )
    return entry


def build_brief(report: Report) -> dict:
    """Machine-readable facts for the model narrator (V3). Only the loud items.

    The model narrates from this; it must invent no numbers not present here
    (ADR-0002). The `loud` flag is what the CI workflow branches on.
    """
    return {
        "loud": report.is_loud,
        "publish_utc": report.publish_utc.isoformat(),
        "coverage": report.coverage_note,
        "changes": [_brief_change(it) for it in report.items if it.change],
        "retractions": [
            {"place": r.place, "last_alert": r.last_alert, "last_mag": r.last_mag,
             "reason": r.reason}
            for r in report.retractions
        ],
    }


def _load(args) -> tuple[dict, str, bool, str]:
    """Return (raw, final_url, feed_ok, note). Degrade loud on fetch failure."""
    if args.fixture:
        raw = json.loads(Path(args.fixture).read_text())
        return raw, f"file://{Path(args.fixture).resolve()}", True, "offline fixture"
    try:
        raw, final_url = usgs.fetch()
        log.info("fetched USGS feed: %s", final_url)  # the FINAL url (CLAUDE.md #2)
        return raw, final_url, True, ""
    except Exception as exc:  # degrade loud, never crash the sitrep
        log.error("USGS fetch failed: %s", exc)
        return {"features": [], "metadata": {}}, usgs.FEED_URL, False, f"fetch failed: {exc}"


def _load_gdacs(args, geo: Geo, now: datetime
                ) -> tuple[list[GdacsEvent], FeedHealth] | tuple[None, None]:
    """Load GDACS (RSS-first, JSON drop-in). Returns (events, feed-health), or
    (None, None) when GDACS is not requested this run. Degrades loud on failure."""
    if not (args.gdacs or args.gdacs_fixture or args.gdacs_json_fixture):
        return None, None

    cap_note = (f"JSON list capped at {gdacs.JSON_LIST_CAP} (rolling) — an active "
                "event can age out; absence is not 'ended'")
    rss_note = "RSS mode (wider window; single ISO3, no source/GLIDE structure)"
    try:
        if args.gdacs_json_fixture:
            raw = json.loads(Path(args.gdacs_json_fixture).read_text())
            events = gdacs.parse_json(raw, geo=geo)
            url = f"file://{Path(args.gdacs_json_fixture).resolve()}"
            return events, FeedHealth(name="GDACS", url=url, ok=True, as_of=now,
                                      note=f"offline JSON fixture — {cap_note}")
        if args.gdacs_fixture:
            xml = Path(args.gdacs_fixture).read_text()
            events = gdacs.parse_rss(xml, geo=geo)
            url = f"file://{Path(args.gdacs_fixture).resolve()}"
            return events, FeedHealth(name="GDACS", url=url, ok=True,
                                      as_of=gdacs.channel_pubdate(xml) or now,
                                      note=f"offline RSS fixture — {rss_note}")
        # Live: RSS-first (ADR-0008).
        xml, final_url = gdacs.fetch_rss()
        log.info("fetched GDACS RSS feed: %s", final_url)  # final url (CLAUDE.md #2)
        events = gdacs.parse_rss(xml, geo=geo)
        return events, FeedHealth(name="GDACS", url=final_url, ok=True,
                                  as_of=gdacs.channel_pubdate(xml) or now,
                                  note=rss_note)
    except Exception as exc:  # degrade loud, never crash the sitrep
        log.error("GDACS fetch failed: %s", exc)
        return [], FeedHealth(name="GDACS", url=gdacs.FEED_URL_RSS, ok=False,
                              as_of=None, note=f"fetch failed: {exc}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="HADR morning sitrep (USGS + GDACS)")
    parser.add_argument("--fixture", help="read a saved USGS payload instead of fetching")
    parser.add_argument("--out", default="dashboard.html", help="output HTML path")
    parser.add_argument("--state", default=DEFAULT_PATH, help="state DB path")
    parser.add_argument("--brief", help="write a JSON brief (loud flag + changes) for the narrator")
    parser.add_argument("--now", help="ISO-8601 UTC publish time (default: now)")
    parser.add_argument("--gdacs", action="store_true",
                        help="also fetch GDACS live (RSS-first multi-hazard join)")
    parser.add_argument("--gdacs-fixture", help="read a saved GDACS RSS payload")
    parser.add_argument("--gdacs-json-fixture", help="read a saved GDACS JSON payload")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    now = (datetime.fromisoformat(args.now).replace(tzinfo=timezone.utc)
           if args.now else datetime.now(timezone.utc))

    geo = Geo()
    store = StateStore(args.state)
    prior = store.load()

    raw, final_url, feed_ok, note = _load(args)
    gdacs_events, gdacs_feed = _load_gdacs(args, geo, now)
    gdacs_prior = store.load_gdacs() if gdacs_feed is not None else None

    report, result = build_report(
        raw, final_url, feed_ok, note, geo, now, prior,
        gdacs_events=gdacs_events, gdacs_feed=gdacs_feed, gdacs_prior=gdacs_prior,
    )

    Path(args.out).write_text(render.render(report))

    if args.brief:
        Path(args.brief).write_text(json.dumps(build_brief(report), indent=2))

    # Persist only on a good fetch — never overwrite state from an outage (ADR-0007).
    if feed_ok:
        store.replace(result.next_rows)
    if gdacs_feed is not None and gdacs_feed.ok and result.gdacs is not None:
        store.replace_gdacs(result.gdacs.next_rows)
    store.close()

    verdict = "LOUD" if report.is_loud else "quiet"
    log.info("wrote %s — %d line(s), %d retraction(s), %s, usgs_ok=%s, gdacs=%s",
             args.out, len(report.items), len(report.retractions), verdict, feed_ok,
             "off" if gdacs_feed is None else f"ok={gdacs_feed.ok}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
