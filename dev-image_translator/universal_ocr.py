import os
import io
import base64
import re
import json
import numpy as np
import requests
from enum import Enum
from typing import List, Any, Union, Optional
from PIL import Image, ImageOps, ImageEnhance, ImageFilter
import openai

try:
    from google.cloud import vision
except ImportError:
    vision = None

class OCREngine(Enum):
    CHATGPT = "chatgpt"
    GOOGLE_VISION = "google_vision"
    OCR_SPACE = "ocr_space"

class OCRResult:
    def __init__(
        self,
        text_blocks: List[dict],                 # [{"text":..., "box":[x0,y0,x1,y1]}, ...]
        word_boxes: Optional[List[List[dict]]] = None  # [[{"text":..., "box":[x0,y0,x1,y1]}, ...], ...]
    ):
        self.text_blocks = text_blocks
        self.word_boxes = word_boxes or [[] for _ in text_blocks]

    def get_word_boxes(self, flat: bool = True):
        """
        Возвращает список координат боксов слов:
            - flat=True: [[x0, y0, x1, y1], ...] — все слова во всех блоках одним списком.
            - flat=False: [[[x0, y0, x1, y1], ...], ...] — список списков по блокам.
        """
        boxes_by_block = [
            [word['box'] for word in block if 'box' in word and word['box'] is not None]
            for block in self.word_boxes
        ]
        if flat:
            return [box for block in boxes_by_block for box in block]
        return boxes_by_block

    @property
    def texts(self):
        return [b['text'] for b in self.text_blocks]

    @property
    def text_boxes(self):
        return [b['box'] for b in self.text_blocks]

