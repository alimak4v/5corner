from telethon.sync import TelegramClient
from telethon.tl.types import PeerChannel
from openai import OpenAI
import time
import json
import os
import datetime
from dotenv import load_dotenv
import pytz

# === Загрузка переменных из .env ===
load_dotenv()

# === Настройки ===
PROCESSED_MESSAGES_FILE = "processed_messages.json"
NEWS_CACHE_FILE = "news_cache.json"
POSTING_TIMES = ["00:00"]
# @test_news5          @cho_tam_official
TARGET_CHANNEL = "@cho_tam_official"
BACKING_IMAGE = "backing.png"  # Путь к изображению для прикрепления

# === Настройки Telegram клиента ===
api_id = os.getenv("API_ID")
api_hash = os.getenv("API_HASH")
phone = os.getenv("PHONE")
client_tg = TelegramClient(phone, api_id, api_hash)
client_tg.start()

# === Список каналов для отслеживания ===
channel_usernames = ['@fsprussia',
                     '@truetechcommunity',
                     '@phystechunion',
                     '@stfpmi',
                     '@partynewpeople',
                     '@rucodefestival',
                     '@rozetked',
                     '@roscosmos_gk',
                     '@miptru',
                     '@mephi_of',
                     '@naukamsu',
                     '@skolkovolive',
                     '@bmstu1830',
                     '@thecodemedia',
                     '@t_central_university',
                     '@techno_yandex',
                     '@habr_com',
                     '@rosatomru',
                     '@fpmi_students',
                     '@innopolistg',
                     '@vkjobs',
                     '@tb_invest_official']

# === Настройки OpenAI / OpenRouter ===
# ИСПРАВЛЕНО: убраны лишние пробелы в URL
client_ai = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY")
)


