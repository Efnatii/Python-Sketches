# dev-group_supervisor

Утилиты для автоматизации рутинных задач разработки. Модуль
`chat_history_compressor.py` предоставляет класс `ChatHistoryCompressor`,
который использует API DeepSeek Reasoner для рекурсивного сжатия длинной
истории чата OpenAI. Он сохраняет важные даты и числа и сокращает
каждый блок, пока история не уместится в две трети лимита токенов
целевой модели.

## Пример

```python
from chat_history_compressor import ChatHistoryCompressor

messages = [
    {"role": "user", "content": "Привет"},
    {"role": "assistant", "content": "Здравствуйте"},
]

compressor = ChatHistoryCompressor(api_key="YOUR_TOKEN")

try:
    short_history = compressor.compress_messages(messages, max_model_tokens=4096)
except requests.RequestException as exc:
    print("Ошибка обращения к API:", exc)
```
