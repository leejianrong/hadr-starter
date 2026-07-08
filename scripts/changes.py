"""Deterministic loud-change detection (ADR-0006).

Compares the current thresholded clusters against persisted last-published state
and flags what a reader needs to know: new events, escalations, material
revisions, review confirmations, and withdrawals. No model — pure comparisons
with named, tunable constants. "Loud" = the model should wake (V3); for V2 it
drives the NEW/REVISED/CORRECTED flags and the quiet-but-alive heartbeat.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .decluster import haversine_km
from .model import ALERT_RANK, Cluster, Quake, Retraction
from .state import StateRow

# --- tunable constants (ADR-0006) ---
MAG_REVISION_M = 0.3        # magnitude move at/above this is a revision (mww-family scale)
RELOCATE_KM = 50.0          # epicentre move at/above this is a revision
DEPTH_BOUNDARY_KM = 70.0    # crossing shallow<->deep is a revision


@dataclass
class DetectResult:
    clusters: list[Cluster]              # annotated in place with change/change_reason
    retractions: list[Retraction] = field(default_factory=list)
    next_rows: list[StateRow] = field(default_factory=list)
    is_loud: bool = False


def _compare(row: StateRow, q: Quake) -> list[str]:
    """Why a matched, still-shown event counts as REVISED (empty = quiet)."""
    reasons: list[str] = []
    old_rank = ALERT_RANK.get(row.alert, 0)
    new_rank = ALERT_RANK.get(q.alert, 0)
    if new_rank > old_rank:
        reasons.append(f"escalated {row.alert or 'none'}→{q.alert}")
    elif new_rank < old_rank and old_rank >= ALERT_RANK["orange"]:
        # A walk-down from orange+ still matters — the reader was briefed on it.
        reasons.append(f"de-escalated {row.alert}→{q.alert or 'none'}")

    if row.mag is not None and q.mag is not None and abs(q.mag - row.mag) >= MAG_REVISION_M:
        reasons.append(f"M{row.mag:.1f}→{q.mag:.1f}")

    if row.lat is not None and row.lon is not None:
        if haversine_km(row.lat, row.lon, q.lat, q.lon) >= RELOCATE_KM:
            reasons.append("relocated ≥50 km")

    if row.depth_km is not None:
        if (row.depth_km <= DEPTH_BOUNDARY_KM) != (q.depth_km <= DEPTH_BOUNDARY_KM):
            reasons.append("depth reclassified")

    if row.status == "automatic" and q.status == "reviewed":
        reasons.append("now reviewed")

    return reasons


def _row_for(key: str, c: Cluster, now: datetime) -> StateRow:
    q = c.mainshock
    return StateRow(
        key=key,
        ids=q.ids,
        alert=q.alert,
        mag=q.mag,
        depth_km=q.depth_km,
        status=q.status,
        lat=q.lat,
        lon=q.lon,
        place=q.place,
        last_seen=now,
        published=True,
    )


def detect(prior: dict[str, StateRow], clusters: list[Cluster], feed_ok: bool,
           now: datetime) -> DetectResult:
    """Annotate clusters, compute retractions + the state to persist, decide loud."""
    used: set[str] = set()
    next_rows: list[StateRow] = []
    loud = False

    for c in clusters:
        cids = c.mainshock.ids
        match = None
        for key, row in prior.items():
            if key in used:
                continue
            if cids & row.ids:      # matched across runs by shared USGS id
                match = row
                break

        if match is None:
            c.change, c.change_reason = "NEW", ""
            loud = True
            key = c.mainshock.id or (min(cids) if cids else c.mainshock.place)
        else:
            used.add(match.key)
            key = match.key
            reasons = _compare(match, c.mainshock)
            if reasons:
                c.change, c.change_reason = "REVISED", "; ".join(reasons)
                loud = True
            else:
                c.change, c.change_reason = None, ""

        next_rows.append(_row_for(key, c, now))

    retractions: list[Retraction] = []
    if feed_ok:
        # A published event that no current thresholded cluster claims has been
        # withdrawn or revised below threshold. Guarded on feed_ok so an outage
        # never manufactures a false deletion (ADR-0006 trigger 5).
        for key, row in prior.items():
            if row.published and key not in used:
                retractions.append(
                    Retraction(
                        place=row.place,
                        last_alert=row.alert,
                        last_mag=row.mag,
                        reason="no longer meets threshold (revised down or withdrawn)",
                    )
                )
        if retractions:
            loud = True

    return DetectResult(clusters=clusters, retractions=retractions,
                        next_rows=next_rows, is_loud=loud)
