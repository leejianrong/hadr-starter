"""Impact-based severity + the slice-1 attention threshold (ADR-0004).

Deterministic. Constants are named here so tuning is a one-line, model-free change
(CLAUDE.md #1). Severity is IMPACT, consumed from PAGER — magnitude is a descriptor
only (ADR-0002). Because the USGS-only slice has PAGER `alert` null below ~M5.5 and
no exposure count, tier 2 falls back to a magnitude+depth+onshore proxy and is
honest on the page about what it misses.
"""
from __future__ import annotations

from .model import ALERT_RANK, Cluster, GdacsEvent, Quake, ReportItem

# --- tunable constants (ADR-0004) ---
MAG_SHOW_ANYWHERE = 6.0        # mww-family M at/above this shows regardless of location
MAG_SHOW_ONSHORE = 5.0         # ...combined with shallow depth + onshore
DEPTH_SHALLOW_KM = 70.0
SIG_INCLUDE = 600              # significant-feed membership; an ADDITIONAL include
# The "moment magnitude" family — the only types comparable for the gate (USGS:
# an `mb 6.0` is not an `mww 6.0`).
MWW_FAMILY = {"mw", "mww", "mwc", "mwb", "mwr", "mwmwd"}


def is_mww_family(mag_type: str | None) -> bool:
    return (mag_type or "").lower() in MWW_FAMILY


def passes_threshold(q: Quake) -> bool:
    """Does this earthquake earn a line in the slice-1 sudden-onset section?"""
    # Tier 1 — PAGER ran, so trust it: show yellow/orange/red, hide green.
    if q.alert is not None:
        return ALERT_RANK.get(q.alert, 0) >= ALERT_RANK["yellow"]

    # Tier 2 — alert is None (the majority). Physical proxy, mww-family only.
    if q.mag is not None and is_mww_family(q.mag_type):
        if q.mag >= MAG_SHOW_ANYWHERE:
            return True
        if q.mag >= MAG_SHOW_ONSHORE and q.depth_km <= DEPTH_SHALLOW_KM and q.onshore:
            return True

    # `sig` supplements the physical heuristic (not the primary gate).
    if q.sig is not None and q.sig >= SIG_INCLUDE:
        return True

    return False


def severity_rank(q: Quake) -> int:
    return ALERT_RANK.get(q.alert, 0)


def cluster_sort_key(c: Cluster):
    """Rank clusters most-severe first: PAGER colour, then magnitude, then sig."""
    m = c.mainshock
    return (severity_rank(m), m.mag or 0.0, m.sig or 0)


# --- GDACS threshold (ADR-0004 branch 1: severity ≥ orange) ---
# GDACS is Green-dominated noise (the live feed was ~78% Green wildfires — blindspot);
# the "reached ReliefWeb" and "yellow-with-exposure" branches arrive with ReliefWeb
# (V5). For V4 the deterministic gate is the peak alert colour at orange or above.
GDACS_SHOW_RANK = ALERT_RANK["orange"]


def gdacs_passes_threshold(e: GdacsEvent) -> bool:
    """Does this GDACS alert earn a sudden-onset line? Rank on the peak colour
    (`alertlevel`), never the raw `alertscore` (not comparable across feeds)."""
    return ALERT_RANK.get(e.alert, 0) >= GDACS_SHOW_RANK


def item_sort_key(item: ReportItem):
    """Rank a unified report line most-severe first, across hazards.

    Primary axis is the alert **colour** (impact, ADR-0002). The numeric tiebreaker
    is native to a single source/format and is only ever compared like-with-like:
    an EQ falls back to magnitude+sig; a GDACS line uses its own peak_score. We never
    put a GDACS raw score and a USGS magnitude on the same axis — they aren't one.
    """
    rank = item.rank
    if item.eq is not None:
        m = item.eq.mainshock
        return (rank, m.mag or 0.0, float(m.sig or 0))
    if item.gdacs is not None:
        return (rank, item.gdacs.peak_score, 0.0)
    return (rank, 0.0, 0.0)


def ongoing_sort_key(item: ReportItem) -> float:
    """Order the slow-onset/curated section by most-recently-curated first.
    ReliefWeb carries no alert colour (severity there is 'a human made a page'),
    so recency of curation is the honest ordering — not a fabricated severity."""
    d = item.reliefweb
    if d is not None and d.pub_date is not None:
        return d.pub_date.timestamp()
    return 0.0
