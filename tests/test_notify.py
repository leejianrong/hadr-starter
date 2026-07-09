"""Notify loop — the push gate, idempotency, and honest message formatting.

All offline: no token, no network. The gate is deterministic, so it is unit-tested
directly; the fixture flow is exercised end-to-end via `main(--dry-run)`.
"""
from __future__ import annotations

from datetime import datetime, timezone

from scripts import notify
from scripts.model import Cluster, ReportItem
from scripts.state import NotifyRow, StateStore

from .helpers import make_gdacs, make_quake

NOW = datetime(2026, 7, 8, 12, 0, tzinfo=timezone.utc)


def eq_item(**kw) -> ReportItem:
    q = make_quake(**kw)
    return ReportItem(kind="EQ", eq=Cluster(mainshock=q), sources=["USGS"])


def gdacs_item(**kw) -> ReportItem:
    g = make_gdacs(**kw)
    return ReportItem(kind=g.eventtype, gdacs=g, sources=[f"GDACS·{g.source}"])


# ------------------------------------------------------------------- the gate

def test_gate_orange_and_red_pass():
    assert notify.notify_level(gdacs_item(peak_level="Orange")) == 2
    assert notify.notify_level(gdacs_item(peak_level="Red")) == 3


def test_gate_sub_orange_is_daily_page_only():
    # A yellow-rated quake stays on the daily page, never a phone push.
    assert notify.notify_level(eq_item(alert="yellow", mag=5.5)) == 0
    assert notify.notify_level(eq_item(alert="green", mag=5.0)) == 0


def test_gate_unscored_major_quake_is_phone_worthy():
    # PAGER didn't run (alert=None) but it's a major mww-family quake — orange-equiv.
    assert notify.notify_level(eq_item(alert=None, mag=6.5, mag_type="mww")) == 2


def test_gate_unscored_small_or_wrong_magtype_stays_quiet():
    assert notify.notify_level(eq_item(alert=None, mag=5.2, mag_type="mww")) == 0
    # non-mww magnitudes aren't comparable for the gate (USGS) — do not push.
    assert notify.notify_level(eq_item(alert=None, mag=6.8, mag_type="mb")) == 0


# ------------------------------------------------------------- idempotency

def test_first_sight_sends_and_records():
    items = [gdacs_item(eventtype="TC", eventid=1, peak_level="Orange")]
    d = notify.decide(items, prior={}, now=NOW)
    assert d.to_send == items
    assert d.next_rows[0].key == "GDACS:TC1"
    assert d.next_rows[0].level == 2


def test_same_level_is_not_resent():
    prior = {"GDACS:TC1": NotifyRow("GDACS:TC1", "TC", 2, "x", NOW)}
    items = [gdacs_item(eventtype="TC", eventid=1, peak_level="Orange")]
    d = notify.decide(items, prior=prior, now=NOW)
    assert d.to_send == []


def test_escalation_resends():
    prior = {"GDACS:TC1": NotifyRow("GDACS:TC1", "TC", 2, "x", NOW)}
    items = [gdacs_item(eventtype="TC", eventid=1, peak_level="Red")]
    d = notify.decide(items, prior=prior, now=NOW)
    assert len(d.to_send) == 1
    assert d.next_rows[0].level == 3


def test_de_escalation_does_not_resend():
    prior = {"GDACS:TC1": NotifyRow("GDACS:TC1", "TC", 3, "x", NOW)}
    items = [gdacs_item(eventtype="TC", eventid=1, peak_level="Orange")]
    d = notify.decide(items, prior=prior, now=NOW)
    assert d.to_send == []


def test_below_threshold_never_tracked():
    items = [eq_item(alert="yellow", mag=5.0)]
    d = notify.decide(items, prior={}, now=NOW)
    assert d.to_send == [] and d.next_rows == []


def test_merged_eq_gdacs_keys_on_earthquake():
    q = make_quake(id="us7000", alert="orange")
    it = ReportItem(kind="EQ", eq=Cluster(mainshock=q), gdacs=make_gdacs(),
                    sources=["USGS", "GDACS·NEIC"])
    assert notify.notify_key(it) == "EQ:us7000"


# ------------------------------------------------------------- formatting

def test_message_is_honest_and_escaped():
    it = eq_item(id="us1", alert="red", mag=6.5, place="10 km W of A & B")
    msg = notify.format_message([it], NOW)
    assert "🔴" in msg and "Impact: Red" in msg
    assert "Earthquake — M6.5" in msg
    assert "Source: USGS" in msg
    assert "earthquake.usgs.gov/earthquakes/eventpage/us1" in msg
    assert "&amp;" in msg          # the raw "&" is HTML-escaped, never injected


def test_message_unscored_label():
    it = eq_item(alert=None, mag=6.4, mag_type="mww")
    msg = notify.format_message([it], NOW)
    assert "not yet scored for impact" in msg
    assert "⚪" in msg


def test_message_caps_items():
    items = [gdacs_item(eventid=i, peak_level="Orange") for i in range(15)]
    msg = notify.format_message(items, NOW)
    assert "and 5 more" in msg


# ------------------------------------------------------ state roundtrip

def test_notifications_upsert(tmp_path):
    p = tmp_path / "n.sqlite3"
    store = StateStore(p)
    store.upsert_notifications([NotifyRow("GDACS:TC1", "TC", 2, "here", NOW)])
    store.upsert_notifications([NotifyRow("GDACS:TC1", "TC", 3, "here", NOW)])  # escalate
    loaded = store.load_notifications()
    assert loaded["GDACS:TC1"].level == 3      # upsert updated in place, no dup
    store.close()


# ------------------------------------------------------ end-to-end (dry-run)

def test_main_dry_run_over_fixtures(tmp_path, caplog):
    import logging
    with caplog.at_level(logging.INFO, logger="notify.telegram"):
        rc = notify.main([
            "--fixture", "tests/fixtures/usgs_all_hour_sample.json",
            "--gdacs-fixture", "tests/fixtures/gdacs_rss_sample.xml",
            "--state", str(tmp_path / "n.sqlite3"),
            "--dry-run", "--now", "2026-07-08T12:00:00",
        ])
    assert rc == 0
    assert any("would POST" in r.message for r in caplog.records)
