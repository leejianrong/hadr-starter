"""Aftershock declustering (ADR-0001 / CONTEXT).

One mainshock spawns dozens-to-hundreds of aftershocks; reporting each as its own
line is how the sitrep becomes noise. Group a space-time neighbourhood into one
sequence anchored by its largest event. Pure and deterministic.
"""
from __future__ import annotations

import math

from .model import Cluster, Quake

# --- tunable constants ---
DECLUSTER_KM = 100.0           # epicentres within this join the same sequence
DECLUSTER_HOURS = 24.0         # ...and within this time (the report window)
SWARM_MIN_EVENTS = 3
SWARM_DOMINANCE_M = 0.5        # mainshock barely bigger than largest aftershock -> swarm


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlam / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _near(main: Quake, q: Quake) -> bool:
    if haversine_km(main.lat, main.lon, q.lat, q.lon) > DECLUSTER_KM:
        return False
    return abs((main.time - q.time).total_seconds()) <= DECLUSTER_HOURS * 3600


def _is_swarm(c: Cluster) -> bool:
    la = c.largest_aftershock
    if la is None or c.mainshock.mag is None or la.mag is None:
        return False
    return c.count >= SWARM_MIN_EVENTS and (c.mainshock.mag - la.mag) < SWARM_DOMINANCE_M


def decluster(quakes: list[Quake]) -> list[Cluster]:
    """Greedy: largest events anchor sequences; nearby smaller events attach.

    Deterministic ordering — by descending magnitude, then time, then id — so the
    same input always yields the same clusters.
    """
    ordered = sorted(quakes, key=lambda q: (-(q.mag or 0.0), q.time, q.id))
    clusters: list[Cluster] = []
    for q in ordered:
        for c in clusters:
            if _near(c.mainshock, q):
                c.aftershocks.append(q)
                break
        else:
            clusters.append(Cluster(mainshock=q))
    for c in clusters:
        c.is_swarm = _is_swarm(c)
    return clusters
