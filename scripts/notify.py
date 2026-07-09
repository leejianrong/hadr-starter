"""Notify loop — one-way Telegram push on a genuinely new / escalated fast-feed event.

A second, lighter cadence than the daily 08:30 sitrep (see scripts.sitrep): runs
~hourly on the FAST feeds only (USGS + GDACS). ReliefWeb is days-latent, so it
stays on the daily page and never drives an alert.

Shape A holds (ADR-0002/0005): the deterministic pipeline decides *what* happened
and the deterministic gate here decides *whether to push* — no model is in this
loop at all (Phase 1). A later phase may let a cheap model refine the wording of an
already-composed message; it will never gain a vote on severity, merges, or firing.

    uv run python -m scripts.notify --dry-run          # print, don't send (no secret)
    uv run python -m scripts.notify                    # live fetch + send
    uv run python -m scripts.notify --fixture F --gdacs-fixture G --dry-run

Config (env, never hard-coded) when actually sending:
    TELEGRAM_BOT_TOKEN     from @BotFather
    TELEGRAM_CHAT_ID       the channel/group to post to ("@name" or numeric "-100…")
    NOTIFY_DASHBOARD_URL   optional link to the full report, added as a footer
"""
from __future__ import annotations

import argparse
import html
import json
import logging
import os
import re
from argparse import Namespace
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from . import severity, sitrep, telegram
from .geo import Geo
from .model import ALERT_RANK, ReportItem
from .state import NotifyRow, StateStore

log = logging.getLogger("notify")

# The notify loop keeps its OWN state DB (its own Actions cache), decoupled from the
# daily sitrep's hadr-state.sqlite3 so the two cadences never race on one file.
DEFAULT_NOTIFY_STATE = "hadr-notify-state.sqlite3"

# The live report the alert links back to (GitHub Pages). Overridable via env for
# forks; defaults to the deployed page so a message always carries a real link.
LIVE_REPORT_URL = "https://leejianrong.github.io/hadr-starter/"

# --- the push gate (chattiness). Named + tunable, model-free (CLAUDE.md #1). ---
# Only orange/red impact reaches a phone; sub-orange stays on the daily page. The
# base trigger is still the pipeline's own new/escalation detection — this is the
# additional "is it worth interrupting someone" narrowing the user chose.
NOTIFY_MIN_RANK = ALERT_RANK["orange"]      # 2
# One honest exception: a big earthquake PAGER has not scored yet (alert=None, so
# rank 0) is still phone-worthy — silencing a fresh major quake because the impact
# model has not run would be the obvious failure. The message stays honest ("not
# yet scored for impact"); this only affects *priority*, never a severity claim.
NOTIFY_MAG_UNSCORED = 6.0                   # mww-family M at/above this
# Telegram caps a message at 4096 chars; cap items so one push can't overflow.
MAX_ITEMS_PER_MESSAGE = 10

GDACS_HAZARD = {
    "EQ": "Earthquake", "TC": "Tropical cyclone", "FL": "Flood", "WF": "Wildfire",
    "VO": "Volcano", "DR": "Drought", "TS": "Tsunami",
}


# --------------------------------------------------------------------------- gate

def notify_level(item: ReportItem) -> int:
    """Phone-worthiness of one report line: 0 = daily-page only, 2 = orange-equiv,
    3 = red. This is the axis the idempotency marker compares on, so an escalation
    (a higher level than last pushed) re-fires while a de-escalation never does."""
    rank = item.rank
    if rank >= NOTIFY_MIN_RANK:
        return rank
    # PAGER did not score it, but it is a major earthquake — treat as orange-equiv.
    if item.eq is not None and item.alert is None:
        m = item.eq.mainshock
        if (m.mag is not None and severity.is_mww_family(m.mag_type)
                and m.mag >= NOTIFY_MAG_UNSCORED):
            return NOTIFY_MIN_RANK
    return 0


def notify_key(item: ReportItem) -> str:
    """Stable idempotency key. A merged EQ+GDACS line keys on the physical
    earthquake (its identity), so the two feeds never double-alert it.

    Caveat (USGS #1): the USGS top-level id can change between runs; a re-keyed
    quake could, at worst, alert once more. Bounded and rare within an hourly loop;
    recorded in implementation-notes.md rather than papered over."""
    if item.eq is not None:
        return f"EQ:{item.eq.mainshock.id}"
    if item.gdacs is not None:
        return f"GDACS:{item.gdacs.key}"
    return f"{item.kind}:{_place(item)}"


