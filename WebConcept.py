# combined_app.py
import asyncio
import json
import os
import datetime
from threading import Thread
from flask import Flask, render_template_string, request, jsonify
from telethon.sync import TelegramClient
from telethon.tl.types import PeerChannel
from openai import OpenAI
from dotenv import load_dotenv
import pytz

# === Загрузка переменных из .env ===
load_dotenv()

# === Настройки ===
PROCESSED_MESSAGES_FILE = "processed_messages.json"
NEWS_CACHE_FILE = "news_cache.json"
WEB_NEWS_FILE = "web_news.json"
POSTING_TIMES = ["00:00"]
TARGET_CHANNEL = "@cho_tam_official"
BACKING_IMAGE = "backing.png"

# === Настройки Telegram клиента ===
api_id = os.getenv("API_ID")
api_hash = os.getenv("API_HASH")
phone = os.getenv("PHONE")

# === Список каналов для отслеживания ===
channel_usernames = ['@fsprussia', '@truetechcommunity', '@phystechunion', '@stfpmi',
                     '@partynewpeople', '@rucodefestival', '@rozetked', '@roscosmos_gk',
                     '@miptru', '@mephi_of', '@naukamsu', '@skolkovolive', '@bmstu1830',
                     '@thecodemedia', '@t_central_university', '@techno_yandex', '@habr_com',
                     '@rosatomru', '@fpmi_students', '@innopolistg', '@vkjobs', '@tb_invest_official']

# === Исправленная инициализация OpenAI / OpenRouter ===
try:
    # Новый способ инициализации для последних версий
    client_ai = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.getenv("OPENROUTER_API_KEY")
    )
except TypeError as e:
    # Старый способ инициализации
    print(f"Используем старый способ инициализации OpenAI: {e}")
    client_ai = OpenAI(
        api_key=os.getenv("OPENROUTER_API_KEY"),
        base_url="https://openrouter.ai/api/v1"
    )

# === Глобальные переменные ===
telegram_client = None
flask_app = None

