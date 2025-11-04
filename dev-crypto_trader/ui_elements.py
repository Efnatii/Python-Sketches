"""Reusable pygame UI widgets."""

from __future__ import annotations

from typing import Callable, Iterable, List, Optional, Sequence

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

    def handle_event(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and self.rect.collidepoint(event.pos):
            layout = self._visible_message_layout()
            y = event.pos[1]
            for message, top, bottom, _ in layout:
                if top <= y < bottom:
                    try:
                        pygame.scrap.put(pygame.SCRAP_TEXT, message.encode("utf-8"))
                    except pygame.error:
                        pass
                    return True
        return False

    def draw(self, surface: pygame.Surface) -> None:
        pygame.draw.rect(surface, (24, 24, 32), self.rect)
        pygame.draw.rect(surface, (55, 55, 75), self.rect, 1)
        line_h = self.font.get_height() + 4
        for _, top, _, lines in self._visible_message_layout():
            y = top
            for line in lines:
                label = self.font.render(line, True, (210, 210, 220))
                surface.blit(label, (self.rect.x + 6, y))
                y += line_h

    def _visible_message_layout(self):
        with self.state["lock"]:
            messages = list(self.state.get("status_log", []))
        line_h = self.font.get_height() + 4
        max_lines = self.rect.height // line_h
        max_width = self.rect.width - 12
        y = self.rect.y + 6
        drawn = 0
        layout = []
        for msg in messages:
            if drawn >= max_lines:
                break
            lines = list(self._wrap_text(msg, max_width))
            if not lines:
                lines = [""]
            available = max_lines - drawn
            visible_lines = lines[:available]
            top = y
            bottom = y + line_h * len(visible_lines)
            layout.append((msg, top, bottom, visible_lines))
            y = bottom
            drawn += len(visible_lines)
        return layout

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
