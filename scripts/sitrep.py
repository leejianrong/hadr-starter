"""V1 orchestrator — USGS earthquakes → one-shot dashboard.html.

Deterministic pipeline, no model / no state / no schedule (those are V2/V3):
fetch → normalize → decluster → threshold → render. Run it:

    uv run python -m scripts.sitrep                 # live USGS fetch
    uv run python -m scripts.sitrep --fixture F     # offline, from a saved payload
    uv run python -m scripts.sitrep --out page.html # choose the output path
"""
from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import decluster as dc
from . import render, severity, usgs
from .geo import Geo
from .model import FeedHealth, Report, from_ms

WINDOW_HOURS = 24
COVERAGE_NOTE = (
    "Coverage: earthquakes only (USGS). No flood/cyclone/epidemic/conflict "
    "monitoring yet. Onshore is approximated as inside a country polygon."
)
log = logging.getLogger("sitrep")


def build_report(raw: dict, final_url: str, feed_ok: bool, feed_note: str,
                 geo: Geo, now_utc: datetime) -> Report:
    """Pure pipeline over an already-fetched payload — the testable core."""
    window_start = now_utc - timedelta(hours=WINDOW_HOURS)
    quakes = usgs.parse(raw, geo=geo)
    in_window = [q for q in quakes if window_start <= q.time <= now_utc]

    clusters = dc.decluster(in_window)
    kept = [c for c in clusters if severity.passes_threshold(c.mainshock)]
    kept.sort(key=severity.cluster_sort_key, reverse=True)

    gen = usgs.generated_ms(raw)
    as_of = from_ms(gen) if gen else (now_utc if feed_ok else None)
    feed = FeedHealth(name="USGS", url=final_url, ok=feed_ok, as_of=as_of, note=feed_note)

    return Report(
        publish_utc=now_utc,
        window_start_utc=window_start,
        window_end_utc=now_utc,
        clusters=kept,
        feeds=[feed],
        coverage_note=COVERAGE_NOTE,
    )


def _load(args) -> tuple[dict, str, bool, str]:
    """Return (raw, final_url, feed_ok, note). Degrade loud on fetch failure."""
    if args.fixture:
        raw = json.loads(Path(args.fixture).read_text())
        return raw, f"file://{Path(args.fixture).resolve()}", True, "offline fixture"
    try:
        raw, final_url = usgs.fetch()
        log.info("fetched USGS feed: %s", final_url)  # the FINAL url (CLAUDE.md #2)
        return raw, final_url, True, ""
    except Exception as exc:  # noqa: BLE001 — degrade loud, never crash the sitrep
        log.error("USGS fetch failed: %s", exc)
        return {"features": [], "metadata": {}}, usgs.FEED_URL, False, f"fetch failed: {exc}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="HADR morning sitrep (V1, USGS only)")
    parser.add_argument("--fixture", help="read a saved USGS payload instead of fetching")
    parser.add_argument("--out", default="dashboard.html", help="output HTML path")
    parser.add_argument("--now", help="ISO-8601 UTC publish time (default: now)")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    now = (datetime.fromisoformat(args.now).replace(tzinfo=timezone.utc)
           if args.now else datetime.now(timezone.utc))

    geo = Geo()
    raw, final_url, feed_ok, note = _load(args)
    report = build_report(raw, final_url, feed_ok, note, geo, now)

    out = Path(args.out)
    out.write_text(render.render(report))
    log.info("wrote %s — %d event(s) shown, feed_ok=%s", out, len(report.clusters), feed_ok)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