# === HTML ШАБЛОНЫ ===
INDEX_TEMPLATE = '''
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ЧТАМ ОТ - Дайджест новостей</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background-color: #f5f5f5;
            color: #333;
            line-height: 1.6;
        }

        .header {
            background: white;
            border-bottom: 1px solid #e0e0e0;
            position: sticky;
            top: 0;
            z-index: 100;
        }

        .search-container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }

        .search-box {
            display: flex;
            max-width: 600px;
            margin: 0 auto;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            border-radius: 8px;
            overflow: hidden;
        }

        .search-input {
            flex: 1;
            padding: 12px 16px;
            border: 1px solid #dfe1e5;
            border-right: none;
            border-radius: 8px 0 0 8px;
            font-size: 16px;
            outline: none;
        }

        .search-input:focus {
            border-color: #4285f4;
        }

        .search-button {
            background: #4285f4;
            color: white;
            border: none;
            padding: 12px 24px;
            border-radius: 0 8px 8px 0;
            cursor: pointer;
            font-size: 16px;
        }

        .search-button:hover {
            background: #3367d6;
        }

        .container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }

        .last-updated {
            text-align: center;
            color: #666;
            margin-bottom: 30px;
            font-size: 14px;
        }

        .categories-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
            gap: 24px;
            margin-bottom: 40px;
        }

        .category-card {
            background: white;
            border-radius: 12px;
            padding: 24px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.08);
            transition: transform 0.2s, box-shadow 0.2s;
        }

        .category-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 20px rgba(0,0,0,0.12);
        }

        .category-header {
            display: flex;
            align-items: center;
            margin-bottom: 20px;
            padding-bottom: 16px;
            border-bottom: 2px solid #f0f0f0;
        }

        .category-emoji {
            font-size: 24px;
            margin-right: 12px;
        }

        .category-title {
            font-size: 20px;
            font-weight: 600;
            color: #1a1a1a;
        }

        .news-list {
            space-y: 16px;
        }

        .news-item {
            padding: 16px 0;
            border-bottom: 1px solid #f0f0f0;
        }

        .news-item:last-child {
            border-bottom: none;
        }

        .news-title {
            font-size: 16px;
            font-weight: 500;
            margin-bottom: 8px;
            color: #1a1a1a;
        }

        .news-title a {
            color: inherit;
            text-decoration: none;
        }

        .news-title a:hover {
            color: #4285f4;
        }

        .news-summary {
            font-size: 14px;
            color: #666;
            margin-bottom: 8px;
            line-height: 1.5;
        }

        .news-meta {
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 12px;
            color: #999;
        }

        .news-source {
            font-weight: 500;
        }

        .news-time {
            margin-left: auto;
        }

        .footer {
            text-align: center;
            padding: 40px 20px;
            color: #666;
            font-size: 14px;
        }

        .loading {
            text-align: center;
            padding: 40px;
            color: #666;
        }

        @media (max-width: 768px) {
            .categories-grid {
                grid-template-columns: 1fr;
            }

            .container {
                padding: 16px;
            }

            .search-container {
                padding: 16px;
            }
        }
    </style>
</head>
<body>
    <div class="header">
        <div class="search-container">
            <form action="/search" method="get" class="search-box">
                <input type="text" name="q" class="search-input" placeholder="Поиск в Google..." value="">
                <button type="submit" class="search-button">Найти</button>
            </form>
        </div>
    </div>

    <div class="container">
        {% if news_data.last_updated %}
        <div class="last-updated">
            📅 Последнее обновление: {{ news_data.last_updated }}
        </div>
        {% endif %}

        {% if news_data.categories %}
            <div class="categories-grid">
                {% for category in news_data.categories %}
                <div class="category-card">
                    <div class="category-header">
                        <span class="category-emoji">{{ category.emoji }}</span>
                        <h2 class="category-title">{{ category.title }}</h2>
                    </div>
                    <div class="news-list">
                        {% for news in category.news %}
                        <div class="news-item">
                            <h3 class="news-title">
                                <a href="{{ news.url }}" target="_blank" rel="noopener">
                                    {{ news.title }}
                                </a>
                            </h3>
                            <p class="news-summary">{{ news.summary }}</p>
                            <div class="news-meta">
                                <span class="news-source">{{ news.source }}</span>
                                <span class="news-time">{{ news.time_ago }}</span>
                            </div>
                        </div>
                        {% endfor %}
                    </div>
                </div>
                {% endfor %}
            </div>
        {% else %}
            <div class="loading">
                <p>Новости загружаются...</p>
            </div>
        {% endif %}
    </div>

    <div class="footer">
        <p>ЧТАМ ОТ - Автоматический дайджест новостей</p>
        <p>Обновляется ежедневно из проверенных источников</p>
        <p>© {{ current_year }} ЧТАМ ОТ</p>
    </div>

    <script>
        setTimeout(() => {
            window.location.reload();
        }, 300000);
    </script>
</body>
</html>
'''

SEARCH_TEMPLATE = '''
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Поиск - ЧТАМ ОТ</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background-color: #f5f5f5;
            color: #333;
        }

        .header {
            background: white;
            border-bottom: 1px solid #e0e0e0;
            padding: 20px 0;
        }

        .search-container {
            max-width: 600px;
            margin: 0 auto;
            display: flex;
        }

        .search-input {
            flex: 1;
            padding: 12px 16px;
            border: 1px solid #dfe1e5;
            border-right: none;
            border-radius: 8px 0 0 8px;
            font-size: 16px;
            outline: none;
        }

        .search-button {
            background: #4285f4;
            color: white;
            border: none;
            padding: 12px 24px;
            border-radius: 0 8px 8px 0;
            cursor: pointer;
        }

        .container {
            max-width: 800px;
            margin: 40px auto;
            padding: 0 20px;
            text-align: center;
        }

        .back-link {
            display: inline-block;
            margin-top: 20px;
            color: #4285f4;
            text-decoration: none;
        }

        .back-link:hover {
            text-decoration: underline;
        }
    </style>
</head>
<body>
    <div class="header">
        <div class="search-container">
            <form action="/search" method="get">
                <input type="text" name="q" class="search-input" placeholder="Поиск в Google..." value="{{ query }}">
                <button type="submit" class="search-button">Найти</button>
            </form>
        </div>
    </div>

    <div class="container">
        {% if query %}
            <h2>Результаты поиска для: "{{ query }}"</h2>
            <p>Перенаправление в Google...</p>
            <script>
                setTimeout(() => {
                    window.location.href = 'https://www.google.com/search?q={{ query }}';
                }, 2000);
            </script>
        {% else %}
            <h2>Введите поисковый запрос</h2>
        {% endif %}

        <a href="/" class="back-link">← Вернуться к новостям</a>
    </div>
</body>
</html>
'''


