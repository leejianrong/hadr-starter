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

from . import changes, cluster, gdacs, reliefweb, render, severity, usgs
from . import decluster as dc
from .geo import Geo
from .model import (
    ALERT_RANK,
    SGT,
    ActivityDay,
    FeedHealth,
    GdacsEvent,
    ReliefWebDisaster,
    Report,
    ReportItem,
    ScanSummary,
    from_ms,
)
from .state import (
    DEFAULT_PATH,
    GdacsStateRow,
    ReliefWebStateRow,
    StateRow,
    StateStore,
)

COVERAGE_USGS_ONLY = (
    "Coverage: earthquakes only (USGS). No flood/cyclone/epidemic/conflict "
    "monitoring yet. Onshore is approximated as inside a country polygon."
)
COVERAGE_MULTIHAZARD = (
    "Coverage: earthquakes (USGS) + GDACS multi-hazard (cyclone/flood/wildfire/"
    "volcano). No epidemic/conflict monitoring yet (ReliefWeb arrives next). "
    "Onshore is approximated as inside a country polygon."
)
COVERAGE_FULL = (
    "Coverage: earthquakes (USGS) + GDACS multi-hazard + ReliefWeb curated "
    "disasters (incl. epidemics & conflict). ReliefWeb is in RSS mode — see "
    "feed-health for what the API would add. Onshore is approximated as inside a "
    "country polygon."
)
WINDOW_HOURS = 24        # sudden-onset "what's new" window
LOOKBACK_DAYS = 7        # Past-7-days context section reaches back this far
log = logging.getLogger("sitrep")


def build_report(
    raw: dict, final_url: str, feed_ok: bool, feed_note: str, geo: Geo,
    now_utc: datetime, prior: dict[str, StateRow],
    gdacs_events: list[GdacsEvent] | None = None,
    gdacs_feed: FeedHealth | None = None,
    gdacs_prior: dict[str, GdacsStateRow] | None = None,
    reliefweb_disasters: list[ReliefWebDisaster] | None = None,
    reliefweb_feed: FeedHealth | None = None,
    reliefweb_prior: dict[str, ReliefWebStateRow] | None = None,
) -> tuple[Report, changes.DetectResult]:
    """Pure pipeline over already-fetched payloads — the testable core.

    USGS is passed as raw JSON; GDACS and ReliefWeb are passed as *parsed* records
    (the RSS-first / API drop-in boundary lives in each adapter, so this stays
    format-agnostic). Returns the Report and the USGS DetectResult; the GDACS and
    ReliefWeb passes (when run) hang off `result.gdacs` / `result.reliefweb` so
    V1–V3's 2-tuple unpacking is unchanged.
    """
    window_start = now_utc - timedelta(hours=WINDOW_HOURS)   # last 24h (the brief)
    week_start = now_utc - timedelta(days=LOOKBACK_DAYS)      # past 7 days (context)

    quakes = usgs.parse(raw, geo=geo)
    in_week = [q for q in quakes if week_start <= q.time <= now_utc]

    # Decluster over the whole week, then split by mainshock time: fresh clusters are
    # the sudden-onset brief; older ones are the Past-7-days context section.
    week_clusters = dc.decluster(in_week)
    kept = [c for c in week_clusters if severity.passes_threshold(c.mainshock)]
    kept.sort(key=severity.cluster_sort_key, reverse=True)
    today_clusters = [c for c in kept if c.mainshock.time >= window_start]
    recent_clusters = [c for c in kept if c.mainshock.time < window_start]

    # Change detection runs over the FULL 7-day kept set so an event ageing from the
    # 24h brief into the context section is still "seen" — never a spurious retraction
    # just for getting older (only a real withdrawal/below-threshold drop retracts).
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
    usgs_scanned = len(in_week)
    gdacs_scanned = reliefweb_scanned = 0

    # --- GDACS multi-hazard + the cross-feed join (V4) ---
    gdacs_today: list[GdacsEvent] = []
    gdacs_recent: list[GdacsEvent] = []
    if gdacs_feed is not None:
        coverage = COVERAGE_MULTIHAZARD
        feeds.append(gdacs_feed)
        gdacs_scanned = len(gdacs_events or [])
        gprior = gdacs_prior or {}
        # Sudden-onset windows on CURRENCY, not onset. Cyclones/floods/wildfires run
        # for days: a Red cyclone begun a week ago is still today's top line while
        # `iscurrent` holds. Inferring "ended" from age would be the ADR-0007 error.
        gdacs_today = [
            e for e in (gdacs_events or [])
            if severity.gdacs_passes_threshold(e)
            and (e.is_current
                 or (e.from_date is not None and window_start <= e.from_date <= now_utc))
        ]
        # Past-7-days GDACS: significant events that have since closed (not current)
        # with an onset inside the week but before the 24h brief.
        gdacs_recent = [
            e for e in (gdacs_events or [])
            if severity.gdacs_passes_threshold(e) and not e.is_current
            and e.from_date is not None and week_start <= e.from_date < window_start
        ]
        gdacs_result = changes.detect_gdacs(
            gprior, gdacs_today, feed_ok=gdacs_feed.ok, now=now_utc
        )
        retractions.extend(gdacs_result.retractions)
        is_loud = is_loud or gdacs_result.is_loud

    result.clusters = today_clusters   # brief + narrator see only the 24h set
    items = cluster.join(today_clusters, gdacs_today)
    _annotate_changes(items, gdacs_result)
    items.sort(key=severity.item_sort_key, reverse=True)

    recent = cluster.join(recent_clusters, gdacs_recent)
    _annotate_changes(recent, None)    # historical context; GDACS-recent isn't re-flagged
    recent.sort(key=severity.item_sort_key, reverse=True)

    # --- ReliefWeb curated disasters + slow-onset/ongoing section (V5) ---
    ongoing: list[ReportItem] = []
    reliefweb_result: changes.ReliefWebDetectResult | None = None
    if reliefweb_feed is not None:
        coverage = COVERAGE_FULL
        feeds.append(reliefweb_feed)
        disasters = reliefweb_disasters or []
        reliefweb_scanned = len(disasters)
        # Every curated disaster clears the bar (the "reached ReliefWeb" floor,
        # ADR-0004 branch 3) and is window-exempt — slow-onset has no onset instant.
        reliefweb_result = changes.detect_reliefweb(reliefweb_prior or {}, disasters,
                                                    now=now_utc)
        is_loud = is_loud or reliefweb_result.is_loud
        # GLIDE-stack onto sudden-onset lines; the rest become ongoing items.
        ongoing = cluster.attach_reliefweb(items, disasters)
        rchanges = reliefweb_result.changes
        for it in ongoing:
            if it.reliefweb is not None:
                it.change, it.change_reason = rchanges.get(it.reliefweb.key, (None, ""))
        ongoing.sort(key=severity.ongoing_sort_key, reverse=True)

    scan = ScanSummary(
        usgs_scanned=usgs_scanned,
        gdacs_scanned=gdacs_scanned,
        reliefweb_scanned=reliefweb_scanned,
        shown_today=len(items),
        shown_week=len(recent),
        ongoing=len(ongoing),
        activity=_build_activity(now_utc, kept, gdacs_today + gdacs_recent),
    )

    result.gdacs = gdacs_result
    result.reliefweb = reliefweb_result
    report = Report(
        publish_utc=now_utc,
        window_start_utc=window_start,
        window_end_utc=now_utc,
        clusters=today_clusters,
        feeds=feeds,
        coverage_note=coverage,
        items=items,
        recent=recent,
        ongoing=ongoing,
        retractions=retractions,
        scan=scan,
        is_loud=is_loud,
    )
    return report, result


