"""\
Утилиты для сжатия длинной истории переписки с использованием DeepSeek Reasoner.
"""

from __future__ import annotations

import logging
import math
from typing import List, Dict

import requests
import tiktoken


class ChatHistoryCompressor:
    """\
    Рекурсивно сжимает историю чата с помощью API DeepSeek Reasoner.
    """

    def __init__(self, api_key: str, model: str = "deepseek-chat") -> None:
        self.api_key = api_key
        self.model = model
        self.encoding = tiktoken.encoding_for_model("gpt-3.5-turbo")
        self._log = logging.getLogger(self.__class__.__name__)

    def _count_tokens(self, messages: List[Dict[str, str]]) -> int:
        """\
        Подсчитать количество токенов в списке сообщений формата OpenAI.
        """
        tokens_per_message = 4
        tokens_per_name = -1
        total = 0
        for m in messages:
            total += tokens_per_message
            for k, v in m.items():
                total += len(self.encoding.encode(v))
                if k == "name":
                    total += tokens_per_name
        return total + 2

    def _split_blocks(self, messages: List[Dict[str, str]], block_token_limit: int) -> List[List[Dict[str, str]]]:
        blocks: List[List[Dict[str, str]]] = []
        current: List[Dict[str, str]] = []
        tokens = 0
        for msg in messages:
            msg_tokens = self._count_tokens([msg])
            if tokens + msg_tokens > block_token_limit and current:
                blocks.append(current)
                current = [msg]
                tokens = msg_tokens
            else:
                current.append(msg)
                tokens += msg_tokens
        if current:
            blocks.append(current)
        return blocks

    def _compress_block(self, block: List[Dict[str, str]]) -> Dict[str, str]:
        text = "\n".join(f"{m['role']}: {m['content']}" for m in block)
        prompt = (
            "Сожми следующие сообщения без потери смысла и важной информации дат "
            "и чисел. Сформулируй суть коротко на русском:\n" + text
        )
        url = "https://api.deepseek.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
        }
        self._log.debug("Requesting DeepSeek compression")
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as exc:
            self._log.error("Ошибка запроса к DeepSeek: %s", exc)
            raise
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        return {"role": "system", "content": content.strip()}

    def compress_messages(self, messages: List[Dict[str, str]], max_model_tokens: int) -> List[Dict[str, str]]:
        """\
        Рекурсивно сжимает ``messages``, чтобы результат занимал не более
        двух третей от ``max_model_tokens``.
        """
        limit = math.floor(max_model_tokens * (2 / 3))
        compressed = list(messages)
        while self._count_tokens(compressed) > limit:
            block_limit = max(256, limit // 2)
            blocks = self._split_blocks(compressed, block_limit)
            compressed = [self._compress_block(b) for b in blocks]
        return compressed
