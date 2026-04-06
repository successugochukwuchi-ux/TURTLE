"""
Telegram Bot Notifier
Sends alerts via the Telegram Bot HTTP API.
"""

import logging
import requests
from typing import Optional

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """
    Sends messages to a Telegram chat via Bot API.

    Usage:
        notifier = TelegramNotifier(token="123:ABC", chat_id="-100xxx")
        notifier.send("🐢 ENTER_LONG @ 2350.00")
    """

    BASE_URL = "https://api.telegram.org/bot{token}/sendMessage"

    def __init__(self, token: str, chat_id: str):
        if not token or not chat_id:
            raise ValueError("Both token and chat_id are required.")
        self.token   = token
        self.chat_id = str(chat_id)
        self._url    = self.BASE_URL.format(token=token)

    def send(self, text: str, parse_mode: str = "Markdown") -> bool:
        """
        Send a message. Returns True on success, False on failure.
        Raises on network errors; catches Telegram API errors gracefully.
        """
        payload = {
            "chat_id":    self.chat_id,
            "text":       text,
            "parse_mode": parse_mode,
        }
        try:
            resp = requests.post(self._url, json=payload, timeout=10)
            data = resp.json()
            if not data.get("ok"):
                logger.warning("Telegram API error: %s", data.get("description"))
                return False
            return True
        except requests.RequestException as exc:
            logger.error("Telegram send failed: %s", exc)
            return False

    def test(self) -> bool:
        """Send a test message. Returns True if successful."""
        return self.send("🐢 *Turtle Trader* — Notifier connected ✓")

    @staticmethod
    def format_signal(signal: str, asset: str, price: float, timeframe: str) -> str:
        """Format a rich Markdown alert message."""
        emoji_map = {
            "ENTER_LONG":  "🟢",
            "ENTER_SHORT": "🔴",
            "EXIT_LONG":   "🟡",
            "EXIT_SHORT":  "🟡",
        }
        emoji = emoji_map.get(signal, "⚪")
        return (
            f"{emoji} *{signal.replace('_', ' ')}*\n"
            f"Asset: `{asset}` · TF: `{timeframe}`\n"
            f"Price: `{price:,.2f}`"
        )


class NullNotifier:
    """Drop-in replacement when no notifier is configured."""
    def send(self, *args, **kwargs) -> bool:
        return False

    def test(self) -> bool:
        return False
