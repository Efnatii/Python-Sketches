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
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests

_ENV_LOADED = False


def _value_from_env(*names: str) -> Tuple[Optional[str], Optional[str]]:
    """Return the first non-empty environment variable among ``names``."""

    env_items = list(os.environ.items())
    for name in names:
        raw_value = os.environ.get(name)
        if raw_value is None:
            # ``os.environ`` is case-insensitive on Windows, but users may define
            # variables with a different casing via the GUI.  Perform a
            # case-insensitive lookup to cover such situations.
            upper_name = name.upper()
            for existing, value in env_items:
                if existing.upper() == upper_name:
                    raw_value = value
                    break
        if raw_value is None:
            continue
        if isinstance(raw_value, str):
            cleaned = raw_value.strip()
            if not cleaned:
                continue
        else:
            cleaned = str(raw_value).strip()
            if not cleaned:
                continue
        return name, cleaned
    return None, None


def _strip_inline_comment(raw: str) -> str:
    """Remove trailing comments that start with ``#`` outside of quotes."""

    in_quote = None
    for index, char in enumerate(raw):
        if char in {'"', "'"}:
            if in_quote is None:
                in_quote = char
            elif in_quote == char:
                in_quote = None
        elif char == "#" and in_quote is None:
            return raw[:index]
    return raw


def _ensure_env_loaded(required_names: Tuple[str, ...]) -> None:
    """Populate :mod:`os.environ` with values from a local ``.env`` file."""

    global _ENV_LOADED
    if _ENV_LOADED:
        return

    # Skip reading ``.env`` files if all required variables are already present.
    if all((os.environ.get(name) or "").strip() for name in required_names):
        _ENV_LOADED = True
        return

    _ENV_LOADED = True

    candidates = [
        Path(".env"),
        Path(__file__).resolve().parent / ".env",
        Path(__file__).resolve().parent.parent / ".env",
    ]
    for path in candidates:
        try:
            resolved = path.resolve()
        except FileNotFoundError:
            continue
        if not resolved.is_file():
            continue
        try:
            content = resolved.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in content.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            key = key.strip()
            if not key:
                continue
            cleaned = _strip_inline_comment(value).strip()
            if cleaned and cleaned[0] == cleaned[-1] and cleaned[0] in {'"', "'"}:
                cleaned = cleaned[1:-1]
            if key in os.environ and os.environ.get(key):
                continue
            if cleaned:
                os.environ[key] = cleaned
        break


def _log_to_state(state: Dict, message: str) -> None:
    """Append *message* to the shared status log stored in ``state``."""

    with state["lock"]:
        log = state.setdefault("status_log", [])
        stamp = time.strftime("%H:%M:%S")
        log.insert(0, f"[{stamp}] {message}")
        del log[100:]


