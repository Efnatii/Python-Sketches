# dev-stability_ai

Небольшой клиент для REST API Stable Diffusion v2beta. В файле
`_stabilityai_stableimage_generator.py` реализован класс
`_StabilityAI_StableImage_Generate` с методом `generate()` для
создания изображений по текстовому описанию.

## Быстрый пример

```python
from _stabilityai_stableimage_generator import _StabilityAI_StableImage_Generate

api = _StabilityAI_StableImage_Generate(api_key="YOUR_API_KEY")
img_bytes = api.generate(prompt="cat in space")
```

Укажите `save_path`, чтобы сохранить результат на диск. Для работы
нужны пакеты `requests` и, при необходимости, `Pillow`.
