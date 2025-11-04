"""Background worker that keeps the candle cache up to date."""

from __future__ import annotations

import threading
import time
from typing import Dict, List, Optional

from binance_client import fetch_price, fetch_range
from data_utils import Candle, ONE_MINUTE, dedupe_candles, ensure_history, merge_candles, save_cache
import trader_config as config


class PriceFetcher(threading.Thread):
    """Polls Binance for the latest price and updates the shared state."""

    def __init__(self, state: Dict):
        super().__init__(daemon=True)
        self.state = state
        self._running = True
        self._need_resync = True
        self._next_tail_sync = 0.0
        self._last_minute: Optional[int] = None

    def stop(self) -> None:
        self._running = False

    def _append_status(self, message: str) -> None:
        with self.state["lock"]:
            log: List[str] = self.state.setdefault("status_log", [])
            stamp = time.strftime("%H:%M:%S")
            log.insert(0, f"[{stamp}] {message}")
            del log[100:]

    def run(self) -> None:
        while self._running:
            with self.state["lock"]:
                symbol = self.state.get("current_symbol")

            if symbol:
                try:
                    price, ts = fetch_price(symbol)
                    minute = int(ts // 60) * 60
                    self._apply_price(symbol, minute, price)
                except Exception as exc:
                    self._append_status(f"Ошибка получения цены: {exc}")
                    self._need_resync = True
                    self._next_tail_sync = 0.0

            time.sleep(2.0)

    def _apply_price(self, symbol: str, minute: int, price: float) -> None:
        now = time.time()

        with self.state["lock"]:
            current_symbol = self.state.get("current_symbol")
            candles_snapshot = list(self.state.get("data", []))

        if current_symbol != symbol:
            return

        if not candles_snapshot:
            self.refresh_history()
            return

        last_minute = int(candles_snapshot[-1][0]) if candles_snapshot else None
        new_minute_started = self._last_minute is None or minute > self._last_minute
        needs_gap_fill = last_minute is not None and minute - last_minute > ONE_MINUTE

        patch_from: Optional[float] = None
        patch_to: Optional[float] = None

        if needs_gap_fill:
            start = max(candles_snapshot[0][0], (last_minute or minute) - config.GAP_BACKFILL_PRE_MINUTES * 60)
            patch_from = start
            patch_to = minute + config.GAP_BACKFILL_POST_MINUTES * 60
        elif new_minute_started:
            start = max(float(minute) - config.GAP_BACKFILL_PRE_MINUTES * 60, candles_snapshot[0][0])
            patch_from = start
            patch_to = minute + config.GAP_BACKFILL_POST_MINUTES * 60
        elif self._need_resync or now >= self._next_tail_sync:
            start = max(candles_snapshot[-1][0] - config.TAIL_REFRESH_MINUTES * 60, candles_snapshot[0][0])
            patch_from = start
            patch_to = now + config.GAP_BACKFILL_POST_MINUTES * 60

        patch: List[Candle] = []
        if patch_from is not None and patch_to is not None:
            try:
                patch = fetch_range(symbol, patch_from, patch_to)
            except Exception as exc:
                self._append_status(f"Ошибка подгрузки свечей: {exc}")
                self._need_resync = True
            else:
                self._need_resync = False
                self._next_tail_sync = now + config.TAIL_SYNC_INTERVAL_SECONDS

        updated = merge_candles(candles_snapshot, patch)
        updated = self._update_live_candle(updated, minute, price)
        updated = self._trim_history(updated)

        with self.state["lock"]:
            if self.state.get("current_symbol") != symbol:
                return
            self.state["data"] = updated
            if updated:
                self.state["base_time"] = updated[0][0]
            self.state["last_price"] = price
            candles_for_cache = list(updated)

        save_cache(symbol, candles_for_cache)
        self._last_minute = minute

    def _update_live_candle(self, candles: List[Candle], minute: int, price: float) -> List[Candle]:
        if not candles:
            return candles

        updated = list(candles)
        found = False
        for idx in range(len(updated) - 1, -1, -1):
            ts, o, h, l, c, is_pre = updated[idx]
            if int(ts) == minute:
                updated[idx] = (ts, o, max(h, price), min(l, price), price, False)
                found = True
                break
            if ts < minute:
                break

        if not found:
            prev_close = updated[-1][4]
            open_price = prev_close if prev_close else price
            high = max(open_price, price)
            low = min(open_price, price)
            updated.append((float(minute), open_price, high, low, price, False))

        return dedupe_candles(updated)

    def _trim_history(self, candles: List[Candle]) -> List[Candle]:
        if not candles:
            return candles
        cutoff = time.time() - config.HISTORY_LOOKBACK_SECONDS
        trimmed = [c for c in candles if c[0] >= cutoff]
        return trimmed if trimmed else candles[-1:]

    def refresh_history(self) -> None:
        with self.state["lock"]:
            symbol = self.state.get("current_symbol")
        if not symbol:
            return
        try:
            candles = ensure_history(symbol, config.HISTORY_LOOKBACK_SECONDS)
            with self.state["lock"]:
                self.state["data"] = candles
                self.state["base_time"] = candles[0][0] if candles else None
            self._append_status(f"Загружена история для {symbol}")
            self._need_resync = False
            self._next_tail_sync = time.time() + config.TAIL_SYNC_INTERVAL_SECONDS
            self._last_minute = int(candles[-1][0]) if candles else None
        except Exception as exc:
            self._append_status(f"Ошибка загрузки истории: {exc}")
