"""Candlestick chart widget."""

from __future__ import annotations

import time
from collections import deque
from math import floor
from typing import List, Tuple

import pygame

from data_utils import dedupe_candles

Candle = Tuple[float, float, float, float, float, bool]


def aggregate_candles(candles: List[Candle], minutes: int) -> List[Candle]:
    if minutes <= 1:
        return candles
    result: List[Candle] = []
    bucket = None
    step = minutes * 60
    for ts, o, h, l, c, is_pre in candles:
        key = floor(ts / step) * step
        if bucket is None or key != bucket["key"]:
            if bucket is not None:
                result.append((bucket["key"], bucket["o"], bucket["h"], bucket["l"], bucket["c"], is_pre))
            bucket = {"key": key, "o": o, "h": h, "l": l, "c": c}
        else:
            bucket["h"] = max(bucket["h"], h)
            bucket["l"] = min(bucket["l"], l)
            bucket["c"] = c
    if bucket is not None:
        result.append((bucket["key"], bucket["o"], bucket["h"], bucket["l"], bucket["c"], True))
    return result


def compute_simple_moving_average(candles: List[Candle], period: int) -> dict[float, float]:
    if period <= 0:
        return {}

    window: deque[float] = deque()
    total = 0.0
    averages: dict[float, float] = {}

    for ts, _open, _high, _low, close, _flag in candles:
        window.append(close)
        total += close
        if len(window) > period:
            total -= window.popleft()
        if len(window) == period:
            averages[ts] = total / period

    return averages


def choose_agg_minutes(px_per_candle: float) -> int:
    if px_per_candle >= 8.0:
        return 1
    if px_per_candle >= 4.0:
        return 5
    if px_per_candle >= 2.0:
        return 15
    if px_per_candle >= 1.2:
        return 30
    if px_per_candle >= 0.7:
        return 60
    if px_per_candle >= 0.4:
        return 240
    if px_per_candle >= 0.25:
        return 720
    if px_per_candle >= 0.15:
        return 1440
    if px_per_candle >= 0.10:
        return 4320
    return 10080


