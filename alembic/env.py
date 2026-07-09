"""
alembic/env.py

Конфигурация окружения Alembic для работы с асинхронным SQLAlchemy 2.x.

Обеспечивает:
- Поддержку async движка (asyncpg)
- Автоматическое обнаружение моделей из database.models
- Создание и применение миграций в асинхронном режиме

Использование:
    alembic revision --autogenerate -m "description"
    alembic upgrade head
    alembic downgrade -1

Python: 3.13+
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Импорт Base и всех моделей для autogenerate
from database.models import Base
from shared.env_config import load_env_config

# Загрузка конфигурации Alembic
config = context.config

# Настройка логирования из файла конфигурации
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Загружаем .env конфигурацию для получения URL БД
env_config = load_env_config()

# Устанавливаем URL подключения
config.set_main_option("sqlalchemy.url", env_config.DATABASE_URL)

# Метаданные для autogenerate
target_metadata = Base.metadata

# Исключаем таблицы Alembic из autogenerate (если нужно)
# target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """
    Запуск миграций в офлайн-режиме.

    Создаёт SQL-скрипт без подключения к БД.
    Используется для генерации скриптов миграции.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """
    Выполнить миграции с существующим подключением.

    Args:
        connection: Соединение с БД.
    """
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """
    Запуск миграций в асинхронном режиме.

    Создаёт асинхронный движок и выполняет миграции.
    """
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = env_config.DATABASE_URL

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """
    Запуск миграций в онлайн-режиме.

    Подключается к БД и применяет миграции.
    """
    asyncio.run(run_async_migrations())


# Выбор режима запуска
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()