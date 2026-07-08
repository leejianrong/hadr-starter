"""Loud-change detection — the six triggers (ADR-0006)."""
from __future__ import annotations

from datetime import datetime, timezone

from scripts.changes import detect
from scripts.model import Cluster
from scripts.state import StateRow
from tests.helpers import make_quake

NOW = datetime(2026, 7, 8, 12, tzinfo=timezone.utc)


def _row(**kw):
    defaults = dict(key="k", ids=frozenset({"a"}), alert=None, mag=6.0, depth_km=10.0,
                    status="reviewed", lat=0.0, lon=0.0, place="p", last_seen=NOW,
                    published=True)
    defaults.update(kw)
    defaults["ids"] = frozenset(defaults["ids"])   # real state rows are always frozensets
    return StateRow(**defaults)


def _cluster(**kw):
    kw.setdefault("id", "a")
    kw.setdefault("ids", ["a"])
    return Cluster(mainshock=make_quake(**kw))


def test_new_event_is_loud():
    res = detect({}, [_cluster(id="x", ids=["x"])], feed_ok=True, now=NOW)
    assert res.clusters[0].change == "NEW"
    assert res.is_loud is True
    assert len(res.next_rows) == 1


def test_unchanged_event_is_quiet():
    prior = {"k": _row(ids=("a",), alert=None, mag=6.0, status="reviewed")}
    res = detect(prior, [_cluster(alert=None, mag=6.0, status="reviewed")], feed_ok=True, now=NOW)
    assert res.clusters[0].change is None
    assert res.is_loud is False
    assert res.retractions == []


def test_escalation_is_revised():
    prior = {"k": _row(alert="yellow")}
    res = detect(prior, [_cluster(alert="orange")], feed_ok=True, now=NOW)
    assert res.clusters[0].change == "REVISED"
    assert "escalated" in res.clusters[0].change_reason
    assert res.is_loud is True


def test_magnitude_revision_is_revised():
    prior = {"k": _row(mag=6.0)}
    res = detect(prior, [_cluster(mag=6.4)], feed_ok=True, now=NOW)
    assert res.clusters[0].change == "REVISED"
    assert "6.0" in res.clusters[0].change_reason


def test_reviewed_status_is_revised():
    prior = {"k": _row(status="automatic")}
    res = detect(prior, [_cluster(status="reviewed")], feed_ok=True, now=NOW)
    assert "now reviewed" in res.clusters[0].change_reason


def test_id_change_still_matches_not_new():
    # Top-level id changed (ci999) but shares us123 in the ids set — must match.
    prior = {"k": _row(ids=("us123",), mag=6.0)}
    res = detect(prior, [_cluster(id="ci999", ids=["ci999", "us123"], mag=6.0)],
                 feed_ok=True, now=NOW)
    assert res.clusters[0].change is None  # matched, unchanged — not NEW


def test_vanished_published_event_is_retracted():
    prior = {"k": _row(place="Old Place", alert="orange", mag=6.2)}
    res = detect(prior, [], feed_ok=True, now=NOW)
    assert len(res.retractions) == 1
    assert res.retractions[0].place == "Old Place"
    assert res.is_loud is True


def test_outage_never_manufactures_a_retraction():
    prior = {"k": _row()}
    res = detect(prior, [], feed_ok=False, now=NOW)
    assert res.retractions == []
    assert res.is_loud is False


def test_unpublished_row_not_retracted():
    prior = {"k": _row(published=False)}
    res = detect(prior, [], feed_ok=True, now=NOW)
    assert res.retractions == []
