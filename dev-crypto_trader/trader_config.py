"""Application configuration constants for the crypto trader viewer."""

import os

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

os.makedirs(CACHE_DIR, exist_ok=True)
