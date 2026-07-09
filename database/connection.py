"""
database/connection.py

Подключение к базе данных PostgreSQL через SQLAlchemy 2.x (async).

Обеспечивает:
- Создание асинхронного движка SQLAlchemy
- Управление пулом соединений
- Фабрику асинхронных сессий
- Проверку подключения (health check)
- Корректное закрытие соединений

Использование:
    from database.connection import DatabaseConnection

    db = DatabaseConnection(database_url="postgresql+asyncpg://...")
    await db.connect()
    
    async with db.session() as session:
        result = await session.execute(...)

Python: 3.13+
"""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy import text

from shared.constants import (
    DB_POOL_SIZE,
    DB_MAX_OVERFLOW,
    DB_POOL_RECYCLE,
)
from shared.logger_config import get_server_logger

logger = get_server_logger()


# ============================================================================
# ИСКЛЮЧЕНИЯ БАЗЫ ДАННЫХ
# ============================================================================

class DatabaseConnectionError(Exception):
    """Ошибка подключения к базе данных."""

    def __init__(self, message: str) -> None:
        super().__init__(f"Ошибка подключения к БД: {message}")


class DatabaseNotInitializedError(Exception):
    """База данных не инициализирована."""

    def __init__(self) -> None:
        super().__init__(
            "База данных не инициализирована. Вызовите connect() перед использованием."
        )


# ============================================================================
# ПОДКЛЮЧЕНИЕ К БАЗЕ ДАННЫХ
# ============================================================================

