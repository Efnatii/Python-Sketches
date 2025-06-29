import openai
import os
from deep_translator import (
    GoogleTranslator, YandexTranslator, DeeplTranslator
)
from enum import Enum

class TranslateEngine(Enum):
    GOOGLE = "google"
    YANDEX = "yandex"
    DEEPL = "deepl"
    DEEPSEEK = "deepseek"
    CHATGPT = "chatgpt"

class UniversalTranslator:
    def __init__(self, target_lang='ru', engine=TranslateEngine.GOOGLE, **engine_kwargs):
        if isinstance(engine, str):
            try:
                engine = TranslateEngine(engine.lower())
            except ValueError:
                raise ValueError(f"Недопустимый engine: {engine!r}")
        self.engine = engine
        self.target_lang = target_lang
        self.engine_kwargs = engine_kwargs

        self._init_engine()

    def _init_engine(self):
        match self.engine:
            case TranslateEngine.GOOGLE:
                self.translator = GoogleTranslator(source='auto', target=self.target_lang)
            case TranslateEngine.YANDEX | TranslateEngine.DEEPL:
                api_key = self.engine_kwargs.get('api_key', os.environ.get(f"{self.engine.value.upper()}_API_KEY"))
                if not api_key:
                    raise ValueError(f"{self.engine.value.capitalize()} Translator API key не задан!")
                match self.engine:
                    case TranslateEngine.YANDEX:
                        self.translator = YandexTranslator(api_key=api_key, source='auto', target=self.target_lang)
                    case TranslateEngine.DEEPL:
                        self.translator = DeeplTranslator(api_key=api_key, source='auto', target=self.target_lang)
            case TranslateEngine.DEEPSEEK | TranslateEngine.CHATGPT:
                api_key = self.engine_kwargs.get('api_key', os.environ.get(f"{self.engine.value.upper()}_API_KEY"))
                if not api_key:
                    raise ValueError(f"{self.engine.value.capitalize()} Translator API key не задан!")
                self.translator = openai.OpenAI(
                    api_key=api_key,
                    base_url=None if self.engine == TranslateEngine.CHATGPT else
                        self.engine_kwargs.get('base_url', "https://api.deepseek.com")
                )
            case _:
                raise ValueError(f"Неизвестный переводчик: {self.engine}")

    def translate(self, text, stream=False):
        if not text.strip():
            print("[WARNING] Пустой текст для перевода.")
            return "" if not stream else iter([])

        if self.engine in (TranslateEngine.DEEPSEEK, TranslateEngine.CHATGPT):
            # Сбор общих параметров для OpenAI/DeepSeek
            if self.engine == TranslateEngine.DEEPSEEK:
                model = self.engine_kwargs.get('model', 'deepseek-chat')
                temperature = self.engine_kwargs.get('temperature', 1.3)
            else:
                model = self.engine_kwargs.get('model', 'gpt-4.1')
                temperature = self.engine_kwargs.get('temperature', 1.1)
            max_tokens = self.engine_kwargs.get('max_tokens', 2048)
            system_prompt = self.engine_kwargs.get(
                'system_prompt',
                f"Переведи на {self.target_lang} максимально естественно, сохрани верстку и смысл. в ответ выводт только перевод без лишних пояснений!"
            )
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text}
            ]

            params = dict(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )

            if stream:
                return self._translate_stream(params)
            else:
                return self._translate_sync(params)
        else:
            if stream:
                raise NotImplementedError(
                    f"Streaming (stream=True) не поддерживается для движка {self.engine.value.capitalize()}."
                )
            try:
                return self.translator.translate(text)
            except Exception as e:
                print(f"[ERROR] Ошибка перевода: {e}")
                return ""

    def _translate_sync(self, params):
        try:
            response = self.translator.chat.completions.create(
                **params, stream=False
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"[ERROR] Ошибка обращения к {self.engine.value.capitalize()}: {e}")
            return ""

    def _translate_stream(self, params):
        try:
            response = self.translator.chat.completions.create(
                **params, stream=True
            )
            for chunk in response:
                content = getattr(chunk.choices[0].delta, "content", None)
                if content:
                    yield content
        except Exception as e:
            print(f"[ERROR] Ошибка стриминга {self.engine.value.capitalize()}: {e}")


# Пример использования:
if __name__ == "__main__":
    # Для DeepSeek
    # translator = UniversalTranslator(target_lang='ru', engine=TranslateEngine.DEEPSEEK, api_key="sk-xxx")
    # Для ChatGPT (OpenAI, AnyScale и пр.)
    translator = UniversalTranslator(target_lang='ru', engine=TranslateEngine.CHATGPT)
    text = """The Importance of Learning a Second Language

In today's globalized world, learning a second language has become more than just a skill—it is a necessity. Whether for personal growth, career opportunities, or cultural understanding, being bilingual or multilingual offers countless benefits.

First, knowing another language opens up career opportunities. Many international companies prefer employees who can communicate with clients and partners worldwide. For example, professionals who speak both English and Mandarin have an advantage in global business. Additionally, learning a language like Spanish, French, or German can increase job prospects in various fields.

Second, language learning enhances cognitive abilities. Studies show that bilingual individuals have better memory, problem-solving skills, and multitasking abilities. Learning grammar and vocabulary exercises the brain, improving overall mental agility.

Finally, speaking another language allows for deeper cultural understanding. Language is closely tied to traditions, history, and values. By learning a new language, people gain insight into different ways of life, fostering tolerance and global awareness.

In conclusion, mastering a second language is valuable for professional success, mental development, and cultural appreciation. In an interconnected world, it is an investment that pays off in countless ways."""
    # Синхронно:
    #print(translator.translate(text))
    # Потоково:
    for part in translator.translate(text, stream=True):
        print(part, end="", flush=True)