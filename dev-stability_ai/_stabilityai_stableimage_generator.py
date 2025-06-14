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
    """Aspect ratio options for image generation."""
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
    """Available output image formats."""
    JPEG = "jpeg"
    PNG = "png"
    WEBP = "webp"

class ModelType(Enum):
    """Stable Diffusion model type."""
    ULTRA = "ultra"
    CORE = "core"
    SD3 = "sd3"

class StylePreset(Enum):
    """Style presets from the Stability API."""
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
    """Client for the StabilityAI REST API (v2beta) for image generation."""

    BASE_URL = "https://api.stability.ai/v2beta/stable-image/generate"

    def __init__(
        self,
        api_key: str,
        client_id: Optional[str] = None,
        client_user_id: Optional[str] = None,
        client_version: Optional[str] = None,
    ):
        """Initialize the client for the Stable Diffusion API.

        Args:
            api_key: Your StabilityAI API key.
            client_id: Optional application identifier.
            client_user_id: Optional unique user identifier.
            client_version: Optional client version string.
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
        """Generate an image from ``prompt`` using the StabilityAI REST API.

        Args:
            prompt: Text prompt for generation.
            model: Generation model to use.
            negative_prompt: Text that must not appear in the image.
            aspect_ratio: Desired aspect ratio of the result.
            seed: Seed for deterministic generation or ``None`` for random.
            output_format: Output image format.
            samples: Number of images to generate.
            image: Optional source image for img2img/inpainting. Can be a path,
                bytes, a file-like object or ``PIL.Image``.
            style_preset: Optional style preset.
            strength: Strength of modification for img2img mode.
            accept: Response type, usually not changed.
            save_path: Optional path to save the result.
            return_type: Result format: ``"bytes"`` (default), ``"str"`` (path with
                ``save_path``), ``"BinaryIO"`` or ``"PIL"``.

        Returns:
            bytes | list: When ``return_type="bytes"``. List if ``samples > 1``.
            str | list: Path(s) when ``return_type="str"`` and ``save_path`` is set.
            io.BytesIO | list: When ``return_type="BinaryIO"``.
            PIL.Image.Image | list: When ``return_type="PIL"``.

        Raises:
            ValueError: If an invalid image type or ``return_type`` is provided.
            Exception: Raised when the API returns an error.
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