@dataclass
class Decision:
    to_send: list[ReportItem]
    next_rows: list[NotifyRow]


def decide(items: list[ReportItem], prior: dict[str, NotifyRow],
           now: datetime) -> Decision:
    """Pure gate: which items to push + the markers to persist. Sends an item when
    it is phone-worthy AND either never pushed before or escalated above the level
    last pushed. Everything else is an idempotent skip (its prior marker stands)."""
    to_send: list[ReportItem] = []
    next_rows: list[NotifyRow] = []
    for it in items:
        level = notify_level(it)
        if level <= 0:
            continue
        key = notify_key(it)
        was = prior.get(key)
        if was is None or level > was.level:
            to_send.append(it)
            next_rows.append(NotifyRow(key=key, kind=it.kind, level=level,
                                       place=_place(it), notified_at=now))
    return Decision(to_send=to_send, next_rows=next_rows)


# ---------------------------------------------------------------------- formatting

def _esc(s: str) -> str:
    return html.escape(s or "")


def _place(item: ReportItem) -> str:
    if item.eq is not None:
        return item.eq.mainshock.place
    if item.gdacs is not None:
        return item.gdacs.name or item.gdacs.country
    return item.kind


def _iso3(item: ReportItem) -> tuple[str, ...]:
    if item.eq is not None:
        return item.eq.mainshock.iso3
    if item.gdacs is not None:
        return item.gdacs.iso3
    return ()


def _title(item: ReportItem) -> str:
    if item.eq is not None:
        m = item.eq.mainshock
        mag = f"M{m.mag:.1f}" if m.mag is not None else "M?"
        return f"Earthquake — {mag}"
    if item.gdacs is not None:
        return GDACS_HAZARD.get(item.gdacs.eventtype, item.gdacs.eventtype)
    return item.kind


def _severity_display(item: ReportItem) -> tuple[str, str]:
    """(emoji, impact line). None = a major quake PAGER hasn't rated (honest)."""
    alert = item.alert
    if alert == "red":
        return "🔴", "Impact: Red"
    if alert == "orange":
        return "🟠", "Impact: Orange"
    return "⚪", "Impact: not yet scored for impact"


def _link(item: ReportItem) -> str:
    if item.eq is not None:
        return f"https://earthquake.usgs.gov/earthquakes/eventpage/{item.eq.mainshock.id}"
    if item.gdacs is not None:
        return item.gdacs.report_url or ""
    return ""


def _block(item: ReportItem) -> str:
    emoji, impact = _severity_display(item)
    place = _esc(_place(item))
    iso3 = _iso3(item)
    if iso3:
        place += f" ({_esc(' '.join(iso3))})"
    lines = [f"{emoji} <b>{_esc(_title(item))}</b>", f"📍 {place}"]
    when = item.when
    if when is not None:
        lines.append(f"🕐 {when.astimezone(timezone.utc):%Y-%m-%d %H:%M UTC}")
    lines.append(impact)
    lines.append(f"Source: {_esc(', '.join(item.sources) or '—')}")
    link = _link(item)
    if link:
        lines.append(f'<a href="{_esc(link)}">View report</a>')
    return "\n".join(lines)


def format_message(items: list[ReportItem], now: datetime,
                   dashboard_url: str = "") -> str:
    """The deterministic push text — the same honest facts the dashboard shows, no
    summed figures, no invented numbers (ADR-0002). This IS the source of truth; a
    later model-refinement phase only rephrases it and falls back to this."""
    shown = items[:MAX_ITEMS_PER_MESSAGE]
    dropped = len(items) - len(shown)
    n = len(items)
    header = (f"<b>🚨 HADR alert — {n} event{'s' if n != 1 else ''}</b>\n"
              f"{now.astimezone(timezone.utc):%Y-%m-%d %H:%M UTC}")
    blocks = [header] + [_block(it) for it in shown]
    if dropped > 0:
        log.info("message capped at %d items (%d more not shown)",
                 MAX_ITEMS_PER_MESSAGE, dropped)
        blocks.append(f"…and {dropped} more — see the full report.")
    if dashboard_url:
        blocks.append(f'<a href="{_esc(dashboard_url)}">Full situation report</a>')
    return "\n\n".join(blocks)


