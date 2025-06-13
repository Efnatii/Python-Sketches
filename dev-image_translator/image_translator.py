"""\
Утилита для перевода текста, выделяемого на экране.

Модуль предоставляет небольшое окно, следующее за курсором. Когда
пользователь правой кнопкой мыши выделяет прямоугольную область,
её содержимое захватывается, распознаётся через OCR и переводится.
Переведённый текст отображается рядом с курсором.
"""

import sys
import os
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
    """Вспомогательный класс для управления окном pygame через WinAPI."""

    hwnd = None

    @classmethod
    def init(cls, hwnd):
        """Сохраняет дескриптор окна для последующих операций."""
        cls.hwnd = hwnd

    @classmethod
    def set_position(cls, x, y):
        """Перемещает окно в указанную позицию."""
        win32gui.SetWindowPos(cls.hwnd, win32con.HWND_TOPMOST, x, y, 0, 0, win32con.SWP_NOSIZE)

    @classmethod
    def set_size(cls, w, h):
        """Изменяет размер окна без перемещения."""
        win32gui.SetWindowPos(cls.hwnd, win32con.HWND_TOPMOST, 0, 0, w, h, win32con.SWP_NOMOVE)

    @classmethod
    def make_transparent(cls, color=(0, 0, 0), alpha=255):
        """Делает окно прозрачным по заданному цвету.

        ``alpha`` оставлен для обратной совместимости, но используется
        только маска цвета ``LWA_COLORKEY``. Полупрозрачность обеспечивается
        через :func:`UpdateLayeredWindow`.
        """
        win32gui.SetWindowLong(
            cls.hwnd,
            win32con.GWL_EXSTYLE,
            win32gui.GetWindowLong(cls.hwnd, win32con.GWL_EXSTYLE) | win32con.WS_EX_LAYERED,
        )
        win32gui.SetLayeredWindowAttributes(
            cls.hwnd,
            win32api.RGB(*color),
            0,
            win32con.LWA_COLORKEY,
        )


class LayeredWindow(Window):
    """Обновление содержимого окна через ``UpdateLayeredWindow``."""

    @classmethod
    def init(cls, hwnd):
        cls.hwnd = hwnd

    @classmethod
    def update(cls, surface):
        import pygame

        width, height = surface.get_size()
        data = pygame.image.tostring(surface, "BGRA")

        hdc_screen = win32gui.GetDC(0)
        mem_dc = win32gui.CreateCompatibleDC(hdc_screen)

        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [
                ("biSize", ctypes.c_uint32),
                ("biWidth", ctypes.c_long),
                ("biHeight", ctypes.c_long),
                ("biPlanes", ctypes.c_ushort),
                ("biBitCount", ctypes.c_ushort),
                ("biCompression", ctypes.c_uint32),
                ("biSizeImage", ctypes.c_uint32),
                ("biXPelsPerMeter", ctypes.c_long),
                ("biYPelsPerMeter", ctypes.c_long),
                ("biClrUsed", ctypes.c_uint32),
                ("biClrImportant", ctypes.c_uint32),
            ]

        class BITMAPINFO(ctypes.Structure):
            _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", ctypes.c_uint32 * 1)]

        class SIZE(ctypes.Structure):
            _fields_ = [("cx", ctypes.c_long), ("cy", ctypes.c_long)]

        class POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

        class BLENDFUNCTION(ctypes.Structure):
            _fields_ = [
                ("BlendOp", ctypes.c_byte),
                ("BlendFlags", ctypes.c_byte),
                ("SourceConstantAlpha", ctypes.c_byte),
                ("AlphaFormat", ctypes.c_byte),
            ]

        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = width
        bmi.bmiHeader.biHeight = -height  # top-down DIB
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = win32con.BI_RGB
        bmi.bmiHeader.biSizeImage = len(data)

        bits = ctypes.c_void_p()
        hbitmap = ctypes.windll.gdi32.CreateDIBSection(
            mem_dc, ctypes.byref(bmi), win32con.DIB_RGB_COLORS, ctypes.byref(bits), 0, 0
        )
        ctypes.memmove(bits, data, len(data))
        old_bmp = win32gui.SelectObject(mem_dc, hbitmap)

        blend = BLENDFUNCTION()
        blend.BlendOp = win32con.AC_SRC_OVER
        blend.BlendFlags = 0
        blend.SourceConstantAlpha = 255
        blend.AlphaFormat = win32con.AC_SRC_ALPHA

        size = SIZE(width, height)
        src_pt = POINT(0, 0)

        ctypes.windll.user32.UpdateLayeredWindow(
            cls.hwnd,
            0,
            None,
            ctypes.byref(size),
            mem_dc,
            ctypes.byref(src_pt),
            0,
            ctypes.byref(blend),
            win32con.ULW_ALPHA,
        )

        win32gui.SelectObject(mem_dc, old_bmp)
        win32gui.DeleteObject(hbitmap)
        win32gui.DeleteDC(mem_dc)
        win32gui.ReleaseDC(0, hdc_screen)

