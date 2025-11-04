"""Simple helper for interacting with the Binance Futures HTTP API.

This module focuses on the small subset of endpoints that are useful for
demo trading inside the pygame viewer.  It intentionally keeps the
implementation lightweight and dependency free – the standard ``requests``
package is used directly and requests are signed manually with HMAC.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import threading
import time
from dataclasses import dataclass
from typing import ClassVar, Dict, Iterable, List, Optional, Tuple

import requests


def _log_to_state(state: Dict, message: str) -> None:
    """Append *message* to the shared status log stored in ``state``."""

    with state["lock"]:
        log = state.setdefault("status_log", [])
        stamp = time.strftime("%H:%M:%S")
        log.insert(0, f"[{stamp}] {message}")
        del log[100:]


def _first_env(names: Iterable[str]) -> Optional[str]:
    """Return the first non-empty environment variable among *names*."""

    for name in names:
        value = os.environ.get(name)
        if value is None:
            continue
        stripped = value.strip()
        if stripped:
            return stripped
    return None


@dataclass
class BinanceFuturesConfig:
    """Runtime configuration for the :class:`BinanceFuturesClient`."""

    API_KEY_ENV_NAMES: ClassVar[Tuple[str, ...]] = (
        "BINANCE_FUTURES_API_KEY",
        "BINANCE_FUTURES_KEY",
        "BINANCE_API_KEY",
        "BINANCE_KEY",
    )
    API_SECRET_ENV_NAMES: ClassVar[Tuple[str, ...]] = (
        "BINANCE_FUTURES_API_SECRET",
        "BINANCE_FUTURES_SECRET",
        "BINANCE_API_SECRET",
        "BINANCE_SECRET",
        "BINANCE_SECRET_KEY",
    )
    BASE_URL_ENV_NAMES: ClassVar[Tuple[str, ...]] = (
        "BINANCE_FUTURES_BASE_URL",
        "BINANCE_FUTURES_URL",
    )

    api_key: str
    api_secret: str
    base_url: str = "https://testnet.binancefuture.com"
    timeout: float = 10.0

    @classmethod
    def from_env(cls) -> Optional["BinanceFuturesConfig"]:
        """Create configuration using environment variables if available."""

        api_key = _first_env(cls.API_KEY_ENV_NAMES)
        api_secret = _first_env(cls.API_SECRET_ENV_NAMES)
        if not api_key or not api_secret:
            return None
        base_url = _first_env(cls.BASE_URL_ENV_NAMES) or cls.base_url
        timeout_env = _first_env(["BINANCE_FUTURES_TIMEOUT"])
        timeout = float(timeout_env) if timeout_env else cls.timeout
        return cls(api_key=api_key, api_secret=api_secret, base_url=base_url, timeout=timeout)


class BinanceFuturesClient:
    """Tiny wrapper around a couple of Binance Futures endpoints."""

    def __init__(self, config: BinanceFuturesConfig, session: Optional[requests.Session] = None) -> None:
        self.config = config
        self.session = session or requests.Session()

    # -- low level helpers -------------------------------------------------
    def _sign(self, params: Dict[str, str]) -> List[Tuple[str, str]]:
        ordered = [(key, str(params[key])) for key in sorted(params)]
        query = "&".join(f"{key}={value}" for key, value in ordered)
        signature = hmac.new(self.config.api_secret.encode("utf-8"), query.encode("utf-8"), hashlib.sha256).hexdigest()
        ordered.append(("signature", signature))
        return ordered

    def _headers(self) -> Dict[str, str]:
        return {"X-MBX-APIKEY": self.config.api_key}

    # -- public API --------------------------------------------------------
    def post(self, path: str, params: Dict[str, str]) -> Dict:
        signed = self._sign(params)
        response = self.session.post(
            f"{self.config.base_url}{path}",
            params=signed,
            headers=self._headers(),
            timeout=self.config.timeout,
        )
        response.raise_for_status()
        return response.json()

    def get(self, path: str, params: Dict[str, str]) -> Dict:
        signed = self._sign(params)
        response = self.session.get(
            f"{self.config.base_url}{path}",
            params=signed,
            headers=self._headers(),
            timeout=self.config.timeout,
        )
        response.raise_for_status()
        return response.json()

    # -- higher level helpers ---------------------------------------------
    def place_market_order(self, symbol: str, side: str, quantity: str, reduce_only: bool = False) -> Dict:
        params = {
            "symbol": symbol,
            "side": side,
            "type": "MARKET",
            "quantity": quantity,
            "timestamp": str(int(time.time() * 1000)),
            "newOrderRespType": "RESULT",
        }
        if reduce_only:
            params["reduceOnly"] = "true"
        return self.post("/fapi/v1/order", params)

    def get_balances(self):
        params = {
            "timestamp": str(int(time.time() * 1000)),
        }
        return self.get("/fapi/v2/balance", params)


class DemoFuturesTrader:
    """Utility class that exposes a friendly API for demo trading.

    The class is intentionally thin.  It reads credentials from the
    environment and, if available, allows firing market buy/sell orders.  If
    credentials are missing, the class keeps working but simply reports that
    demo trading is disabled.
    """

    def __init__(self, state: Dict) -> None:
        self.state = state
        self._lock = threading.Lock()
        self._client: Optional[BinanceFuturesClient] = None
        config = BinanceFuturesConfig.from_env()
        if config is None:
            available_keys = [name for name in BinanceFuturesConfig.API_KEY_ENV_NAMES if os.environ.get(name)]
            available_secrets = [name for name in BinanceFuturesConfig.API_SECRET_ENV_NAMES if os.environ.get(name)]

            if available_keys and not available_secrets:
                _log_to_state(
                    state,
                    "Найден API ключ, но отсутствует секрет. Укажите одну из переменных: "
                    + ", ".join(BinanceFuturesConfig.API_SECRET_ENV_NAMES),
                )
            elif available_secrets and not available_keys:
                _log_to_state(
                    state,
                    "Найден секрет, но отсутствует API ключ. Укажите одну из переменных: "
                    + ", ".join(BinanceFuturesConfig.API_KEY_ENV_NAMES),
                )
            else:
                _log_to_state(
                    state,
                    "Ключи Binance Futures не найдены. Установите переменные: "
                    + ", ".join(BinanceFuturesConfig.API_KEY_ENV_NAMES)
                    + " и одну из "
                    + ", ".join(BinanceFuturesConfig.API_SECRET_ENV_NAMES),
                )
            return
        self._client = BinanceFuturesClient(config)
        _log_to_state(state, f"Демо торговля активна (endpoint: {config.base_url})")
        self._log_balances_async()

    # -- helpers -----------------------------------------------------------
    def is_enabled(self) -> bool:
        return self._client is not None

    def _format_quantity(self, value: float) -> str:
        # Keep a tiny minimum to avoid sending zero after rounding.
        precision = 3
        precision_env = os.environ.get("BINANCE_FUTURES_DEMO_PRECISION")
        if precision_env:
            try:
                precision = max(0, int(precision_env))
            except ValueError:
                pass
        minimum = 10 ** -precision if precision else 1.0
        value = max(value, minimum)
        formatted = f"{value:.{precision}f}".rstrip("0").rstrip(".")
        return formatted or "0"

    def _determine_quantity(self, symbol: str, price: float) -> Optional[str]:
        custom_qty = os.environ.get("BINANCE_FUTURES_DEMO_QUANTITY")
        if custom_qty:
            try:
                qty = float(custom_qty)
            except ValueError:
                _log_to_state(self.state, f"Некорректное значение BINANCE_FUTURES_DEMO_QUANTITY: {custom_qty}")
            else:
                if qty > 0:
                    return self._format_quantity(qty)
                _log_to_state(self.state, "Количество в BINANCE_FUTURES_DEMO_QUANTITY должно быть > 0")

        notional_env = os.environ.get("BINANCE_FUTURES_DEMO_NOTIONAL", "50")
        try:
            notional = float(notional_env)
        except ValueError:
            _log_to_state(self.state, f"Некорректное значение BINANCE_FUTURES_DEMO_NOTIONAL: {notional_env}")
            return None
        if notional <= 0:
            _log_to_state(self.state, "BINANCE_FUTURES_DEMO_NOTIONAL должно быть положительным")
            return None
        if price <= 0:
            _log_to_state(self.state, "Невозможно рассчитать количество без актуальной цены")
            return None
        raw_qty = notional / price
        return self._format_quantity(raw_qty)

    def _log_balances_async(self) -> None:
        if not self.is_enabled():
            return

        def worker() -> None:
            assert self._client is not None
            try:
                balances = self._client.get_balances()
            except Exception as exc:  # pragma: no cover - network errors
                _log_to_state(self.state, f"Не удалось получить баланс демо счёта: {exc}")
                return
            if isinstance(balances, list):
                usdt = next((item for item in balances if item.get("asset") == "USDT"), None)
                if usdt:
                    balance = usdt.get("balance") or usdt.get("walletBalance")
                    if balance is not None:
                        _log_to_state(self.state, f"Баланс USDT: {balance}")

        threading.Thread(target=worker, daemon=True).start()

    # -- public API --------------------------------------------------------
    def place_market_order(self, symbol: str, side: str, mark_price: Optional[float], reduce_only: bool = False) -> None:
        if not self.is_enabled():
            _log_to_state(self.state, "Демо торговля недоступна: нет API ключей")
            return
        if not symbol:
            _log_to_state(self.state, "Нельзя отправить ордер без выбранного символа")
            return
        if mark_price is None:
            _log_to_state(self.state, "Нет последней цены для расчёта количества")
            return

        quantity = self._determine_quantity(symbol, mark_price)
        if not quantity:
            return

        with self._lock:
            assert self._client is not None
            try:
                response = self._client.place_market_order(symbol, side, quantity, reduce_only=reduce_only)
            except requests.HTTPError as exc:
                try:
                    payload = exc.response.json()
                    message = payload.get("msg") if isinstance(payload, dict) else str(payload)
                except Exception:  # pragma: no cover - network errors
                    message = str(exc)
                _log_to_state(self.state, f"Биржа отклонила ордер {side} {symbol}: {message}")
                return
            except Exception as exc:  # pragma: no cover - network errors
                _log_to_state(self.state, f"Ошибка отправки ордера {side} {symbol}: {exc}")
                return

        executed = response.get("executedQty") or response.get("origQty") or quantity
        avg_price = response.get("avgPrice") or response.get("price") or mark_price
        _log_to_state(
            self.state,
            f"Создан ордер {side} {symbol}: qty={executed} по цене ~{avg_price}",
        )