# === Функции работы с данными ===
def load_processed_ids():
    """Загружает ID обработанных сообщений"""
    if os.path.exists(PROCESSED_MESSAGES_FILE):
        try:
            with open(PROCESSED_MESSAGES_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except:
            return set()
    return set()


def save_processed_ids(ids):
    """Сохраняет ID обработанных сообщений"""
    with open(PROCESSED_MESSAGES_FILE, "w", encoding="utf-8") as f:
        json.dump(list(ids), f, indent=2)


def load_news_cache():
    """Загружает накопленные новости из кэша"""
    if os.path.exists(NEWS_CACHE_FILE):
        try:
            with open(NEWS_CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return []
    return []


def save_news_cache(news):
    """Сохраняет накопленные новости в кэш"""
    with open(NEWS_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(news, f, indent=2, ensure_ascii=False)


def clear_news_cache():
    """Очищает кэш новостей после публикации"""
    if os.path.exists(NEWS_CACHE_FILE):
        os.remove(NEWS_CACHE_FILE)
    return []


# === Функция получения краткого резюме от ИИ ===
def summarize_news(news_items):
    """Генерирует краткую сводку из собранных новостей"""
    if not news_items:
        return ""

    prompt = (
        "Создай краткий дайджест новостей для Telegram-канала в формате Markdown."
        "Сгруппируй новости по 3-5 темам. Для каждой темы:\n\n"
        "1. **Заголовок**: 2-3 эмодзи + название темы (жирным)\n"
        "2. **Новости**: 2-4 пункта в формате:\n"
        "   • Краткое описание [источник](ссылка)\n\n"
        "     ```анализ новости```"
        "**Требования:**\n"
        "• Только самые важные новости\n"
        "• Максимально краткие формулировки\n"
        "• Ссылки в формате Markdown: [текст](url)\n"
        "• Разделитель \n\n между темами\n"
        "• Без нумерации, дат и лишних деталей\n\n"
        "**Пример формата:**\n"
        "**🚀 Космос**\n"
        "• Прогресс МС-32 пристыковался к МКС [Роскосмос](t.me/roscosmos_gk/18301)\n"
        "• Открытие Национального космического центра [FAKY](https://old.mipt.ru/dasr/)\n"
        "``` Космический центр - ...(краткий анализ ЛИШЬ САМЫХ ВАЖНЫХ для студентов новостей) ```"
        "\n\n"
        "**🎓 Образование**\n"
        "• Новая магистратура по биотехнологиям [МФТИ](t.me/miptru/8802)\n\n"
        "Новости для обработки:\n"
    )

    for i, item in enumerate(news_items):
        prompt += f"{i + 1}. {item['text']} t.me/{item['channel_username'].replace('@', '')}/{item['message_id']}\n\n"

    try:
        completion = client_ai.chat.completions.create(
            model="google/gemini-2.0-flash-exp:free",
            messages=[
                {"role": "system",
                 "content": "Вы — опытный аналитик новостей, который профессионально отбирает самые важные новости и группирует их по темам."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1024,
            temperature=0.1
        )
        return completion.choices[0].message.content
    except Exception as e:
        print(f"Ошибка при генерации сводки: {e}")
        return "Ошибка при генерации сводки. Попробуйте позже."


# === Проверка времени для публикации ===
def should_post_now():
    """Проверяет, нужно ли публиковать сводку сейчас"""
    moscow_tz = pytz.timezone('Europe/Moscow')
    now = datetime.datetime.now(moscow_tz).strftime("%H:%M")
    return now in POSTING_TIMES


# === Основная функция сбора новостей ===
def collect_news():
    """Собирает новые сообщения из отслеживаемых каналов"""
    processed_ids = load_processed_ids()
    news_cache = load_news_cache()
    new_news_collected = False

    for username in channel_usernames:
        try:
            entity = client_tg.get_entity(username)
            messages = client_tg.get_messages(entity, limit=13)

            for msg in messages:
                if msg.id not in processed_ids and msg.text and msg.text.strip():
                    news_cache.append({
                        'text': msg.text,
                        'channel_username': username,
                        'message_id': msg.id,
                        'timestamp': datetime.datetime.now().isoformat()
                    })
                    processed_ids.add(msg.id)
                    new_news_collected = True
                    print(f"Новость добавлена из {username}")
        except Exception as e:
            print(f"Ошибка при получении данных из {username}: {e}")

    if new_news_collected:
        save_news_cache(news_cache)
        save_processed_ids(processed_ids)

    return new_news_collected


# === Публикация сводки и очистка кэша ===
def publish_summary():
    """Публикует сводку и очищает кэш"""
    news_cache = load_news_cache()
    if news_cache:
        print(f"Подготовка сводки из {len(news_cache)} новостей...")
        summary = summarize_news(news_cache)
        now = datetime.datetime.now(pytz.timezone('Europe/Moscow')).strftime("%d.%m.%Y")
        header = f"#ЧЕТАМ_ОТ {now}\n\n"
        full_message = header + summary
        print(full_message)

        if summary:
            try:
                if os.path.exists(BACKING_IMAGE):
                    short_caption = full_message
                    client_tg.send_file(
                        TARGET_CHANNEL,
                        BACKING_IMAGE,
                        caption=short_caption,
                        link_preview=False
                    )
                    print(f"Изображение с заголовком отправлено в {TARGET_CHANNEL}")
                else:
                    client_tg.send_message(
                        TARGET_CHANNEL,
                        full_message,
                        link_preview=False
                    )
                    print(f"Сводка без изображения опубликована в {TARGET_CHANNEL} (файл {BACKING_IMAGE} не найден)")
                clear_news_cache()
                print("Кэш новостей очищен после публикации")
            except Exception as e:
                client_tg.send_message(
                    TARGET_CHANNEL,
                    full_message,
                    link_preview=False
                )
                print(f"Ошибка при публикации в канал: {e}")
    else:
        print("Нет новостей для публикации")


# === Основной цикл ===
def main():
    print("Запуск новостного бота...")
    print(f"Будет публиковать сводки в: {', '.join(POSTING_TIMES)} по московскому времени")

    # Проверяем наличие файла с изображением
    if os.path.exists(BACKING_IMAGE):
        print(f"Изображение {BACKING_IMAGE} будет прикрепляться к постам")
    else:
        print(f"Внимание: файл {BACKING_IMAGE} не найден, посты будут публиковаться без изображения")

    # Загружаем уже обработанные ID
    processed_ids = load_processed_ids()
    print(f"Загружено {len(processed_ids)} обработанных сообщений")

    collect_news()
    print(f"Время публикации! ({datetime.datetime.now(pytz.timezone('Europe/Moscow')).strftime('%H:%M')})")
    publish_summary()


if __name__ == "__main__":
    main()
