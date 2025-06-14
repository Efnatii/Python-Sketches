"""Utility for translating text selected on the screen.

The module displays a small window following the cursor. When the user selects
a rectangular area with the mouse, its contents are captured, recognized via
OCR and translated. The translated text appears near the cursor.
"""

import sys
import os
from typing import Sequence
from PIL import Image

import ctypes

WINDOWS = sys.platform.startswith("win")

if WINDOWS:
    from pynput import mouse, keyboard
    try:
        import win32gui
        import win32ui
        import win32con
        import win32api
    except ImportError as exc:  # pragma: no cover - platform specific
        raise ImportError(
            "Required Windows dependencies are missing: {}".format(exc)
        ) from exc
else:  # pragma: no cover - platform specific
    raise ImportError(
        "The image_translator module only supports Windows platforms"
    )

from math import sin

import pytesseract

pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

try:
    ctypes.windll.user32.SetProcessDPIAware()
except Exception:
    # Запасной вариант для старых версий Windows или отсутствующего атрибута
    pass

from translate import Translator

class Window:
    """Helper class for controlling the pygame window via the WinAPI."""

    hwnd = None

    @classmethod
    def init(cls, hwnd: int) -> None:
        """Store window handle for further operations."""
        cls.hwnd = hwnd

    @classmethod
    def set_position(cls, x: int, y: int) -> None:
        """Move the window to the given position."""
        win32gui.SetWindowPos(cls.hwnd, win32con.HWND_TOPMOST, x, y, 0, 0, win32con.SWP_NOSIZE)

    @classmethod
    def set_size(cls, w: int, h: int) -> None:
        """Change the window size without moving it."""
        win32gui.SetWindowPos(cls.hwnd, win32con.HWND_TOPMOST, 0, 0, w, h, win32con.SWP_NOMOVE)

    @classmethod
    def make_transparent(
        cls, color: tuple[int, int, int] = (0, 0, 0), alpha: int = 255
    ) -> None:
        """Make the window transparent using the given color.

        ``alpha`` is kept for backward compatibility but the window is always
        set to fully opaque with ``LWA_COLORKEY | LWA_ALPHA`` which allows using
        semi-transparent ``pygame`` surfaces.
        """
        win32gui.SetWindowLong(
            cls.hwnd,
            win32con.GWL_EXSTYLE,
            win32gui.GetWindowLong(cls.hwnd, win32con.GWL_EXSTYLE) | win32con.WS_EX_LAYERED,
        )
        win32gui.SetLayeredWindowAttributes(
            cls.hwnd,
            win32api.RGB(*color),
            alpha,
            win32con.LWA_COLORKEY | win32con.LWA_ALPHA,
        )

    @classmethod
    def enable_blur(cls) -> None:
        """Enable blur behind the window if supported by the system."""
        if not WINDOWS or cls.hwnd is None:
            return
        try:
            dwmapi = ctypes.windll.dwmapi

            class DWM_BLURBEHIND(ctypes.Structure):
                _fields_ = [
                    ("dwFlags", ctypes.c_uint),
                    ("fEnable", ctypes.c_bool),
                    ("hRgnBlur", ctypes.c_void_p),
                    ("fTransitionOnMaximized", ctypes.c_bool),
                ]

            blur = DWM_BLURBEHIND(1, True, None, False)
            dwmapi.DwmEnableBlurBehindWindow(cls.hwnd, ctypes.byref(blur))
        except Exception:
            try:
                class ACCENTPOLICY(ctypes.Structure):
                    _fields_ = [
                        ("AccentState", ctypes.c_int),
                        ("AccentFlags", ctypes.c_int),
                        ("GradientColor", ctypes.c_int),
                        ("AnimationId", ctypes.c_int),
                    ]

                class WINDOWCOMPOSITIONATTRIBDATA(ctypes.Structure):
                    _fields_ = [
                        ("Attribute", ctypes.c_int),
                        ("Data", ctypes.c_void_p),
                        ("SizeOfData", ctypes.c_size_t),
                    ]

                accent = ACCENTPOLICY(3, 0, 0, 0)
                data = WINDOWCOMPOSITIONATTRIBDATA(19, ctypes.byref(accent), ctypes.sizeof(accent))
                ctypes.windll.user32.SetWindowCompositionAttribute(cls.hwnd, ctypes.byref(data))
            except Exception:
                # Игнорируем, если API недоступно
                pass

    @classmethod
    def disable_blur(cls) -> None:
        """Disable blur behind the window."""
        if not WINDOWS or cls.hwnd is None:
            return
        try:
            dwmapi = ctypes.windll.dwmapi

            class DWM_BLURBEHIND(ctypes.Structure):
                _fields_ = [
                    ("dwFlags", ctypes.c_uint),
                    ("fEnable", ctypes.c_bool),
                    ("hRgnBlur", ctypes.c_void_p),
                    ("fTransitionOnMaximized", ctypes.c_bool),
                ]

            blur = DWM_BLURBEHIND(1, False, None, False)
            dwmapi.DwmEnableBlurBehindWindow(cls.hwnd, ctypes.byref(blur))
        except Exception:
            try:
                class ACCENTPOLICY(ctypes.Structure):
                    _fields_ = [
                        ("AccentState", ctypes.c_int),
                        ("AccentFlags", ctypes.c_int),
                        ("GradientColor", ctypes.c_int),
                        ("AnimationId", ctypes.c_int),
                    ]

                class WINDOWCOMPOSITIONATTRIBDATA(ctypes.Structure):
                    _fields_ = [
                        ("Attribute", ctypes.c_int),
                        ("Data", ctypes.c_void_p),
                        ("SizeOfData", ctypes.c_size_t),
                    ]

                accent = ACCENTPOLICY(0, 0, 0, 0)
                data = WINDOWCOMPOSITIONATTRIBDATA(19, ctypes.byref(accent), ctypes.sizeof(accent))
                ctypes.windll.user32.SetWindowCompositionAttribute(cls.hwnd, ctypes.byref(data))
            except Exception:
                pass