class DatabaseConnection:
    """
    Управление подключением к PostgreSQL.

    Создаёт асинхронный движок SQLAlchemy с пулом соединений
    и предоставляет фабрику сессий для выполнения запросов.

    Attributes:
        database_url: URL подключения к БД.
        engine: Асинхронный движок SQLAlchemy (создаётся при connect()).
        session_factory: Фабрика асинхронных сессий.
        _connected: Флаг успешного подключения.

    Usage:
        db = DatabaseConnection("postgresql+asyncpg://user:pass@localhost:5432/db")
        await db.connect()
        
        async with db.session() as session:
            result = await session.execute(select(User))
    """

    def __init__(
        self,
        database_url: str,
        pool_size: int | None = None,
        max_overflow: int | None = None,
        pool_recycle: int | None = None,
        echo: bool = False,
    ) -> None:
        """
        Инициализация подключения.

        Args:
            database_url: URL подключения (postgresql+asyncpg://...).
            pool_size: Размер пула соединений (по умолчанию DB_POOL_SIZE).
            max_overflow: Дополнительные соединения сверх пула.
            pool_recycle: Время жизни соединения в секундах.
            echo: Логировать SQL-запросы (только для DEBUG).
        """
        self.database_url: str = database_url
        self.pool_size: int = pool_size if pool_size is not None else DB_POOL_SIZE
        self.max_overflow: int = max_overflow if max_overflow is not None else DB_MAX_OVERFLOW
        self.pool_recycle: int = pool_recycle if pool_recycle is not None else DB_POOL_RECYCLE
        self.echo: bool = echo

        self._engine: Optional[AsyncEngine] = None
        self._session_factory: Optional[async_sessionmaker[AsyncSession]] = None
        self._connected: bool = False

    # ========================================================================
    # УПРАВЛЕНИЕ ПОДКЛЮЧЕНИЕМ
    # ========================================================================

    async def connect(self) -> None:
        """
        Установить подключение к базе данных.

        Создаёт движок и фабрику сессий. Проверяет соединение
        тестовым запросом.

        Raises:
            DatabaseConnectionError: Если подключение не удалось.
        """
        if self._connected:
            logger.warning("Подключение к БД уже установлено")
            return

        logger.info(
            "Подключение к PostgreSQL: %s (pool=%d, overflow=%d)",
            self._mask_url(self.database_url),
            self.pool_size,
            self.max_overflow,
        )

        try:
            self._engine = create_async_engine(
                self.database_url,
                pool_size=self.pool_size,
                max_overflow=self.max_overflow,
                pool_recycle=self.pool_recycle,
                pool_pre_ping=True,  # Проверка соединения перед использованием
                echo=self.echo,
            )

            self._session_factory = async_sessionmaker(
                self._engine,
                class_=AsyncSession,
                expire_on_commit=False,
            )

            # Проверка подключения
            await self._health_check()

            self._connected = True
            logger.info("Подключение к PostgreSQL установлено успешно")

        except Exception as e:
            logger.error("Ошибка подключения к PostgreSQL: %s", e)
            raise DatabaseConnectionError(str(e)) from e

    async def disconnect(self) -> None:
        """
        Закрыть подключение к базе данных.

        Освобождает все соединения в пуле и останавливает движок.
        """
        if not self._connected:
            return

        logger.info("Закрытие подключения к PostgreSQL...")

        try:
            if self._engine:
                await self._engine.dispose()
                self._engine = None

            self._session_factory = None
            self._connected = False

            logger.info("Подключение к PostgreSQL закрыто")

        except Exception as e:
            logger.error("Ошибка при закрытии подключения к БД: %s", e)

    async def _health_check(self) -> None:
        """
        Проверить работоспособность подключения тестовым запросом.

        Raises:
            DatabaseConnectionError: Если проверка не пройдена.
        """
        if not self._engine:
            raise DatabaseNotInitializedError()

        try:
            async with self._engine.connect() as conn:
                result = await conn.execute(text("SELECT 1"))
                await result.fetchone()
                logger.debug("Health check БД: OK")
        except Exception as e:
            raise DatabaseConnectionError(
                f"Проверка подключения не пройдена: {e}"
            ) from e

    async def health_check(self) -> bool:
        """
        Проверить работоспособность подключения.

        Returns:
            True, если БД доступна.
        """
        try:
            await self._health_check()
            return True
        except DatabaseConnectionError:
            return False

    # ========================================================================
    # ДОСТУП К СЕССИЯМ
    # ========================================================================

    @property
    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        """
        Получить фабрику асинхронных сессий.

        Returns:
            Фабрика сессий.

        Raises:
            DatabaseNotInitializedError: Если БД не инициализирована.
        """
        if not self._session_factory:
            raise DatabaseNotInitializedError()
        return self._session_factory

    def session(self) -> AsyncSession:
        """
        Создать новую асинхронную сессию.

        Используйте как контекстный менеджер:
            async with db.session() as session:
                ...

        Returns:
            Новая асинхронная сессия.

        Raises:
            DatabaseNotInitializedError: Если БД не инициализирована.
        """
        if not self._session_factory:
            raise DatabaseNotInitializedError()
        return self._session_factory()

    @property
    def engine(self) -> AsyncEngine:
        """
        Получить асинхронный движок SQLAlchemy.

        Returns:
            Движок.

        Raises:
            DatabaseNotInitializedError: Если БД не инициализирована.
        """
        if not self._engine:
            raise DatabaseNotInitializedError()
        return self._engine

    @property
    def is_connected(self) -> bool:
        """Проверить, установлено ли подключение."""
        return self._connected

    # ========================================================================
    # ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ
    # ========================================================================

    @staticmethod
    def _mask_url(url: str) -> str:
        """
        Маскировать пароль в URL для безопасного логирования.

        Args:
            url: URL подключения.

        Returns:
            URL с замаскированным паролем.
        """
        try:
            # Формат: postgresql+asyncpg://user:password@host:port/db
            if "@" in url and "://" in url:
                protocol, rest = url.split("://", 1)
                if "@" in rest:
                    auth, host = rest.split("@", 1)
                    if ":" in auth:
                        user, _ = auth.split(":", 1)
                        auth = f"{user}:***"
                    return f"{protocol}://{auth}@{host}"
            return url
        except Exception:
            return "***"

    def __repr__(self) -> str:
        status = "connected" if self._connected else "disconnected"
        return (
            f"DatabaseConnection(url={self._mask_url(self.database_url)}, "
            f"status={status})"
        )


# ============================================================================
# ФАБРИКА ДЛЯ УДОБНОГО СОЗДАНИЯ
# ============================================================================

async def create_database_connection(
    database_url: str,
    pool_size: int | None = None,
    max_overflow: int | None = None,
    echo: bool = False,
) -> DatabaseConnection:
    """
    Создать и инициализировать подключение к БД.

    Args:
        database_url: URL подключения.
        pool_size: Размер пула.
        max_overflow: Дополнительные соединения.
        echo: Логировать SQL.

    Returns:
        Инициализированный экземпляр DatabaseConnection.
    """
    db = DatabaseConnection(
        database_url=database_url,
        pool_size=pool_size,
        max_overflow=max_overflow,
        echo=echo,
    )
    await db.connect()
    return db