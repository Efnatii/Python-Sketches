"""Helper classes for capturing screenshots and manipulating window properties."""

import ctypes
import os
import sys
from PIL import Image

WINDOWS = sys.platform.startswith("win")

if WINDOWS:
    try:
        import win32gui
        import win32ui
        import win32con
        import win32api
    except ImportError as exc:  # pragma: no cover - platform specific
        raise ImportError(
            f"Required Windows dependencies are missing: {exc}"
        ) from exc
else:  # pragma: no cover - platform specific
    raise ImportError("The image_translator package only supports Windows platforms")


class Window:
    """Utility wrapper around WinAPI window manipulation methods."""

    hwnd = None

    @classmethod
    def init(cls, hwnd):
        """Store the window handle for later operations."""
        cls.hwnd = hwnd

    @classmethod
    def set_position(cls, x, y):
        """Move the window to the given coordinates."""
        win32gui.SetWindowPos(cls.hwnd, win32con.HWND_TOPMOST, x, y, 0, 0, win32con.SWP_NOSIZE)

    @classmethod
    def set_size(cls, w, h):
        """Resize the window without moving it."""
        win32gui.SetWindowPos(cls.hwnd, win32con.HWND_TOPMOST, 0, 0, w, h, win32con.SWP_NOMOVE)

    @classmethod
    def make_transparent(cls, color=(0, 0, 0), alpha=255):
        """Make the window transparent for the given color."""
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
    def enable_blur(cls):
        """Enable blur behind the window if the OS supports it."""
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
                pass

    @classmethod
    def disable_blur(cls):
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
    """Functions to capture screen areas using WinAPI."""

    @classmethod
    def grab(cls, rect, bmp_filename=None, hwnd=0):
        """Capture a rectangle of the screen and save it to ``bmp_filename``."""
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
        """Return :class:`PIL.Image` of the selected area without saving."""
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
