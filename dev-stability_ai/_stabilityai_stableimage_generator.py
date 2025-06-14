import requests
from enum import Enum
from typing import Optional, Union, BinaryIO
import io
import os

try:
    from PIL import Image as PILImage
except ImportError:
    PILImage = None

class AspectRatio(Enum):
    """Варианты пропорций для генерации изображений."""
    AR_16_9 = "16:9"
    AR_1_1 = "1:1"
    AR_21_9 = "21:9"
    AR_2_3 = "2:3"
    AR_3_2 = "3:2"
    AR_4_5 = "4:5"
    AR_5_4 = "5:4"
    AR_9_16 = "9:16"
    AR_9_21 = "9:21"

class OutputFormat(Enum):
    """Варианты формата вывода изображения."""
    JPEG = "jpeg"
    PNG = "png"
    WEBP = "webp"

class ModelType(Enum):
    """Тип модели генерации Stable Diffusion."""
    ULTRA = "ultra"
    CORE = "core"
    SD3 = "sd3"

class StylePreset(Enum):
    """Варианты стилей генерации (style_preset) из Stability API."""
    THREE_D_MODEL = "3d-model"
    ANALOG_FILM = "analog-film"
    ANIME = "anime"
    CINEMATIC = "cinematic"
    COMIC_BOOK = "comic-book"
    DIGITAL_ART = "digital-art"
    ENHANCE = "enhance"
    FANTASY_ART = "fantasy-art"
    ISOMETRIC = "isometric"
    LINE_ART = "line-art"
    LOW_POLY = "low-poly"
    MODELING_COMPOUND = "modeling-compound"
    NEON_PUNK = "neon-punk"
    ORIGAMI = "origami"
    PHOTOGRAPHIC = "photographic"
    PIXEL_ART = "pixel-art"
    TILE_TEXTURE = "tile-texture"


class _StabilityAI_StableImage_Generate:
    """
    Класс для взаимодействия с REST API StabilityAI (v2beta) — генерация изображений.

    Позволяет генерировать изображения по текстовому описанию через разные модели Stable Diffusion.
    """

    BASE_URL = "https://api.stability.ai/v2beta/stable-image/generate"

    def __init__(
        self,
        api_key: str,
        client_id: Optional[str] = None,
        client_user_id: Optional[str] = None,
        client_version: Optional[str] = None,
    ):
        """
        Инициализация клиента для API Stable Diffusion.

        Args:
            api_key (str): Ваш API-ключ StabilityAI (обязательно).
            client_id (Optional[str]): ID вашего приложения (опционально).
            client_user_id (Optional[str]): Уникальный идентификатор пользователя (опционально).
            client_version (Optional[str]): Версия вашего клиента (опционально).
        """
        self.api_key = api_key
        self.client_id = client_id
        self.client_user_id = client_user_id
        self.client_version = client_version

    def generate(
        self,
        prompt: str,
        model: ModelType = ModelType.ULTRA,
        negative_prompt: Optional[str] = None,
        aspect_ratio: Optional[AspectRatio] = None,
        seed: Optional[int] = None,
        output_format: OutputFormat = OutputFormat.WEBP,
        samples: int = 1,
        image: Optional[Union[str, bytes, BinaryIO, "PILImage.Image"]] = None,
        style_preset: Optional[StylePreset] = None,
        strength: Optional[float] = None,
        accept: str = "image/*",
        save_path: Optional[str] = None,
        return_type: str = "bytes",
    ) -> Union[bytes, str, BinaryIO, "PILImage.Image", list]:
        """
        Генерирует изображение по текстовому описанию через REST API StabilityAI.

        Args:
            prompt (str): Описательный текстовый запрос (обязательно).
            model (ModelType): Модель генерации (ultra, core, sd3).
            negative_prompt (Optional[str]): Текст того, чего не должно быть на изображении (опционально).
            aspect_ratio (Optional[AspectRatio]): Пропорция изображения (опционально).
            seed (Optional[int]): Число для детерминированной генерации; если None, результат случайный (опционально).
        output_format (OutputFormat): Формат выдаваемого изображения (webp, png, jpeg).
        samples (int): Количество изображений для генерации.
        image (Optional[Union[str, bytes, BinaryIO, PILImage.Image]]):
                Исходное изображение для режимов img2img/inpainting.
                Можно передать путь до файла (str), байты (bytes), файловый объект (BinaryIO) или объект PIL.Image (Pillow).
            style_preset (Optional[str]): Предустановленный стиль (опционально, см. документацию StabilityAI).
            strength (Optional[float]): Сила изменения исходного изображения (0..1, только для img2img/inpainting).
            accept (str): Тип возвращаемых данных от API — "image/*" (байты) или "application/json" (base64) (обычно не менять).
            save_path (Optional[str]): Если указан, результат сохраняется по этому пути (опционально).
            return_type (str): Формат результата: "bytes" (байты, по умолчанию),
                "str" (путь к файлу, только с save_path), "BinaryIO" (io.BytesIO), "PIL" (PIL.Image.Image).

        Returns:
            bytes | list: Если return_type="bytes". При samples>1 возвращается список.
            str | list: Путь к файлам, если return_type="str" и указан save_path. При samples>1 список путей.
            io.BytesIO | list: Если return_type="BinaryIO". При samples>1 список объектов.
            PIL.Image.Image | list: Если return_type="PIL" и установлен Pillow. При samples>1 список изображений.

        Raises:
            ValueError: Если передан некорректный тип изображения или return_type.
            Exception: При ошибке API возвращается текст ошибки.
        """
        url = f"{self.BASE_URL}/{model.value}"

        headers = {
            "authorization": f"Bearer {self.api_key}",
            "accept": accept,
        }
        if self.client_id:
            headers["stability-client-id"] = self.client_id
        if self.client_user_id:
            headers["stability-client-user-id"] = self.client_user_id
        if self.client_version:
            headers["stability-client-version"] = self.client_version

        data = {
            "prompt": prompt,
            "output_format": output_format.value,
        }
        if negative_prompt:
            data["negative_prompt"] = negative_prompt
        if aspect_ratio:
            data["aspect_ratio"] = aspect_ratio.value
        if seed is not None:
            data["seed"] = seed
        if style_preset:
            data["style_preset"] = style_preset.value
        if strength is not None:
            data["strength"] = strength

        results = []
        for i in range(samples):
            files = None
            # Обработка разных форматов изображения
            if image is not None:
                if isinstance(image, str):
                    # Передан путь до файла
                    with open(image, "rb") as f:
                        files = {"image": f}
                        response = requests.post(url, headers=headers, files=files, data=data)
                elif isinstance(image, bytes):
                    # Переданы байты
                    files = {"image": ("image", image)}
                    response = requests.post(url, headers=headers, files=files, data=data)
                elif hasattr(image, "read"):
                    # Файловый объект (например io.BytesIO)
                    files = {"image": ("image", image.read())}
                    response = requests.post(url, headers=headers, files=files, data=data)
                elif PILImage and isinstance(image, PILImage.Image):
                    # Объект PIL.Image (Pillow)
                    buf = io.BytesIO()
                    image.save(buf, format="PNG")
                    buf.seek(0)
                    files = {"image": ("image", buf.read())}
                    response = requests.post(url, headers=headers, files=files, data=data)
                else:
                    raise ValueError("Параметр image должен быть str (путь), bytes, BinaryIO или PIL.Image.Image")
            else:
                # Для чисто текстовой генерации по требованиям API
                files = {"none": ""}
                response = requests.post(url, headers=headers, files=files, data=data)

            if response.status_code == 200:
                current_save = None
                if save_path:
                    base, ext = os.path.splitext(save_path)
                    current_save = f"{base}{i+1}{ext}" if samples > 1 else save_path
                    with open(current_save, "wb") as file:
                        file.write(response.content)
                    if return_type == "str":
                        results.append(current_save)
                        continue

                if return_type == "bytes":
                    results.append(response.content)
                elif return_type == "BinaryIO":
                    results.append(io.BytesIO(response.content))
                elif return_type == "PIL":
                    if not PILImage:
                        raise ImportError("Pillow (PIL) не установлен!")
                    results.append(PILImage.open(io.BytesIO(response.content)))
                elif return_type == "str":
                    results.append(current_save if current_save else "")
                else:
                    raise ValueError(f"Неизвестный return_type: {return_type}")
            else:
                try:
                    error_info = response.json()
                except Exception:
                    error_info = response.text
                raise Exception(f"StabilityAI API Error: {error_info}")

        return results[0] if samples == 1 else results

