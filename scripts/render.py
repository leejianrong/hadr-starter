"""Deterministic HTML renderer for the morning sitrep (Shape A, part A6).

Pure: takes a Report, returns an HTML string — no model, no clock of its own (the
Report carries all times), so a quiet morning renders byte-identically except for
the timestamps it is handed. Fixed four-section anatomy (CONTEXT / ADR-0003).
"""
from __future__ import annotations

import html
from datetime import datetime

from .model import SGT, Cluster, FeedHealth, GdacsEvent, Quake, Report, ReportItem, Retraction

_HAZARD_LABEL = {
    "EQ": "Earthquake", "TC": "Tropical cyclone", "FL": "Flood",
    "WF": "Wildfire", "VO": "Volcano", "DR": "Drought", "TS": "Tsunami",
}

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


def _eq_where(item: ReportItem) -> str:
    """Where-label for an earthquake line. Our onshore test uses coarse (110m)
    country polygons, so a genuinely-onshore quake near a coast can read as
    offshore; if a merged GDACS record supplies the country, prefer it (attributed)
    rather than a bare '(offshore)'."""
    q = item.eq.mainshock
    if not q.iso3 and item.gdacs is not None and item.gdacs.iso3:
        return (html.escape(f"{q.place} [{', '.join(item.gdacs.iso3)}]")
                + ' <span class="muted">(country via GDACS)</span>')
    return _where(q)


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


def _flag(change: str | None, reason: str) -> str:
    if change == "NEW":
        return '<span class="flag flag-new">NEW</span>'
    if change == "REVISED":
        title = f' title="{html.escape(reason)}"' if reason else ""
        arrow = " ↑" if "escalated" in reason else ""
        return f'<span class="flag flag-rev"{title}>REVISED{arrow}</span>'
    return ""


def _hazard(kind: str) -> str:
    return _HAZARD_LABEL.get(kind, kind)


def _gdacs_where(g: GdacsEvent) -> str:
    if g.iso3:
        return html.escape(f"{g.name or _hazard(g.eventtype)} [{', '.join(g.iso3)}]")
    return html.escape(g.name or g.country or _hazard(g.eventtype))


def _gdacs_severity(g: GdacsEvent) -> str:
    """Per-hazard descriptor — value+unit, never compared across types (ADR-0002)."""
    txt = g.severity_text or (
        f"{g.severity_value:g} {g.severity_unit}".strip()
        if g.severity_value is not None else ""
    )
    return html.escape(txt)


def _provenance(item: ReportItem) -> str:
    """Sources + the confidence/independence note (ADR-0001 / ADR-0002 / ADR-0008)."""
    bits: list[str] = []
    if item.sources:
        bits.append("sources: " + html.escape(" + ".join(item.sources)))
    # A merged earthquake is one NEIC reading arriving from two feeds — say so, so a
    # reader never reads feed-agreement as corroboration (and it's never summed).
    if item.eq is not None and item.gdacs is not None and not item.independent:
        bits.append("same NEIC reading — not independent corroboration, not double-counted")
    if item.confidence == "medium":
        bits.append("likely the same event (medium confidence)")
    lines = ""
    if bits:
        lines += f'<span class="prov">{" · ".join(bits)}</span>'
    for note in item.cross_links:
        lines += f'<span class="prov xlink">↔ {html.escape(note)}</span>'
    return lines


def _eq_line(item: ReportItem, now: datetime) -> str:
    c = item.eq
    q = c.mainshock
    # Severity is the max colour across the merged sources; show the loudest chip.
    reason = ""
    if item.change_reason:
        reason = f' <span class="muted">— {html.escape(item.change_reason)}</span>'
    return (
        '<li class="event">'
        f"{_flag(item.change, item.change_reason)}{_chip(item.alert)}"
        f'<span class="what">{_eq_where(item)}</span>'
        f'<span class="meta">{_mag(q)}{_sequence(c)} · depth {q.depth_km:.0f} km'
        f' · {_sgt(q.time)} ({_age(q.time, now)}){reason}</span>'
        f"{_provenance(item)}"
        "</li>"
    )