class Screenshot:
    """Функции для создания скриншотов через WinAPI."""

    @classmethod
    def grab(cls, rect, bmp_filename=None, hwnd=0):
        """Захватывает прямоугольную область экрана и сохраняет её в ``bmp_filename``."""
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
    def grab_image(cls, rect, hwnd=0):
        """Возвращает :class:`PIL.Image` выбранной области экрана без записи на диск."""
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
    """Интерактивное приложение для перевода выделений на экране."""

    def __init__(self, debug=False):
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
        LayeredWindow.init(Window.hwnd)
        Window.set_size(self.text_size[0][0] + 30, self.text_size[0][1] + 30)

        self.key_state = set()
        keyboard.Listener(
            on_press=self.on_key_press, on_release=self.on_key_release
        ).start()
        mouse.Listener(on_move=self.on_move).start()

    def update_drag_rect(self):
        """Пересчитать текущий прямоугольник выделения на основе ``self.drag_points``."""
        x1, y1, x2, y2 = self.drag_points
        self.current_drag_rect = [min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1)]

    def process_selection(self, selected_rect, proc_id):
        """Распознаёт текст из ``selected_rect`` и переводит его."""
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
    def on_move(self, x, y):
        """Отслеживать перемещение курсора во время выделения.

        ``pynput`` уже отдаёт глобальные координаты, но мы дополнительно
        запрашиваем положение курсора через ``win32api``, чтобы начальная и
        конечная точки всегда были относительно всего экрана, независимо
        от положения окна.
        """
        if self.pressed:
            sx, sy = win32api.GetCursorPos()
            self.drag_points[2:] = [sx, sy]
            self.update_drag_rect()
        return not self.done


    def start_selection(self):
        """Начать выделение при нажатии горячих клавиш."""
        sx, sy = win32api.GetCursorPos()
        self.drag_points[0:4] = [sx, sy, sx, sy]
        self.update_drag_rect()
        self.rect[0:2] = [sx, sy]
        self.pressed = True

    def finish_selection(self):
        """Завершить выделение после отпускания горячих клавиш."""
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
        """Отслеживать нажатия клавиш для запуска выделения."""
        if key in (keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
            self.key_state.add("ctrl")
        if key in (keyboard.Key.alt_l, keyboard.Key.alt_r):
            self.key_state.add("alt")

        if {"ctrl", "alt"}.issubset(self.key_state) and not self.pressed:
            self.start_selection()
        return not self.done

    def on_key_release(self, key):
        """Отслеживать отпускание клавиш для завершения выделения."""
        if key in (keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
            self.key_state.discard("ctrl")
        if key in (keyboard.Key.alt_l, keyboard.Key.alt_r):
            self.key_state.discard("alt")

        if ("ctrl" not in self.key_state or "alt" not in self.key_state) and self.pressed:
            self.finish_selection()
        return not self.done

    # Основной цикл ----------------------------------------------------------
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

                surface_to_update = self.screen.subsurface((0, 0, self.w, self.h))
                surface_to_update.fill((0, 0, 0, 0))

                if self.text and self.text != ["..."]:
                    bg = self.pygame.Surface((self.w, self.h), self.pygame.SRCALPHA)
                    bg.fill((32, 32, 32, int(200 * self.fade)))
                    surface_to_update.blit(bg, (0, 0))

                    total_h = sum(s[1] for s in self.text_size)
                    y = (self.h - total_h) // 2
                    for idx, (line, size) in enumerate(zip(self.text, self.text_size)):
                        surf = self.font.render(line, False, blink_color)
                        surf.set_alpha(int(255 * self.fade))
                        x = (self.w - size[0]) // 2
                        surface_to_update.blit(surf, (x, y))
                        y += size[1]

                LayeredWindow.update(surface_to_update)
            else:
                left, top, width, height = self.current_drag_rect

                Window.set_position(left - 1, top - 1)
                Window.set_size(width + 2, height + 2)
                surface_to_update = self.screen.subsurface((0, 0, width + 2, height + 2))
                surface_to_update.fill((0, 0, 0, 0))

                pygame.draw.rect(
                    surface_to_update,
                    blink_color,
                    (1, 1, width, height),
                    2,
                )
                LayeredWindow.update(surface_to_update)

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.done = True

            self.delta = self.clock.tick(60)

        pygame.quit()


def main(argv=None):
    """Точка входа при запуске как скрипта."""
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
