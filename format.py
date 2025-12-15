import logging
import os
from typing import Optional

from openai import OpenAI
from loader import get_prompt

logger = logging.getLogger(__name__)


def _default_client() -> OpenAI:
    """Создаёт клиент OpenAI по умолчанию"""
    return OpenAI(
        base_url=os.getenv("OPENAI_BASE_URL", "https://openrouter.ai/api/v1"),
        api_key=os.getenv("OPENROUTER_API_KEY"),
    )


def format_for_telegram(summary_markdown: str, client: Optional[OpenAI] = None) -> str:
    """Форматирует дайджест для публикации в Telegram и добавляет краткую подводку"""
    if not summary_markdown or not summary_markdown.strip():
        return ""

    ai_client = client or _default_client()
    model = os.getenv("MODEL")

    system_prompt = get_prompt("FORMAT_SYSTEM")
    user_prompt = get_prompt("FORMAT_USER", summary_markdown=summary_markdown)

    try:
        completion = ai_client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.35,
            max_tokens=800,
        )
        return completion.choices[0].message.content
    except Exception as e:
        logger.error("Ошибка при форматировании для Telegram: %s", e)
        return summary_markdown
