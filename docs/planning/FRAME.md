---
shaping: true
---

# HADR Monitor — Frame

The "why", stakeholder-level. Solution detail lives in `docs/PRD.md` and
`SHAPING.md`; this fixes the problem and the outcome so the shaping stays honest.

## Source

Verbatim, from `README.md` ("The end state"):

> By Wednesday afternoon this repository contains an agent that:
>
> - watches live disaster feeds — GDACS, USGS and ReliefWeb (see `feeds/`)
> - filters out the noise and assesses what remains: what happened, where, how
>   bad, who is affected
> - publishes a morning situation report to `dashboard.html` at 08:30 Singapore
>   time
> - runs on a schedule, unattended, and stays quiet when nothing has changed
>
> How it does any of that is not specified anywhere in this repository. That is
> the course.

Three decisions the product owner locked (2026-07-08, `implementation-notes.md`):

> - Report window = last 24h ending 08:30 SGT (rolling).
> - Attention threshold = PAGER/GDACS ≥ orange, OR yellow with meaningful
>   population exposure, OR anything curated onto ReliefWeb.
> - First vertical slice = USGS earthquakes, end-to-end.

## Problem

A decision-maker in Singapore needs, in ~30 seconds each morning, a trustworthy
picture of the world's active disasters — *what, where, how bad, who* — but the
raw feeds actively mislead:

- They are **three different object types** at different atomicity and latency,
  not three views of one thing, so naive merging double-counts and mis-clusters.
- **Magnitude is not severity** — a big deep-ocean quake is harmless, a moderate
  shallow one under a poor city is catastrophic.
- **Silence is ambiguous** — a blank or stale page reads as "quiet night" when it
  may mean "the pipeline died," and a data outage read as calm gets people
  unserved.
- **Aftershock swarms and low-severity noise** bury the few events that matter.

The value is **judgement and trust**, not data relay.

## Outcome

Success looks like: at 08:30 SGT the reader opens one page and, in a glance,
knows what deserves attention in the last day, ranked by human impact, with every
figure honest about its source and uncertainty — and can trust that:

- a **quiet morning still shows a fresh, timestamped page** (alive, not dead);
- **blindspots and outages are stated on the page**, never hidden;
- **things that change or turn out false are explicitly corrected**, not silently
  dropped;
- the severity calls and merges are **deterministic** — a model writes prose, it
  never decides an alert level.

Non-goals (so the frame doesn't drift): recomputing severity ourselves, real-time
sub-daily alerting, feeds beyond the three, an interactive UI beyond a static page.
