"""Application configuration constants for the crypto trader viewer."""

from __future__ import annotations

import os
from typing import Optional

WIDTH, HEIGHT, FPS = 1180, 680, 60
RIGHT_PANEL_W = 280
COLOR_BG = (19, 20, 26)
COLOR_TEXT = (245, 245, 245)
COLOR_HINT = (165, 165, 175)
TOPBAR_Y = 10

PLOT_MARGIN = 10
PLOT_RECT = (PLOT_MARGIN, 50, WIDTH - RIGHT_PANEL_W - 2 * PLOT_MARGIN, HEIGHT - 60)
STATUS_RECT = (WIDTH - RIGHT_PANEL_W + 6, 50, RIGHT_PANEL_W - 12, HEIGHT - 60)
SEARCH_RECT = (10, 10, 320, 26)

CACHE_DIR = "cache"
HISTORY_LOOKBACK_SECONDS = 7 * 24 * 3600
TAIL_REFRESH_MINUTES = 15

BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"
BINANCE_PRICE_URL = "https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
BINANCE_ALL_TICKERS_URL = "https://api.binance.com/api/v3/ticker/price"

LAST_SYMBOL_FILE = os.path.join(CACHE_DIR, "last_symbol.txt")

os.makedirs(CACHE_DIR, exist_ok=True)


def load_last_symbol() -> Optional[str]:
    """Return the last selected trading pair if it exists on disk."""

    try:
        with open(LAST_SYMBOL_FILE, "r", encoding="utf-8") as fh:
            symbol = fh.read().strip()
    except FileNotFoundError:
        return None
    except OSError:
        return None
    return symbol or None


def save_last_symbol(symbol: str) -> None:
    """Persist the currently selected trading pair to disk."""

    try:
        with open(LAST_SYMBOL_FILE, "w", encoding="utf-8") as fh:
            fh.write(symbol)
    except OSError:
        pass
