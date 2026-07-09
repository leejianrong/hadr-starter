"""V6: the 7-day history split, scanned-vs-shown summary, activity chart, and the
union change-detection that stops an aged-out event looking like a retraction."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from scripts.render import render
from scripts.sitrep import build_report
from tests.helpers import raw_feature, raw_feed

NOW = datetime(2026, 7, 8, 12, 0, tzinfo=timezone.utc)


class FakeGeo:
    def iso3_for(self, lat, lon):
        return ["XXX"]

    def is_onshore(self, lat, lon):
        return True


def _ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def _build(feed, now=NOW, prior=None):
    return build_report(feed, "file://x", True, "", FakeGeo(), now, prior or {})


def test_last_24h_event_is_sudden_not_recent():
    feed = raw_feed([raw_feature(eid="fresh", ids=",fresh,", mag=6.5,
                                 time_ms=_ms(NOW - timedelta(hours=6)))])
    report, _ = _build(feed)
    assert [it.eq.mainshock.id for it in report.items] == ["fresh"]
    assert report.recent == []


def test_two_day_old_event_is_recent_not_sudden():
    feed = raw_feed([raw_feature(eid="old", ids=",old,", mag=6.5,
                                 time_ms=_ms(NOW - timedelta(days=2)))])
    report, _ = _build(feed)
    assert report.items == []
    assert [it.eq.mainshock.id for it in report.recent] == ["old"]


def test_event_older_than_7_days_is_excluded():
    feed = raw_feed([raw_feature(eid="ancient", ids=",ancient,", mag=6.5,
                                 time_ms=_ms(NOW - timedelta(days=9)))])
    report, _ = _build(feed)
    assert report.items == []
    assert report.recent == []


def test_scan_summary_counts_and_activity_days():
    feed = raw_feed([
        raw_feature(eid="a", ids=",a,", mag=6.5, time_ms=_ms(NOW - timedelta(hours=3))),
        raw_feature(eid="b", ids=",b,", mag=6.6, lon=40.0, lat=40.0,
                    time_ms=_ms(NOW - timedelta(days=3))),
        raw_feature(eid="tiny", ids=",tiny,", mag=2.0, mag_type="ml", sig=10,
                    lon=-40.0, lat=-40.0, time_ms=_ms(NOW - timedelta(hours=1))),
    ])
    report, _ = _build(feed)
    s = report.scan
    assert s is not None
    assert s.usgs_scanned == 3        # all three are within the 7-day window
    assert s.shown_today == 1         # only "a" cleared the bar in the last 24h
    assert s.shown_week == 1          # "b" is the past-7-days line
    assert len(s.activity) == 7       # one bucket per day


def test_aged_out_event_is_not_a_retraction():
    # Publish an event fresh, then re-run two days later. It has aged from the 24h
    # brief into the Past-7-days section — that must NOT read as a withdrawal, and it
    # must not re-flag NEW.
    t = datetime(2026, 7, 8, 6, 0, tzinfo=timezone.utc)
    feed = raw_feed([raw_feature(eid="q", ids=",q,", mag=6.5, time_ms=_ms(t))])

    r1, res1 = _build(feed, now=datetime(2026, 7, 8, 12, 0, tzinfo=timezone.utc))
    assert [it.eq.mainshock.id for it in r1.items] == ["q"]
    assert r1.items[0].change == "NEW"

    prior = {row.key: row for row in res1.next_rows}
    r2, _ = _build(feed, now=datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc),
                   prior=prior)
    assert r2.retractions == []                                   # not withdrawn
    assert [it.eq.mainshock.id for it in r2.recent] == ["q"]       # now context
    assert r2.items == []
    assert all(it.change is None for it in r2.recent)             # quiet, not NEW again


def test_render_shows_scan_line_chart_and_past_week_section():
    feed = raw_feed([
        raw_feature(eid="a", ids=",a,", mag=6.5, time_ms=_ms(NOW - timedelta(hours=3))),
        raw_feature(eid="b", ids=",b,", mag=6.6, lon=40.0, lat=40.0,
                    time_ms=_ms(NOW - timedelta(days=3))),
    ])
    report, _ = _build(feed)
    html = render(report)
    assert "Scanned" in html and "Cleared the bar" in html
    assert "Past 7 days" in html
    assert "Significant events per day" in html      # the chart caption
    assert "<svg" in html
