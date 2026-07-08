# ADR-0005 — "Quiet" = model asleep + no ping; the page always refreshes

Status: Accepted (2026-07-08)

## Context

Two requirements appear to collide: the README says the agent "stays quiet when
nothing has changed" and the CI workflow wakes the (expensive) model *only* on
change — yet a decision-maker who sees nothing cannot tell "quiet night" from
"the cron job died." Silence is indistinguishable from failure.

## Decision

Separate two layers:

- **Deterministic layer (cheap `scripts/`):** runs every morning at 08:30 **no
  matter what** and **regenerates `dashboard.html` unconditionally**, stamping the
  current SGT publish time and per-feed "as of" times, and rendering a templated
  "No new sudden-onset events crossed threshold in the last 24h" line plus the
  standing slow-onset and feed-health sections.
- **Model layer (expensive):** wakes **only when the change-detector reports a
  loud change** (ADR-0006), to write the narrative prose, and only then is a
  notification sent.

So **"quiet" means: model stays asleep, no notification — NOT the page goes
stale.** The **page timestamp is the heartbeat**: stamped today ⇒ healthy quiet
night; still stamped yesterday ⇒ cron died. Deterministic refresh is
non-negotiable — the silence of the *page* is the only real alarm.

## Consequences

- The `sitrep.yml` workflow shape holds: step 1 (deterministic check + render)
  always runs; step 2 (model narrative + notify) is guarded on step 1's change
  signal.
- `dashboard.html` can be produced with **zero** model calls on a quiet morning.

## Open owner-decision

Whether a **daily lightweight all-clear ping** (deterministic, no model) is wanted
so that absence-of-ping unambiguously means failure. **Recommended: yes** — it
fully honours "stay quiet" (model asleep) while closing the silent-death gap.
Deferred to the owner; default to no extra ping until decided.
