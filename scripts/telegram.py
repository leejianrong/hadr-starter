"""Telegram Bot API sender — the one-way push transport for the notify loop.

Deliberately tiny: one HTTPS POST to `sendMessage`, no bot framework, no webhook,
no always-on host (the loop is a scheduled GitHub Action). `requests` is imported
lazily so the formatter/decision code in `scripts.notify` stays offline-testable
with no network and no token. HTML parse mode — we escape the dynamic text with
`html.escape`, which is exactly the set Telegram's HTML mode requires (`& < >`).

Config is read from the environment by the caller, never hard-coded:
  TELEGRAM_BOT_TOKEN  — from @BotFather
  TELEGRAM_CHAT_ID    — the channel/group the bot posts to (e.g. "@my_channel" or
                        the numeric "-100…" id for a private channel/supergroup)
"""
from __future__ import annotations

import logging

API_ROOT = "https://api.telegram.org"
log = logging.getLogger("notify.telegram")


class TelegramError(RuntimeError):
    """A non-OK response from the Bot API (surfaced so the loop can degrade loud)."""


def _endpoint(token: str) -> str:
    """The sendMessage URL. Kept out of logs with the token in it — we log a
    redacted form (CLAUDE.md #2: log the URL actually hit, minus the secret)."""
    return f"{API_ROOT}/bot{token}/sendMessage"


def send_message(
    token: str,
    chat_id: str,
    text: str,
    *,
    dry_run: bool = False,
    timeout: float = 30.0,
) -> bool:
    """POST one HTML message to `chat_id`. Returns True on send (or dry-run).

    Raises TelegramError on an API-level failure so the caller can decide whether
    to keep the idempotency marker (we do NOT record a push that never landed).
    Link previews are disabled — an alert should stay one compact block.
    """
    if dry_run:
        log.info("[dry-run] would POST to %s (chat_id=%s):\n%s",
                 _endpoint("<redacted>"), chat_id, text)
        return True

    import requests

    resp = requests.post(
        _endpoint(token),
        json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        },
        timeout=timeout,
    )
    log.info("POST %s (chat_id=%s) -> %s", _endpoint("<redacted>"), chat_id,
             resp.status_code)
    # Telegram returns 200 with {"ok": true, ...}; on error a 4xx with a
    # {"description": "..."} we surface rather than swallow.
    if not resp.ok:
        detail = ""
        try:
            detail = resp.json().get("description", "")
        except Exception:
            detail = resp.text[:200]
        raise TelegramError(f"Telegram API {resp.status_code}: {detail}")
    return True
