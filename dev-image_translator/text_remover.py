import cv2
import numpy as np
from typing import Any, List, Optional, Union
from PIL import Image, ImageDraw
import io
import os
from enum import Enum

try:
    from skimage.restoration import inpaint as sk_inpaint
except ImportError:
    sk_inpaint = None

class TextRemoverEngine(Enum):
    OPENCV = "opencv"
    SCIKIT = "scikit"

class TextRemover:
    def __init__(
        self,
        method: str = "telea",
        inpaint_radius: int = 7,
        engine: TextRemoverEngine = TextRemoverEngine.OPENCV,
    ):
        self.engine = engine
        self.radius = inpaint_radius

        match method:
            case "telea":
                self.inpaint_method = cv2.INPAINT_TELEA
            case "ns":
                self.inpaint_method = cv2.INPAINT_NS
            case _:
                raise ValueError(f"Unknown OpenCV inpaint method: {method}")

    def _pil_to_cv(self, img: Image.Image) -> np.ndarray:
        return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR) if img.mode == "RGB" else np.array(img)

    def _cv_to_pil(self, img: np.ndarray) -> Image.Image:
        if len(img.shape) == 2:
            return Image.fromarray(img)
        return Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))

    def _pil_to_np(self, img: Image.Image) -> np.ndarray:
        arr = np.array(img)
        if arr.dtype == np.uint8:
            arr = arr / 255.0
        return arr

    def _np_to_pil(self, arr: np.ndarray) -> Image.Image:
        arr = np.clip(arr, 0, 1)
        arr = (arr * 255).astype(np.uint8)
        return Image.fromarray(arr)

    def _load_image(self, img: Union[Image.Image, np.ndarray, str, bytes]) -> Image.Image:
        if isinstance(img, Image.Image):
            return img.convert("RGB")
        elif isinstance(img, np.ndarray):
            if img.dtype != np.uint8:
                img = (img * 255).astype(np.uint8)
            if len(img.shape) == 2:
                return Image.fromarray(img).convert("RGB")
            return Image.fromarray(img).convert("RGB")
        elif isinstance(img, str):
            return Image.open(img).convert("RGB")
        elif isinstance(img, bytes):
            return Image.open(io.BytesIO(img)).convert("RGB")
        else:
            raise ValueError("Unsupported image format")

    def _is_valid_box(self, box):
        if box is None:
            return False
        xmin, ymin, xmax, ymax = [int(v) for v in box]
        if xmax < xmin:
            xmin, xmax = xmax, xmin
        if ymax < ymin:
            ymin, ymax = ymax, ymin
        if xmax <= xmin or ymax <= ymin:
            return False
        return True

    def _fix_box(self, box):
        if box is None:
            return None
        xmin, ymin, xmax, ymax = [int(v) for v in box]
        if xmax < xmin:
            xmin, xmax = xmax, xmin
        if ymax < ymin:
            ymin, ymax = ymax, ymin
        return [xmin, ymin, xmax, ymax]

    def _expand_boxes(self, boxes: List[Optional[list]], img_size, radius: int):
        w, h = img_size
        new_boxes = []
        for box in boxes:
            if box is None:
                new_boxes.append(None)
                continue
            xmin, ymin, xmax, ymax = box
            new_box = [
                max(0, xmin - radius),
                max(0, ymin - radius),
                min(w, xmax + radius),
                min(h, ymax + radius),
            ]
            new_boxes.append(new_box)
        return new_boxes

    def _boxes_to_mask(self, image: Image.Image, boxes: List[Optional[list]]) -> np.ndarray:
        mask = Image.new("L", image.size, 0)
        draw = ImageDraw.Draw(mask)
        for box in boxes:
            if not self._is_valid_box(box):
                continue
            xmin, ymin, xmax, ymax = self._fix_box(box)
            draw.rectangle([xmin, ymin, xmax, ymax], fill=255)
        return np.array(mask) > 0

    def _opencv_inpaint(self, pil_img: Image.Image, boxes: List[Optional[list]]) -> Image.Image:
        cv_img = self._pil_to_cv(pil_img)
        mask = np.zeros(cv_img.shape[:2], dtype=np.uint8)
        for box in boxes:
            if not self._is_valid_box(box):
                continue
            xmin, ymin, xmax, ymax = self._fix_box(box)
            cv2.rectangle(mask, (xmin, ymin), (xmax, ymax), 255, thickness=-1)
        result = cv2.inpaint(cv_img, mask, self.radius, self.inpaint_method)
        return self._cv_to_pil(result)

    def _scikit_inpaint(self, pil_img: Image.Image, boxes: List[Optional[list]]) -> Image.Image:
        if sk_inpaint is None:
            raise ImportError("scikit-image не установлен! Установите через pip install scikit-image")
        np_img = self._pil_to_np(pil_img)
        mask = self._boxes_to_mask(pil_img, boxes)
        result = sk_inpaint.inpaint_biharmonic(np_img, mask, channel_axis=-1)
        return self._np_to_pil(result)

    def remove_text(
        self,
        img: Union[Image.Image, np.ndarray, str, bytes],
        text_boxes: List[Optional[list]],
        output: str = "pil"
    ) -> Union[Image.Image, np.ndarray, bytes, str, os.PathLike]:
        pil_img = self._load_image(img)
        match self.engine:
            case TextRemoverEngine.OPENCV:
                result_pil = self._opencv_inpaint(pil_img, text_boxes)
            case TextRemoverEngine.SCIKIT:
                result_pil = self._scikit_inpaint(pil_img, text_boxes)
            case _:
                raise ValueError(f"Unknown engine: {self.engine}")
        match output:
            case "pil":
                return result_pil
            case "ndarray":
                return np.array(result_pil)
            case "bytes":
                buf = io.BytesIO()
                result_pil.save(buf, format="JPEG")
                return buf.getvalue()
            case "str":
                buf = io.BytesIO()
                result_pil.save(buf, format="JPEG")
                import base64
                b64 = base64.b64encode(buf.getvalue()).decode()
                return b64
            case _ if output.startswith("file:"):
                path = output[5:]
                result_pil.save(path)
                return path
            case _:
                raise ValueError(f"Unknown output type: {output}")

# === Пример использования ===
if __name__ == "__main__":
    from universal_ocr import *

    ocr_vision = UniversalOCR(engine=OCREngine.GOOGLE_VISION)
    result = ocr_vision.extract_text_blocks("ocr_test_image_nsfw.png")

    remover = TextRemover(engine=TextRemoverEngine.OPENCV, method="ns", inpaint_radius=10)
    img_no_text = remover.remove_text("ocr_test_image_nsfw.png", result.text_boxes, output="pil")
    img_no_text.show()

    remover_sk = TextRemover(engine=TextRemoverEngine.SCIKIT, inpaint_radius=10)
    img_no_text_sk = remover_sk.remove_text("ocr_test_image_nsfw.png", result.text_boxes, output="pil")
    img_no_text_sk.show()