# === Функции работы с данными ===
def load_processed_ids():
    if os.path.exists(PROCESSED_MESSAGES_FILE):
        try:
            with open(PROCESSED_MESSAGES_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except:
            return set()
    return set()


def save_processed_ids(ids):
    with open(PROCESSED_MESSAGES_FILE, "w", encoding="utf-8") as f:
        json.dump(list(ids), f, indent=2)


def load_news_cache():
    if os.path.exists(NEWS_CACHE_FILE):
        try:
            with open(NEWS_CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return []
    return []


def save_news_cache(news):
    with open(NEWS_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(news, f, indent=2, ensure_ascii=False)


def load_web_news():
    if os.path.exists(WEB_NEWS_FILE):
        try:
            with open(WEB_NEWS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Ошибка загрузки новостей: {e}")

    return {
        "categories": [
            {
                "title": "Новости",
                "emoji": "📰",
                "news": [
                    {
                        "title": "Добро пожаловать в ЧТАМ ОТ!",
                        "summary": "Это ваш персональный дайджест новостей из мира технологий, образования и науки. Новости обновляются автоматически.",
                        "source": "ЧТАМ ОТ",
                        "url": "#",
                        "image": "",
                        "time_ago": "только что",
                        "category": "Приветствие"
                    }
                ]
            }
        ],
        "last_updated": "Загрузка...",
        "timestamp": datetime.datetime.now().isoformat()
    }


def save_web_news(news_data):
    with open(WEB_NEWS_FILE, "w", encoding="utf-8") as f:
        json.dump(news_data, f, indent=2, ensure_ascii=False, default=str)


def clear_news_cache():
    if os.path.exists(NEWS_CACHE_FILE):
        os.remove(NEWS_CACHE_FILE)
    return []


# === Альтернативная инициализация OpenAI для старых версий ===
def get_ai_client():
    """Универсальная функция для получения AI клиента"""
    try:
        # Попробуем новый способ
        return OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.getenv("OPENROUTER_API_KEY")
        )
    except TypeError as e:
        # Если новый способ не работает, используем минимальную конфигурацию
        print(f"Используем альтернативную инициализацию OpenAI: {e}")
        return OpenAI(
            api_key=os.getenv("OPENROUTER_API_KEY"),
            base_url="https://openrouter.ai/api/v1"
        )


# === Функция получения структурированных новостей для веба ===
def generate_web_news(news_items):
    if not news_items:
        return {"categories": [], "timestamp": datetime.datetime.now().isoformat()}

    prompt = (
        "Создай структурированный JSON с новостями для веб-сайта в формате Яндекс.Дзен. "
        "Верни ТОЛЬКО JSON без каких-либо пояснений.\n\n"
        "Формат JSON:\n"
        "{\n"
        '  "categories": [\n'
        "    {\n"
        '      "title": "Название категории",\n'
        '      "emoji": "🎓",\n'
        '      "news": [\n'
        "        {\n"
        '          "title": "Заголовок новости",\n'
        '          "summary": "Краткое описание (2-3 предложения)",\n'
        '          "source": "Источник",\n'
        '          "url": "ссылка",\n'
        '          "image": "URL изображения (оставь пустым)",\n'
        '          "time_ago": "2 часа назад",\n'
        '          "category": "Образование"\n'
        "        }\n"
        "      ]\n"
        "    }\n"
        "  ]\n"
        "}\n\n"
        "Требования:\n"
        "- 3-5 категорий (Образование, Наука, Технологии, Студенческая жизнь, Карьера)\n"
        "- В каждой категории 3-5 новостей\n"
        "- Заголовки: яркие, привлекательные, до 100 символов\n"
        "- Описания: информативные, но краткие\n"
        "- Источники: используй реальные названия каналов\n"
        "- Ссылки: в формаite t.me/channel/message_id\n"
        "- time_ago: в формате 'X часов/дней назад'\n\n"
        "Новости для обработки:\n"
    )

    for i, item in enumerate(news_items):
        prompt += f"{i + 1}. {item['text'][:200]}... | Источник: {item['channel_username']} | ID: {item['message_id']}\n"

    try:
        ai_client = get_ai_client()
        completion = ai_client.chat.completions.create(
            model="google/gemini-2.0-flash-exp:free",
            messages=[
                {"role": "system",
                 "content": "Ты - профессиональный редактор новостей. Создавай только валидный JSON."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=4000,
            temperature=0.7
        )

        response_text = completion.choices[0].message.content
        response_text = response_text.replace('```json', '').replace('```', '').strip()

        news_data = json.loads(response_text)
        news_data["timestamp"] = datetime.datetime.now().isoformat()
        news_data["last_updated"] = datetime.datetime.now(pytz.timezone('Europe/Moscow')).strftime("%d.%m.%Y %H:%M")

        return news_data

    except Exception as e:
        print(f"Ошибка при генерации веб-новостей: {e}")
        return {
            "categories": [
                {
                    "title": "Технологии",
                    "emoji": "🚀",
                    "news": [
                        {
                            "title": "Новости обновляются",
                            "summary": "В настоящее время происходит обновление новостной ленты. Попробуйте обновить страницу через несколько минут.",
                            "source": "Система",
                            "url": "#",
                            "image": "",
                            "time_ago": "только что",
                            "category": "Система"
                        }
                    ]
                }
            ],
            "timestamp": datetime.datetime.now().isoformat(),
            "last_updated": datetime.datetime.now(pytz.timezone('Europe/Moscow')).strftime("%d.%m.%Y %H:%M")
        }


# === Функция получения краткого резюме для Telegram ===
def summarize_news(news_items):
    if not news_items:
        return ""

    prompt = (
        "Создай краткий дайджест новостей для Telegram-канала в формате Markdown."
        "Сгруппируй новости по 3-5 темам. Для каждой темы:\n\n"
        "1. **Заголовок**: 2-3 эмодзи + название темы (жирным)\n"
        "2. **Новости**: 2-4 пункта в формате:\n"
        "   • Краткое описание [источник](ссылка)\n\n"
        "**Требования:**\n"
        "• Только самые важные новости\n"
        "• Максимально краткие формулировки\n"
        "• Ссылки в формате Markdown: [текст](url)\n"
        "• Разделитель между темами\n"
        "• Без нумерации, дат и лишних деталей\n\n"
        "**Пример формата:**\n"
        "**🚀 Космос**\n"
        "• Прогресс МС-32 пристыковался к МКС [Роскосмос](t.me/roscosmos_gk/18301)\n"
        "• Открытие Национального космического центра [FAKY](https://old.mipt.ru/dasr/)\n"
        "\n\n"
        "**🎓 Образование**\n"
        "• Новая магистратура по биотехнологиям [МФТИ](t.me/miptru/8802)\n\n"
        "Новости для обработки:\n"
    )

    for i, item in enumerate(news_items):
        prompt += f"{i + 1}. {item['text']} t.me/{item['channel_username'].replace('@', '')}/{item['message_id']}\n\n"

    try:
        ai_client = get_ai_client()
        completion = ai_client.chat.completions.create(
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


# === Основная функция сбора новостей ===
def collect_news():
    global telegram_client

    if telegram_client is None:
        telegram_client = TelegramClient(phone, api_id, api_hash)
        telegram_client.start()

    processed_ids = load_processed_ids()
    news_cache = load_news_cache()
    new_news_collected = False

    for username in channel_usernames:
        try:
            entity = telegram_client.get_entity(username)
            messages = telegram_client.get_messages(entity, limit=10)

            for msg in messages:
                if msg.id not in processed_ids and msg.text and msg.text.strip():
                    news_item = {
                        'text': msg.text,
                        'channel_username': username,
                        'message_id': msg.id,
                        'timestamp': datetime.datetime.now().isoformat()
                    }
                    news_cache.append(news_item)
                    processed_ids.add(msg.id)
                    new_news_collected = True
                    print(f"Новость добавлена из {username}")
        except Exception as e:
            print(f"Ошибка при получении данных из {username}: {e}")

    if new_news_collected:
        save_news_cache(news_cache)
        save_processed_ids(processed_ids)

        web_news = generate_web_news(news_cache)
        save_web_news(web_news)
        print("Веб-новости успешно сгенерированы")

    return new_news_collected


# === Публикация сводки в Telegram ===
def publish_summary():
    global telegram_client

    if telegram_client is None:
        telegram_client = TelegramClient(phone, api_id, api_hash)
        telegram_client.start()

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
                    telegram_client.send_file(
                        TARGET_CHANNEL,
                        BACKING_IMAGE,
                        caption=full_message,
                        link_preview=False
                    )
                    print(f"Изображение с заголовком отправлено в {TARGET_CHANNEL}")
                else:
                    telegram_client.send_message(
                        TARGET_CHANNEL,
                        full_message,
                        link_preview=False
                    )
                    print(f"Сводка без изображения опубликована в {TARGET_CHANNEL}")
                clear_news_cache()
                print("Кэш новостей очищен после публикации")
            except Exception as e:
                telegram_client.send_message(
                    TARGET_CHANNEL,
                    full_message,
                    link_preview=False
                )
                print(f"Ошибка при публикации в канал: {e}")
    else:
        print("Нет новостей для публикации")


# === Проверка времени для публикации ===
def should_post_now():
    moscow_tz = pytz.timezone('Europe/Moscow')
    now = datetime.datetime.now(moscow_tz).strftime("%H:%M")
    return now in POSTING_TIMES


# === Фоновая задача для бота ===
def bot_worker():
    print("Запуск новостного бота в фоновом режиме...")

    while True:
        try:
            # Собираем новости каждый час
            collect_news()
            print(f"Сбор новостей завершен в {datetime.datetime.now().strftime('%H:%M')}")

            # Проверяем время публикации
            if should_post_now():
                print("Время публикации! Отправляем сводку...")
                publish_summary()

            # Ждем 1 час до следующей проверки
            import time
            time.sleep(3600)

        except Exception as e:
            print(f"Ошибка в боте: {e}")
            import time
            time.sleep(300)


# === Создание Flask приложения ===
def create_flask_app():
    app = Flask(__name__)

    @app.route('/')
    def index():
        news_data = load_web_news()
        current_year = datetime.datetime.now().year
        return render_template_string(INDEX_TEMPLATE, news_data=news_data, current_year=current_year)

    @app.route('/api/news')
    def api_news():
        news_data = load_web_news()
        return jsonify(news_data)

    @app.route('/search')
    def search():
        query = request.args.get('q', '')
        return render_template_string(SEARCH_TEMPLATE, query=query)

    return app


# === Основная функция ===
def main():
    global flask_app

    print("Запуск комбинированного приложения...")
    print("1. Инициализация Telegram клиента...")

    # Запускаем бота в отдельном потоке
    bot_thread = Thread(target=bot_worker, daemon=True)
    bot_thread.start()

    print("2. Запуск Flask сервера...")
    flask_app = create_flask_app()
    flask_app.run(debug=False, host='0.0.0.0', port=5000)


if __name__ == "__main__":
    main()
