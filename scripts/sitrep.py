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

from . import changes, render, severity, usgs
from . import decluster as dc
from .geo import Geo
from .model import FeedHealth, Report, from_ms
from .state import DEFAULT_PATH, StateRow, StateStore

WINDOW_HOURS = 24
COVERAGE_NOTE = (
    "Coverage: earthquakes only (USGS). No flood/cyclone/epidemic/conflict "
    "monitoring yet. Onshore is approximated as inside a country polygon."
)
log = logging.getLogger("sitrep")


def build_report(
    raw: dict, final_url: str, feed_ok: bool, feed_note: str, geo: Geo,
    now_utc: datetime, prior: dict[str, StateRow],
) -> tuple[Report, changes.DetectResult]:
    """Pure pipeline over an already-fetched payload — the testable core.

    Returns the Report and the DetectResult (whose `next_rows` the caller persists).
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
    feed = FeedHealth(name="USGS", url=final_url, ok=feed_ok, as_of=as_of, note=feed_note)

    report = Report(
        publish_utc=now_utc,
        window_start_utc=window_start,
        window_end_utc=now_utc,
        clusters=result.clusters,
        feeds=[feed],
        coverage_note=COVERAGE_NOTE,
        retractions=result.retractions,
        is_loud=result.is_loud,
    )
    return report, result


def build_brief(report: Report) -> dict:
    """Machine-readable facts for the model narrator (V3). Only the loud items.

    The model narrates from this; it must invent no numbers not present here
    (ADR-0002). The `loud` flag is what the CI workflow branches on.
    """
    return {
        "loud": report.is_loud,
        "publish_utc": report.publish_utc.isoformat(),
        "coverage": report.coverage_note,
        "changes": [
            {
                "place": c.mainshock.place,
                "iso3": list(c.mainshock.iso3),
                "mag": c.mainshock.mag,
                "mag_type": c.mainshock.mag_type,
                "alert": c.mainshock.alert,
                "depth_km": c.mainshock.depth_km,
                "change": c.change,
                "reason": c.change_reason,
                "aftershocks": len(c.aftershocks),
                "swarm": c.is_swarm,
            }
            for c in report.clusters
            if c.change
        ],
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="HADR morning sitrep (USGS)")
    parser.add_argument("--fixture", help="read a saved USGS payload instead of fetching")
    parser.add_argument("--out", default="dashboard.html", help="output HTML path")
    parser.add_argument("--state", default=DEFAULT_PATH, help="state DB path")
    parser.add_argument("--brief", help="write a JSON brief (loud flag + changes) for the narrator")
    parser.add_argument("--now", help="ISO-8601 UTC publish time (default: now)")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    now = (datetime.fromisoformat(args.now).replace(tzinfo=timezone.utc)
           if args.now else datetime.now(timezone.utc))

    geo = Geo()
    store = StateStore(args.state)
    prior = store.load()

    raw, final_url, feed_ok, note = _load(args)
    report, result = build_report(raw, final_url, feed_ok, note, geo, now, prior)

    Path(args.out).write_text(render.render(report))

    if args.brief:
        Path(args.brief).write_text(json.dumps(build_brief(report), indent=2))

    # Persist only on a good fetch — never overwrite state from an outage (ADR-0007).
    if feed_ok:
        store.replace(result.next_rows)
    store.close()

    verdict = "LOUD" if report.is_loud else "quiet"
    log.info("wrote %s — %d shown, %d retraction(s), %s, feed_ok=%s",
             args.out, len(report.clusters), len(report.retractions), verdict, feed_ok)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
