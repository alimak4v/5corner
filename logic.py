import datetime
import json
import logging
import os
from typing import Any, Dict, List

import pytz
from telethon.sync import TelegramClient
from openai import OpenAI

from censure import moderate_content, should_block_content, review_summary
from dedup import deduplicate_news
from format import format_for_telegram
from rate import rate_batch, RatingResult
from summarize import summarize_news

logger = logging.getLogger(__name__)

# === Настройки ===
PROCESSED_MESSAGES_FILE = "processed_messages.json"
NEWS_CACHE_FILE = "news_cache.json"
POSTING_TIMES = ["00:00"]
TARGET_CHANNEL = os.getenv("TARGET_CHANNEL", "@cho_tam_official")

# === Настройки Telegram клиента ===
api_id = int(os.getenv("API_ID"))
api_hash = os.getenv("API_HASH")
phone = os.getenv("PHONE")
client_tg = TelegramClient(phone, api_id, api_hash)
client_tg.start()

# === Настройки OpenAI / OpenRouter ===
client_ai = OpenAI(
    base_url=os.getenv("OPENAI_BASE_URL", "https://openrouter.ai/api/v1"),
    api_key=os.getenv("OPENROUTER_API_KEY"),
)

# === Список каналов для отслеживания ===
channel_usernames = [
    "@fsprussia",
    "@truetechcommunity",
    "@phystechunion",
    "@stfpmi",
    "@partynewpeople",
    "@rucodefestival",
    "@rozetked",
    "@roscosmos_gk",
    "@miptru",
    "@mephi_of",
    "@naukamsu",
    "@skolkovolive",
    "@bmstu1830",
    "@thecodemedia",
    "@t_central_university",
    "@techno_yandex",
    "@habr_com",
    "@rosatomru",
    "@fpmi_students",
    "@innopolistg",
    "@vkjobs",
    "@tb_invest_official",
]


# === Функции работы с данными ===
def load_processed_ids() -> set:
    """Загружает множество ID обработанных сообщений"""
    if os.path.exists(PROCESSED_MESSAGES_FILE):
        try:
            with open(PROCESSED_MESSAGES_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except:
            return set()
    return set()


def save_processed_ids(ids: set) -> None:
    """Сохраняет множество ID обработанных сообщений"""
    with open(PROCESSED_MESSAGES_FILE, "w", encoding="utf-8") as f:
        json.dump(list(ids), f, indent=2)


def load_news_cache() -> List[Dict[str, Any]]:
    """Загружает накопленные новости из кэша на диске"""
    if os.path.exists(NEWS_CACHE_FILE):
        try:
            with open(NEWS_CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return []
    return []


def save_news_cache(news: List[Dict[str, Any]]) -> None:
    """Сохраняет накопленные новости в кэш на диске"""
    with open(NEWS_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(news, f, indent=2, ensure_ascii=False)


def clear_news_cache() -> List[Dict[str, Any]]:
    """Очищает кэш новостей после успешной публикации"""
    if os.path.exists(NEWS_CACHE_FILE):
        os.remove(NEWS_CACHE_FILE)
    return []


def select_top_news(
    news_items: List[Dict[str, Any]], top_n: int = 15
) -> List[Dict[str, Any]]:
    """Оценивает новости с помощью агента и возвращает топ-N по рейтингу"""
    rated_news = []

    try:
        ratings: List[RatingResult] = rate_batch(
            [item["text"] for item in news_items], client_ai
        )
        for item, rating in zip(news_items, ratings):
            item_with_rating = {
                **item,
                "rating_score": rating.score,
                "rating_reason": rating.reasoning,
            }
            rated_news.append(item_with_rating)
    except Exception as e:
        logger.error(f"Ошибка при пакетной оценке новостей: {e}")

    rated_news.sort(key=lambda x: x.get("rating_score", 0.0), reverse=True)

    if len(rated_news) > top_n:
        rated_news = rated_news[:top_n]

    logger.info(f"Отобрано {len(rated_news)} лучших новостей из {len(news_items)}")
    return rated_news


def should_post_now() -> bool:
    """Проверяет, нужно ли публиковать дайджест по расписанию"""
    moscow_tz = pytz.timezone("Europe/Moscow")
    now = datetime.datetime.now(moscow_tz).strftime("%H:%M")
    return now in POSTING_TIMES


def collect_news() -> bool:
    """Собирает новые сообщения из отслеживаемых Telegram каналов"""
    processed_ids = load_processed_ids()
    news_cache = load_news_cache()
    new_news_collected = False

    for username in channel_usernames:
        try:
            entity = client_tg.get_entity(username)
            messages = client_tg.get_messages(entity, limit=13)

            for msg in messages:
                if msg.id not in processed_ids and msg.text and msg.text.strip():
                    news_cache.append(
                        {
                            "text": msg.text,
                            "channel_username": username,
                            "message_id": msg.id,
                            "timestamp": datetime.datetime.now().isoformat(),
                        }
                    )
                    processed_ids.add(msg.id)
                    new_news_collected = True
                    logger.info(f"Новость добавлена из {username}")
        except Exception as e:
            logger.error(f"Ошибка при получении данных из {username}: {e}")

    if new_news_collected:
        save_news_cache(news_cache)
        save_processed_ids(processed_ids)

    return new_news_collected


def publish_summary() -> None:
    """Публикует обработанный дайджест в Telegram и очищает кэш новостей"""
    news_cache = load_news_cache()
    if news_cache:
        logger.info(f"Подготовка сводки из {len(news_cache)} новостей...")
        news_cache = deduplicate_news(news_cache, client_ai)
        best_news = select_top_news(news_cache)
        if not best_news:
            logger.warning("Нет новостей после отбора для суммаризации")
            return

        # Итеративная модерация и правки (до 5 циклов)
        summary = summarize_news(best_news, client_ai)
        feedback = ""
        for attempt in range(5):
            if not summary or not summary.strip():
                logger.error("Суммаризатор вернул пустой результат")
                return
            review = review_summary(summary, client_ai)
            if review.get("approved"):
                break
            feedback = review.get("feedback", "")
            logger.info(f"Модератор просит правки (итерация {attempt+1}): {feedback}")
            summary = summarize_news(best_news, client_ai, feedback=feedback)

        formatted_summary = format_for_telegram(summary, client_ai)
        if not formatted_summary or not formatted_summary.strip():
            logger.error("Форматирование вернуло пустой результат")
            return

        now = datetime.datetime.now(pytz.timezone("Europe/Moscow")).strftime("%d.%m.%Y")

        # Финальная проверка отформатированного текста
        try:
            moderation_result = moderate_content(formatted_summary, client_ai)
            if should_block_content(moderation_result):
                logger.warning(
                    "Сводка отклонена финальной модерацией и не будет опубликована."
                )
                return
        except Exception as e:
            logger.error(f"Ошибка финальной модерации: {e}")
            return

        header = f"#ЧЕТАМ_ОТ {now}\n\n"
        full_message = header + formatted_summary

        try:
            client_tg.send_message(TARGET_CHANNEL, full_message, link_preview=False)
            logger.info(f"Сводка опубликована в {TARGET_CHANNEL}")
            clear_news_cache()
            logger.info("Кэш новостей очищен после публикации")
        except Exception as e:
            logger.error(f"Ошибка при публикации в канал: {e}")
    else:
        logger.warning("Нет новостей для публикации")
