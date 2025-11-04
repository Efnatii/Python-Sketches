"""Minimal modular candlestick viewer without AI components."""

from __future__ import annotations

import threading
from typing import List

import pygame

import trader_config as config
from binance_client import fetch_all_symbols
from chart_view import CandlesChart
from price_fetcher import PriceFetcher
from ui_elements import DropdownList, StatusPanel, TextInput


class BaseApp:
    def __init__(self, width: int, height: int, title: str, fps: int = 60) -> None:
        pygame.init()
        self.screen = pygame.display.set_mode((width, height))
        pygame.display.set_caption(title)
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
        }

        self.search = TextInput(pygame.Rect(*config.SEARCH_RECT), self.small, placeholder="...")
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

        self.all_symbols = fetch_all_symbols()
        self.filtered_symbols: List[str] = self.all_symbols[:300]
        self.dropdown.set_items(self.filtered_symbols)

        self._load_last_symbol()

    def _on_symbol(self, symbol: str) -> None:
        self.search.set_text(symbol)
        with self.state["lock"]:
            self.state["current_symbol"] = symbol
        self.price_fetcher.refresh_history()
        self.chart.reset_view()
        self.dropdown.visible = False
        self.search.active = False
        config.save_last_symbol(symbol)

    def handle_event(self, event: pygame.event.Event) -> None:
        if self.search.handle_event(event):
            query = self.search.text.upper()
            self.filtered_symbols = [s for s in self.all_symbols if query in s][:300] if query else self.all_symbols[:300]
            self.dropdown.set_items(self.filtered_symbols)
            self.dropdown.visible = True
            return
        if self.dropdown.handle_event(event):
            return

        if event.type == pygame.MOUSEBUTTONDOWN:
            if not self.search.rect.collidepoint(event.pos) and not self.dropdown.hit_test(event.pos):
                self.dropdown.visible = False
                self.search.active = False

        if not self.search.active and self.chart.handle_event(event):
            return

        if event.type == pygame.KEYDOWN and event.key == pygame.K_RETURN and not self.search.active and self.filtered_symbols:
            self._on_symbol(self.filtered_symbols[0])
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.running = False

    def update(self, dt: float) -> None:
        if not self.search.active:
            self.dropdown.visible = False
        self.chart.update(dt)

    def draw(self, screen: pygame.Surface) -> None:
        screen.fill(config.COLOR_BG)
        self.search.draw(screen)
        self.chart.draw(screen)
        self.status_panel.draw(screen)
        self.dropdown.draw(screen)

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