# --- Пример использования ---

if __name__ == "__main__":
    import os

    api = _StabilityAI_StableImage_Generate(api_key=os.environ['_STABILITYAI_API_KEY_1'])

    img = api.generate(
        prompt="""cinematic detailed 8k illustration of a shy anthro pony girl (no horn) with short soft white
fur, large upright pony ears (pink inner), small gentle muzzle and teal-turquoise wavy
mid-length hair and long flowing tail, side-parted bangs framing the face, round gold-rim
coral glasses, subtle pink blush across cheeks and nose, golden hazel eyes. 8k illustration
full-body shot of shy anthro pony girl with realistic cloth folds on a very large bust
emphasized by ribbed cream turtleneck sweater, realistic sweater tucked into high-waisted
black pleated micro-skirt, detailed textures on sheer glossy black thigh-high stockings and
black patent-leather Mary-Jane heels.

Artstation trending masterpiece concept art volumetric lighting cinematic 8k illustration of
shy anthro pony girl with soft rim light edging hair and contours, subsurface-scattering on
fur and skin, HDR, subtle bloom, anime-realism hybrid, 3-D painted feel.

In the middle of a narrow library aisle with tall wooden bookshelves with concept art level
polish, by WLOP, Sakimichan, RossDraws, cinematic volumetric light rays, realistic background,
warm afternoon sunlight pouring through large right-hand windows. Shadows cast on the glossy
beige tiled floor with reflections, shallow depth-of-field.

F/1.8 35 mm lens, soft bokeh, ultra detailed 8k illustration of shy anthro pony girl holding a
closed burgundy spellbook with ornate gold embossing, subtle lighting, cinematic lighting
effects, high quality detail.""",
        negative_prompt="""lowres, worst quality, blurry illustration of shy anthro pony girl with bad anatomy,
deformed, disfigured, mutated hands, extra fingers, extra limbs, gross proportions, nude,
skimpy clothing, open shirt.

No cinematic lighting effects, flat shading, grainy art, jpeg artifacts, high contrast, low
resolution, concept art, artistic style, 0 detail.

artwork by xxx_nsfw_xxx, 8k jpeg image with watermark, highly detailed,""",
        aspect_ratio=AspectRatio.AR_2_3,
        model=ModelType.ULTRA,
        style_preset=StylePreset.FANTASY_ART,
        output_format=OutputFormat.PNG,

        return_type="PIL",
    )
    if PILImage:
        img.show()

