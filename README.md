# Python Sketches

Сборник небольших прототипов и утилит, иногда оформленных неидеально,
но содержащих интересные идеи.

## Содержимое
- **dev-image_translator** — перевод текста с экрана через OCR и WinAPI
  (требует установленный Tesseract).
- **dev-group_supervisor** — сжатие истории чатов с помощью DeepSeek Reasoner.
- **dev-stability_ai** — простой клиент к REST API Stable Diffusion.

## Установка зависимостей

Перед запуском скриптов рекомендуется создать виртуальное окружение и
установить необходимые пакеты из `requirements.txt`:

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Пакет `pywin32` обязателен только для Windows и может не устанавливаться на
других системах.

## Лицензия

Исходный код распространяется под лицензией MIT. Подробности в файле `LICENSE`.
