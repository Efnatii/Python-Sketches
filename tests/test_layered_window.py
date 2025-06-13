import os
import importlib.util
import sys
import types
import ctypes
from unittest import mock, TestCase

MODULE_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', 'dev-image_translator', 'image_translator.py')
)

def load_image_translator():
    dummy_win32gui = types.ModuleType('win32gui')
    dummy_win32gui.GetDC = mock.Mock(return_value='hdc')
    dummy_win32gui.CreateCompatibleDC = mock.Mock(return_value='mem_dc')
    dummy_win32gui.SelectObject = mock.Mock(side_effect=['old_bmp', None])
    dummy_win32gui.DeleteObject = mock.Mock()
    dummy_win32gui.DeleteDC = mock.Mock()
    dummy_win32gui.ReleaseDC = mock.Mock()
    dummy_win32ui = types.ModuleType('win32ui')
    dummy_win32con = types.ModuleType('win32con')
    for name in ['HWND_TOPMOST', 'SWP_NOSIZE', 'SWP_NOMOVE', 'GWL_EXSTYLE',
                 'WS_EX_LAYERED', 'LWA_COLORKEY', 'BI_RGB', 'DIB_RGB_COLORS',
                 'AC_SRC_OVER', 'AC_SRC_ALPHA', 'ULW_ALPHA', 'SRCCOPY']:
        setattr(dummy_win32con, name, 0)
    dummy_win32api = types.ModuleType('win32api')
    dummy_win32api.RGB = lambda r, g, b: (r, g, b)
    dummy_win32api.GetCursorPos = mock.Mock(return_value=(0, 0))
    translate_mod = types.ModuleType('translate')
    class DummyTranslator:
        def __init__(self, *args, **kwargs):
            pass
        def translate(self, text):
            return text
    translate_mod.Translator = DummyTranslator
    pytess = types.ModuleType('pytesseract')
    pytess_sub = types.ModuleType('pytesseract.pytesseract')
    pytess_sub.image_to_string = mock.Mock(return_value='dummy')
    pytess.pytesseract = pytess_sub
    pytess.image_to_string = pytess_sub.image_to_string
    pil = types.ModuleType('PIL')
    pil_image = types.ModuleType('PIL.Image')
    pil.Image = pil_image
    pynput = types.ModuleType('pynput')
    pynput_mouse = types.ModuleType('pynput.mouse')
    pynput_keyboard = types.ModuleType('pynput.keyboard')
    pynput.mouse = pynput_mouse
    pynput.keyboard = pynput_keyboard
    modules = {
        'win32gui': dummy_win32gui,
        'win32ui': dummy_win32ui,
        'win32con': dummy_win32con,
        'win32api': dummy_win32api,
        'translate': translate_mod,
        'pytesseract': pytess,
        'pytesseract.pytesseract': pytess_sub,
        'PIL': pil,
        'PIL.Image': pil_image,
        'pynput': pynput,
        'pynput.mouse': pynput_mouse,
        'pynput.keyboard': pynput_keyboard,
    }
    patcher = mock.patch.dict(sys.modules, modules)
    patcher.start()
    windll_stub = types.SimpleNamespace(
        user32=types.SimpleNamespace(SetProcessDPIAware=lambda: None, UpdateLayeredWindow=mock.Mock()),
        gdi32=types.SimpleNamespace(CreateDIBSection=mock.Mock(return_value=1))
    )
    orig_windll = getattr(ctypes, 'windll', None)
    ctypes.windll = windll_stub
    spec = importlib.util.spec_from_file_location('image_translator', MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.ctypes.memmove = lambda *args, **kwargs: None
    return module, modules, patcher, orig_windll, windll_stub

class LayeredWindowTests(TestCase):
    def setUp(self):
        self.module, self.modules, self.patcher, self.orig_windll, self.windll = load_image_translator()

    def tearDown(self):
        self.patcher.stop()
        if self.orig_windll is not None:
            ctypes.windll = self.orig_windll
        else:
            delattr(ctypes, 'windll')

    def test_update_releases_resources(self):
        pygame_mod = types.ModuleType('pygame')
        pygame_mod.image = types.SimpleNamespace(tostring=mock.Mock(return_value=b'x'*16))
        with mock.patch.dict(sys.modules, {'pygame': pygame_mod}):
            surf = mock.Mock()
            surf.get_size.return_value = (2, 2)
            self.module.LayeredWindow.init(10)
            self.module.LayeredWindow.update(surf)
        gui = self.modules['win32gui']
        gui.GetDC.assert_called_with(0)
        gui.CreateCompatibleDC.assert_called_with('hdc')
        self.assertEqual(gui.SelectObject.call_count, 2)
        gui.DeleteObject.assert_called()
        gui.DeleteDC.assert_called_with('mem_dc')
        gui.ReleaseDC.assert_called_with(0, 'hdc')
        self.assertEqual(self.windll.user32.UpdateLayeredWindow.call_count, 1)

class ProcessSelectionTests(TestCase):
    def setUp(self):
        self.module, self.modules, self.patcher, self.orig_windll, self.windll = load_image_translator()

    def tearDown(self):
        self.patcher.stop()
        if self.orig_windll is not None:
            ctypes.windll = self.orig_windll
        else:
            delattr(ctypes, 'windll')

    def test_process_selection_uses_translator(self):
        dummy_img = object()
        with mock.patch.object(self.module, 'Screenshot') as sc, \
             mock.patch.object(self.module.pytesseract, 'image_to_string', return_value='hello') as itos:
            sc.grab_image.return_value = dummy_img
            app = self.module.ImageTranslatorApp.__new__(self.module.ImageTranslatorApp)
            app.debug = False
            app.pending_text = None
            app.selection_counter = 5
            app.translator = mock.Mock()
            app.translator.translate.return_value = 'привет\nмир'
            app.process_selection([1,2,3,4], 5)
            sc.grab_image.assert_called_with([1,2,3,4])
            itos.assert_called_with(dummy_img, lang='eng')
            app.translator.translate.assert_called_with('hello')
            self.assertEqual(app.pending_text, ['привет', 'мир'])

