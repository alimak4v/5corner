import json
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


def deduplicate_news(
    news_items: List[Dict[str, Any]], client: Optional[OpenAI] = None
) -> List[Dict[str, Any]]:
    """
    Обнаруживает и удаляет дубликаты похожих новостей в одном пакетном вызове.

    Args:
        news_items: Список словарей новостей с 'text', 'channel_username', 'message_id'
        client: Опциональный OpenAI клиент

    Returns:
        Дедуплицированный список новостей (сохраняет исходный элемент с лучшей информацией)
    """
    if not news_items or len(news_items) <= 1:
        return news_items

    ai_client = client or _default_client()
    model = os.getenv("MODEL")

    # Build a prompt asking the model to identify duplicates
    news_list = "\n\n".join(
        [f"ID {i}: {item['text'][:200]}" for i, item in enumerate(news_items)]
    )

    prompt = get_prompt("DEDUP_USER", count=len(news_items), news_list=news_list)

    try:
        logger.info(f"Deduplicating {len(news_items)} news items...")

        response = ai_client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": get_prompt("DEDUP_SYSTEM"),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=500,
        )

        result_text = response.choices[0].message.content
        data = json.loads(result_text)
        groups = data.get("groups", [])

        # Build deduplicated list: keep first item from each group, merge sources
        seen_indices = set()
        deduplicated = []

        for group in groups:
            if not group:
                continue
            primary_idx = group[0]
            if primary_idx in seen_indices:
                continue

            primary_item = news_items[primary_idx].copy()

            # Merge sources from duplicates
            sources = [primary_item.get("channel_username", "")]
            for dup_idx in group[1:]:
                if dup_idx not in seen_indices:
                    dup_source = news_items[dup_idx].get("channel_username", "")
                    if dup_source and dup_source not in sources:
                        sources.append(dup_source)
                    seen_indices.add(dup_idx)

            primary_item["merged_sources"] = sources
            deduplicated.append(primary_item)
            seen_indices.add(primary_idx)

        # Add any ungrouped items (those not in any group)
        for i, item in enumerate(news_items):
            if i not in seen_indices:
                deduplicated.append(item)
                seen_indices.add(i)

        removed = len(news_items) - len(deduplicated)
        logger.info(
            f"Дедупликация: {len(news_items)} → {len(deduplicated)} (удалено {removed})"
        )

        return deduplicated

    except Exception as e:
        logger.error(f"Ошибка дедупликации: {e}. Пропускаю.")
        return news_items
