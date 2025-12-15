import os
import json
import logging
from typing import Dict, Any, Optional

from openai import OpenAI
from loader import get_prompt

logger = logging.getLogger(__name__)


def _default_client() -> OpenAI:
    """Создаёт клиент OpenAI по умолчанию"""
    return OpenAI(
        base_url=os.getenv("OPENAI_BASE_URL", "https://openrouter.ai/api/v1"),
        api_key=os.getenv("OPENROUTER_API_KEY"),
    )


def moderate_content(text: str, client: Optional[OpenAI] = None) -> Dict[str, Any]:
    """
    Модерирует контент с использованием function calling.
    Возвращает стандартизированный результат по категориям нарушений.
    
    Args:
        text: Текст для модерации
        client: Экземпляр OpenAI клиента (создаёт новый, если не предоставлен)
        
    Returns:
        Словарь с категориями модерации и оценками
    """
    if client is None:
        client = _default_client()
    
    model = os.getenv("MODEL")
    
    try:
        completion = client.chat.completions.create(
            model=model,
            messages=[
                dict(
                    role="user",
                    content=get_prompt("MODERATE_USER", text=text),
                )
            ],
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "content_moderation",
                        "description": "Анализ контента на предмет нарушений для социальной сети",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "violence": {
                                    "type": "object",
                                    "properties": {
                                        "score": {
                                            "type": "number",
                                            "description": "Оценка насилия 0-1",
                                        },
                                        "flags": {
                                            "type": "array",
                                            "items": {"type": "string"},
                                        },
                                    },
                                },
                                "hate_speech": {
                                    "type": "object",
                                    "properties": {
                                        "score": {
                                            "type": "number",
                                            "description": "Оценка разжигания ненависти 0-1",
                                        },
                                        "flags": {
                                            "type": "array",
                                            "items": {"type": "string"},
                                        },
                                    },
                                },
                                "adult_content": {
                                    "type": "object",
                                    "properties": {
                                        "score": {
                                            "type": "number",
                                            "description": "Оценка взрослого контента 0-1",
                                        },
                                        "flags": {
                                            "type": "array",
                                            "items": {"type": "string"},
                                        },
                                    },
                                },
                                "self_harm": {
                                    "type": "object",
                                    "properties": {
                                        "score": {
                                            "type": "number",
                                            "description": "Оценка самоповреждения 0-1",
                                        },
                                        "flags": {
                                            "type": "array",
                                            "items": {"type": "string"},
                                        },
                                    },
                                },
                                "misinformation": {
                                    "type": "object",
                                    "properties": {
                                        "score": {
                                            "type": "number",
                                            "description": "Оценка дезинформации 0-1",
                                        },
                                        "flags": {
                                            "type": "array",
                                            "items": {"type": "string"},
                                        },
                                    },
                                },
                                "government_content": {
                                    "type": "object",
                                    "properties": {
                                        "score": {
                                            "type": "number",
                                            "description": "Оценка контента о власти 0-1",
                                        },
                                        "flags": {
                                            "type": "array",
                                            "items": {"type": "string"},
                                        },
                                    },
                                },
                            },
                            "required": [
                                "violence",
                                "hate_speech",
                                "adult_content",
                                "self_harm",
                                "misinformation",
                                "government_content",
                            ],
                        },
                    },
                }
            ],
            tool_choice={
                "type": "function",
                "function": {"name": "content_moderation"},
            },
            temperature=0.1,
            max_tokens=1000,
        )

        # Извлекаем результат из function call
        tool_call = completion.choices[0].message.tool_calls[0]
        result = json.loads(tool_call.function.arguments)

        logger.info(f"Успешная модерация контента: {text[:50]}...")
        return {"categories": result}

    except Exception as e:
        logger.error(f"Ошибка модерации: {str(e)}")
        return _get_error_response(str(e))