class UniversalOCR:
    def __init__(
        self,
        api_key_or_creds=None,
        engine: OCREngine = OCREngine.CHATGPT,
    ):
        self.engine = engine
        match self.engine:
            case OCREngine.CHATGPT:
                self.api_key = api_key_or_creds or os.environ.get("CHATGPT_API_KEY")
                if not self.api_key:
                    raise ValueError("Не указан API-ключ для ChatGPT OCR (CHATGPT_API_KEY или api_key_or_creds).")
                openai.api_key = self.api_key
            case OCREngine.GOOGLE_VISION:
                self.creds_path = api_key_or_creds or os.environ.get("GOOGLE_CREDS_PATH")
                if vision is None:
                    raise ImportError("Установите google-cloud-vision: pip install google-cloud-vision")
                if not self.creds_path:
                    raise ValueError("Укажите GOOGLE_CREDS_PATH или api_key_or_creds с путем к JSON-файлу сервисного аккаунта Google Cloud Vision.")
                os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = self.creds_path
                self.vision_client = vision.ImageAnnotatorClient()
            case OCREngine.OCR_SPACE:
                self.api_key = api_key_or_creds or os.environ.get("OCRSPACE_API_KEY")
                if not self.api_key:
                    raise ValueError("Не указан API-ключ для OCR.space (OCRSPACE_API_KEY или api_key_or_creds).")
            case _:
                raise ValueError(f"Движок {self.engine} не поддерживается.")

    def _preprocess_image_for_engine(self, img: Image.Image, engine: OCREngine) -> Image.Image:
        match engine:
            case OCREngine.GOOGLE_VISION:
                if img.mode != "RGB":
                    img = img.convert("RGB")
                img = ImageOps.autocontrast(img)
                img = img.filter(ImageFilter.SHARPEN)
                return img
            case OCREngine.CHATGPT:
                if img.mode != "RGB":
                    img = img.convert("RGB")
                img = ImageOps.autocontrast(img)
                img = ImageEnhance.Contrast(img).enhance(1.15)
                return img
            case OCREngine.OCR_SPACE:
                if img.mode != "RGB":
                    img = img.convert("RGB")
                img = ImageOps.autocontrast(img)
                return img
            case _:
                return img

    def _load_image(self, input_data: Any) -> Image.Image:
        match input_data:
            case Image.Image():
                return input_data
            case str() if input_data.startswith("http"):
                resp = requests.get(input_data)
                return Image.open(io.BytesIO(resp.content))
            case str():
                return Image.open(input_data)
            case bytes():
                return Image.open(io.BytesIO(input_data))
            case np.ndarray():
                return Image.fromarray(input_data)
            case _:
                raise ValueError("Неподдерживаемый формат входных данных для изображения.")

    def _find_json(self, text):
        matches = list(re.finditer(r'\{[\s\S]*\}', text))
        for m in matches:
            try:
                return json.loads(m.group(0))
            except Exception:
                continue
        raise ValueError("Не удалось найти валидный JSON в ответе ChatGPT.")

    def extract_text_blocks(self, input_data: Any) -> OCRResult:
        img = None
        if self.engine in [OCREngine.CHATGPT, OCREngine.GOOGLE_VISION, OCREngine.OCR_SPACE]:
            img = self._load_image(input_data)
        match self.engine:
            case OCREngine.CHATGPT:
                return self._extract_text_chatgpt(img)
            case OCREngine.GOOGLE_VISION:
                return self._extract_text_google_vision(img)
            case OCREngine.OCR_SPACE:
                return self._extract_text_ocr_space(img)
            case _:
                raise ValueError(f"Движок {self.engine} не поддерживается.")

    def _extract_text_chatgpt(self, img: Image.Image) -> OCRResult:
        proc_img = self._preprocess_image_for_engine(img, OCREngine.CHATGPT)
        buf = io.BytesIO()
        proc_img = proc_img.convert("RGB") if proc_img.mode != "RGB" else proc_img
        proc_img.save(buf, format="JPEG")
        b64img = base64.b64encode(buf.getvalue()).decode()
        prompt = (
            "Распознай текст на изображении. Для каждого блока верни JSON вида: "
            "{blocks: [{text: str, box: [xmin, ymin, xmax, ymax]}]}.\n"
            "В поле text для каждого блока возвращай текст точно с теми переносами строк (\\n), которые есть в изображении. "
            "Не удаляй и не объединяй строки — полностью сохраняй структуру. "
            "box — координаты прямоугольника блока в пикселях изображения ([xmin, ymin, xmax, ymax])."
        )
        response = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64img}"}}
                    ]
                }
            ],
            max_tokens=2048,
            temperature=0
        )
        content = response.choices[0].message.content
        text_blocks = []
        word_boxes = []
        try:
            obj = self._find_json(content)
            for block in obj.get("blocks", []):
                text_blocks.append({
                    "text": block.get("text", ""),
                    "box": block.get("box") if isinstance(block.get("box"), list) else None
                })
                # ChatGPT пока не возвращает word_boxes — просто пустой массив
                word_boxes.append([])
        except Exception as e:
            print("Ошибка при парсинге ответа:", e)
        return OCRResult(text_blocks, word_boxes)

    def _extract_text_google_vision(self, img: Image.Image) -> OCRResult:
        proc_img = self._preprocess_image_for_engine(img, OCREngine.GOOGLE_VISION)
        buf = io.BytesIO()
        proc_img = proc_img.convert("RGB") if proc_img.mode != "RGB" else proc_img
        proc_img.save(buf, format="PNG")
        content = buf.getvalue()
        image = vision.Image(content=content)
        response = self.vision_client.document_text_detection(image=image)
        if response.error.message:
            raise Exception(f'Google Vision API error: {response.error.message}')

        blocks_with_coords = []
        for page in response.full_text_annotation.pages:
            for block in page.blocks:
                xs = [v.x for v in block.bounding_box.vertices]
                ys = [v.y for v in block.bounding_box.vertices]
                xmin, xmax = min(xs), max(xs)
                ymin, ymax = min(ys), max(ys)
                blocks_with_coords.append((block, [xmin, ymin, xmax, ymax], ymin, xmin))
        blocks_with_coords.sort(key=lambda tup: (tup[2], tup[3]))

        text_blocks = []
        word_boxes = []
        for block, box, *_ in blocks_with_coords:
            block_lines = []
            words_info = []
            for paragraph in block.paragraphs:
                para_line = ""
                for word in paragraph.words:
                    word_text = ""
                    xs = [v.x for v in word.bounding_box.vertices]
                    ys = [v.y for v in word.bounding_box.vertices]
                    word_box = [min(xs), min(ys), max(xs), max(ys)]
                    words_info.append({"text": ''.join([s.text for s in word.symbols]), "box": word_box})

                    # Собираем слово по символам, обрабатывая detected_break
                    for idx, symbol in enumerate(word.symbols):
                        word_text += symbol.text
                        # detected_break всегда стоит на последнем символе слова!
                        if hasattr(symbol, 'property') and symbol.property and symbol.property.detected_break:
                            br = symbol.property.detected_break
                            if br.type == 1:  # SPACE
                                word_text += ' '
                            elif br.type == 3:  # LINE_BREAK
                                word_text += '\n'
                    para_line += word_text
                block_lines.append(para_line.strip())
            # Собираем весь текст блока
            block_text = "\n".join([line for line in block_lines if line]).strip()
            if block_text:
                text_blocks.append({"text": block_text, "box": box})
                word_boxes.append(words_info)
        if not text_blocks and response.full_text_annotation.text:
            text_blocks = [{"text": response.full_text_annotation.text.strip(), "box": None}]
            word_boxes = [[]]
        return OCRResult(text_blocks, word_boxes)

    def _extract_text_ocr_space(self, img: Image.Image) -> OCRResult:
        proc_img = self._preprocess_image_for_engine(img, OCREngine.OCR_SPACE)
        # --- Сжатие до 1 МБ ---
        buf = io.BytesIO()
        quality = 90
        while True:
            buf.seek(0)
            buf.truncate()
            proc_img.save(buf, format="JPEG", quality=quality, optimize=True)
            if buf.tell() <= 1024 * 1024 or quality < 30:
                break
            quality -= 10
        buf.seek(0)
        url = 'https://api.ocr.space/parse/image'
        files = {'file': ('image.jpg', buf, 'image/jpeg')}
        payload = {
            'apikey': self.api_key,
            'language': 'auto',
            'isOverlayRequired': True,
            'OCREngine': 2
        }
        resp = requests.post(url, files=files, data=payload, timeout=120)
        try:
            result = resp.json()
        except Exception:
            raise Exception(f"OCR.space: не удалось декодировать ответ. RAW response: {resp.text[:500]}")
        if not isinstance(result, dict):
            raise Exception(f"OCR.space: неверный ответ: {resp.text[:500]}")
        if result.get("IsErroredOnProcessing") and result.get("ErrorMessage"):
            raise Exception(f"OCR.space: {result['ErrorMessage']}")
        text_blocks, word_boxes = [], []
        try:
            parsed = result.get("ParsedResults", [])[0]
            lines = parsed.get("TextOverlay", {}).get("Lines", [])
            if not lines:
                text = parsed.get("ParsedText", "")
                if text:
                    text_blocks.append({"text": text, "box": None})
                    word_boxes.append([])
            else:
                merged_blocks = []
                for line in lines:
                    words = line.get("Words", [])
                    if not words:
                        continue
                    xs = [w["Left"] for w in words] + [w["Left"] + w["Width"] for w in words]
                    ys = [w["Top"] for w in words] + [w["Top"] + w["Height"] for w in words]
                    xmin, xmax = min(xs), max(xs)
                    ymin, ymax = min(ys), max(ys)
                    words_info = [
                        {"text": w.get("WordText", ""), "box": [
                            w["Left"], w["Top"],
                            w["Left"] + w["Width"], w["Top"] + w["Height"]
                        ]} for w in words
                    ]
                    text = " ".join([w.get("WordText", "") for w in words])
                    merged_blocks.append({
                        "text": text,
                        "box": [xmin, ymin, xmax, ymax],
                        "words": words_info
                    })
                # Сортировка по Y, потом по X
                merged_blocks.sort(key=lambda b: (b["box"][1], b["box"][0]))
                def is_close(b1, b2, x_thresh=40, y_thresh=30):
                    horz = not (b1[2] < b2[0] or b2[2] < b1[0])
                    vert = abs(b2[1] - b1[3]) < y_thresh or abs(b1[1] - b2[3]) < y_thresh
                    return horz and vert
                merged = []
                for block in merged_blocks:
                    if not merged:
                        merged.append(block)
                        continue
                    last = merged[-1]
                    if is_close(last["box"], block["box"]):
                        last["text"] += "\n" + block["text"]
                        last["box"] = [
                            min(last["box"][0], block["box"][0]),
                            min(last["box"][1], block["box"][1]),
                            max(last["box"][2], block["box"][2]),
                            max(last["box"][3], block["box"][3]),
                        ]
                        last["words"].extend(block["words"])
                    else:
                        merged.append(block)
                for block in merged:
                    text_blocks.append({"text": block["text"], "box": block["box"]})
                    word_boxes.append(block["words"])
        except Exception as e:
            raise Exception(f"OCR.space: ошибка парсинга ответа: {e}, RAW response: {resp.text[:500]}")
        return OCRResult(text_blocks, word_boxes)