# ------------------------------------------ Phase 2: emit → refine → send protocol
#
# The scheduled workflow runs three steps that hand off through files in a directory:
#   1. emit  (deterministic) — fetch + gate + decide; write the facts, the
#      deterministic message (the source of truth + fallback), and the markers.
#   2. refine (Claude Haiku via claude-code-action) — rewrite ONLY the wording into
#      message.refined.txt, guarded by skills/telegram-alert/SKILL.md.
#   3. send  (deterministic) — pick the refined text IFF it is safe, else the
#      default; POST; persist markers only after a confirmed send.
# Splitting the send from the decision keeps the model out of the trigger and the
# numbers (ADR-0002/0005): it can only rephrase text that is already correct.

BRIEF_FILE = "brief.json"
MESSAGE_FILE = "message.txt"
REFINED_FILE = "message.refined.txt"
MARKERS_FILE = "markers.json"

_NUM_RE = re.compile(r"\d+(?:\.\d+)?")


def _brief_for(items: list[ReportItem], now: datetime) -> dict:
    """The honest facts the refiner may draw on — exactly what the message shows,
    no figures it couldn't already see (mirrors sitrep.build_brief for the page)."""
    events = []
    for it in items:
        _, impact = _severity_display(it)
        events.append({
            "title": _title(it),
            "place": _place(it),
            "iso3": list(_iso3(it)),
            "impact": impact,
            "sources": it.sources,
            "when": it.when.astimezone(timezone.utc).isoformat() if it.when else None,
            "link": _link(it),
        })
    return {"count": len(items),
            "publish_utc": now.astimezone(timezone.utc).isoformat(),
            "events": events}


def _numbers(text: str) -> set[float]:
    """Numeric values in `text`, compared by value so 'M6.5' == 'magnitude 6.5' and
    '08' == '8' — the refiner may reformat, but not introduce a new figure."""
    return {float(m) for m in _NUM_RE.findall(text or "")}


def _refined_is_safe(refined: str, default: str) -> bool:
    """The refiner may only rephrase: every number it prints must already appear in
    the deterministic message. A novel figure is an invented number — reject and
    fall back (ADR-0002). Empty/whitespace also fails."""
    if not refined or not refined.strip():
        return False
    return _numbers(refined).issubset(_numbers(default))


def _emit(decision: "Decision", now: datetime, out_dir: str, dashboard_url: str) -> None:
    d = Path(out_dir)
    d.mkdir(parents=True, exist_ok=True)
    default_msg = format_message(decision.to_send, now, dashboard_url=dashboard_url)
    (d / MESSAGE_FILE).write_text(default_msg)
    (d / BRIEF_FILE).write_text(json.dumps(_brief_for(decision.to_send, now), indent=2))
    (d / MARKERS_FILE).write_text(json.dumps(
        [{"key": r.key, "kind": r.kind, "level": r.level, "place": r.place,
          "notified_at": r.notified_at.astimezone(timezone.utc).isoformat()}
         for r in decision.next_rows], indent=2))


def _choose_send_text(out_dir: str) -> str:
    """Refined text if present AND safe; otherwise the deterministic default."""
    d = Path(out_dir)
    default_msg = (d / MESSAGE_FILE).read_text()
    refined_path = d / REFINED_FILE
    if refined_path.exists():
        refined = refined_path.read_text()
        if _refined_is_safe(refined, default_msg):
            log.info("using Haiku-refined message")
            return refined.strip()
        log.warning("refined message rejected (empty or introduced a figure) — "
                    "sending the deterministic message")
    return default_msg


def _load_markers(out_dir: str) -> list[NotifyRow]:
    rows = json.loads((Path(out_dir) / MARKERS_FILE).read_text())
    return [NotifyRow(key=r["key"], kind=r["kind"], level=int(r["level"]),
                      place=r["place"], notified_at=datetime.fromisoformat(r["notified_at"]))
            for r in rows]


