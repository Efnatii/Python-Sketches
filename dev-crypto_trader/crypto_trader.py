"""Minimal modular candlestick viewer without AI components."""

from __future__ import annotations

import threading
import time
from typing import List, Optional

import pygame

import trader_config as config
from binance_client import fetch_all_symbols
from chart_view import CandlesChart
from futures_trader import DemoFuturesTrader
from price_fetcher import PriceFetcher
from ui_elements import Button, DropdownList, OrderDialog, StatusPanel, TextInput


class BaseApp:
    def __init__(self, width: int, height: int, title: str, fps: int = 60) -> None:
        pygame.init()
        self.screen = pygame.display.set_mode((width, height))
        pygame.display.set_caption(title)
        if not pygame.scrap.get_init():
            pygame.scrap.init()
        self.clock = pygame.time.Clock()
        self.fps = fps
        self.running = True

    def handle_event(self, event: pygame.event.Event) -> None:
        pass

    def update(self, dt: float) -> None:
        pass

    def draw(self, screen: pygame.Surface) -> None:
        pass

    def run(self) -> None:  # pragma: no cover - graphical loop
        while self.running:
            dt = self.clock.tick(self.fps) / 1000.0
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                else:
                    self.handle_event(event)
            self.update(dt)
            self.draw(self.screen)
            pygame.display.flip()
        pygame.quit()


