"""Background worker that keeps the candle cache up to date."""

from __future__ import annotations

import threading
import time
from typing import Dict, List

from binance_client import fetch_price
from data_utils import ensure_history, save_cache
import trader_config as config


class PriceFetcher(threading.Thread):
    """Polls Binance for the latest price and updates the shared state."""

    def __init__(self, state: Dict):
        super().__init__(daemon=True)
        self.state = state
        self._running = True

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
                    with self.state["lock"]:
                        candles = self.state.setdefault("data", [])
                        if not candles:
                            candles.append((float(minute), price, price, price, price, False))
                            self.state["base_time"] = float(minute)
                        else:
                            last = candles[-1]
                            if int(last[0]) == minute:
                                _, o, h, l, _c, _ = last
                                candles[-1] = (
                                    last[0],
                                    o,
                                    max(h, price),
                                    min(l, price),
                                    price,
                                    False,
                                )
                            elif minute > int(last[0]):
                                candles.append((float(minute), price, price, price, price, False))
                        self.state["last_price"] = price
                        save_cache(symbol, candles)
                except Exception as exc:
                    self._append_status(f"Ошибка получения цены: {exc}")

            time.sleep(2.0)

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
        except Exception as exc:
            self._append_status(f"Ошибка загрузки истории: {exc}")
