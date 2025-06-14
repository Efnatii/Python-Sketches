import importlib.util
import os
import sys
import types

import pytest


def load_module(monkeypatch):
    # Pretend to be on Windows
    monkeypatch.setattr(sys, "platform", "win32", raising=False)

    # Provide stub modules required for import
    stubs = types.SimpleNamespace()
    pynput = types.ModuleType("pynput")
    pynput.mouse = stubs
    pynput.keyboard = stubs
    monkeypatch.setitem(sys.modules, "pynput", pynput)
    monkeypatch.setitem(sys.modules, "pynput.mouse", stubs)
    monkeypatch.setitem(sys.modules, "pynput.keyboard", stubs)
    for mod in ["win32gui", "win32ui", "win32con", "win32api"]:
        monkeypatch.setitem(sys.modules, mod, stubs)

    spec = importlib.util.spec_from_file_location(
        "image_translator",
        os.path.join(os.path.dirname(__file__), "..", "dev-image_translator", "image_translator.py"),
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_tesseract_path_argument(monkeypatch, tmp_path):
    module = load_module(monkeypatch)
    captured = {}

    class DummyApp:
        def __init__(self, debug=False):
            captured["debug"] = debug
        def run(self):
            captured["run"] = True
    monkeypatch.setattr(module, "ImageTranslatorApp", DummyApp)

    path = tmp_path / "tess.exe"
    module.main(["--tesseract-path", str(path)])

    assert module.pytesseract.pytesseract.tesseract_cmd == str(path)
    assert captured.get("run")
