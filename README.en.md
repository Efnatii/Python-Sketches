## About the project

A small collection of experimental Python scripts. Some of them may be rough but demonstrate interesting ideas.

* **Image Translator** – uses WinAPI to capture a selected screen region, recognizes English text with OCR, translates it into Russian and displays the result on top of other windows.

This file is an English translation of the main [README](README.md).

## Requirements

- Python 3.8 or newer;
- Windows is required for the Image Translator module (it relies on WinAPI);
- packages listed in `requirements.txt`.

Some modules rely on environment variables (see below).

## Installing dependencies

```bash
pip install -r requirements.txt
```

## Usage examples

Image Translator:

```bash
set TESSERACT_CMD=C:\\Program Files\\Tesseract-OCR\\tesseract.exe
python dev-image_translator/image_translator.py
```

Image generation via StabilityAI:

```bash
set _STABILITYAI_API_KEY_1=your_api_key
python dev-stability_ai/_stabilityai_stableimage_generator.py
```

## Environment variables

- `TESSERACT_CMD` – path to the `tesseract.exe` executable used by the *Image Translator* module. Defaults to `C:\Program Files\Tesseract-OCR\tesseract.exe` if not set.
- `_STABILITYAI_API_KEY_1` – API key for the StabilityAI service used by `_stabilityai_stableimage_generator.py`.

## License

The source code is available under the MIT license. See `LICENSE` for details.
