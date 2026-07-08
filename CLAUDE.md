# CLAUDE.md

## Language & tooling

Python 3.12+, managed with `uv` (`pyproject.toml` + `uv.lock`). Standard library
first; add a dependency only when it earns its place. `requests` for HTTP,
`pytest` for tests. Add deps with `uv add` (dev deps with `uv add --dev`).

## Test command

`uv run pytest` (run from the repo root).

## Development workflow (for humans and agents)

- **One branch per slice**, off a fresh `main`; land via PR. Keep `main` green.
- **Fast local gate before pushing:** `uv run ruff check . && uv run pytest`.
  A tracked pre-push hook runs exactly this — install it once per clone:
  `ln -sf ../../scripts/git-hooks/pre-push .git/hooks/pre-push`
  (`git push --no-verify` bypasses it for a one-off).
- **CI** (`.github/workflows/ci.yml`) runs `ruff` + `pytest` on every PR and push
  to `main` — the merge gate. It mirrors the pre-push hook, exhaustively.
- **Lint:** `ruff` (config in `pyproject.toml`: `E`, `F`, `I`; line length 100).

## Conventions

1. Deterministic logic lives in `scripts/` and never calls a model.
2. Log the final URL actually fetched, not the one requested.
3. One learning per file in `docs/solutions/` when something costs more than
   ten minutes.

## Deviations policy

Any departure from the PRD or this file is recorded in
`implementation-notes.md` with its reason. An undocumented deviation is a bug.