def _build_activity(now_utc: datetime, eq_clusters, gdacs_events) -> list[ActivityDay]:
    """Per-day counts (by severity rank) over the last 7 days, for the activity chart.
    Uses SGT calendar days so the bars line up with the report's clock."""
    today_sgt = now_utc.astimezone(SGT).date()
    days = [today_sgt - timedelta(days=n) for n in range(LOOKBACK_DAYS - 1, -1, -1)]
    buckets = {d: ActivityDay(label=d.strftime("%b %d"), counts={0: 0, 1: 0, 2: 0, 3: 0})
               for d in days}
    for c in eq_clusters:
        d = c.mainshock.time.astimezone(SGT).date()
        if d in buckets:
            buckets[d].counts[severity.severity_rank(c.mainshock)] += 1
    for e in gdacs_events:
        if e.from_date is None:
            continue
        d = e.from_date.astimezone(SGT).date()
        if d in buckets:
            buckets[d].counts[ALERT_RANK.get(e.alert, 0)] += 1
    return [buckets[d] for d in days]


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


def _iso3_for(it: ReportItem) -> list[str]:
    if it.eq is not None:
        return list(it.eq.mainshock.iso3)
    if it.gdacs is not None:
        return list(it.gdacs.iso3)
    if it.reliefweb is not None:
        return list(it.reliefweb.iso3)
    return []


