"""Utility for translating text from screen selections.

The module provides a small window that follows the cursor. When the user
selects a rectangular region with the right mouse button, the contents of the
region are captured, recognized via OCR and translated. The translated text is
displayed near the cursor.
"""

from pynput import mouse
from PIL import Image

import ctypes

import win32gui
import win32ui
import win32con
import win32api

from math import sin

import pytesseract

pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

try:
    ctypes.windll.user32.SetProcessDPIAware()
except Exception:
    # Fallback for older Windows versions or missing attribute
    pass

from translate import Translator

class Window:
    """Helper for manipulating the pygame window using WinAPI."""

    hwnd = None

    @classmethod
    def init(cls, hwnd):
        """Store window handle for further operations."""
        cls.hwnd = hwnd

    @classmethod
    def set_position(cls, x, y):
        """Move the window to the specified position."""
        win32gui.SetWindowPos(cls.hwnd, win32con.HWND_TOPMOST, x, y, 0, 0, win32con.SWP_NOSIZE)

    @classmethod
    def set_size(cls, w, h):
        """Resize the window without moving it."""
        win32gui.SetWindowPos(cls.hwnd, win32con.HWND_TOPMOST, 0, 0, w, h, win32con.SWP_NOMOVE)

    @classmethod
    def make_transparent(cls, color=(0, 0, 0)):
        """Make the window transparent for a specific color key."""
        win32gui.SetWindowLong(
            cls.hwnd,
            win32con.GWL_EXSTYLE,
            win32gui.GetWindowLong(cls.hwnd, win32con.GWL_EXSTYLE) | win32con.WS_EX_LAYERED,
        )
        win32gui.SetLayeredWindowAttributes(cls.hwnd, win32api.RGB(*color), 0, win32con.LWA_COLORKEY)

class Screenshot:
    """Screenshot utilities using WinAPI."""

    @classmethod
    def grab(cls, rect, bmp_filename=r".\screenshots\screenshot.bmp", hwnd=0):
        """Capture a rectangular region of the screen and save it to ``bmp_filename``."""
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
    def grab_image(cls, rect, hwnd=0):
        """Return a :class:`PIL.Image` of the screen region without writing to disk."""
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
    """Interactive application for translating screen selections."""

    def __init__(self, debug=False):
        import pygame

        self.debug = debug

        # Runtime state
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
        self.screen = pygame.display.set_mode((2000, 2000), pygame.NOFRAME)
        self.font = pygame.font.SysFont("sans serif", 20)
        self.clock = pygame.time.Clock()

        self.text_size = [self.font.size(self.text[0])]

        Window.init(pygame.display.get_wm_info()["window"])
        Window.make_transparent()
        Window.set_size(self.text_size[0][0] + 30, self.text_size[0][1] + 30)

        mouse.Listener(on_click=self.on_click, on_move=self.on_move).start()

    def update_drag_rect(self):
        """Recalculate the current drag rectangle based on ``self.drag_points``."""
        x1, y1, x2, y2 = self.drag_points
        self.current_drag_rect = [min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1)]

    def process_selection(self, selected_rect, proc_id):
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

    # Event handlers -----------------------------------------------------
    def on_move(self, x, y):
        """Track cursor movement while dragging.

        ``pynput`` already provides global coordinates, but we explicitly
        query the current cursor position via ``win32api`` so that the start
        and end points are always relative to the entire screen, regardless of
        the window location.
        """
        if self.pressed:
            sx, sy = win32api.GetCursorPos()
            self.drag_points[2:] = [sx, sy]
            self.update_drag_rect()
        return not self.done

    def on_click(self, x, y, button, pressed):
        """Handle mouse button events.

        The incoming coordinates from ``pynput`` may already be global, but we
        re-fetch them using ``win32api.GetCursorPos`` so that the selection is
        based on absolute screen coordinates.
        """
        if button != mouse.Button.right:
            return not self.done

        sx, sy = win32api.GetCursorPos()

        if pressed:
            self.drag_points[0:4] = [sx, sy, sx, sy]
            self.update_drag_rect()
            self.rect[0:2] = [sx, sy]
            self.pressed = True
        else:
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

            if self.pending_text is not None:
                self.text = self.pending_text
                self.text_size = [self.font.size(t) for t in self.text]
                self.w = max(s[0] for s in self.text_size) + 20
                self.h = sum(s[1] for s in self.text_size) + 10
                Window.set_size(self.w, self.h)
                self.fade = 0.0
                self.pending_text = None

            if not self.pressed:
                Window.set_position(self.cursor_position[0] + 12, self.cursor_position[1] + 14)
                Window.set_size(self.w, self.h)

                for idx, line in enumerate(self.text):
                    surf = self.font.render(line, False, blink_color)
                    surf.set_alpha(int(255 * self.fade))
                    self.screen.blit(surf, (10, idx * self.text_size[idx][1]))

                pygame.display.flip()
                self.screen.fill((0, 0, 0))
            else:
                left, top, width, height = self.current_drag_rect

                Window.set_position(left - 1, top - 1)
                Window.set_size(width + 2, height + 2)
                self.screen.fill((0, 0, 0))

                start_x, start_y, end_x, end_y = self.drag_points
                sx = start_x - (left - 1)
                sy = start_y - (top - 1)
                ex = end_x - (left - 1)
                ey = end_y - (top - 1)
                points = [(sx, sy), (ex, sy), (ex, ey), (sx, ey)]
                pygame.draw.lines(self.screen, blink_color, True, points, 2)
                pygame.display.flip()

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.done = True

            self.delta = self.clock.tick(60)

        pygame.quit()


def main(argv=None):
    """Entry point for running as a script."""
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
