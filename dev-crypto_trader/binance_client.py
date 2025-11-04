"""Utility functions for retrieving data from the Binance HTTP API."""

from __future__ import annotations

import time
from typing import Iterable, List, Tuple

import requests

import trader_config as config

Candle = Tuple[float, float, float, float, float, bool]


def _klines_to_candles(klines: Iterable[Iterable]) -> List[Candle]:
    candles: List[Candle] = []
    for item in klines:
        ts = float(item[0]) / 1000.0
        o, h, l, c = map(float, (item[1], item[2], item[3], item[4]))
        candles.append((ts, o, h, l, c, True))
    return candles


def fetch_candles(symbol: str, seconds: int) -> List[Candle]:
    """Load the most recent *seconds* candles for *symbol* from Binance."""
    minutes = max(1, seconds // 60 + 1)
    end_time = None
    collected: List[Candle] = []
    while minutes > 0:
        limit = min(1000, minutes)
        params = {"symbol": symbol, "interval": "1m", "limit": limit}
        if end_time is not None:
            params["endTime"] = end_time - 1
        response = requests.get(config.BINANCE_KLINES_URL, params=params, timeout=6)
        response.raise_for_status()
        part = response.json()
        if not isinstance(part, list) or not part:
            break
        collected = _klines_to_candles(part) + collected
        end_time = part[0][0]
        minutes -= len(part)
    return collected


def fetch_range(symbol: str, t0: float, t1: float) -> List[Candle]:
    """Load candles between timestamps *t0* and *t1* (seconds)."""
    res: List[Candle] = []
    cur = int(t0 * 1000)
    end = int(t1 * 1000)
    while cur < end:
        params = {
            "symbol": symbol,
            "interval": "1m",
            "startTime": cur,
            "endTime": end,
            "limit": 1000,
        }
        response = requests.get(config.BINANCE_KLINES_URL, params=params, timeout=6)
        response.raise_for_status()
        part = response.json()
        if not isinstance(part, list) or not part:
            break
        res.extend(_klines_to_candles(part))
        last = part[-1][0]
        if last == cur:
            break
        cur = last + 60_000
    return res


def fetch_price(symbol: str) -> Tuple[float, float]:
    """Return the latest price and server timestamp for *symbol*."""
    response = requests.get(config.BINANCE_PRICE_URL.format(symbol=symbol), timeout=5)
    response.raise_for_status()
    data = response.json()
    price = float(data["price"])
    return price, time.time()


def fetch_all_symbols() -> List[str]:
    try:
        response = requests.get(config.BINANCE_ALL_TICKERS_URL, timeout=6)
        response.raise_for_status()
        payload = response.json()
        return sorted(item["symbol"] for item in payload if "symbol" in item)
    except Exception:
        # Fallback to common majors when the API is not reachable.
        return ["BTCUSDT", "ETHUSDT", "BNBUSDT"]
