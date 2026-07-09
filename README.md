# HADR Monitor

A monitoring agent for humanitarian assistance and disaster response (HADR).

## The end state

By Wednesday afternoon this repository contains an agent that:

- watches live disaster feeds — GDACS, USGS and ReliefWeb (see `feeds/`)
- filters out the noise and assesses what remains: what happened, where, how bad, who is affected
- publishes a morning situation report to `dashboard.html` at 08:30 Singapore time
- runs on a schedule, unattended, and stays quiet when nothing has changed

How it does any of that is not specified anywhere in this repository. That is the course.

## The three days

1. **Plan** — interrogate the feeds, write the PRD, cut it into vertical slices
2. **Autonomy** — build the first slice, write a skill, wire up the 08:30 routine, launch the overnight loop
3. **Trust** — review code you didn't write, harden the pipeline, demo

## Artefacts expected by the end

`prd.html` · `system-view.html` · `implementation-notes.md` · `dashboard.html` · `goal.md` · at least one skill

## Day 1 setup

1. Sign in to Claude Code with your Team seat
2. Create your own repository from this template, then clone it
3. Run `/install-github-app` so @claude reviews your pull requests from Day 2
4. Install OpenCode and sign in with your Go key

Stack: Python 3.12+ managed with `uv` / pytest — see `CLAUDE.md`. Run
`uv sync` to set up, `uv run pytest` to test.

## Telegram alerts (~hourly push)

Alongside the daily 08:30 page, a second scheduled workflow (`.github/workflows/notify.yml`)
runs ~hourly on the **fast feeds only** (USGS + GDACS) and pushes a one-way Telegram
message when a *new or escalated* event reaches **orange/red** impact (a fresh major
quake PAGER hasn't scored yet also qualifies). ReliefWeb stays on the daily page. The
decision to fire is 100% deterministic (`scripts/notify.py`) — no model in the loop.

Preview it locally without a bot (no send):

```
uv run python -m scripts.notify --dry-run          # live fetch, print the message
uv run python -m scripts.notify \
  --fixture tests/fixtures/usgs_all_hour_sample.json \
  --gdacs-fixture tests/fixtures/gdacs_rss_sample.xml --dry-run   # fully offline
```

To make it send live, point a bot at a **channel or group**:

1. Message [@BotFather](https://t.me/BotFather) → `/newbot` → copy the **bot token**.
2. Create a channel/group, add the bot as an **admin** (needed to post).
3. Get the **chat id**: for a public channel use `@your_channel_name`; for a private
   channel/supergroup, add [@RawDataBot](https://t.me/RawDataBot) briefly (or call the
   Bot API `getUpdates`) to read the numeric id (looks like `-100…`).
4. In the repo: **Settings → Secrets and variables → Actions** → add secrets
   `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`. Optionally add a *variable*
   `NOTIFY_DASHBOARD_URL` (a link appended to each alert).

Without those secrets the workflow runs in `--dry-run` and stays green. Idempotency
("don't re-blast the same alert each tick") lives in `hadr-notify-state.sqlite3`,
cached per run — separate from the daily job's state.