def _brief_change(it: ReportItem) -> dict:
    """One loud item as facts for the narrator — no numbers it can't see (ADR-0002)."""
    entry: dict = {
        "kind": it.kind,
        "iso3": _iso3_for(it),
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
    if it.reliefweb is not None:
        d = it.reliefweb
        entry.update(
            place=entry.get("place") or d.title,
            reliefweb_title=d.title,
            glide=d.glide,
            # The prose summary is context, NOT a source of figures to restate.
            reliefweb_summary=d.summary,
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
        "changes": [_brief_change(it)
                    for it in (report.items + report.ongoing) if it.change],
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


def _load_reliefweb(args, geo: Geo, now: datetime
                    ) -> tuple[list[ReliefWebDisaster], FeedHealth] | tuple[None, None]:
    """Load ReliefWeb (RSS-first, API drop-in). Returns (disasters, feed-health), or
    (None, None) when not requested. Degrades loud on failure."""
    if not (args.reliefweb or args.reliefweb_fixture):
        return None, None

    # The RSS-mode gaps, stated loud on the page (ADR-0008): no status/type/full
    # ISO3/date.event, and only the latest ~20 items (a burst can be dropped).
    rss_note = ("RSS mode, no API — status (alert/current/past), structured "
                "multi-country ISO3, date.event, and pagination (latest ~20 only) "
                "unavailable; request the appname to upgrade")
    try:
        if args.reliefweb_fixture:
            xml = Path(args.reliefweb_fixture).read_text()
            disasters = reliefweb.parse_rss(xml, geo=geo)
            url = f"file://{Path(args.reliefweb_fixture).resolve()}"
            note = f"offline RSS fixture ({reliefweb.item_count(xml)} items) — {rss_note}"
            return disasters, FeedHealth(name="ReliefWeb", url=url, ok=True,
                                         as_of=now, note=note)
        xml, final_url = reliefweb.fetch_rss()
        log.info("fetched ReliefWeb RSS feed: %s", final_url)  # final url (CLAUDE.md #2)
        disasters = reliefweb.parse_rss(xml, geo=geo)
        note = f"{reliefweb.item_count(xml)} items — {rss_note}"
        return disasters, FeedHealth(name="ReliefWeb", url=final_url, ok=True,
                                     as_of=now, note=note)
    except Exception as exc:  # degrade loud, never crash the sitrep
        log.error("ReliefWeb fetch failed: %s", exc)
        return [], FeedHealth(name="ReliefWeb", url=reliefweb.FEED_URL_RSS, ok=False,
                              as_of=None, note=f"fetch failed: {exc}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="HADR morning sitrep (USGS + GDACS + ReliefWeb)")
    parser.add_argument("--fixture", help="read a saved USGS payload instead of fetching")
    parser.add_argument("--out", default="dashboard.html", help="output HTML path")
    parser.add_argument("--state", default=DEFAULT_PATH, help="state DB path")
    parser.add_argument("--brief", help="write a JSON brief (loud flag + changes) for the narrator")
    parser.add_argument("--now", help="ISO-8601 UTC publish time (default: now)")
    parser.add_argument("--gdacs", action="store_true",
                        help="also fetch GDACS live (RSS-first multi-hazard join)")
    parser.add_argument("--gdacs-fixture", help="read a saved GDACS RSS payload")
    parser.add_argument("--gdacs-json-fixture", help="read a saved GDACS JSON payload")
    parser.add_argument("--reliefweb", action="store_true",
                        help="also fetch ReliefWeb live (RSS-first curated disasters)")
    parser.add_argument("--reliefweb-fixture", help="read a saved ReliefWeb RSS payload")
    parser.add_argument("--all-feeds", action="store_true",
                        help="shorthand for --gdacs --reliefweb (live)")
    args = parser.parse_args(argv)
    if args.all_feeds:
        args.gdacs = args.reliefweb = True

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    now = (datetime.fromisoformat(args.now).replace(tzinfo=timezone.utc)
           if args.now else datetime.now(timezone.utc))

    geo = Geo()
    store = StateStore(args.state)
    prior = store.load()

    raw, final_url, feed_ok, note = _load(args)
    gdacs_events, gdacs_feed = _load_gdacs(args, geo, now)
    gdacs_prior = store.load_gdacs() if gdacs_feed is not None else None
    reliefweb_disasters, reliefweb_feed = _load_reliefweb(args, geo, now)
    reliefweb_prior = store.load_reliefweb() if reliefweb_feed is not None else None

    report, result = build_report(
        raw, final_url, feed_ok, note, geo, now, prior,
        gdacs_events=gdacs_events, gdacs_feed=gdacs_feed, gdacs_prior=gdacs_prior,
        reliefweb_disasters=reliefweb_disasters, reliefweb_feed=reliefweb_feed,
        reliefweb_prior=reliefweb_prior,
    )

    Path(args.out).write_text(render.render(report))

    if args.brief:
        Path(args.brief).write_text(json.dumps(build_brief(report), indent=2))

    # Persist only on a good fetch — never overwrite state from an outage (ADR-0007).
    if feed_ok:
        store.replace(result.next_rows)
    if gdacs_feed is not None and gdacs_feed.ok and result.gdacs is not None:
        store.replace_gdacs(result.gdacs.next_rows)
    if reliefweb_feed is not None and reliefweb_feed.ok and result.reliefweb is not None:
        store.replace_reliefweb(result.reliefweb.next_rows)
    store.close()

    verdict = "LOUD" if report.is_loud else "quiet"
    log.info("wrote %s — %d sudden + %d ongoing, %d retraction(s), %s, usgs_ok=%s, "
             "gdacs=%s, reliefweb=%s",
             args.out, len(report.items), len(report.ongoing), len(report.retractions),
             verdict, feed_ok, "off" if gdacs_feed is None else f"ok={gdacs_feed.ok}",
             "off" if reliefweb_feed is None else f"ok={reliefweb_feed.ok}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