# ----------- Пример использования ----------- #
if __name__ == "__main__":
    print("\n--- OCR.space OCR ---")
    ocr_ocrspace = UniversalOCR(
        engine=OCREngine.OCR_SPACE
    )
    try:
        res = ocr_ocrspace.extract_text_blocks("ocr_test_image.jpg")
        for i, (block, words) in enumerate(zip(res.text_blocks, res.word_boxes)):
            print(f"--- Блок {i} ---\n{block['text']}")
            print("Bounding Box:", block['box'])
            print("Word boxes:", words)
    except Exception as e:
        print("Ошибка:", e)

    print("\n--- Google Cloud Vision OCR ---")
    ocr_vision = UniversalOCR(
        engine=OCREngine.GOOGLE_VISION
    )
    try:
        res = ocr_vision.extract_text_blocks("ocr_test_image_nsfw.png")
        for i, (block, words) in enumerate(zip(res.text_blocks, res.word_boxes)):
            print(f"--- Блок {i} ---\n{block['text']}")
            print("Bounding Box:", block['box'])
            print("Word boxes:", words)
    except Exception as e:
        print("Ошибка:", e)

    print("\n--- ChatGPT OCR ---")
    ocr_gpt = UniversalOCR(
        engine=OCREngine.CHATGPT
    )
    try:
        res = ocr_gpt.extract_text_blocks("ocr_test_image.jpg")
        for i, (block, words) in enumerate(zip(res.text_blocks, res.word_boxes)):
            print(f"--- Блок {i} ---\n{block['text']}")
            print("Bounding Box:", block['box'])
            print("Word boxes:", words)
    except Exception as e:
        print("Ошибка:", e)