class Screenshot:
    """Utility functions for creating screenshots via the WinAPI."""

    @classmethod
    def grab(
        cls,
        rect: Sequence[int],
        bmp_filename: str | None = None,
        hwnd: int = 0,
    ) -> None:
        """Capture a rectangular region of the screen and save it to ``bmp_filename``."""
        if bmp_filename is None:
            bmp_filename = os.path.join(os.path.dirname(__file__), "screenshots", "screenshot.bmp")
        window_dc = win32gui.GetWindowDC(hwnd)
        dc_object = win32ui.CreateDCFromHandle(window_dc)
        compatible_dc = dc_object.CreateCompatibleDC()

        data_bitmap = win32ui.CreateBitmap()
        data_bitmap.CreateCompatibleBitmap(dc_object, rect[2], rect[3])

        compatible_dc.SelectObject(data_bitmap)
        compatible_dc.BitBlt((0, 0), (rect[2], rect[3]), dc_object, (rect[0], rect[1]), win32con.SRCCOPY)

        data_bitmap.SaveBitmapFile(compatible_dc, bmp_filename)

        dc_object.DeleteDC()
        compatible_dc.DeleteDC()
        win32gui.ReleaseDC(hwnd, window_dc)
        win32gui.DeleteObject(data_bitmap.GetHandle())

    @classmethod
    def grab_image(cls, rect: Sequence[int], hwnd: int = 0) -> Image.Image:
        """Return a :class:`PIL.Image` of the selected screen area without saving."""
        window_dc = win32gui.GetWindowDC(hwnd)
        dc_object = win32ui.CreateDCFromHandle(window_dc)
        compatible_dc = dc_object.CreateCompatibleDC()

        data_bitmap = win32ui.CreateBitmap()
        data_bitmap.CreateCompatibleBitmap(dc_object, rect[2], rect[3])

        compatible_dc.SelectObject(data_bitmap)
        compatible_dc.BitBlt((0, 0), (rect[2], rect[3]), dc_object, (rect[0], rect[1]), win32con.SRCCOPY)

        bmp_info = data_bitmap.GetInfo()
        bmp_str = data_bitmap.GetBitmapBits(True)

        dc_object.DeleteDC()
        compatible_dc.DeleteDC()
        win32gui.ReleaseDC(hwnd, window_dc)
        win32gui.DeleteObject(data_bitmap.GetHandle())

        return Image.frombuffer('RGB', (bmp_info['bmWidth'], bmp_info['bmHeight']), bmp_str, 'raw', 'BGRX', 0, 1)

