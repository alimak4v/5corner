import json
import logging
import os
from dataclasses import dataclass
from typing import List, Optional

from openai import OpenAI
from loader import get_prompt

logger = logging.getLogger(__name__)


@dataclass
class RatingResult:
    """Результат оценки контента"""

    score: float
    reasoning: str


def rate_content(content: str, client: Optional[OpenAI] = None) -> RatingResult:
    """
    Оценивает контент от 0.0 до 1.0 по качеству, релевантности и важности.

    Args:
        content: Текст новости для оценки
        client: Экземпляр OpenAI клиента (создаёт новый, если не предоставлен)

    Returns:
        RatingResult с оценкой (0.0-1.0) и обоснованием

    Raises:
        ValueError: Если контент пустой
    """
    if not content or not content.strip():
        raise ValueError("Content cannot be empty")

    if client is None:
        client = OpenAI(
            base_url=os.getenv("OPENAI_BASE_URL", "https://openrouter.ai/api/v1"),
            api_key=os.getenv("OPENROUTER_API_KEY"),
        )

    model = os.getenv("MODEL")

    try:
        logger.info(f"Rating content: {content[:100]}...")

        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": get_prompt("RATE_SYSTEM"),
                },
                {"role": "user", "content": get_prompt("RATE_USER", content=content)},
            ],
            temperature=0.3,
        )

        result_text = response.choices[0].message.content
        result_json = json.loads(result_text)

        score = float(result_json.get("score", 0.5))
        reasoning = str(result_json.get("reasoning", "No reasoning provided"))

        # Ensure score is within bounds
        score = max(0.0, min(1.0, score))

        logger.info(f"Rating result: {score} - {reasoning}")

        return RatingResult(score=score, reasoning=reasoning)

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse OpenAI response: {e}")
        raise ValueError(f"Invalid rating response from OpenAI: {e}")
    except Exception as e:
        logger.error(f"Error rating content: {e}")
        raise


def rate_batch(
    contents: List[str], client: Optional[OpenAI] = None
) -> List[RatingResult]:
    """
    Оценивает несколько контентов в одном вызове модели для снижения количества запросов.

    Args:
        contents: Список новостей/текстов для оценки
        client: Опциональный OpenAI клиент

    Returns:
        Список RatingResult в исходном порядке
    """
    if not contents:
        return []

    if client is None:
        client = OpenAI(
            base_url=os.getenv("OPENAI_BASE_URL", "https://openrouter.ai/api/v1"),
            api_key=os.getenv("OPENROUTER_API_KEY"),
        )

    model = os.getenv("MODEL")

    numbered = "\n\n".join([f"{i+1}. {text}" for i, text in enumerate(contents)])
    system = get_prompt("RATE_BATCH_SYSTEM")
    user = get_prompt("RATE_BATCH_USER", numbered_items=numbered)

    try:
        logger.info(f"Batch rating {len(contents)} items...")
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.3,
        )

        result_text = response.choices[0].message.content
        data = json.loads(result_text)
        results: List[RatingResult] = []
        for i, item in enumerate(data):
            score = float(item.get("score", 0.5))
            reasoning = str(item.get("reasoning", "No reasoning"))
            score = max(0.0, min(1.0, score))
            results.append(RatingResult(score=score, reasoning=reasoning))
        if len(results) != len(contents):
            raise ValueError("Batch rating length mismatch")
        return results
    except Exception as e:
        logger.error(f"Error in batch rating: {e}")
        # Fallback: neutral scores
        return [
            RatingResult(score=0.5, reasoning="Fallback due to error") for _ in contents
        ]
