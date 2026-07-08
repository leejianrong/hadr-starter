"""build_report: 24h window filtering, quiet path, degrade-loud feed health."""
from __future__ import annotations

from datetime import datetime, timezone

from scripts.sitrep import build_report
from tests.helpers import raw_feature, raw_feed

NOW = datetime(2026, 7, 8, 12, 0, tzinfo=timezone.utc)


class FakeGeo:
    def iso3_for(self, lat, lon):
        return ["XXX"]

    def is_onshore(self, lat, lon):
        return True


def _ms(y, mo, d, h=0):
    return int(datetime(y, mo, d, h, tzinfo=timezone.utc).timestamp() * 1000)


def test_window_excludes_events_older_than_24h():
    feed = raw_feed([
        raw_feature(eid="in", mag=6.5, time_ms=_ms(2026, 7, 8, 6)),    # in window
        raw_feature(eid="old", mag=6.5, time_ms=_ms(2026, 7, 6, 0)),   # >24h before NOW
    ])
    report, _ = build_report(feed, "file://x", True, "", FakeGeo(), NOW, {})
    shown = {c.mainshock.id for c in report.clusters}
    assert "in" in shown
    assert "old" not in shown


def test_quiet_report_has_no_clusters():
    feed = raw_feed([
        raw_feature(eid="tiny", mag=3.0, mag_type="ml", sig=50, time_ms=_ms(2026, 7, 8, 6)),
    ])
    report, _ = build_report(feed, "file://x", True, "", FakeGeo(), NOW, {})
    assert report.clusters == []
    assert report.feeds[0].ok is True
    assert report.is_loud is False


def test_degrade_loud_feed_unreachable():
    report, _ = build_report({"features": [], "metadata": {}}, "http://usgs", False,
                             "fetch failed: timeout", FakeGeo(), NOW, {})
    assert report.clusters == []
    feed = report.feeds[0]
    assert feed.ok is False
    assert feed.as_of is None
    assert "timeout" in feed.note


def test_first_run_marks_everything_new_and_loud():
    feed = raw_feed([raw_feature(eid="in", mag=6.5, time_ms=_ms(2026, 7, 8, 6))])
    report, result = build_report(feed, "file://x", True, "", FakeGeo(), NOW, {})
    assert report.is_loud is True
    assert report.clusters[0].change == "NEW"
    assert len(result.next_rows) == 1
