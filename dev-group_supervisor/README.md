# dev-group_supervisor

Набор небольших утилит для автоматизации рутинных задач. Основной модуль
`chat_history_compressor.py` содержит класс `ChatHistoryCompressor`,
который использует API DeepSeek Reasoner для рекурсивного сжатия истории чатов,
сохраняя важные даты и числа.

## Установка

```bash
pip install requests tiktoken
```

## Пример

```python
from chat_history_compressor import ChatHistoryCompressor

compressor = ChatHistoryCompressor(api_key="YOUR_DEEPSEEK_KEY")
short = compressor.compress_messages(messages, max_model_tokens=4096)
```
