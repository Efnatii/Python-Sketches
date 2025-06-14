В этот репозиторий будут выкладываться "скетчи", зачастую возможно не хорошо написанные и/или имеющие какую-то хорошую идею.
* Image Translator ("Переводчик изображений") - с помощью WINAPI делает скриншот выбранной области экрана, распознает английский текст с помощью OCR, затем переводит его на русский и выводит переведенный текст на экран.

  Файл `image_translator.py` предполагает, что Tesseract установлен по пути
  `C:\Program Files\Tesseract-OCR\tesseract.exe`. Если путь к исполняемому
  файлу другой, отредактируйте переменную `tesseract_cmd` в коде.

## Установка зависимостей

Перед запуском скриптов установите необходимые пакеты:

```bash
pip install -r requirements.txt
```

## Пример использования ChatHistoryCompressor

```python
from dev_group_supervisor.chat_history_compressor import ChatHistoryCompressor

compressor = ChatHistoryCompressor(api_key="YOUR_TOKEN")
try:
    result = compressor.compress_messages([{"role": "user", "content": "Привет"}], max_model_tokens=4096)
except requests.RequestException as exc:
    print("Ошибка запроса:", exc)
```

## Лицензия

Исходный код распространяется под лицензией MIT. Подробности в файле `LICENSE`.
