"""Deterministic HTML renderer for the morning sitrep (Shape A, part A6).

Pure: takes a Report, returns an HTML string — no model, no clock of its own (the
Report carries all times), so a quiet morning renders byte-identically except for
the timestamps it is handed. Fixed four-section anatomy (CONTEXT / ADR-0003).
"""
from __future__ import annotations

import html
from datetime import datetime

from .model import SGT, Cluster, FeedHealth, Quake, Report

_ALERT_COLOURS = {
    "red": "#c0392b",
    "orange": "#e67e22",
    "yellow": "#d4ac0d",
    "green": "#27ae60",
}


def _sgt(dt: datetime) -> str:
    return dt.astimezone(SGT).strftime("%Y-%m-%d %H:%M SGT")


def _age(as_of: datetime, now: datetime) -> str:
    secs = (now - as_of).total_seconds()
    if secs < 3600:
        return f"{int(secs // 60)}m ago"
    if secs < 86400:
        return f"{int(secs // 3600)}h ago"
    return f"{int(secs // 86400)}d ago"


def _chip(alert: str | None) -> str:
    if alert:
        colour = _ALERT_COLOURS.get(alert, "#7f8c8d")
        return f'<span class="chip" style="background:{colour}">{alert.upper()}</span>'
    # PAGER did not run — a neutral marker, never dressed up as a severity colour.
    return '<span class="chip chip-none">NO PAGER</span>'


def _where(q: Quake) -> str:
    if q.iso3:
        return html.escape(f"{q.place} [{', '.join(q.iso3)}]")
    tag = "offshore" if q.is_offshore else q.place
    marker = ' <span class="muted">(offshore)</span>' if q.is_offshore else ""
    return html.escape(q.place or tag) + marker


def _mag(q: Quake) -> str:
    if q.mag is None:
        return "M?"
    mt = f" {html.escape(q.mag_type)}" if q.mag_type else ""
    return f"M{q.mag:.1f}<span class='muted'>{mt}</span>"


def _sequence(c: Cluster) -> str:
    la = c.largest_aftershock
    if c.is_swarm:
        largest = f", largest M{la.mag:.1f}" if la and la.mag is not None else ""
        return f'<span class="muted"> — swarm, no dominant event ({c.count} events{largest})</span>'
    if la is not None:
        largest = f", largest M{la.mag:.1f}" if la.mag is not None else ""
        return f'<span class="muted"> + {len(c.aftershocks)} aftershocks{largest}</span>'
    return ""


def _event_line(c: Cluster, now: datetime) -> str:
    q = c.mainshock
    return (
        '<li class="event">'
        f"{_chip(q.alert)}"
        f'<span class="what">{_where(q)}</span>'
        f'<span class="meta">{_mag(q)}{_sequence(c)} · depth {q.depth_km:.0f} km'
        f' · {_sgt(q.time)} ({_age(q.time, now)})</span>'
        "</li>"
    )


def _feed_line(f: FeedHealth, now: datetime) -> str:
    if f.ok:
        status = '<span class="ok">● up</span>'
        asof = f"as of {_sgt(f.as_of)} ({_age(f.as_of, now)})" if f.as_of else "as of —"
    else:
        status = '<span class="down">● UNREACHABLE</span>'
        asof = f"last good {_sgt(f.as_of)}" if f.as_of else "no data"
    note = f' — {html.escape(f.note)}' if f.note else ""
    return (
        f'<li>{status} <strong>{html.escape(f.name)}</strong> · {asof}{note}'
        f'<br><span class="url">{html.escape(f.url)}</span></li>'
    )


def render(report: Report) -> str:
    now = report.publish_utc
    window = f"last 24h ending {_sgt(report.window_end_utc)}"

    if report.clusters:
        events = "\n".join(_event_line(c, now) for c in report.clusters)
        sudden = f'<ul class="events">\n{events}\n</ul>'
    else:
        sudden = ('<p class="nothing">No new sudden-onset events crossed threshold '
                  f'in the {html.escape(window)}.</p>')

    feeds = "\n".join(_feed_line(f, now) for f in report.feeds)

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>HADR morning sitrep — {_sgt(report.publish_utc)}</title>
<style>
  :root {{ color-scheme: light dark; }}
  body {{ font: 15px/1.5 system-ui, sans-serif; max-width: 820px; margin: 2rem auto;
         padding: 0 1rem; color: #1a1a1a; }}
  @media (prefers-color-scheme: dark) {{ body {{ color: #e8e8e8; background: #16181c; }} }}
  h1 {{ font-size: 1.4rem; margin: 0 0 .2rem; }}
  h2 {{ font-size: 1rem; text-transform: uppercase; letter-spacing: .05em;
        border-bottom: 1px solid #8884; padding-bottom: .25rem; margin: 1.8rem 0 .6rem; }}
  .sub {{ color: #7f8c8d; font-size: .85rem; }}
  .banner {{ background: #f39c1222; border-left: 3px solid #f39c12; padding: .5rem .75rem;
             margin: .8rem 0; font-size: .9rem; }}
  ul {{ list-style: none; padding: 0; margin: 0; }}
  .events li {{ padding: .55rem 0; border-bottom: 1px solid #8882; }}
  .chip {{ display: inline-block; color: #fff; font-size: .72rem; font-weight: 700;
           padding: .1rem .4rem; border-radius: 3px; margin-right: .5rem; vertical-align: 1px; }}
  .chip-none {{ background: #95a5a6; color: #fff; }}
  .what {{ font-weight: 600; }}
  .meta {{ display: block; color: #7f8c8d; font-size: .85rem; margin-top: .15rem; }}
  .muted {{ color: #95a5a6; }}
  .nothing {{ color: #7f8c8d; font-style: italic; }}
  .ok {{ color: #27ae60; }} .down {{ color: #c0392b; font-weight: 700; }}
  .url {{ color: #95a5a6; font-size: .75rem; word-break: break-all; }}
  footer {{ color: #95a5a6; font-size: .78rem; margin-top: 2rem; }}
</style>
</head>
<body>
<h1>HADR morning situation report</h1>
<p class="sub">Published {_sgt(report.publish_utc)} · window: {html.escape(window)}</p>
<div class="banner">{html.escape(report.coverage_note)}</div>

<h2>Sudden-onset · {html.escape(window)}</h2>
{sudden}

<h2>Slow-onset / ongoing</h2>
<p class="nothing">No slow-onset sources yet — GDACS and ReliefWeb arrive in later slices.</p>

<h2>Feed health</h2>
<ul class="feeds">
{feeds}
</ul>

<footer>
Severity is impact (PAGER), shown as a colour — magnitude is a descriptor only.
Automatic solutions are preliminary and may be revised or withdrawn. Generated
deterministically; no figures are summed across sources.
</footer>
</body>
</html>
"""