@dataclass
class BinanceFuturesConfig:
    """Runtime configuration for the :class:`BinanceFuturesClient`."""

    api_key: str
    api_secret: str
    base_url: str = "https://testnet.binancefuture.com"
    timeout: float = 10.0

    @classmethod
    def from_env(cls) -> Optional["BinanceFuturesConfig"]:
        """Create configuration using environment variables if available."""

        _ensure_env_loaded(("BINANCE_API_KEY", "BINANCE_API_SECRET"))

        _, api_key = _value_from_env("BINANCE_API_KEY")
        _, api_secret = _value_from_env("BINANCE_API_SECRET")

        if not api_key or not api_secret:
            return None
        base_url = os.environ.get("BINANCE_FUTURES_BASE_URL", cls.base_url)
        timeout_env = os.environ.get("BINANCE_FUTURES_TIMEOUT")
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
        return self.place_order(symbol, side, "MARKET", quantity, reduce_only=reduce_only)

    def place_limit_order(
        self,
        symbol: str,
        side: str,
        quantity: str,
        price: str,
        time_in_force: str = "GTC",
        reduce_only: bool = False,
    ) -> Dict:
        return self.place_order(
            symbol,
            side,
            "LIMIT",
            quantity,
            price=price,
            time_in_force=time_in_force,
            reduce_only=reduce_only,
        )

    def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: str,
        *,
        price: Optional[str] = None,
        time_in_force: Optional[str] = None,
        reduce_only: bool = False,
    ) -> Dict:
        params = {
            "symbol": symbol,
            "side": side,
            "type": order_type,
            "quantity": quantity,
            "timestamp": str(int(time.time() * 1000)),
            "newOrderRespType": "RESULT",
        }
        if price is not None:
            params["price"] = price
        if time_in_force is not None:
            params["timeInForce"] = time_in_force
        if reduce_only:
            params["reduceOnly"] = "true"
        return self.post("/fapi/v1/order", params)

    def get_balances(self):
        params = {
            "timestamp": str(int(time.time() * 1000)),
        }
        return self.get("/fapi/v2/balance", params)

    def set_demo_balance(self, asset: str, amount: str) -> Dict:
        params = {
            "asset": asset,
            "amount": amount,
            "timestamp": str(int(time.time() * 1000)),
        }
        return self.post("/fapi/v1/balance", params)


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
            _log_to_state(
                state,
                "Ключи Binance не найдены. Убедитесь, что заданы BINANCE_API_KEY и BINANCE_API_SECRET.",
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

    def _format_price(self, value: float) -> str:
        formatted = f"{value:.8f}".rstrip("0").rstrip(".")
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

    def _append_order_to_state(
        self,
        *,
        symbol: str,
        side: str,
        order_type: str,
        quantity: str,
        price: str,
        status: str,
    ) -> None:
        with self.state["lock"]:
            orders = self.state.setdefault("order_log", [])
            stamp = time.strftime("%H:%M:%S")
            orders.insert(
                0,
                {
                    "time": stamp,
                    "symbol": symbol,
                    "side": side,
                    "type": order_type,
                    "quantity": quantity,
                    "price": price,
                    "status": status,
                },
            )
            del orders[200:]

    def suggest_quantity(self, symbol: str, price: Optional[float]) -> Optional[str]:
        if price is None or price <= 0:
            return None
        return self._determine_quantity(symbol, price)

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
                        try:
                            balance_value = float(balance)
                        except (TypeError, ValueError):
                            balance_value = None
                        else:
                            with self.state["lock"]:
                                self.state["demo_balance"] = balance_value
                        _log_to_state(self.state, f"Баланс USDT: {balance}")

        threading.Thread(target=worker, daemon=True).start()

    # -- public API --------------------------------------------------------
    def place_market_order(
        self,
        symbol: str,
        side: str,
        mark_price: Optional[float],
        *,
        quantity: Optional[float] = None,
        reduce_only: bool = False,
    ) -> None:
        if not self.is_enabled():
            _log_to_state(self.state, "Демо торговля недоступна: нет API ключей")
            return
        if not symbol:
            _log_to_state(self.state, "Нельзя отправить ордер без выбранного символа")
            return
        if mark_price is None and quantity is None:
            _log_to_state(self.state, "Нет последней цены для расчёта количества")
            return

        if quantity is not None:
            qty_value = self._format_quantity(quantity)
        else:
            assert mark_price is not None
            qty_value = self._determine_quantity(symbol, mark_price)
        if not qty_value:
            return

        price_snapshot = self._format_price(mark_price) if mark_price is not None else "-"

        with self._lock:
            assert self._client is not None
            try:
                response = self._client.place_market_order(symbol, side, qty_value, reduce_only=reduce_only)
            except requests.HTTPError as exc:
                try:
                    payload = exc.response.json()
                    message = payload.get("msg") if isinstance(payload, dict) else str(payload)
                except Exception:  # pragma: no cover - network errors
                    message = str(exc)
                _log_to_state(self.state, f"Биржа отклонила ордер {side} {symbol}: {message}")
                self._append_order_to_state(
                    symbol=symbol,
                    side=side,
                    order_type="MARKET",
                    quantity=qty_value,
                    price=price_snapshot,
                    status="Отклонён",
                )
                return
            except Exception as exc:  # pragma: no cover - network errors
                _log_to_state(self.state, f"Ошибка отправки ордера {side} {symbol}: {exc}")
                self._append_order_to_state(
                    symbol=symbol,
                    side=side,
                    order_type="MARKET",
                    quantity=qty_value,
                    price=price_snapshot,
                    status="Ошибка",
                )
                return

        executed = response.get("executedQty") or response.get("origQty") or qty_value
        avg_price = response.get("avgPrice") or response.get("price") or mark_price
        _log_to_state(
            self.state,
            f"Создан ордер {side} {symbol}: qty={executed} по цене ~{avg_price}",
        )
        price_str = self._format_price(float(avg_price)) if avg_price is not None else price_snapshot
        self._append_order_to_state(
            symbol=symbol,
            side=side,
            order_type="MARKET",
            quantity=str(executed),
            price=price_str,
            status="Исполнен",
        )

    def place_limit_order(
        self,
        symbol: str,
        side: str,
        price: float,
        *,
        quantity: Optional[float] = None,
        reduce_only: bool = False,
    ) -> None:
        if not self.is_enabled():
            _log_to_state(self.state, "Демо торговля недоступна: нет API ключей")
            return
        if price <= 0:
            _log_to_state(self.state, "Цена лимитного ордера должна быть положительной")
            return
        if quantity is not None:
            qty_value = self._format_quantity(quantity)
        else:
            qty_value = self._determine_quantity(symbol, price)
        if not qty_value:
            return

        price_formatted = self._format_price(price)

        with self._lock:
            assert self._client is not None
            try:
                response = self._client.place_limit_order(
                    symbol,
                    side,
                    qty_value,
                    price_formatted,
                    reduce_only=reduce_only,
                )
            except requests.HTTPError as exc:
                try:
                    payload = exc.response.json()
                    message = payload.get("msg") if isinstance(payload, dict) else str(payload)
                except Exception:
                    message = str(exc)
                _log_to_state(self.state, f"Биржа отклонила лимитный ордер {side} {symbol}: {message}")
                self._append_order_to_state(
                    symbol=symbol,
                    side=side,
                    order_type="LIMIT",
                    quantity=qty_value,
                    price=price_formatted,
                    status="Отклонён",
                )
                return
            except Exception as exc:
                _log_to_state(self.state, f"Ошибка отправки лимитного ордера {side} {symbol}: {exc}")
                self._append_order_to_state(
                    symbol=symbol,
                    side=side,
                    order_type="LIMIT",
                    quantity=qty_value,
                    price=price_formatted,
                    status="Ошибка",
                )
                return

        status = response.get("status") or "Создан"
        _log_to_state(
            self.state,
            f"Создан лимитный ордер {side} {symbol}: qty={qty_value} по цене {price_formatted} ({status})",
        )
        self._append_order_to_state(
            symbol=symbol,
            side=side,
            order_type="LIMIT",
            quantity=qty_value,
            price=price_formatted,
            status=status,
        )

    def update_demo_balance(self, asset: str, amount: float) -> None:
        formatted = self._format_price(amount)
        if not self.is_enabled():
            with self.state["lock"]:
                self.state["demo_balance"] = amount
            _log_to_state(self.state, f"Локальный демо баланс {asset} установлен на {formatted}")
            return

        def worker() -> None:
            assert self._client is not None
            try:
                self._client.set_demo_balance(asset, formatted)
            except requests.HTTPError as exc:
                try:
                    payload = exc.response.json()
                    message = payload.get("msg") if isinstance(payload, dict) else str(payload)
                except Exception:
                    message = str(exc)
                _log_to_state(self.state, f"Биржа отклонила обновление баланса: {message}")
                return
            except Exception as exc:
                _log_to_state(self.state, f"Ошибка обновления баланса: {exc}")
                return

            with self.state["lock"]:
                self.state["demo_balance"] = amount
            _log_to_state(self.state, f"Баланс {asset} обновлён до {formatted}")
            self._log_balances_async()

        threading.Thread(target=worker, daemon=True).start()

