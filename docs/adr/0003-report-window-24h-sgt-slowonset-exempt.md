# ADR-0003 — Window = last 24h ending 08:30 SGT; slow-onset exempt

Status: Accepted (2026-07-08)

## Context

"Today's disasters at 08:30 Singapore" is ambiguous across three clocks — event
time (UTC), local time at the disaster (the humanitarian-relevant one; PAGER uses
it), and SGT publish time — and three window meanings (rolling 24h, UTC calendar
day, SGT calendar day). Each yields a different report. Slow-onset disasters
(drought, epidemic, famine) have no event instant and fit no daily window.

## Decision

- **Sudden-onset window = last 24h rolling, ending at the 08:30 SGT publish time.**
  Chosen over calendar-day options because rolling 24h has no blind gap (an
  08:30 calendar-day report omits 00:00–08:30) and one easily-labelled lookback.
- **Timestamps stored UTC; the boundary computed in SGT (UTC+8, no DST).** USGS
  times are epoch **milliseconds**; GDACS JSON dates are UTC without a designator
  (attach UTC yourself); RSS is RFC-822 GMT.
- **The window is labelled on every report.**
- **Slow-onset events are exempt** (`event_time` nullable, first-class). They route
  to the always-on ongoing section while ReliefWeb status is `alert`/`current`,
  and leave when marked `past` (or drop off feed with an explicit note). The
  window never filters them out.

## Consequences

- The report has a windowed sudden-onset section and a window-independent ongoing
  section (see ADR-0004: "reached ReliefWeb" also overrides the window).
- Any pipeline assuming every disaster has a timestamp is wrong; `event_time`
  nullability is tested.

## Alternatives rejected

- **SGT calendar day** — blind to 00:00–08:30 events at publish time.
- **UTC calendar day** — drifts from the SGT reader's sense of "today."

Recorded per CLAUDE.md deviations policy (blindspot #9 requires the window choice
be documented and labelled). Also in `implementation-notes.md`.
