"""End-to-end V2 flow: two runs share state → NEW first, quiet second."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from scripts import sitrep
from tests.helpers import raw_feature, raw_feed

NOW = "2026-07-08T08:30"
# An M6.5 event shows anywhere (>= MAG_SHOW_ANYWHERE), so onshore/geo don't matter.
# 2026-07-08 06:00 UTC — inside the 24h window ending 08:30.
EVENT_MS = int(datetime(2026, 7, 8, 6, 0, tzinfo=timezone.utc).timestamp() * 1000)


def _write_feed(tmp_path):
    feed = raw_feed([raw_feature(eid="ev1", mag=6.5, time_ms=EVENT_MS)])
    p = tmp_path / "feed.json"
    p.write_text(json.dumps(feed))
    return p


def _run(feed, state, out):
    return sitrep.main(["--fixture", str(feed), "--state", str(state),
                        "--out", str(out), "--now", NOW])


def test_new_then_quiet_across_runs(tmp_path):
    feed = _write_feed(tmp_path)
    state = tmp_path / "state.sqlite3"
    out = tmp_path / "dashboard.html"

    assert _run(feed, state, out) == 0
    first = out.read_text()
    assert "NEW" in first
    assert "update(s) since last run" in first

    assert _run(feed, state, out) == 0
    second = out.read_text()
    assert "NEW" not in second
    assert "no changes since last run" in second


def test_withdrawn_event_produces_correction(tmp_path):
    feed = _write_feed(tmp_path)
    empty = tmp_path / "empty.json"
    empty.write_text(json.dumps(raw_feed([])))
    state = tmp_path / "state.sqlite3"
    out = tmp_path / "dashboard.html"

    _run(feed, state, out)                       # event published
    _run(empty, state, out)                      # feed no longer lists it
    final = out.read_text()
    assert "CORRECTED" in final
