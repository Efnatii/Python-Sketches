from pynput import mouse
from PIL import Image

import win32gui
import win32ui
import win32con
import win32api

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

    @classmethod
    def grab_image(cls, rect, hwnd=0):
        """Return a PIL Image of the screen region without writing to disk."""
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

if __name__ == "__main__":
    cursor_position = [0, 0]
    rect = [0, 0, 0, 0]
    x, y, w, h = 0, 0, 0, 0
    done = False
    text = ["..."]
    text_size = 0
    fade = 1.0
    pressed = False
    pending_text = None
    selection_counter = 0
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
        global fade
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
        global fade
        global pending_text
        global selection_counter

        if _button == mouse.Button.right:
            if pressed := _pressed:
                rect[0:2] = [_x, _y]
                Window.set_position(x := cursor_position[0], y := cursor_position[1])
                Window.set_size(w := 1, h := 1)
            else:
                rect[2:4] = [_x - rect[0], _y - rect[1]]

                _w = cursor_position[0] - x
                _h = cursor_position[1] - y
                _x_pos = x
                _y_pos = y
                if _w < 0:
                    _x_pos += _w
                    _w = -_w
                if _h < 0:
                    _y_pos += _h
                    _h = -_h
                Window.set_position(_x_pos, _y_pos)
                Window.set_size(w := _w, h := _h)

                text = ["..."]
                text_size = [font.size(text[0])]
                Window.set_size(text_size[0][0] + 30, text_size[0][1] + 30)
                fade = 0.0

                selection_counter += 1
                current_id = selection_counter

                def process(selected_rect, proc_id=current_id):
                    img = Screenshot.grab_image(selected_rect)
                    _raw_text = pytesseract.image_to_string(img, lang='eng').strip()
                    result = translator.translate(_raw_text).split('\n')
                    if proc_id == selection_counter:
                        global pending_text
                        pending_text = result

                import threading
                threading.Thread(target=process, args=(rect.copy(),), daemon=True).start()

            return not done

    mouse.Listener(on_click=on_click, on_move=on_move).start()

    while not done:
        cursor_position = win32api.GetCursorPos()
        time = (time + 0.001 * delta) % 1
        fade = min(fade + 0.002 * delta, 1.0)
        _blink = sin(time * 3.14) / 2
        _blinked_color = (125 + 130 * _blink, 125 + 130 * _blink, 125 + 130 * _blink, 0)

        if pending_text is not None:
            text = pending_text
            text_size = [font.size(_text) for _text in text]
            w = max(s[0] for s in text_size) + 20
            h = sum(s[1] for s in text_size) + 10
            Window.set_size(w, h)
            fade = 0.0
            pending_text = None

        if not pressed:
            Window.set_position(cursor_position[0] + 12, cursor_position[1] + 14)

            for idx in range(len(text)):
                surf = font.render(text[idx], False, _blinked_color)
                surf.set_alpha(int(255 * fade))
                screen.blit(surf, (10, 0 + idx * text_size[idx][1]))

            pygame.display.flip()
            screen.fill((0, 0, 0))
        else:
            screen.fill((0, 0, 0))
            pygame.draw.rect(screen, _blinked_color, (0, 0, w, h), 2, 0)
            pygame.display.flip()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                done = True

        delta = clock.tick(60)

    pygame.quit()
    quit()
