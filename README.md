## О проекте

Небольшая коллекция экспериментальных Python‑скриптов. Некоторые из них могут
быть написаны не самым лучшим образом, но демонстрируют интересные идеи.

* **Image Translator** – при помощи WinAPI делает скриншот выбранной области
  экрана, распознаёт английский текст через OCR, переводит его на русский и
  выводит поверх остальных окон.

Англоязычную версию этого файла можно найти в [README.en.md](README.en.md).

## Требования

- Python 3.8 или новее;
- Windows для работы модуля Image Translator (используется WinAPI);
- пакеты из `requirements.txt`.

Некоторые подмодули требуют настроенные переменные окружения (см. раздел ниже).

## Установка зависимостей

Перед запуском скриптов установите необходимые пакеты:

```bash
pip install -r requirements.txt
```

## Примеры запуска

Image Translator:

```bash
set TESSERACT_CMD=C:\\Program Files\\Tesseract-OCR\\tesseract.exe
python dev-image_translator/image_translator.py
```

Генерация изображений через StabilityAI:

```bash
set _STABILITYAI_API_KEY_1=your_api_key
python dev-stability_ai/_stabilityai_stableimage_generator.py
```

## Переменные окружения

- `TESSERACT_CMD` – путь к исполняемому файлу `tesseract.exe`. Используется
  модулем *Image Translator*. Если переменная не указана, берётся значение
  `C:\Program Files\Tesseract-OCR\tesseract.exe`.
- `_STABILITYAI_API_KEY_1` – API‑ключ для доступа к сервису StabilityAI. Требуется
  скриптом `_stabilityai_stableimage_generator.py`.

## Лицензия

Исходный код распространяется под лицензией MIT. Подробности в файле `LICENSE`.