class ImageTranslatorApp:
    """Interactive application for translating selections on the screen."""

    def __init__(self, debug: bool = False) -> None:
        import pygame

        self.debug = debug

        # Текущее состояние
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

        # Настройка Pygame
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
        keyboard.Listener(
            on_press=self.on_key_press, on_release=self.on_key_release
        ).start()
        mouse.Listener(on_move=self.on_move).start()

    def update_drag_rect(self) -> None:
        """Recalculate ``self.current_drag_rect`` from ``self.drag_points``."""
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

    def process_selection(self, selected_rect: Sequence[int], proc_id: int) -> None:
        """Recognize text from ``selected_rect`` and translate it."""
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

    # Обработчики событий -----------------------------------------------------
    def on_move(self, x: int, y: int) -> bool:
        """Track mouse movement during selection.

        ``pynput`` already provides global coordinates, but we additionally
        query the cursor position via ``win32api`` so that start and end points
        are always relative to the entire screen.
        """
        if self.pressed:
            sx, sy = win32api.GetCursorPos()
            self.drag_points[2:] = [sx, sy]
            self.update_drag_rect()
        return not self.done


    def start_selection(self) -> None:
        """Begin a selection when the hotkeys are pressed."""
        sx, sy = win32api.GetCursorPos()
        self.drag_points[0:4] = [sx, sy, sx, sy]
        self.update_drag_rect()
        self.rect[0:2] = [sx, sy]
        self.pressed = True

    def finish_selection(self) -> None:
        """Finish the selection after the hotkeys are released."""
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

    def on_key_press(self, key) -> bool:
        """Handle key presses to start a selection."""
        if key in (keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
            self.key_state.add("ctrl")
        if key in (keyboard.Key.alt_l, keyboard.Key.alt_r):
            self.key_state.add("alt")

        if {"ctrl", "alt"}.issubset(self.key_state) and not self.pressed:
            self.start_selection()
        return not self.done

    def on_key_release(self, key) -> bool:
        """Handle key releases to finish the selection."""
        if key in (keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
            self.key_state.discard("ctrl")
        if key in (keyboard.Key.alt_l, keyboard.Key.alt_r):
            self.key_state.discard("alt")

        if ("ctrl" not in self.key_state or "alt" not in self.key_state) and self.pressed:
            self.finish_selection()
        return not self.done

    # Основной цикл ----------------------------------------------------------
    def run(self) -> None:
        pygame = self.pygame
        while not self.done:
            self.cursor_position = win32api.GetCursorPos()
            self.time = (self.time + 0.001 * self.delta) % 1
            self.fade = min(self.fade + 0.002 * self.delta, 1.0)
            blink = sin(self.time * 3.14) / 2
            blink_color = (125 + 130 * blink, 125 + 130 * blink, 125 + 130 * blink, 0)

            self._set_blur(
                not self.pressed and self.text and self.text != ["..."]
            )

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
                # Отодвигаем окно перевода немного дальше от курсора,
                # чтобы оно не перекрывало его. Ранее смещение было (12, 14);
                # добавляем ещё по 10 пикселей по диагонали.
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

                pygame.draw.rect(
                    self.screen,
                    blink_color,
                    (1, 1, width, height),
                    2,
                )
                pygame.display.flip()

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.done = True

            self.delta = self.clock.tick(60)

        pygame.quit()


def main(argv: Sequence[str] | None = None) -> None:
    """Entry point when executed as a script."""
    import argparse

    parser = argparse.ArgumentParser(description="Translate screen selections")
    parser.add_argument(
        "--debug",
        action="store_true",
        help="show captured screenshots using PIL",
    )
    args = parser.parse_args(argv)

    ImageTranslatorApp(debug=args.debug).run()


if __name__ == "__main__":
    main()