def _send_and_persist(text: str, rows: list[NotifyRow], state_path: str,
                      dry_run: bool) -> int:
    """Shared send tail: POST, then persist markers only on a confirmed send."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not dry_run and (not token or not chat_id):
        log.error("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set — cannot send. "
                  "Re-run with --dry-run to preview.")
        return 1
    try:
        telegram.send_message(token, chat_id, text, dry_run=dry_run)
    except Exception as exc:  # degrade loud, never crash the loop (mirror sitrep loaders)
        # A push that never landed must NOT be recorded, or the event is lost forever;
        # leaving the markers unsaved means it re-fires next tick. Exit 0 — a red X
        # every hour on a transient outage would be worse than a retry.
        log.error("send failed, not recording markers (will retry next tick): %s", exc)
        return 0
    if not dry_run:
        store = StateStore(state_path)
        store.upsert_notifications(rows)
        store.close()
    log.info("pushed %d event(s)%s", len(rows),
             " [dry-run, markers not saved]" if dry_run else "")
    return 0


# ---------------------------------------------------------------------------- I/O

def _fetch_items(args, geo: Geo, now: datetime) -> list[ReportItem]:
    """USGS + GDACS through the shared pipeline; ReliefWeb stays off the alert loop.

    Priors are empty on purpose: this loop derives its trigger from its OWN notify
    markers (see `decide`), not the daily change flags, so the page-oriented change
    detection inside build_report is irrelevant here. A failed feed degrades to no
    items — never a false alert (each adapter degrades loud in sitrep's loaders)."""
    load_args = Namespace(
        fixture=args.fixture,
        gdacs=True, gdacs_fixture=args.gdacs_fixture, gdacs_json_fixture=None,
        reliefweb=False, reliefweb_fixture=None,
    )
    raw, final_url, feed_ok, note = sitrep._load(load_args)
    gdacs_events, gdacs_feed = sitrep._load_gdacs(load_args, geo, now)
    report, _ = sitrep.build_report(
        raw, final_url, feed_ok, note, geo, now, prior={},
        gdacs_events=gdacs_events, gdacs_feed=gdacs_feed, gdacs_prior={},
    )
    return report.items


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="HADR ~hourly Telegram alert loop (USGS + GDACS)")
    parser.add_argument("--fixture", help="read a saved USGS payload instead of fetching")
    parser.add_argument("--gdacs-fixture", help="read a saved GDACS RSS payload")
    parser.add_argument("--state", default=DEFAULT_NOTIFY_STATE, help="notify state DB path")
    parser.add_argument("--now", help="ISO-8601 UTC time (default: now)")
    parser.add_argument("--dry-run", action="store_true",
                        help="format + print but do not POST (no token needed)")
    parser.add_argument("--emit-dir",
                        help="decide + write brief/message/markers to DIR, do not send "
                             "(step 1 of the model-refinement flow)")
    parser.add_argument("--send-dir",
                        help="send the (refined-or-default) message written in DIR "
                             "(step 3 of the model-refinement flow)")
    parser.add_argument("--github-output",
                        help="append `has_alert=...` to this file (GitHub Actions output)")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    now = (datetime.fromisoformat(args.now).replace(tzinfo=timezone.utc)
           if args.now else datetime.now(timezone.utc))
    dashboard_url = os.environ.get("NOTIFY_DASHBOARD_URL", LIVE_REPORT_URL)

    # --- send mode: transport only, decision already made by an earlier emit ---
    if args.send_dir:
        text = _choose_send_text(args.send_dir)
        return _send_and_persist(text, _load_markers(args.send_dir), args.state,
                                 args.dry_run)

    # --- emit / default: run the pipeline + the deterministic gate ---
    geo = Geo()
    store = StateStore(args.state)
    prior = store.load_notifications()
    items = _fetch_items(args, geo, now)
    decision = decide(items, prior, now)
    store.close()

    if args.emit_dir:
        _emit(decision, now, args.emit_dir, dashboard_url)
        has_alert = bool(decision.to_send)
        log.info("emit: %d event(s) to send (%d scanned)", len(decision.to_send),
                 len(items))
        if args.github_output:
            with open(args.github_output, "a") as f:
                f.write(f"has_alert={'true' if has_alert else 'false'}\n")
        return 0

    # --- default: all-in-one deterministic send (no model), for local use / Phase 1 ---
    if not decision.to_send:
        log.info("no new/escalated orange+ events — nothing to push (%d scanned)",
                 len(items))
        return 0
    text = format_message(decision.to_send, now, dashboard_url=dashboard_url)
    return _send_and_persist(text, decision.next_rows, args.state, args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