def _gdacs_line(item: ReportItem, now: datetime) -> str:
    g = item.gdacs
    when = f" · {_sgt(g.from_date)} ({_age(g.from_date, now)})" if g.from_date else ""
    glide = f' · GLIDE {html.escape(g.glide)}' if g.glide else ""
    reason = ""
    if item.change_reason:
        reason = f' <span class="muted">— {html.escape(item.change_reason)}</span>'
    return (
        '<li class="event">'
        f"{_flag(item.change, item.change_reason)}{_chip(item.alert)}"
        f'<span class="what">{_hazard(g.eventtype)}: {_gdacs_where(g)}</span>'
        f'<span class="meta">{_gdacs_severity(g)}{when}{glide}{reason}</span>'
        f"{_provenance(item)}"
        "</li>"
    )


def _item_line(item: ReportItem, now: datetime) -> str:
    return _eq_line(item, now) if item.eq is not None else _gdacs_line(item, now)


def _retraction_line(r: Retraction) -> str:
    mag = f" M{r.last_mag:.1f}" if r.last_mag is not None else ""
    colour = f" ({r.last_alert})" if r.last_alert else ""
    return (
        '<li class="corr"><span class="flag flag-corr">CORRECTED</span>'
        f"{html.escape(r.place)}{mag}{colour} — {html.escape(r.reason)}</li>"
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


def _items(report: Report) -> list[ReportItem]:
    """Render list. Falls back to wrapping bare EQ clusters so a Report built the
    V1–V3 way (clusters only, no join) still renders."""
    if report.items:
        return report.items
    return [
        ReportItem(kind="EQ", eq=c, sources=["USGS"],
                   change=c.change, change_reason=c.change_reason)
        for c in report.clusters
    ]


def render(report: Report) -> str:
    now = report.publish_utc
    window = f"last 24h ending {_sgt(report.window_end_utc)}"
    render_items = _items(report)

    if render_items:
        events = "\n".join(_item_line(it, now) for it in render_items)
        sudden = f'<ul class="events">\n{events}\n</ul>'
    else:
        sudden = ('<p class="nothing">No new sudden-onset events crossed threshold '
                  f'in the {html.escape(window)}.</p>')

    if report.retractions:
        lines = "\n".join(_retraction_line(r) for r in report.retractions)
        corrections = f'<ul class="events">\n{lines}\n</ul>'
    else:
        corrections = ""

    # Heartbeat line: quiet vs loud is visible, and the timestamp proves liveness.
    n_changes = sum(1 for it in render_items if it.change) + len(report.retractions)
    heartbeat = (f"{n_changes} update(s) since last run" if report.is_loud
                 else "no changes since last run")

    feeds = "\n".join(_feed_line(f, now) for f in report.feeds)
    sub = (f"Published {_sgt(report.publish_utc)} · "
           f"window: {html.escape(window)} · {heartbeat}")

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
  .flag {{ display: inline-block; font-size: .62rem; font-weight: 700; padding: .05rem .35rem;
           border-radius: 3px; margin-right: .4rem; letter-spacing: .03em; color: #fff; }}
  .flag-new {{ background: #2980b9; }}
  .flag-rev {{ background: #8e44ad; }}
  .flag-corr {{ background: #c0392b; }}
  .corr {{ padding: .45rem 0; border-bottom: 1px solid #8882; }}
  .narrative {{ background: #2980b911; border-left: 3px solid #2980b9; padding: .5rem .9rem;
                margin: 1rem 0; }}
  .narrative h2 {{ border: 0; margin: .1rem 0 .3rem; }}
  .narrative p {{ margin: .3rem 0; }}
  .what {{ font-weight: 600; }}
  .meta {{ display: block; color: #7f8c8d; font-size: .85rem; margin-top: .15rem; }}
  .prov {{ display: block; color: #95a5a6; font-size: .78rem; margin-top: .1rem; }}
  .xlink {{ color: #8e44ad; }}
  .muted {{ color: #95a5a6; }}
  .nothing {{ color: #7f8c8d; font-style: italic; }}
  .ok {{ color: #27ae60; }} .down {{ color: #c0392b; font-weight: 700; }}
  .url {{ color: #95a5a6; font-size: .75rem; word-break: break-all; }}
  footer {{ color: #95a5a6; font-size: .78rem; margin-top: 2rem; }}
</style>
</head>
<body>
<h1>HADR morning situation report</h1>
<p class="sub">{sub}</p>
<div class="banner">{html.escape(report.coverage_note)}</div>
<!--NARRATIVE-->
<h2>Sudden-onset · {html.escape(window)}</h2>
{sudden}
{corrections}

<h2>Slow-onset / ongoing</h2>
<p class="nothing">No always-on slow-onset section yet — curated crises (drought/epidemic/
conflict) arrive with ReliefWeb in the next slice.</p>

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
