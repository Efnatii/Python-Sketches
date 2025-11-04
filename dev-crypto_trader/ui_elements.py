"""Reusable pygame UI widgets."""

from __future__ import annotations

from typing import Callable, Iterable, List, Optional, Sequence, Tuple

import pygame


class GUIElement:
    def __init__(self, rect: pygame.Rect):
        self.rect = rect

    def handle_event(self, event: pygame.event.Event) -> bool:
        return False

    def update(self, dt: float) -> None:  # pragma: no cover - graphical utility
        pass

    def draw(self, surface: pygame.Surface) -> None:  # pragma: no cover - graphical utility
        pass


class TextInput(GUIElement):
    def __init__(
        self,
        rect: pygame.Rect,
        font: pygame.font.Font,
        placeholder: str = "...",
        on_enter: Optional[Callable[[str], None]] = None,
    ) -> None:
        super().__init__(rect)
        self.font = font
        self.placeholder = placeholder
        self.on_enter = on_enter
        self.text = ""
        self.active = False

    def set_text(self, value: str) -> None:
        self.text = value

    def handle_event(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.MOUSEBUTTONDOWN:
            self.active = self.rect.collidepoint(event.pos)
            return self.active
        if event.type == pygame.KEYDOWN and self.active:
            if event.key == pygame.K_BACKSPACE:
                self.text = self.text[:-1]
            elif event.key == pygame.K_RETURN:
                if self.on_enter:
                    self.on_enter(self.text)
            else:
                ch = event.unicode
                if ch:
                    self.text += ch
            return True
        return False

    def draw(self, surface: pygame.Surface) -> None:
        pygame.draw.rect(surface, (35, 36, 46), self.rect, border_radius=4)
        pygame.draw.rect(surface, (90, 90, 110), self.rect, 1, border_radius=4)
        text = self.text if (self.text or self.active) else self.placeholder
        color = (240, 240, 240) if self.text or self.active else (150, 150, 160)
        label = self.font.render(text, True, color)
        surface.blit(label, (self.rect.x + 6, self.rect.y + (self.rect.height - label.get_height()) // 2))


class InfoField(GUIElement):
    """Passive text container used for displaying read-only values."""

    def __init__(
        self,
        rect: pygame.Rect,
        font: pygame.font.Font,
        *,
        placeholder: str = "—",
        align: str = "left",
    ) -> None:
        super().__init__(rect)
        self.font = font
        self.placeholder = placeholder
        self.align = align if align in {"left", "right"} else "left"
        self.text = ""

    def set_text(self, value: Optional[str]) -> None:
        self.text = value or ""

    def handle_event(self, event: pygame.event.Event) -> bool:
        return False

    def draw(self, surface: pygame.Surface) -> None:
        pygame.draw.rect(surface, (35, 36, 46), self.rect, border_radius=4)
        pygame.draw.rect(surface, (90, 90, 110), self.rect, 1, border_radius=4)
        text = self.text or self.placeholder
        color = (240, 240, 240) if self.text else (150, 150, 160)
        label = self.font.render(text, True, color)
        if self.align == "right":
            x = self.rect.right - label.get_width() - 8
        else:
            x = self.rect.x + 8
        y = self.rect.y + (self.rect.height - label.get_height()) // 2
        surface.blit(label, (x, y))


class Button(GUIElement):
    def __init__(
        self,
        rect: pygame.Rect,
        text: str,
        font: pygame.font.Font,
        on_click: Optional[Callable[[], None]] = None,
        *,
        bg_color: Tuple[int, int, int] = (55, 60, 80),
        text_color: Tuple[int, int, int] = (230, 230, 240),
        hover_color: Tuple[int, int, int] = (75, 80, 110),
    ) -> None:
        super().__init__(rect)
        self.text = text
        self.font = font
        self.on_click = on_click
        self.bg_color = bg_color
        self.text_color = text_color
        self.hover_color = hover_color
        self._pressed = False

    def handle_event(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and self.rect.collidepoint(event.pos):
            self._pressed = True
            return True
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if self._pressed and self.rect.collidepoint(event.pos):
                if self.on_click:
                    self.on_click()
                self._pressed = False
                return True
            self._pressed = False
        if event.type == pygame.MOUSEMOTION and not self.rect.collidepoint(event.pos):
            self._pressed = False
        return False

    def draw(self, surface: pygame.Surface) -> None:
        if not surface.get_rect().colliderect(self.rect):
            return
        mouse_pos = pygame.mouse.get_pos()
        hovered = self.rect.collidepoint(mouse_pos)
        color = self.hover_color if hovered else self.bg_color
        pygame.draw.rect(surface, color, self.rect, border_radius=6)
        pygame.draw.rect(surface, (40, 45, 60), self.rect, 1, border_radius=6)
        label = self.font.render(self.text, True, self.text_color)
        surface.blit(
            label,
            (
                self.rect.x + (self.rect.width - label.get_width()) // 2,
                self.rect.y + (self.rect.height - label.get_height()) // 2,
            ),
        )


class DropdownList(GUIElement):
    def __init__(
        self,
        x: int,
        y: int,
        width: int,
        item_height: int,
        font: pygame.font.Font,
        surface_height: int,
        on_select: Optional[Callable[[str], None]] = None,
    ) -> None:
        super().__init__(pygame.Rect(x, y, width, item_height))
        self.font = font
        self.surface_height = surface_height
        self.on_select = on_select
        self.item_height = item_height
        self.items: List[str] = []
        self.visible = False
        self.scroll = 0

    def set_items(self, values: Sequence[str]) -> None:
        self.items = list(values)
        self.scroll = 0

    def handle_event(self, event: pygame.event.Event) -> bool:
        if not self.visible:
            return False
        max_h = self.surface_height - self.rect.y - 10
        max_vis = max(1, max_h // self.item_height)
        visible = self.items[self.scroll : self.scroll + max_vis]
        area = pygame.Rect(self.rect.x, self.rect.y, self.rect.width, len(visible) * self.item_height)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button in (4, 5) and area.collidepoint(event.pos):
            if event.button == 4:
                self.scroll = max(0, self.scroll - 1)
            else:
                self.scroll = min(max(0, len(self.items) - max_vis), self.scroll + 1)
            return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and area.collidepoint(event.pos):
            idx = (event.pos[1] - self.rect.y) // self.item_height
            actual = self.scroll + idx
            if 0 <= actual < len(self.items) and self.on_select:
                self.on_select(self.items[actual])
            return True
        return False

    def hit_test(self, pos) -> bool:
        if not self.visible:
            return False
        max_h = self.surface_height - self.rect.y - 10
        max_vis = max(1, max_h // self.item_height)
        visible = self.items[self.scroll : self.scroll + max_vis]
        area = pygame.Rect(self.rect.x, self.rect.y, self.rect.width, len(visible) * self.item_height)
        return area.collidepoint(pos)

    def draw(self, surface: pygame.Surface) -> None:
        if not self.visible:
            return
        max_h = self.surface_height - self.rect.y - 10
        max_vis = max(1, max_h // self.item_height)
        visible = self.items[self.scroll : self.scroll + max_vis]
        height = len(visible) * self.item_height
        pygame.draw.rect(surface, (35, 35, 45), (self.rect.x, self.rect.y, self.rect.width, height), border_radius=4)
        for i, item in enumerate(visible):
            label = self.font.render(item, True, (220, 220, 220))
            surface.blit(label, (self.rect.x + 6, self.rect.y + 2 + i * self.item_height))


class StatusPanel(GUIElement):
    def __init__(self, rect: pygame.Rect, font: pygame.font.Font, state: dict):
        super().__init__(rect)
        self.font = font
        self.state = state
        self.tabs = ["Лог", "Ордера"]
        self.active_tab = 0
        self._tab_height = 32
        self._tab_padding = 6
        self._line_height = self.font.get_height() + 4
        self._scroll_offsets = [0, 0]

    def handle_event(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for idx, rect in self._tab_rects():
                if rect.collidepoint(event.pos):
                    if self.active_tab != idx:
                        self.active_tab = idx
                    return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button in (4, 5) and self.rect.collidepoint(event.pos):
            step = self._line_height * 3
            delta = -step if event.button == 4 else step
            self._scroll(self.active_tab, delta)
            return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and self.rect.collidepoint(event.pos):
            if event.pos[1] < self.rect.y + self._tab_height:
                return True
            if self.active_tab == 0:
                for message, _, top, bottom in self._message_segments():
                    if top <= event.pos[1] < bottom:
                        try:
                            pygame.scrap.put(pygame.SCRAP_TEXT, message.encode("utf-8"))
                        except pygame.error:
                            pass
                        return True
        return False

    def draw(self, surface: pygame.Surface) -> None:
        pygame.draw.rect(surface, (24, 24, 32), self.rect)
        pygame.draw.rect(surface, (55, 55, 75), self.rect, 1)

        self._clamp_scroll(self.active_tab)

        for idx, rect in self._tab_rects():
            color = (70, 75, 100) if idx == self.active_tab else (40, 42, 56)
            pygame.draw.rect(surface, color, rect, border_radius=6)
            pygame.draw.rect(surface, (55, 55, 75), rect, 1, border_radius=6)
            label = self.font.render(self.tabs[idx], True, (230, 230, 240))
            surface.blit(
                label,
                (
                    rect.x + (rect.width - label.get_width()) // 2,
                    rect.y + (rect.height - label.get_height()) // 2,
                ),
            )

        if self.active_tab == 0:
            self._draw_messages(surface)
        else:
            self._draw_orders(surface)

    def _scroll(self, tab: int, delta: int) -> None:
        if delta == 0:
            return
        current = self._scroll_offsets[tab]
        updated = max(0, min(current + delta, self._max_scroll(tab)))
        self._scroll_offsets[tab] = updated

    def _clamp_scroll(self, tab: int) -> None:
        maximum = self._max_scroll(tab)
        if self._scroll_offsets[tab] > maximum:
            self._scroll_offsets[tab] = maximum

    def _max_scroll(self, tab: int) -> int:
        content_rect = self._content_rect()
        available = max(0, content_rect.height - 12)
        total = self._total_content_height(tab)
        if total <= available:
            return 0
        return total - available

    def _total_content_height(self, tab: int) -> int:
        content_rect = self._content_rect()
        width = content_rect.width - 12
        if width <= 0:
            return 0
        if tab == 0:
            with self.state["lock"]:
                entries = list(self.state.get("status_log", []))
            texts = entries
        else:
            with self.state["lock"]:
                orders = list(self.state.get("order_log", []))
            texts = [self._format_order_text(order) for order in orders]
        total_lines = 0
        for text in texts:
            lines = list(self._wrap_text(text, width)) or [""]
            total_lines += len(lines)
        return total_lines * self._line_height

    def _draw_messages(self, surface: pygame.Surface) -> None:
        content_rect = self._content_rect()
        clip = surface.get_clip()
        surface.set_clip(content_rect)
        top_limit = content_rect.y + 6
        bottom_limit = content_rect.bottom - 6
        for message, lines, top, bottom in self._message_segments():
            if bottom < top_limit:
                continue
            if top > bottom_limit:
                break
            first_line = max(0, (top_limit - top) // self._line_height) if top < top_limit else 0
            y = top + first_line * self._line_height
            for line in lines[first_line:]:
                if y >= bottom_limit:
                    break
                label = self.font.render(line, True, (210, 210, 220))
                surface.blit(label, (content_rect.x + 6, y))
                y += self._line_height
        surface.set_clip(clip)

    def _draw_orders(self, surface: pygame.Surface) -> None:
        content_rect = self._content_rect()
        clip = surface.get_clip()
        surface.set_clip(content_rect)
        top_limit = content_rect.y + 6
        bottom_limit = content_rect.bottom - 6
        for _, lines, top, bottom in self._order_segments():
            if bottom < top_limit:
                continue
            if top > bottom_limit:
                break
            first_line = max(0, (top_limit - top) // self._line_height) if top < top_limit else 0
            y = top + first_line * self._line_height
            for line in lines[first_line:]:
                if y >= bottom_limit:
                    break
                label = self.font.render(line, True, (210, 210, 220))
                surface.blit(label, (content_rect.x + 6, y))
                y += self._line_height
        surface.set_clip(clip)

    def _message_segments(self):
        content_rect = self._content_rect()
        width = content_rect.width - 12
        start_y = content_rect.y + 6 - self._scroll_offsets[0]
        with self.state["lock"]:
            messages = list(self.state.get("status_log", []))
        y = start_y
        for message in messages:
            lines = list(self._wrap_text(message, width)) or [""]
            height = len(lines) * self._line_height
            top = y
            bottom = y + height
            yield message, lines, top, bottom
            y = bottom

    def _order_segments(self):
        content_rect = self._content_rect()
        width = content_rect.width - 12
        start_y = content_rect.y + 6 - self._scroll_offsets[1]
        with self.state["lock"]:
            orders = list(self.state.get("order_log", []))
        y = start_y
        for order in orders:
            text = self._format_order_text(order)
            lines = list(self._wrap_text(text, width)) or [""]
            height = len(lines) * self._line_height
            top = y
            bottom = y + height
            yield order, lines, top, bottom
            y = bottom

    def _format_order_text(self, order: dict) -> str:
        return (
            f"[{order.get('time', '')}] {order.get('side', '')} {order.get('symbol', '')}"
            f" {order.get('type', '')} qty={order.get('quantity', '')}"
            f" price={order.get('price', '')} ({order.get('status', '')})"
        )

    def _wrap_text(self, text: str, max_width: int):
        if not text:
            yield ""
            return

        words = text.split()
        if not words:
            yield ""
            return

        line = ""
        for word in words:
            candidate = word if not line else f"{line} {word}"
            if self.font.size(candidate)[0] <= max_width:
                line = candidate
                continue

            if line:
                yield from self._split_segment(line, max_width)
                line = ""

            if self.font.size(word)[0] <= max_width:
                line = word
            else:
                yield from self._split_segment(word, max_width)

        if line:
            yield from self._split_segment(line, max_width)

    def _split_segment(self, text: str, max_width: int):
        if self.font.size(text)[0] <= max_width:
            yield text
            return

        chunk = ""
        for ch in text:
            candidate = f"{chunk}{ch}" if chunk else ch
            if self.font.size(candidate)[0] <= max_width:
                chunk = candidate
            else:
                if chunk:
                    yield chunk
                chunk = ch
        if chunk:
            yield chunk

    def _content_rect(self) -> pygame.Rect:
        return pygame.Rect(
            self.rect.x,
            self.rect.y + self._tab_height,
            self.rect.width,
            self.rect.height - self._tab_height,
        )

    def _tab_rects(self):
        width = (self.rect.width - (len(self.tabs) + 1) * self._tab_padding) // max(1, len(self.tabs))
        for idx, _ in enumerate(self.tabs):
            x = self.rect.x + self._tab_padding + idx * (width + self._tab_padding)
            rect = pygame.Rect(x, self.rect.y + self._tab_padding, width, self._tab_height - 2 * self._tab_padding)
            yield idx, rect


class OrderDialog(GUIElement):
    def __init__(
        self,
        rect: pygame.Rect,
        font: pygame.font.Font,
        small_font: pygame.font.Font,
    ) -> None:
        super().__init__(rect)
        self.font = font
        self.small_font = small_font
        self.visible = False
        self.symbol = ""
        self.side = "BUY"
        self.order_type = "MARKET"
        self.reduce_only = False
        self.last_price: Optional[float] = None
        self._padding = 30
        self._column_gap = 16
        self._control_height = 32
        self._field_height = 30
        self._side_top = 0
        self._type_top = 0
        self._half_width = 0
        self._side_left = 0
        self._type_left = 0
        self._side_label_pos = (rect.x + self._padding, rect.y + 70)
        self._type_label_pos = (rect.x + self._padding, rect.y + 70)
        self._quantity_label_pos = (rect.x + self._padding, rect.y + 140)
        self._price_label_pos = (rect.x + self._padding, rect.y + 200)
        self._buttons_top = rect.y + rect.height - self._padding - self._control_height
        self._reduce_only_rect_cache = pygame.Rect(rect.x + self._padding, rect.y + rect.height - 90, 24, 24)

        placeholder_rect = pygame.Rect(rect.x + self._padding, rect.y + 160, rect.width - 2 * self._padding, self._field_height)
        self.quantity_input = TextInput(placeholder_rect.copy(), small_font, placeholder="Количество")
        self.price_input = TextInput(placeholder_rect.copy(), small_font, placeholder="Цена")
        self.confirm_button = Button(pygame.Rect(rect.x, rect.y, 160, self._control_height), "Отправить", small_font)
        self.cancel_button = Button(pygame.Rect(rect.x, rect.y, 120, self._control_height), "Отмена", small_font)
        self.on_submit: Optional[Callable[[dict], None]] = None
        self.on_cancel: Optional[Callable[[], None]] = None
        self._apply_layout()

    def open(self, symbol: str, last_price: Optional[float], on_submit: Callable[[dict], None], on_cancel: Callable[[], None]) -> None:
        self.visible = True
        self.symbol = symbol
        self.last_price = last_price
        self.on_submit = on_submit
        self.on_cancel = on_cancel
        self.side = "BUY"
        self.order_type = "MARKET"
        self.reduce_only = False
        self._apply_layout()
        self.quantity_input.set_text("")
        if last_price is not None:
            self.price_input.set_text(f"{last_price:.4f}")
        else:
            self.price_input.set_text("")
        self.quantity_input.active = False
        self.price_input.active = False

    def close(self) -> None:
        self.visible = False
        self.quantity_input.active = False
        self.price_input.active = False

    def handle_event(self, event: pygame.event.Event) -> bool:
        if not self.visible:
            return False
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if not self.rect.collidepoint(event.pos):
                self._cancel()
                return True
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self._cancel()
            return True
        if event.type == pygame.KEYDOWN and event.key == pygame.K_RETURN:
            if self.on_submit:
                payload = {
                    "symbol": self.symbol,
                    "side": self.side,
                    "type": self.order_type,
                    "quantity": self.quantity_input.text.strip(),
                    "price": self.price_input.text.strip(),
                    "reduce_only": self.reduce_only,
                }
                self.on_submit(payload)
            return True

        if self.quantity_input.handle_event(event):
            return True
        if self.order_type == "LIMIT" and self.price_input.handle_event(event):
            return True

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self._side_rect("BUY").collidepoint(event.pos):
                self.side = "BUY"
                return True
            if self._side_rect("SELL").collidepoint(event.pos):
                self.side = "SELL"
                return True
            if self._type_rect("MARKET").collidepoint(event.pos):
                self.order_type = "MARKET"
                self.price_input.active = False
                return True
            if self._type_rect("LIMIT").collidepoint(event.pos):
                self.order_type = "LIMIT"
                if not self.price_input.text and self.last_price is not None:
                    self.price_input.set_text(f"{self.last_price:.4f}")
                return True
            if self._reduce_only_rect().collidepoint(event.pos):
                self.reduce_only = not self.reduce_only
                return True

        def submit() -> None:
            payload = {
                "symbol": self.symbol,
                "side": self.side,
                "type": self.order_type,
                "quantity": self.quantity_input.text.strip(),
                "price": self.price_input.text.strip(),
                "reduce_only": self.reduce_only,
            }
            if self.on_submit:
                self.on_submit(payload)

        def cancel() -> None:
            self._cancel()

        self.confirm_button.on_click = submit
        self.cancel_button.on_click = cancel

        if self.confirm_button.handle_event(event):
            return True
        if self.cancel_button.handle_event(event):
            return True
        return False

    def draw(self, surface: pygame.Surface) -> None:
        if not self.visible:
            return
        self._apply_layout()
        overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        overlay.fill((5, 5, 8, 160))
        surface.blit(overlay, (0, 0))
        pygame.draw.rect(surface, (30, 32, 44), self.rect, border_radius=12)
        pygame.draw.rect(surface, (90, 95, 120), self.rect, 1, border_radius=12)

        title = self.font.render(f"Новый ордер {self.symbol or ''}", True, (235, 235, 245))
        surface.blit(title, (self.rect.x + 30, self.rect.y + 24))

        subtitle = self.small_font.render("Сторона", True, (180, 180, 190))
        surface.blit(subtitle, self._side_label_pos)
        for side in ("BUY", "SELL"):
            rect = self._side_rect(side)
            color = (50, 110, 70) if side == "BUY" else (130, 60, 60)
            if self.side != side:
                color = tuple(int(c * 0.5) for c in color)
            pygame.draw.rect(surface, color, rect, border_radius=6)
            pygame.draw.rect(surface, (40, 45, 60), rect, 1, border_radius=6)
            label = self.small_font.render("Покупка" if side == "BUY" else "Продажа", True, (240, 240, 250))
            surface.blit(label, (rect.x + (rect.width - label.get_width()) // 2, rect.y + 6))

        order_type_lbl = self.small_font.render("Тип", True, (180, 180, 190))
        surface.blit(order_type_lbl, self._type_label_pos)
        for otype in ("MARKET", "LIMIT"):
            rect = self._type_rect(otype)
            color = (80, 80, 110) if self.order_type == otype else (50, 52, 70)
            pygame.draw.rect(surface, color, rect, border_radius=6)
            pygame.draw.rect(surface, (40, 45, 60), rect, 1, border_radius=6)
            label = self.small_font.render("Рыночный" if otype == "MARKET" else "Лимитный", True, (235, 235, 245))
            surface.blit(label, (rect.x + (rect.width - label.get_width()) // 2, rect.y + 6))

        quantity_lbl = self.small_font.render("Количество", True, (180, 180, 190))
        surface.blit(quantity_lbl, self._quantity_label_pos)
        self.quantity_input.draw(surface)

        if self.order_type == "LIMIT":
            price_lbl = self.small_font.render("Цена", True, (180, 180, 190))
            surface.blit(price_lbl, self._price_label_pos)
            self.price_input.draw(surface)

        reduce_rect = self._reduce_only_rect()
        pygame.draw.rect(surface, (40, 45, 60), reduce_rect, border_radius=4)
        if self.reduce_only:
            pygame.draw.rect(surface, (120, 180, 120), reduce_rect.inflate(-6, -6), border_radius=3)
        label = self.small_font.render("Закрытие позиции", True, (210, 210, 220))
        surface.blit(label, (reduce_rect.right + 10, reduce_rect.y + 2))

        self.cancel_button.draw(surface)
        self.confirm_button.draw(surface)

    def _reduce_only_rect(self) -> pygame.Rect:
        return self._reduce_only_rect_cache.copy()

    def _side_rect(self, side: str) -> pygame.Rect:
        index = 0 if side == "BUY" else 1
        x = self._side_left + index * (self._half_width + self._column_gap)
        return pygame.Rect(x, self._side_top, self._half_width, self._control_height)

    def _type_rect(self, order_type: str) -> pygame.Rect:
        index = 0 if order_type == "MARKET" else 1
        x = self._type_left + index * (self._half_width + self._column_gap)
        return pygame.Rect(x, self._type_top, self._half_width, self._control_height)

    def _cancel(self) -> None:
        self.close()
        if self.on_cancel:
            self.on_cancel()

    def _apply_layout(self) -> None:
        content_width = max(200, self.rect.width - 2 * self._padding)
        self._half_width = max(100, (content_width - self._column_gap) // 2)
        self._side_left = self.rect.x + self._padding
        self._type_left = self._side_left + self._half_width + self._column_gap
        self._side_top = self.rect.y + 96
        self._type_top = self._side_top
        self._side_label_pos = (self._side_left, self._side_top - 24)
        self._type_label_pos = (self._type_left, self._type_top - 24)

        quantity_label_y = self._side_top + self._control_height + 24
        self._quantity_label_pos = (self._side_left, quantity_label_y)
        quantity_rect = pygame.Rect(self._side_left, quantity_label_y + 20, content_width, self._field_height)
        self.quantity_input.rect = quantity_rect

        price_label_y = quantity_rect.bottom + 20
        self._price_label_pos = (self._side_left, price_label_y)
        price_rect = pygame.Rect(self._side_left, price_label_y + 20, content_width, self._field_height)
        self.price_input.rect = price_rect

        self._buttons_top = self.rect.bottom - self._padding - self._control_height
        confirm_width = max(150, min(220, content_width // 2 + 40))
        self.confirm_button.rect = pygame.Rect(
            self.rect.right - self._padding - confirm_width,
            self._buttons_top,
            confirm_width,
            self._control_height,
        )
        self.cancel_button.rect = pygame.Rect(
            self._side_left,
            self._buttons_top,
            120,
            self._control_height,
        )

        min_checkbox_y = max(price_rect.bottom + 16, self.rect.y + self._padding)
        max_checkbox_y = self._buttons_top - self._control_height - 12
        checkbox_y = min_checkbox_y
        if max_checkbox_y < checkbox_y:
            checkbox_y = max_checkbox_y
        self._reduce_only_rect_cache = pygame.Rect(self._side_left, checkbox_y, 24, 24)