class CandlesChart:
    def __init__(self, rect: pygame.Rect, font_small: pygame.font.Font, state: dict):
        self.rect = rect
        self.font_small = font_small
        self.state = state
        self.seconds_per_screen = 180.0
        self.x_start = 0.0
        self.dragging = False
        self.drag_x0 = 0
        self.drag_off0 = 0.0
        self.user_pan = False
        self.hover_candle = None

    def reset_view(self) -> None:
        self.seconds_per_screen = 180.0
        self.x_start = 0.0
        self.user_pan = False

    def handle_event(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.MOUSEBUTTONDOWN and self.rect.collidepoint(event.pos):
            if event.button in (4, 5):
                mx = event.pos[0]
                rel = max(0, min(1, (mx - self.rect.left) / self.rect.width))
                t_at = self.x_start + rel * self.seconds_per_screen
                new = max(30.0, self.seconds_per_screen * (0.8 if event.button == 4 else 1.25))
                new = min(new, 6 * 24 * 3600.0)
                self.seconds_per_screen = new
                self.x_start = max(0.0, t_at - rel * new)
                self.user_pan = True
                return True
            if event.button == 1:
                self.dragging = True
                self.drag_x0 = event.pos[0]
                self.drag_off0 = self.x_start
                return True
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1 and self.dragging:
            self.dragging = False
            return True
        if event.type == pygame.MOUSEMOTION and self.dragging:
            dx = event.pos[0] - self.drag_x0
            spp = self.seconds_per_screen / self.rect.width
            self.x_start = max(0.0, self.drag_off0 - dx * spp)
            self.user_pan = True
            return True
        return False

    def update(self, dt: float) -> None:
        with self.state["lock"]:
            candles = list(self.state.get("data", []))
            base = self.state.get("base_time")
        if candles and not self.user_pan and base is not None:
            last_open = candles[-1][0]
            last_close = last_open + 60
            now_rel = last_close - base
            self.x_start = max(0.0, now_rel - self.seconds_per_screen)

    def _draw_axes(self, surf: pygame.Surface, pmin: float, pmax: float, base: float, v0: float, v1: float) -> None:
        px_per_sec = self.rect.width / (v1 - v0)
        for i in range(5):
            yy = self.rect.top + i * (self.rect.height / 4.0)
            pygame.draw.line(surf, (48, 48, 54), (self.rect.left, yy), (self.rect.right, yy), 1)
            price = pmax - (pmax - pmin) * (i / 4.0)
            label = self.font_small.render(f"{price:.6f}", True, (180, 180, 190))
            surf.blit(label, (self.rect.right - 120, yy - 10))
        for i in range(7):
            xx = self.rect.left + i * (self.rect.width / 6.0)
            pygame.draw.line(surf, (40, 40, 46), (xx, self.rect.top), (xx, self.rect.bottom), 1)
            sec = v0 + (v1 - v0) * (i / 6.0)
            ts_abs = base + sec
            label = time.strftime("%d.%m %H:%M", time.localtime(ts_abs))
            text = self.font_small.render(label, True, (160, 160, 170))
            surf.blit(text, (xx + 2, self.rect.bottom - 18))

    def draw(self, surf: pygame.Surface) -> None:
        pygame.draw.rect(surf, (15, 16, 22), self.rect)
        pygame.draw.rect(surf, (60, 60, 80), self.rect, 1)

        with self.state["lock"]:
            candles = list(self.state.get("data", []))
            base = self.state.get("base_time")
        if not candles or base is None:
            return

        candles = dedupe_candles(candles)
        v0, v1 = self.x_start, self.x_start + self.seconds_per_screen
        px_per_sec = self.rect.width / (v1 - v0)
        px_per_1m = 60 * px_per_sec
        agg_min = choose_agg_minutes(px_per_1m)
        draw_candles = aggregate_candles(candles, agg_min)

        visible = []
        for c in draw_candles:
            st = c[0] - base
            en = st + agg_min * 60
            if en >= v0 and st <= v1:
                visible.append(c)
        if not visible:
            visible = draw_candles[-200:]

        highs = [c[2] for c in visible]
        lows = [c[3] for c in visible]
        pmax, pmin = max(highs), min(lows)
        if abs(pmax - pmin) < 1e-12:
            pmax += 0.5
            pmin -= 0.5

        def y_from(price: float) -> float:
            n = (price - pmin) / (pmax - pmin)
            return self.rect.bottom - n * self.rect.height

        self._draw_axes(surf, pmin, pmax, base, v0, v1)
        self._draw_scale_label(surf, agg_min)

        self.hover_candle = None
        mx, my = pygame.mouse.get_pos()
        prev_ts = None
        prev_x_end = None
        expected_step = agg_min * 60.0
        for c in visible:
            ts_open, o, h, l, cl, _ = c
            st_rel = ts_open - base
            x = self.rect.left + (st_rel - v0) * px_per_sec
            w = max(2, int(agg_min * 60 * px_per_sec) - 2)
            y_h, y_l, y_o, y_c = y_from(h), y_from(l), y_from(o), y_from(cl)

            if prev_ts is not None and prev_x_end is not None:
                diff = ts_open - prev_ts
                excess = diff - expected_step
                if excess > 60.0:
                    x1 = int(prev_x_end)
                    x2 = int(x)
                    self._draw_dashed_v(surf, x1, self.rect.top, self.rect.bottom, (255, 180, 180))
                    self._draw_dashed_v(surf, x2, self.rect.top, self.rect.bottom, (255, 180, 180))

            color = (0, 190, 90) if cl >= o else (230, 70, 70)
            pygame.draw.line(surf, (215, 215, 215), (x + w // 2, y_h), (x + w // 2, y_l), 1)
            top = min(y_o, y_c)
            h_body = max(1, abs(y_c - y_o))
            pygame.draw.rect(surf, color, (x, top, w, h_body))

            rect = pygame.Rect(x, min(y_l, y_h), w, max(4, abs(y_l - y_h)))
            if rect.collidepoint(mx, my):
                self.hover_candle = {"candle": c, "x": x, "y": y_c}

            prev_ts = ts_open
            prev_x_end = x + w

        ma_settings = [
            (7, (255, 206, 86)),
            (25, (102, 191, 255)),
            (99, (183, 102, 255)),
        ]
        self._draw_moving_averages(
            surf,
            draw_candles,
            base,
            v0,
            v1,
            px_per_sec,
            y_from,
            ma_settings,
        )

        if self.hover_candle:
            ts_open, o, h, l, cl, _ = self.hover_candle["candle"]
            lines = [
                time.strftime("Время: %d.%m %H:%M", time.localtime(ts_open)),
                f"Откр.: {o:.6f}",
                f"Макс.: {h:.6f}",
                f"Мин.: {l:.6f}",
                f"Закр.: {cl:.6f}",
            ]
            pad = 4
            surfaces = [self.font_small.render(t, True, (0, 0, 0)) for t in lines]
            width = max(surface.get_width() for surface in surfaces) + 2 * pad
            height = len(surfaces) * (self.font_small.get_height() + 2) + 2 * pad
            tx = min(max(self.hover_candle["x"] + 10, self.rect.left + 6), self.rect.right - 6 - width)
            ty = max(self.rect.top + 6, min(self.hover_candle["y"] - height - 10, self.rect.bottom - 6 - height))
            pygame.draw.rect(surf, (240, 240, 240), (tx, ty, width, height), border_radius=4)
            for idx, surface_text in enumerate(surfaces):
                surf.blit(surface_text, (tx + pad, ty + pad + idx * (self.font_small.get_height() + 2)))

        self._draw_crosshair(surf, base, v0, v1, pmin, pmax)

    def _draw_moving_averages(
        self,
        surf: pygame.Surface,
        candles: List[Candle],
        base: float,
        v0: float,
        v1: float,
        px_per_sec: float,
        y_from,
        ma_settings: List[Tuple[int, Tuple[int, int, int]]],
    ) -> None:
        for period, color in ma_settings:
            averages = compute_simple_moving_average(candles, period)
            if not averages:
                continue

            last_point = None
            for candle in candles:
                ts_open = candle[0]
                value = averages.get(ts_open)
                if value is None:
                    continue

                st_rel = ts_open - base
                if st_rel > v1:
                    break

                x = self.rect.left + (st_rel - v0) * px_per_sec
                y = y_from(value)
                point = (x, y)

                if last_point is not None:
                    pygame.draw.line(surf, color, last_point, point, 2)

                last_point = point

    def _draw_dashed_v(
        self,
        surface: pygame.Surface,
        x: int,
        y1: float,
        y2: float,
        color=(255, 255, 255),
        dash=6,
        gap=4,
    ) -> None:
        y = y1
        while y < y2:
            y2_ = min(y + dash, y2)
            pygame.draw.line(surface, color, (x, y), (x, y2_), 1)
            y += dash + gap

    def _draw_dashed_h(
        self,
        surface: pygame.Surface,
        y: int,
        x1: float,
        x2: float,
        color=(255, 255, 255),
        dash=6,
        gap=4,
    ) -> None:
        x = x1
        while x < x2:
            x2_ = min(x + dash, x2)
            pygame.draw.line(surface, color, (x, y), (x2_, y), 1)
            x += dash + gap

    def _draw_scale_label(self, surf: pygame.Surface, agg_min: int) -> None:
        label = self._format_scale_label(agg_min)
        text = self.font_small.render(f"Таймфрейм: {label}", True, (230, 230, 238))
        pad = 6
        box_w = text.get_width() + 2 * pad
        box_h = text.get_height() + 2 * pad
        x = self.rect.left + 10
        y = self.rect.top + 10
        pygame.draw.rect(surf, (28, 30, 38), (x, y, box_w, box_h), border_radius=4)
        pygame.draw.rect(surf, (54, 56, 70), (x, y, box_w, box_h), 1, border_radius=4)
        surf.blit(text, (x + pad, y + pad))

    def _format_scale_label(self, agg_min: int) -> str:
        if agg_min < 60:
            return f"{agg_min}m"
        if agg_min % 1440 == 0:
            days = agg_min // 1440
            return f"{days}d"
        if agg_min % 60 == 0:
            hours = agg_min // 60
            return f"{hours}h"
        return f"{agg_min}m"

    def _draw_crosshair(self, surf: pygame.Surface, base: float, v0: float, v1: float, pmin: float, pmax: float) -> None:
        mx, my = pygame.mouse.get_pos()
        if not self.rect.collidepoint(mx, my):
            return

        self._draw_dashed_v(surf, mx, self.rect.top, self.rect.bottom, (255, 255, 255))
        self._draw_dashed_h(surf, my, self.rect.left, self.rect.right, (255, 255, 255))

        rel_x = (mx - self.rect.left) / self.rect.width
        rel_x = max(0.0, min(1.0, rel_x))
        seconds = v0 + rel_x * (v1 - v0)
        ts_abs = base + seconds
        price_rel = (my - self.rect.top) / self.rect.height
        price_rel = max(0.0, min(1.0, price_rel))
        price = pmax - price_rel * (pmax - pmin)

        lines = [
            time.strftime("%d.%m %H:%M:%S", time.localtime(ts_abs)),
            f"Цена: {price:.6f}",
        ]
        pad = 6
        text_color = (18, 18, 24)
        surfaces = [self.font_small.render(text, True, text_color) for text in lines]
        width = max(surface.get_width() for surface in surfaces) + 2 * pad
        height = len(surfaces) * (self.font_small.get_height() + 2) + 2 * pad

        if mx < self.rect.centerx:
            box_x = mx + 12
        else:
            box_x = mx - width - 12
        if my < self.rect.centery:
            box_y = my + 12
        else:
            box_y = my - height - 12

        box_x = max(self.rect.left + 4, min(box_x, self.rect.right - width - 4))
        box_y = max(self.rect.top + 4, min(box_y, self.rect.bottom - height - 4))

        pygame.draw.rect(surf, (245, 245, 245), (box_x, box_y, width, height), border_radius=4)
        pygame.draw.rect(surf, (52, 52, 60), (box_x, box_y, width, height), 1, border_radius=4)

        for idx, surface_text in enumerate(surfaces):
            surf.blit(surface_text, (box_x + pad, box_y + pad + idx * (self.font_small.get_height() + 2)))