def _get_error_response(error_message: str) -> Dict[str, Any]:
    """Возвращает ответ при ошибке (все категории 1.0 с флагом ошибки)"""
    error_categories = {}
    categories_list = [
        "violence",
        "hate_speech",
        "adult_content",
        "self_harm",
        "misinformation",
        "government_content",
    ]

    for i, category in enumerate(categories_list):
        flags = [error_message] if i == 0 else []
        error_categories[category] = {"score": 1.0, "flags": flags}

    return {"categories": error_categories}


def should_block_content(moderation_result: Dict[str, Any]) -> bool:
    """
    Определяет, нужно ли блокировать контент на основе результатов модерации.
    
    Args:
        moderation_result: Результат от moderate_content()
        
    Returns:
        True если контент должен быть заблокирован, иначе False
    """
    # Либеральные пороги: блокируем только явные/экстремальные нарушения
    thresholds = {
        "violence": 0.97,
        "hate_speech": 0.95,
        "adult_content": 0.97,
        "self_harm": 0.98,
        "misinformation": 0.96,
        "government_content": 0.98,
    }

    for category, threshold in thresholds.items():
        score = moderation_result["categories"][category]["score"]
        if score >= threshold:
            logger.info(f"Контент заблокирован по категории {category}: {score}")
            return True

    return False


def review_summary(text: str, client: Optional[OpenAI] = None) -> Dict[str, Any]:
    """
    Рецензирует готовый дайджест: возвращает approved (bool) и feedback (str)
    с конкретными правками для суммаризатора.
    
    Args:
        text: Текст дайджеста для рецензии
        client: Экземпляр OpenAI клиента (создаёт новый, если не предоставлен)
        
    Returns:
        Словарь с 'approved' (bool) и 'feedback' (str)
    """
    try:
        result = moderate_content(text, client)
        # Очень мягкая логика: одобрять, если нет экстремальных нарушений
        if not should_block_content(result):
            # даже при наличии замечаний даём мягкую обратную связь, но одобряем
            categories = result.get("categories", {})
            issues = []
            for name, data in categories.items():
                score = data.get("score", 0.0)
                flags = data.get("flags", [])
                if score >= 0.85:  # мягкий порог для рекомендаций
                    example = f" ('{flags[0]}')" if flags else ""
                    issues.append(f"{name}: смягчить формулировки{example}")
            feedback = ("Небольшие правки: " + ", ".join(issues)) if issues else ""
            return {"approved": True, "feedback": feedback}

        # Сформировать краткие рекомендации по категориям с высокими оценками
        categories = result.get("categories", {})
        issues = []
        for name, data in categories.items():
            score = data.get("score", 0.0)
            flags = data.get("flags", [])
            if score >= 0.98:  # блокируем только экстремальные случаи
                example = f" ('{flags[0]}')" if flags else ""
                issues.append(
                    f"{name}: удалить или радикально переформулировать проблемные фразы{example}"
                )

        feedback = (
            "Обнови сводку, устранив нарушения: " + ", ".join(issues)
            if issues
            else "Перепроверь нейтральность формулировок и избегай оценочных суждений."
        )
        return {"approved": False, "feedback": feedback}
    except Exception as e:
        logger.error(f"Ошибка review_summary: {e}")
        return {
            "approved": False,
            "feedback": "Не удалось провести модерацию. Смягчи формулировки и проверь нейтральность.",
        }


if __name__ == "__main__":
    # Тестовые кейсы для валидации
    test_cases = ["Какого хрена ты все африканцы не умеют интегрировать?"]

    for test_case in test_cases:
        print(f"\nАнализ: '{test_case}'")

        result = moderate_content(test_case)
        print(f"Результат: {json.dumps(result, indent=2, ensure_ascii=False)}")

        blocked = should_block_content(result)
        status = "ЗАБЛОКИРОВАН" if blocked else "ОДОБРЕН"
        print(f"Статус: {status}")
