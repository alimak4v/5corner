"""
Модуль для загрузки и форматирования промптов из prompts.txt
"""
import os
from typing import Dict

_PROMPTS_CACHE: Dict[str, str] = {}


def _load_prompts() -> Dict[str, str]:
    """Загружает все промпты из prompts.txt в словарь"""
    if _PROMPTS_CACHE:
        return _PROMPTS_CACHE
    
    prompts_file = os.path.join(os.path.dirname(__file__), "prompts.txt")
    
    with open(prompts_file, "r", encoding="utf-8") as f:
        content = f.read()
    
    current_key = None
    current_lines = []
    
    for line in content.split("\n"):
        if line.startswith("[") and line.endswith("]"):
            # Сохраняем предыдущий промпт, если существует
            if current_key:
                _PROMPTS_CACHE[current_key] = "\n".join(current_lines).strip()
            # Начинаем новый промпт
            current_key = line[1:-1]
            current_lines = []
        elif current_key and not line.startswith("#"):
            current_lines.append(line)
    
    # Сохраняем последний промпт
    if current_key:
        _PROMPTS_CACHE[current_key] = "\n".join(current_lines).strip()
    
    return _PROMPTS_CACHE


def get_prompt(key: str, **kwargs) -> str:
    """
    Получает промпт по ключу и форматирует его с переданными аргументами
    
    Args:
        key: Ключ промпта (например, "RATE_SYSTEM", "SUMMARIZE_USER")
        **kwargs: Переменные для форматирования промпта
    
    Returns:
        Отформатированная строка промпта
    """
    prompts = _load_prompts()
    
    if key not in prompts:
        raise KeyError(f"Ключ промпта '{key}' не найден в prompts.txt")
    
    template = prompts[key]
    
    # Форматируем с аргументами, если они есть
    if kwargs:
        return template.format(**kwargs)
    
    return template
