"""Interactive application that translates selected screen areas."""

import sys
from math import sin

if sys.platform.startswith("win"):
    from pynput import mouse, keyboard
    import pygame
    import win32api
    import win32con
else:  # pragma: no cover - platform specific
    raise ImportError("The image_translator package only supports Windows platforms")

from translate import Translator
import pytesseract

from .screenshot import Window, Screenshot
from .utils import configure_tesseract, init_dpi_awareness

configure_tesseract()
init_dpi_awareness()


class ImageTranslatorApp:
    """Interactive application for translating screen selections."""

    def __init__(self, debug=False):
        self.debug = debug

        # Current state
        self.cursor_position = [0, 0]
        self.rect = [0, 0, 0, 0]
        self.drag_points = [0, 0, 0, 0]
        self.w = self.h = 0
        self.done = False
        self.text = ["..."]
        self.fade = 1.0
        self.pressed = False
        self.pending_text = None
        self.current_drag_rect = [0, 0, 0, 0]
        self.selection_counter = 0
        self.time = 0
        self.delta = 0

        self.translator = Translator(from_lang="en", to_lang="ru")

        # Pygame setup
        pygame.init()
        pygame.font.init()
        self.pygame = pygame
        self.screen = pygame.display.set_mode((2000, 2000), pygame.NOFRAME | pygame.SRCALPHA)
        self.font = pygame.font.SysFont("sans serif", 20)
        self.clock = pygame.time.Clock()

        self.text_size = [self.font.size(self.text[0])]

        Window.init(pygame.display.get_wm_info()["window"])
        Window.make_transparent()
        Window.disable_blur()
        self.blur_enabled = False
        Window.set_size(self.text_size[0][0] + 30, self.text_size[0][1] + 30)

        self.key_state = set()
        keyboard.Listener(on_press=self.on_key_press, on_release=self.on_key_release).start()
        mouse.Listener(on_move=self.on_move).start()

    def update_drag_rect(self):
        """Recalculate current selection rectangle based on ``self.drag_points``."""
        x1, y1, x2, y2 = self.drag_points
        self.current_drag_rect = [min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1)]

    def _set_blur(self, enable: bool) -> None:
        """Enable or disable blur depending on ``enable``."""
        if enable and not self.blur_enabled:
            Window.enable_blur()
            self.blur_enabled = True
        elif not enable and self.blur_enabled:
            Window.disable_blur()
            self.blur_enabled = False

    def process_selection(self, selected_rect, proc_id):
        """Recognise text from ``selected_rect`` and translate it."""
        img = Screenshot.grab_image(selected_rect)
        if self.debug:
            try:
                img.show()
            except Exception:
                pass
        raw_text = pytesseract.image_to_string(img, lang="eng").strip()
        result = self.translator.translate(raw_text).split("\n")
        if proc_id == self.selection_counter:
            self.pending_text = result

    # Event handlers -----------------------------------------------------
    def on_move(self, x, y):
        """Track cursor movement during selection."""
        if self.pressed:
            sx, sy = win32api.GetCursorPos()
            self.drag_points[2:] = [sx, sy]
            self.update_drag_rect()
        return not self.done

    def start_selection(self):
        """Start capturing when hotkeys pressed."""
        sx, sy = win32api.GetCursorPos()
        self.drag_points[0:4] = [sx, sy, sx, sy]
        self.update_drag_rect()
        self.rect[0:2] = [sx, sy]
        self.pressed = True

    def finish_selection(self):
        """Finish selection after releasing hotkeys."""
        sx, sy = win32api.GetCursorPos()
        self.drag_points[2:] = [sx, sy]
        self.update_drag_rect()
        self.rect = self.current_drag_rect.copy()
        self.text = ["..."]
        self.text_size = [self.font.size(self.text[0])]
        self.w = self.text_size[0][0] + 30
        self.h = self.text_size[0][1] + 30
        self.fade = 0.0

        self.selection_counter += 1
        current_id = self.selection_counter

        import threading

        threading.Thread(
            target=self.process_selection,
            args=(self.rect.copy(), current_id),
            daemon=True,
        ).start()

        self.pressed = False

    def on_key_press(self, key):
        """Track key presses to start selection."""
        if key in (keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
            self.key_state.add("ctrl")
        if key in (keyboard.Key.alt_l, keyboard.Key.alt_r):
            self.key_state.add("alt")

        if {"ctrl", "alt"}.issubset(self.key_state) and not self.pressed:
            self.start_selection()
        return not self.done

    def on_key_release(self, key):
        """Track key release to finish selection."""
        if key in (keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
            self.key_state.discard("ctrl")
        if key in (keyboard.Key.alt_l, keyboard.Key.alt_r):
            self.key_state.discard("alt")

        if ("ctrl" not in self.key_state or "alt" not in self.key_state) and self.pressed:
            self.finish_selection()
        return not self.done

    # Main loop ----------------------------------------------------------
    def run(self):
        pygame = self.pygame
        while not self.done:
            self.cursor_position = win32api.GetCursorPos()
            self.time = (self.time + 0.001 * self.delta) % 1
            self.fade = min(self.fade + 0.002 * self.delta, 1.0)
            blink = sin(self.time * 3.14) / 2
            blink_color = (125 + 130 * blink, 125 + 130 * blink, 125 + 130 * blink, 0)

            self._set_blur(not self.pressed and self.text and self.text != ["..."])

            if self.pending_text is not None:
                self.text = self.pending_text
                self.text_size = [self.font.size(t) for t in self.text]
                text_height = sum(s[1] for s in self.text_size)
                text_width = max(s[0] for s in self.text_size)
                self.w = text_width + 20
                self.h = text_height + 20
                Window.set_size(self.w, self.h)
                self.fade = 0.0
                self.pending_text = None

            if not self.pressed:
                Window.set_position(self.cursor_position[0] + 22, self.cursor_position[1] + 24)
                Window.set_size(self.w, self.h)

                if self.text and self.text != ["..."]:
                    total_h = sum(s[1] for s in self.text_size)
                    y = (self.h - total_h) // 2
                    for idx, (line, size) in enumerate(zip(self.text, self.text_size)):
                        surf = self.font.render(line, False, blink_color)
                        surf.set_alpha(int(255 * self.fade))
                        x = (self.w - size[0]) // 2
                        self.screen.blit(surf, (x, y))
                        y += size[1]

                pygame.display.flip()
                self.screen.fill((0, 0, 0, 0))
            else:
                left, top, width, height = self.current_drag_rect

                Window.set_position(left - 1, top - 1)
                Window.set_size(width + 2, height + 2)
                self.screen.fill((0, 0, 0, 0))

                pygame.draw.rect(self.screen, blink_color, (1, 1, width, height), 2)
                pygame.display.flip()

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.done = True

            self.delta = self.clock.tick(60)

        pygame.quit()


def main(argv=None):
    """Entry point when running as a script."""
    import argparse

    parser = argparse.ArgumentParser(description="Translate screen selections")
    parser.add_argument("--debug", action="store_true", help="show captured screenshots using PIL")
    args = parser.parse_args(argv)

    ImageTranslatorApp(debug=args.debug).run()


if __name__ == "__main__":
    main()
