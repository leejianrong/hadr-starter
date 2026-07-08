# Architecture Decision Records

One decision per file, format: **Context · Decision · Consequences · Alternatives**.
Status is `Accepted` unless noted. Produced during the grill step (2026-07-08).

| ADR | Decision |
|---|---|
| [0001](0001-cluster-is-the-unit-of-reporting.md) | The reader-facing unit is a resolved cross-feed cluster (N:1:1) |
| [0002](0002-severity-is-impact-consumed-not-modelled.md) | Severity is impact, consumed from PAGER/GDACS — never modelled |
| [0003](0003-report-window-24h-sgt-slowonset-exempt.md) | Window = last 24h ending 08:30 SGT; slow-onset exempt |
| [0004](0004-attention-threshold-and-slice1-fallback.md) | Attention threshold, and the honest USGS-only slice-1 fallback |
| [0005](0005-quiet-means-model-asleep-page-always-refreshes.md) | "Quiet" = model asleep + no ping; the page always refreshes |
| [0006](0006-loud-change-detection-six-boolean-triggers.md) | Loud-change detection = six deterministic boolean triggers |
| [0007](0007-degrade-loud-and-persistent-state.md) | Degrade loud; persistent state store and its minimum contents |
| [0008](0008-provenance-never-sum-rss-first.md) | Carry provenance, never sum feeds; RSS-first with API drop-in |
| [0009](0009-preliminary-labelled-corrections-explicit.md) | Publish preliminary-and-labelled; corrections are explicit |
