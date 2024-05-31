from pynput import mouse
from pynput import keyboard
from PIL import Image

import win32gui
import win32ui
import win32con
import win32api

from time import sleep

from math import sin

import pytesseract

pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

from translate import Translator

class Window:
    hwnd = None
    @classmethod
    def init(cls, hwnd):
        cls.hwnd = hwnd

    @classmethod
    def set_position(cls, x, y):
        win32gui.SetWindowPos(cls.hwnd, win32con.HWND_TOPMOST, x, y, 0, 0, win32con.SWP_NOSIZE)

    @classmethod
    def set_size(cls, w, h):
        win32gui.SetWindowPos(cls.hwnd, win32con.HWND_TOPMOST, 0, 0, w, h, win32con.SWP_NOMOVE)

    @classmethod
    def make_transparent(cls, color = (0, 0, 0)):
        win32gui.SetWindowLong(cls.hwnd, win32con.GWL_EXSTYLE,
                           win32gui.GetWindowLong(cls.hwnd, win32con.GWL_EXSTYLE) | win32con.WS_EX_LAYERED)
        win32gui.SetLayeredWindowAttributes(cls.hwnd, win32api.RGB(*color), 0, win32con.LWA_COLORKEY)

class Screenshot:
    @classmethod
    def grab(cls, rect, bmp_filename = r".\screenshots\screenshot.bmp", hwnd = 0):
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

if __name__ == "__main__":
    cursor_position = [0, 0]
    rect = [0, 0, 0, 0]
    x, y, w, h = 0, 0, 0, 0
    done = False
    text = ["..."]
    text_size = 0
    pressed = False
    time = 0
    delta = 0
    translator = Translator(from_lang="en", to_lang="ru")

    import pygame

    pygame.init()
    pygame.font.init()

    screen = pygame.display.set_mode((2000, 2000), pygame.NOFRAME)
    font = pygame.font.SysFont('sans serif', 20)
    clock = pygame.time.Clock()

    text_size = [font.size(text[0])]

    Window.init(pygame.display.get_wm_info()["window"])
    Window.make_transparent()

    Window.set_size(w := text_size[0][0] + 30, h := text_size[0][1] + 30)

    def on_move(_x, _y):
        global cursor_position
        global done
        global pressed
        global x, y, w, h

        if pressed:
            Window.set_size(w := cursor_position[0] - x, h := cursor_position[1] - y)
            screen.fill((0, 0, 0))

        return not done
    def on_click(_x, _y, _button, _pressed):
        global text, text_size
        global cursor_position
        global done
        global pressed
        global x, y, w, h

        if _button == mouse.Button.right:
            if pressed := _pressed:
                rect[0:2] = [_x, _y]
                Window.set_position(x := cursor_position[0], y := cursor_position[1])
                Window.set_size(w := 1, h := 1)
            else:
                rect[2:4] = [_x - rect[0], _y - rect[1]]
                Window.set_size(w := cursor_position[0] - x, h := cursor_position[1] - y)

                Screenshot.grab(rect)
                _raw_text = pytesseract.image_to_string(Image.open(r".\screenshots\screenshot.bmp"))[:-1]
                text = ("(" + _raw_text + ")\n\n" + translator.translate(_raw_text)).split('\n')
                text_size = [font.size(_text) for _text in text]
                w = 0
                h = 0
                for idx in range(len(text)):
                    w = text_size[idx][0] if text_size[idx][0] > w else w
                    h += text_size[idx][1]

                w += 20
                h += 10
                Window.set_size(w, h)

            return not done

    mouse.Listener(on_click=on_click, on_move=on_move).start()

    while not done:
        cursor_position = win32api.GetCursorPos()
        time = (time + 0.001 * delta) % 1
        _blink = sin(time * 3.14) / 2
        _blinked_color = (125 + 130 * _blink, 125 + 130 * _blink, 125 + 130 * _blink, 0)

        if not pressed:
            Window.set_position(cursor_position[0] + 12, cursor_position[1] + 14)

            for idx in range(len(text)):
                screen.blit(font.render(text[idx], False, _blinked_color), (10, 0 + idx * text_size[idx][1]))

            pygame.display.flip()
            screen.fill((0, 0, 0))
        else:
            pygame.draw.rect(screen, _blinked_color, (0, 0, w, h), 1, 0)
            pygame.display.flip()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                done = True

        delta = clock.tick(0)

    pygame.quit()
    quit()
