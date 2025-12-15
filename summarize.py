import logging
import os
from typing import Any, Dict, List, Optional

from openai import OpenAI
from loader import get_prompt

logger = logging.getLogger(__name__)


def _default_client() -> OpenAI:
    """Создаёт клиент OpenAI по умолчанию"""
    return OpenAI(
        base_url=os.getenv("OPENAI_BASE_URL", "https://openrouter.ai/api/v1"),
        api_key=os.getenv("OPENROUTER_API_KEY"),
    )


def summarize_news(
    news_items: List[Dict[str, Any]],
    client: Optional[OpenAI] = None,
    feedback: Optional[str] = None,
) -> str:
    """Генерирует краткий дайджест из собранных новостей"""
    if not news_items:
        return ""

    news_list = ""
    for i, item in enumerate(news_items):
        news_list += f"{i + 1}. {item['text']} t.me/{item['channel_username'].replace('@', '')}/{item['message_id']}\n\n"
    
    prompt = get_prompt("SUMMARIZE_USER", news_list=news_list)

    ai_client = client or _default_client()
    model = os.getenv("MODEL")

    try:
        messages = [
            {
                "role": "system",
                "content": get_prompt("SUMMARIZE_SYSTEM"),
            },
            {"role": "user", "content": prompt},
        ]
        if feedback and feedback.strip():
            messages.append(
                {
                    "role": "user",
                    "content": get_prompt("SUMMARIZE_FEEDBACK", feedback=feedback),
                }
            )

        completion = ai_client.chat.completions.create(
            model=model, messages=messages, max_tokens=1024, temperature=0.1
        )
        return completion.choices[0].message.content
    except Exception as e:
        logger.error("Ошибка при генерации сводки: %s", e)
        return "Ошибка при генерации сводки. Попробуйте позже."
