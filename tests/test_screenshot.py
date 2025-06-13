import os
import sys
import tempfile
from pathlib import Path
import unittest
import importlib.util

MODULE_PATH = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__), "..", "dev-image_translator", "image_translator.py"
    )
)

spec = importlib.util.spec_from_file_location('image_translator', MODULE_PATH)
image_translator = importlib.util.module_from_spec(spec)

try:
    spec.loader.exec_module(image_translator)
    Screenshot = image_translator.Screenshot
    AVAILABLE = True
except Exception:
    AVAILABLE = False
    Screenshot = None

class TestScreenshot(unittest.TestCase):
    @unittest.skipUnless(
        sys.platform.startswith('win') and AVAILABLE,
        'Screenshot functionality not available',
    )
    def test_grab_creates_file(self):
        tmp_file = Path(tempfile.gettempdir()) / 'test_screenshot.bmp'
        if tmp_file.exists():
            tmp_file.unlink()
        try:
            Screenshot.grab((0, 0, 10, 10), tmp_file)
            self.assertTrue(tmp_file.exists())
        finally:
            if tmp_file.exists():
                tmp_file.unlink()

if __name__ == '__main__':
    unittest.main()
