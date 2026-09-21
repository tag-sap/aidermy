# conftest.py — общая подготовка тестов.
# Применяет миграции схемы БД (init_db) перед прогоном тестов, чтобы тесты
# не зависели от устаревшего снапшота aidermy.db в репозитории.

from app.database import init_db


def pytest_sessionstart(session):
    init_db()
