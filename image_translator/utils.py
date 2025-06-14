"""Utility helpers for the image translator package."""

import ctypes
import sys
import pytesseract

WINDOWS = sys.platform.startswith("win")


def init_dpi_awareness():
    """Set process DPI awareness on Windows to avoid blurry output."""
    if not WINDOWS:
        return
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def configure_tesseract(path=r"C:\\Program Files\\Tesseract-OCR\\tesseract.exe"):
    """Configure pytesseract executable path."""
    pytesseract.pytesseract.tesseract_cmd = path
