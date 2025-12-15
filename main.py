import logging
from dotenv import load_dotenv

load_dotenv()

from logic import collect_news, publish_summary

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def main() -> None:
    """Основной цикл приложения"""
    logger.info("Запуск новостного бота...")
    logger.info("Будет публиковать сводки по расписанию")
    collect_news()
    logger.info("Сбор новостей завершён")
    publish_summary()


if __name__ == "__main__":
    main()