class CryptoTraderApp(BaseApp):
    def __init__(self) -> None:
        super().__init__(config.WIDTH, config.HEIGHT, "Crypto Trader", config.FPS)
        self.font = pygame.font.SysFont("consolas", 18)
        self.small = pygame.font.SysFont("consolas", 14)

        self.state = {
            "lock": threading.Lock(),
            "current_symbol": None,
            "data": [],
            "base_time": None,
            "status_log": ["Выберите пару, чтобы загрузить данные"],
            "order_log": [],
            "demo_balance": None,
        }

        self.search = TextInput(pygame.Rect(*config.SEARCH_RECT), self.small, placeholder="...")
        self.new_order_button = Button(
            pygame.Rect(*config.NEW_ORDER_RECT),
            "Новый ордер",
            self.small,
            on_click=self._open_order_dialog,
        )
        self.balance_input = TextInput(
            pygame.Rect(*config.BALANCE_RECT),
            self.small,
            placeholder="Баланс",
            on_enter=self._update_balance,
        )
        self.dropdown = DropdownList(
            config.SEARCH_RECT[0],
            config.SEARCH_RECT[1] + config.SEARCH_RECT[3],
            config.SEARCH_RECT[2],
            20,
            self.small,
            config.HEIGHT,
            on_select=self._on_symbol,
        )
        self.dropdown.visible = False

        plot_rect = pygame.Rect(*config.PLOT_RECT)
        self.chart = CandlesChart(plot_rect, self.small, self.state)

        status_rect = pygame.Rect(*config.STATUS_RECT)
        self.status_panel = StatusPanel(status_rect, self.small, self.state)

        self.price_fetcher = PriceFetcher(self.state)
        self.price_fetcher.start()

        self.trader = DemoFuturesTrader(self.state)
        if self.trader.is_enabled():
            self._append_status("Демо торговля активна — используйте кнопку \"Новый ордер\"")

        self.all_symbols = fetch_all_symbols()
        self.filtered_symbols: List[str] = self.all_symbols[:300]
        self.dropdown.set_items(self.filtered_symbols)

        self._load_last_symbol()
        dialog_rect = pygame.Rect(config.WIDTH // 2 - 220, 120, 440, 320)
        self.order_dialog = OrderDialog(dialog_rect, self.font, self.small)

    def _on_symbol(self, symbol: str) -> None:
        self.search.set_text(symbol)
        with self.state["lock"]:
            self.state["current_symbol"] = symbol
        self.price_fetcher.refresh_history()
        self.chart.reset_view()
        self.dropdown.visible = False
        self.search.active = False
        config.save_last_symbol(symbol)
        self._append_status(f"Текущий символ: {symbol}")

    def _append_status(self, message: str) -> None:
        with self.state["lock"]:
            log: List[str] = self.state.setdefault("status_log", [])
            stamp = time.strftime("%H:%M:%S")
            log.insert(0, f"[{stamp}] {message}")
            del log[100:]

    def _open_order_dialog(self) -> None:
        with self.state["lock"]:
            symbol = self.state.get("current_symbol")
            last_price = self.state.get("last_price")
        if not symbol:
            self._append_status("Выберите торговую пару перед созданием ордера")
            return
        self.order_dialog.open(symbol, last_price, self._submit_order_dialog, self._cancel_order_dialog)
        suggestion = self.trader.suggest_quantity(symbol, last_price)
        if suggestion:
            self.order_dialog.quantity_input.set_text(suggestion)

    def _cancel_order_dialog(self) -> None:
        self.order_dialog.close()

    def _submit_order_dialog(self, payload: dict) -> None:
        symbol = payload.get("symbol")
        if not symbol:
            self._append_status("Не выбран торговый символ")
            return
        side = payload.get("side", "BUY")
        order_type = payload.get("type", "MARKET")
        reduce_only = bool(payload.get("reduce_only"))
        quantity_text = (payload.get("quantity") or "").replace(",", ".").strip()
        price_text = (payload.get("price") or "").replace(",", ".").strip()

        quantity_value: Optional[float] = None
        if quantity_text:
            try:
                quantity_value = float(quantity_text)
            except ValueError:
                self._append_status(f"Некорректное количество: {quantity_text}")
                return
            if quantity_value <= 0:
                self._append_status("Количество должно быть больше нуля")
                return

        with self.state["lock"]:
            last_price = self.state.get("last_price")

        if order_type == "LIMIT":
            if not price_text:
                self._append_status("Для лимитного ордера укажите цену")
                return
            try:
                price_value = float(price_text)
            except ValueError:
                self._append_status(f"Некорректная цена: {price_text}")
                return
            if price_value <= 0:
                self._append_status("Цена должна быть больше нуля")
                return

            def worker() -> None:
                self.trader.place_limit_order(symbol, side, price_value, quantity=quantity_value, reduce_only=reduce_only)

            threading.Thread(target=worker, daemon=True).start()
            self.order_dialog.close()
            return

        def worker() -> None:
            self.trader.place_market_order(symbol, side, last_price, quantity=quantity_value, reduce_only=reduce_only)

        threading.Thread(target=worker, daemon=True).start()
        self.order_dialog.close()

    def _update_balance(self, value: str) -> None:
        cleaned = value.replace(",", ".").strip()
        if not cleaned:
            return
        try:
            amount = float(cleaned)
        except ValueError:
            self._append_status(f"Некорректный баланс: {value}")
            return
        if amount <= 0:
            self._append_status("Баланс должен быть больше нуля")
            return

        self.trader.update_demo_balance("USDT", amount)

    def handle_event(self, event: pygame.event.Event) -> None:
        if self.order_dialog.visible:
            self.order_dialog.handle_event(event)
            return
        if self.search.handle_event(event):
            query = self.search.text.upper()
            self.filtered_symbols = [s for s in self.all_symbols if query in s][:300] if query else self.all_symbols[:300]
            self.dropdown.set_items(self.filtered_symbols)
            self.dropdown.visible = True
            return
        if self.new_order_button.handle_event(event):
            return
        if self.balance_input.handle_event(event):
            return
        if self.dropdown.handle_event(event):
            return
        if self.status_panel.handle_event(event):
            return

        if event.type == pygame.MOUSEBUTTONDOWN:
            if not self.search.rect.collidepoint(event.pos) and not self.dropdown.hit_test(event.pos):
                self.dropdown.visible = False
                self.search.active = False
                self.balance_input.active = False

        if not self.search.active and self.chart.handle_event(event):
            return

        if event.type == pygame.KEYDOWN and event.key == pygame.K_RETURN and not self.search.active and self.filtered_symbols:
            self._on_symbol(self.filtered_symbols[0])
            return
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.running = False
            return

    def update(self, dt: float) -> None:
        if not self.search.active:
            self.dropdown.visible = False
        self.chart.update(dt)
        with self.state["lock"]:
            balance = self.state.get("demo_balance")
        if balance is not None and not self.balance_input.active:
            try:
                numeric_balance = float(balance)
            except (TypeError, ValueError):
                numeric_balance = None
            if numeric_balance is not None:
                formatted = f"{numeric_balance:.2f}"
                if self.balance_input.text != formatted:
                    self.balance_input.set_text(formatted)

    def draw(self, screen: pygame.Surface) -> None:
        screen.fill(config.COLOR_BG)
        self.search.draw(screen)
        self.new_order_button.draw(screen)
        label = self.small.render("Демо баланс", True, config.COLOR_HINT)
        screen.blit(label, (config.BALANCE_RECT[0] - label.get_width() - 8, config.BALANCE_RECT[1] + 5))
        self.balance_input.draw(screen)
        self.chart.draw(screen)
        self.status_panel.draw(screen)
        self.dropdown.draw(screen)
        if self.order_dialog.visible:
            self.order_dialog.draw(screen)

    def _load_last_symbol(self) -> None:
        last = config.load_last_symbol()
        if last and last in self.all_symbols:
            self._on_symbol(last)

    def stop(self) -> None:
        self.price_fetcher.stop()

    def run(self) -> None:  # pragma: no cover - graphical loop
        try:
            super().run()
        finally:
            self.stop()


if __name__ == "__main__":  # pragma: no cover - manual run only
    app = CryptoTraderApp()
    app.run()
