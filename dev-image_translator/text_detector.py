import os
import sys
import urllib.request
import subprocess
import base64
from typing import Union
from enum import Enum
import cv2
import numpy as np
import torch
from PIL import Image

def _ensure_craft_repo_and_patch():
    """Клонирует CRAFT-pytorch и патчит vgg16_bn.py, если требуется"""
    repo_url = "https://github.com/clovaai/CRAFT-pytorch.git"
    repo_dir = os.path.abspath("./CRAFT-pytorch")
    vgg_file = os.path.join(repo_dir, "basenet", "vgg16_bn.py")

    if not os.path.exists(repo_dir):
        print("Клонирую репозиторий CRAFT-pytorch...")
        subprocess.check_call(["git", "clone", repo_url, repo_dir])

    if os.path.exists(vgg_file):
        with open(vgg_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
        patched = False
        with open(vgg_file, "w", encoding="utf-8") as f:
            for line in lines:
                if "from torchvision.models.vgg import model_urls" in line:
                    f.write("model_urls = {}\n")
                    patched = True
                elif "model_urls['vgg16_bn']" in line:
                    f.write("# " + line)
                    patched = True
                else:
                    f.write(line)
        if patched:
            print("Патч для 'model_urls' и 'vgg16_bn' успешно применён в vgg16_bn.py")
    sys.path.insert(0, repo_dir)

try:
    from craft import CRAFT
    from craft_utils import getDetBoxes
    from imgproc import normalizeMeanVariance, resize_aspect_ratio
except ImportError:
    _ensure_craft_repo_and_patch()
    from craft import CRAFT
    from craft_utils import getDetBoxes
    from imgproc import normalizeMeanVariance, resize_aspect_ratio

import requests
def download_file_from_hf(url, destination):
    print(f"Скачиваю веса CRAFT с Hugging Face: {url} ...")
    with requests.get(url, stream=True) as r:
        r.raise_for_status()
        with open(destination, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
    print("Скачивание завершено.")

class Engine(Enum):
    CRAFT = "craft"
    EAST = "east"

class TextDetector:
    MODEL_URLS = {
        Engine.CRAFT: "https://huggingface.co/amitesh863/craft/resolve/main/craft_mlt_25k.pth",
        Engine.EAST:  "https://github.com/opencv/opencv_extra/raw/master/testdata/dnn/frozen_east_text_detection.pb",
    }
    MODEL_PATHS = {
        Engine.CRAFT: "./model/craft_mlt_25k.pth",
        Engine.EAST:  "./model/frozen_east_text_detection.pb",
    }

    def __init__(self, engine: Engine = Engine.CRAFT, cuda=None):
        self.engine = engine
        if cuda is None:
            cuda = torch.cuda.is_available()
        self.cuda = cuda

        self._ensure_model()
        if self.engine == Engine.CRAFT:
            state = torch.load(self.MODEL_PATHS[self.engine], map_location="cuda" if cuda else "cpu")
            # Убираем префикс "module." если он есть
            if any(k.startswith('module.') for k in state):
                state = {k.replace('module.', ''): v for k, v in state.items()}
            self.net = CRAFT()
            self.net.load_state_dict(state)
            if self.cuda:
                self.net = self.net.cuda()
            self.net.eval()
        elif self.engine == Engine.EAST:
            self.net = cv2.dnn.readNet(self.MODEL_PATHS[self.engine])
        else:
            raise NotImplementedError(f"Engine {self.engine} not implemented.")

    def _ensure_model(self):
        os.makedirs("./model", exist_ok=True)
        path = self.MODEL_PATHS[self.engine]
        url = self.MODEL_URLS[self.engine]
        need_download = not os.path.exists(path)
        if self.engine == Engine.CRAFT and os.path.exists(path):
            if os.path.getsize(path) < 80_000_000:  # Вес должен быть ~82 МБ
                print("Файл весов CRAFT повреждён или не докачан, скачиваю заново...")
                os.remove(path)
                need_download = True
        if need_download:
            print(f"Downloading {self.engine.value.upper()} model...")
            if self.engine == Engine.CRAFT:
                download_file_from_hf(url, path)
            else:
                urllib.request.urlretrieve(url, path)
            print("Download complete.")

    def _to_ndarray(self, image: Union[np.ndarray, Image.Image, str, bytes]) -> np.ndarray:
        if isinstance(image, np.ndarray):
            return image
        if isinstance(image, Image.Image):
            return cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
        if isinstance(image, str):
            image = image.strip()
            if image.startswith("http://") or image.startswith("https://"):
                with urllib.request.urlopen(image) as resp:
                    arr = np.asarray(bytearray(resp.read()), dtype=np.uint8)
                    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                    return img
            elif image.startswith("data:image/"):
                base64_str = image.split(",", 1)[1]
                img_bytes = base64.b64decode(base64_str)
                img_arr = np.frombuffer(img_bytes, np.uint8)
                img = cv2.imdecode(img_arr, cv2.IMREAD_COLOR)
                return img
            elif os.path.exists(image):
                img = cv2.imread(image)
                if img is None:
                    raise ValueError(f"Файл найден ({image}), но не удалось загрузить как изображение.")
                return img
            else:
                # Пытаемся декодировать как base64 только если это длинная строка
                if len(image) > 100:
                    try:
                        img_bytes = base64.b64decode(image)
                        img_arr = np.frombuffer(img_bytes, np.uint8)
                        img = cv2.imdecode(img_arr, cv2.IMREAD_COLOR)
                        return img
                    except Exception:
                        pass
                raise ValueError(f"Не удалось загрузить изображение по строке: {image}")
        if isinstance(image, bytes):
            img_arr = np.frombuffer(image, np.uint8)
            img = cv2.imdecode(img_arr, cv2.IMREAD_COLOR)
            return img
        raise TypeError("Unsupported image format.")

    def _mask_convert(self, mask: np.ndarray, mask_type: str) -> Union[np.ndarray, Image.Image, bytes, str]:
        if mask_type == "ndarray":
            return mask
        elif mask_type == "PIL":
            return Image.fromarray(mask)
        elif mask_type == "bytes":
            is_success, buffer = cv2.imencode(".png", mask)
            if not is_success:
                raise ValueError("Failed to encode mask as PNG bytes")
            return buffer.tobytes()
        elif mask_type == "base64":
            is_success, buffer = cv2.imencode(".png", mask)
            if not is_success:
                raise ValueError("Failed to encode mask as PNG bytes")
            base64_str = base64.b64encode(buffer).decode("utf-8")
            return base64_str
        elif mask_type.startswith("file:"):
            path = mask_type[5:]
            path = path.strip()
            if not path:
                path = "text_mask.png"
            cv2.imwrite(path, mask)
            return path
        else:
            raise ValueError("Unknown mask_type: choose one of 'ndarray', 'PIL', 'bytes', 'base64', 'file:path/to/file.png'.")

    def detect(
        self,
        image: Union[np.ndarray, Image.Image, str, bytes],
        text_threshold=0.7,
        link_threshold=0.4,
        low_text=0.4,
        canvas_size=1280,
        mask_type: str = "ndarray"
    ):
        """
        image: np.ndarray, PIL.Image, URL, file path, base64 str, bytes
        mask_type: 'ndarray', 'PIL', 'bytes', 'base64', or 'file:path/to/file.png'
        """
        image = self._to_ndarray(image)
        if image is None:
            raise ValueError("Image could not be loaded.")

        if self.engine == Engine.CRAFT:
            img_resized, target_ratio, size_heatmap = resize_aspect_ratio(image, canvas_size, interpolation=cv2.INTER_LINEAR)
            x = normalizeMeanVariance(img_resized)
            x = torch.from_numpy(x).permute(2, 0, 1).unsqueeze(0).float()
            if self.cuda:
                x = x.cuda()

            with torch.no_grad():
                y, feature = self.net(x)
                score_text = y[0, :, :, 0].cpu().data.numpy()
                score_link = y[0, :, :, 1].cpu().data.numpy()

            boxes, polys = getDetBoxes(score_text, score_link, text_threshold, link_threshold, low_text, False)
            if boxes is not None:
                boxes = np.array(boxes) / target_ratio
            if polys is not None:
                polys = [np.array(p) / target_ratio if p is not None else None for p in polys]

            mask_arr = (score_text > text_threshold).astype(np.uint8) * 255
            mask_arr = cv2.resize(mask_arr, (image.shape[1], image.shape[0]), interpolation=cv2.INTER_NEAREST)

            mask_res = self._mask_convert(mask_arr, mask_type)
            return mask_res, boxes, polys

        elif self.engine == Engine.EAST:
            min_confidence = text_threshold
            width, height = 1280, 1280  # Размеры должны быть кратны 32 для EAST

            orig_h, orig_w = image.shape[:2]
            blob = cv2.dnn.blobFromImage(image, 1.0, (width, height),
                                         (123.68, 116.78, 103.94), True, False)
            self.net.setInput(blob)
            scores, geometry = self.net.forward(["feature_fusion/Conv_7/Sigmoid", "feature_fusion/concat_3"])

            detections = []
            (numRows, numCols) = scores.shape[2:4]
            for y in range(0, numRows):
                scoresData = scores[0, 0, y]
                xData0 = geometry[0, 0, y]
                xData1 = geometry[0, 1, y]
                xData2 = geometry[0, 2, y]
                xData3 = geometry[0, 3, y]
                anglesData = geometry[0, 4, y]
                for x in range(0, numCols):
                    if scoresData[x] < min_confidence:
                        continue
                    (offsetX, offsetY) = (x * 4.0, y * 4.0)
                    angle = anglesData[x]
                    cos = np.cos(angle)
                    sin = np.sin(angle)
                    h = xData0[x] + xData2[x]
                    w = xData1[x] + xData3[x]
                    endX = int(offsetX + (cos * xData1[x]) + (sin * xData2[x]))
                    endY = int(offsetY - (sin * xData1[x]) + (cos * xData2[x]))
                    startX = int(endX - w)
                    startY = int(endY - h)
                    detections.append((startX, startY, endX, endY))
            polys = [np.array([[b[0], b[1]], [b[2], b[1]], [b[2], b[3]], [b[0], b[3]]]) for b in detections]

            mask_arr = np.zeros((orig_h, orig_w), dtype=np.uint8)
            for b in detections:
                scale_x = orig_w / width
                scale_y = orig_h / height
                x1 = int(b[0] * scale_x)
                y1 = int(b[1] * scale_y)
                x2 = int(b[2] * scale_x)
                y2 = int(b[3] * scale_y)
                cv2.rectangle(mask_arr, (x1, y1), (x2, y2), 255, -1)
            mask_res = self._mask_convert(mask_arr, mask_type)
            return mask_res, np.array(detections), polys

        else:
            raise NotImplementedError(f"Engine {self.engine} not implemented.")

# ============ Пример использования ============
if __name__ == "__main__":
    detector = TextDetector(engine=Engine.CRAFT)
    mask, boxes, polys = detector.detect("ocr_test_image_nsfw.png", mask_type="PIL", canvas_size=4096)
    print("CRAFT:", type(mask), boxes.shape if boxes is not None else None)
    mask.show()

    detector_east = TextDetector(engine=Engine.EAST)
    mask, boxes, polys = detector_east.detect("ocr_test_image_nsfw.png", mask_type="ndarray")
    print("EAST:", type(mask), np.array(boxes).shape if boxes is not None else None)
