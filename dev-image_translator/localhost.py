import sys
import subprocess
import importlib.util
import os
import signal

# --- Проверка Python версии ---
if sys.version_info < (3, 12):
    sys.exit("❌ Требуется Python 3.12 или новее!")

# --- Установка зависимостей ---
required = [
    "fastapi", "uvicorn", "pillow", "numpy",
    "requests", "openai", "deep-translator", "python-multipart"
]
for pkg in required:
    if importlib.util.find_spec(pkg.replace("-", "_")) is None:
        subprocess.check_call([sys.executable, "-m", "pip", "install", pkg])

# --- Импорты ---
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import JSONResponse
from enum import Enum
from universal_ocr import UniversalOCR, OCREngine
from universal_translator import UniversalTranslator, TranslateEngine

app = FastAPI()

class OCRRequestEngine(str, Enum):
    chatgpt = "chatgpt"
    google_vision = "google_vision"
    ocr_space = "ocr_space"

class TranslateRequestEngine(str, Enum):
    google = "google"
    yandex = "yandex"
    deepl = "deepl"
    deepseek = "deepseek"
    chatgpt = "chatgpt"

@app.post("/ocr/")
async def ocr_image(
    file: UploadFile = File(...),
    engine: OCRRequestEngine = Form(default="chatgpt"),
    api_key_or_creds: str = Form(default="")
):
    try:
        image_bytes = await file.read()
        ocr = UniversalOCR(api_key_or_creds or None, engine=OCREngine(engine))
        result = ocr.extract_text_blocks(image_bytes)
        return {"blocks": result.text_blocks, "words": result.word_boxes}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/translate/")
async def translate_text(
    text: str = Form(...),
    target_lang: str = Form(default="ru"),
    engine: TranslateRequestEngine = Form(default="google"),
    api_key: str = Form(default=""),
    stream: bool = Form(default=False)
):
    try:
        translator = UniversalTranslator(
            target_lang=target_lang,
            engine=TranslateEngine(engine),
            api_key=api_key
        )
        result = "".join(translator.translate(text, stream=True)) if stream else translator.translate(text)
        return {"translated": result}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.api_route("/shutdown/", methods=["POST", "GET"])
async def shutdown():
    pid = os.getpid()
    print(f"🛑 Завершаю процесс PID={pid}")
    os.kill(pid, signal.SIGTERM)
    return {"status": f"Процесс {pid} завершён"}

if __name__ == "__main__":
    import uvicorn
    print("🚀 Запуск сервера на http://127.0.0.1:8000")
    uvicorn.run(app, host="127.0.0.1", port=8000)
