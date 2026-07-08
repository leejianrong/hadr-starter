"""Impact-based severity + the slice-1 attention threshold (ADR-0004).

Deterministic. Constants are named here so tuning is a one-line, model-free change
(CLAUDE.md #1). Severity is IMPACT, consumed from PAGER — magnitude is a descriptor
only (ADR-0002). Because the USGS-only slice has PAGER `alert` null below ~M5.5 and
no exposure count, tier 2 falls back to a magnitude+depth+onshore proxy and is
honest on the page about what it misses.
"""
from __future__ import annotations

from .model import ALERT_RANK, Cluster, Quake

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
