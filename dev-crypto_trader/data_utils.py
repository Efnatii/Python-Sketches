"""Helper utilities for working with cached candle data."""

from __future__ import annotations

import json
import os
import time
from typing import List, Tuple

import trader_config as config
from binance_client import fetch_candles, fetch_range

Candle = Tuple[float, float, float, float, float, bool]
ONE_MINUTE = 60


def dedupe_candles(candles: List[Candle]) -> List[Candle]:
    by_ts = {}
    for ts, o, h, l, c, is_pre in candles:
        by_ts[float(ts)] = (float(ts), float(o), float(h), float(l), float(c), bool(is_pre))
    return [by_ts[t] for t in sorted(by_ts.keys())]


def cache_path(symbol: str) -> str:
    return os.path.join(config.CACHE_DIR, f"{symbol.upper()}.json")


def load_cache(symbol: str) -> Tuple[List[Candle], float]:
    path = cache_path(symbol)
    if not os.path.exists(path):
        return [], 0.0
    with open(path, "r", encoding="utf-8") as fp:
        payload = json.load(fp)
    candles = [
        (
            float(item[0]),
            float(item[1]),
            float(item[2]),
            float(item[3]),
            float(item[4]),
            bool(item[5]) if len(item) > 5 else True,
        )
        for item in payload.get("candles", [])
    ]
    return dedupe_candles(candles), float(payload.get("saved_at", 0.0))


def save_cache(symbol: str, candles: List[Candle], saved_at: float | None = None) -> None:
    path = cache_path(symbol)
    payload = {
        "candles": [list(item) for item in dedupe_candles(candles)],
        "saved_at": float(saved_at if saved_at is not None else time.time()),
    }
    with open(path, "w", encoding="utf-8") as fp:
        json.dump(payload, fp)


def _fill_gaps_and_refresh(symbol: str, candles: List[Candle]) -> List[Candle]:
    if not candles:
        return candles

    candles = dedupe_candles(candles)
    fixed = list(candles)

    # stitch missing minutes between candles (> 60 seconds)
    i = 0
    while i < len(fixed) - 1:
        a = fixed[i]
        b = fixed[i + 1]
        if (b[0] - a[0]) > ONE_MINUTE:
            fill = fetch_range(symbol, a[0] + ONE_MINUTE, b[0] - ONE_MINUTE)
            if fill:
                fixed[i + 1 : i + 1] = fill
                i += len(fill)
                continue
        i += 1

    last_ts = fixed[-1][0]
    tail_from = max(fixed[0][0], last_ts - config.TAIL_REFRESH_MINUTES * ONE_MINUTE)
    fresh = fetch_range(symbol, tail_from, time.time())
    if fresh:
        cut_ts = fresh[0][0]
        head = [c for c in fixed if c[0] < cut_ts]
        fixed = dedupe_candles(head + fresh)

    return fixed


def ensure_history(symbol: str, seconds: int) -> List[Candle]:
    """Return a continuous chunk of candles for *symbol* covering *seconds*."""
    now = time.time()
    candles, _ = load_cache(symbol)

    if not candles:
        candles = fetch_candles(symbol, seconds)
        candles = dedupe_candles(candles)
        save_cache(symbol, candles, saved_at=now)
        return candles

    candles = _fill_gaps_and_refresh(symbol, candles)

    need_from = now - seconds
    if candles and candles[0][0] > need_from + ONE_MINUTE:
        need_sec = int(candles[0][0] - need_from)
        more = fetch_candles(symbol, need_sec)
        if more:
            candles = dedupe_candles(more + candles)

    save_cache(symbol, candles, saved_at=now)
    return candles
