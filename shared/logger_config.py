"""
shared/logger_config.py

Централизованная конфигурация логирования для проекта "Миллиардер".

Создаёт и настраивает отдельные логгеры для каждого аспекта системы:
- server.log     — запуск, остановка, общие события сервера
- game.log       — игровые события, ходы, покупки
- network.log    — подключения, отключения, пакеты
- security.log   — попытки взлома, подозрительная активность
- admin.log      — админ-команды
- chat.log       — сообщения чата

Все логгеры настроены на ротацию по размеру файла с сохранением
заданного количества архивных копий.

Использование:
    from shared.logger_config import (
        get_server_logger,
        get_game_logger,
        get_network_logger,
        get_security_logger,
        get_admin_logger,
        get_chat_logger,
        setup_all_loggers,
    )

    # Настройка всех логгеров при запуске
    setup_all_loggers(log_dir="logs", log_level="INFO")

    # Получение логгера
    logger = get_game_logger()
    logger.info("Игра началась")

Python: 3.13+
"""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional


# ============================================================================
# КОНСТАНТЫ ЛОГИРОВАНИЯ
# ============================================================================

# Имена логгеров
SERVER_LOGGER_NAME: str = "billionaire.server"
GAME_LOGGER_NAME: str = "billionaire.game"
NETWORK_LOGGER_NAME: str = "billionaire.network"
SECURITY_LOGGER_NAME: str = "billionaire.security"
ADMIN_LOGGER_NAME: str = "billionaire.admin"
CHAT_LOGGER_NAME: str = "billionaire.chat"

# Имена файлов логов
SERVER_LOG_FILENAME: str = "server.log"
GAME_LOG_FILENAME: str = "game.log"
NETWORK_LOG_FILENAME: str = "network.log"
SECURITY_LOG_FILENAME: str = "security.log"
ADMIN_LOG_FILENAME: str = "admin.log"
CHAT_LOG_FILENAME: str = "chat.log"

# Формат сообщений лога
LOG_FORMAT: str = (
    "%(asctime)s | %(levelname)-8s | %(name)-28s | "
    "%(funcName)-24s | %(message)s"
)

# Формат даты в логах
LOG_DATE_FORMAT: str = "%Y-%m-%d %H:%M:%S"

# Максимальный размер одного файла лога (10 МБ)
LOG_MAX_BYTES: int = 10_485_760

# Количество файлов ротации логов
LOG_BACKUP_COUNT: int = 5

# Уровень логирования для корневого логгера
ROOT_LOG_LEVEL: int = logging.WARNING


# ============================================================================
# НАСТРОЙКА ЛОГГЕРОВ
# ============================================================================

class LogManager:
    """
    Менеджер логирования.

    Управляет созданием, настройкой и получением всех логгеров проекта.
    Гарантирует, что каждый логгер настраивается только один раз.
    """

    _initialized: bool = False
    _log_dir: str = "logs"
    _log_level: str = "INFO"
    _console_output: bool = False

    @classmethod
    def setup(
        cls,
        log_dir: str = "logs",
        log_level: str = "INFO",
        console_output: bool = False,
    ) -> None:
        """
        Единоразовая настройка всех логгеров проекта.

        Создаёт директорию для логов, настраивает форматтеры и обработчики
        для каждого специализированного логгера.

        Args:
            log_dir: Путь к директории для хранения лог-файлов.
            log_level: Уровень логирования (DEBUG, INFO, WARNING, ERROR, CRITICAL).
            console_output: Дублировать ли логи в stdout (удобно при разработке).

        Note:
            Метод идемпотентен — повторный вызов не создаёт дублирующих обработчиков.
        """
        if cls._initialized:
            return

        cls._log_dir = log_dir
        cls._log_level = log_level.upper()
        cls._console_output = console_output

        # Создаём директорию для логов
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)

        # Настраиваем корневой логгер
        root_logger = logging.getLogger()
        root_logger.setLevel(ROOT_LOG_LEVEL)

        # Удаляем стандартный обработчик, если он есть
        if root_logger.handlers:
            root_logger.handlers.clear()

        # Настраиваем специализированные логгеры
        cls._setup_logger(
            name=SERVER_LOGGER_NAME,
            filename=SERVER_LOG_FILENAME,
        )
        cls._setup_logger(
            name=GAME_LOGGER_NAME,
            filename=GAME_LOG_FILENAME,
        )
        cls._setup_logger(
            name=NETWORK_LOGGER_NAME,
            filename=NETWORK_LOG_FILENAME,
        )
        cls._setup_logger(
            name=SECURITY_LOGGER_NAME,
            filename=SECURITY_LOG_FILENAME,
        )
        cls._setup_logger(
            name=ADMIN_LOGGER_NAME,
            filename=ADMIN_LOG_FILENAME,
        )
        cls._setup_logger(
            name=CHAT_LOGGER_NAME,
            filename=CHAT_LOG_FILENAME,
        )

        cls._initialized = True

        # Логируем факт инициализации
        server_logger = logging.getLogger(SERVER_LOGGER_NAME)
        server_logger.info(
            "Логирование настроено. Директория: %s, уровень: %s",
            os.path.abspath(log_dir),
            log_level,
        )

    @classmethod
    def _setup_logger(
        cls,
        name: str,
        filename: str,
    ) -> logging.Logger:
        """
        Настройка одного логгера с файловым и опционально консольным выводом.

        Args:
            name: Имя логгера.
            filename: Имя файла лога (без пути).

        Returns:
            Настроенный экземпляр logging.Logger.
        """
        logger = logging.getLogger(name)
        logger.setLevel(getattr(logging, cls._log_level, logging.INFO))
        logger.propagate = False  # Не передаём сообщения корневому логгеру

        # Проверяем, не настроен ли уже этот логгер
        if logger.handlers:
            return logger

        # Файловый обработчик с ротацией
        file_path = os.path.join(cls._log_dir, filename)
        file_handler = RotatingFileHandler(
            filename=file_path,
            maxBytes=LOG_MAX_BYTES,
            backupCount=LOG_BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setLevel(getattr(logging, cls._log_level, logging.INFO))
        file_formatter = logging.Formatter(
            fmt=LOG_FORMAT,
            datefmt=LOG_DATE_FORMAT,
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

        # Консольный обработчик (опционально)
        if cls._console_output:
            console_handler = logging.StreamHandler()
            console_handler.setLevel(getattr(logging, cls._log_level, logging.INFO))
            console_formatter = logging.Formatter(
                fmt="%(levelname)-8s | %(name)-28s | %(message)s",
                datefmt=LOG_DATE_FORMAT,
            )
            console_handler.setFormatter(console_formatter)
            logger.addHandler(console_handler)

        return logger

    @classmethod
    def get_logger(cls, name: str) -> logging.Logger:
        """
        Получить логгер по имени.

        Если логгер не был настроен, возвращает логгер с базовой конфигурацией.

        Args:
            name: Имя логгера.

        Returns:
            Экземпляр logging.Logger.
        """
        logger = logging.getLogger(name)
        if not logger.handlers and not cls._initialized:
            # Базовая настройка для непредусмотренных логгеров
            logger.setLevel(logging.WARNING)
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(logging.Formatter(LOG_FORMAT))
            logger.addHandler(console_handler)
        return logger

    @classmethod
    def set_log_level(cls, log_level: str) -> None:
        """
        Изменить уровень логирования для всех логгеров.

        Args:
            log_level: Новый уровень логирования (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        """
        level = getattr(logging, log_level.upper(), logging.INFO)
        cls._log_level = log_level.upper()

        for logger_name in [
            SERVER_LOGGER_NAME,
            GAME_LOGGER_NAME,
            NETWORK_LOGGER_NAME,
            SECURITY_LOGGER_NAME,
            ADMIN_LOGGER_NAME,
            CHAT_LOGGER_NAME,
        ]:
            logger = logging.getLogger(logger_name)
            logger.setLevel(level)
            for handler in logger.handlers:
                handler.setLevel(level)

    @classmethod
    def shutdown(cls) -> None:
        """
        Корректное завершение логирования.

        Закрывает все обработчики и очищает состояние.
        Вызывается при остановке сервера.
        """
        for logger_name in [
            SERVER_LOGGER_NAME,
            GAME_LOGGER_NAME,
            NETWORK_LOGGER_NAME,
            SECURITY_LOGGER_NAME,
            ADMIN_LOGGER_NAME,
            CHAT_LOGGER_NAME,
        ]:
            logger = logging.getLogger(logger_name)
            for handler in logger.handlers[:]:
                handler.close()
                logger.removeHandler(handler)

        cls._initialized = False


# ============================================================================
# ФУНКЦИИ ПОЛУЧЕНИЯ ЛОГГЕРОВ
# ============================================================================

def get_server_logger() -> logging.Logger:
    """
    Получить логгер серверных событий.

    Используется для: запуск/остановка сервера, инициализация модулей,
    общие информационные сообщения.

    Returns:
        Логгер server.log.
    """
    return LogManager.get_logger(SERVER_LOGGER_NAME)


def get_game_logger() -> logging.Logger:
    """
    Получить логгер игровых событий.

    Используется для: ходы игроков, броски кубиков, покупки, продажи,
    строительство, банкротства, завершение игр.

    Returns:
        Логгер game.log.
    """
    return LogManager.get_logger(GAME_LOGGER_NAME)


def get_network_logger() -> logging.Logger:
    """
    Получить логгер сетевых событий.

    Используется для: подключения, отключения, отправка/получение пакетов,
    таймауты, heartbeat, проблемы с соединением.

    Returns:
        Логгер network.log.
    """
    return LogManager.get_logger(NETWORK_LOGGER_NAME)


def get_security_logger() -> logging.Logger:
    """
    Получить логгер событий безопасности.

    Используется для: попытки взлома, подозрительная активность,
    неверные пароли, нарушение целостности пакетов, блокировки.

    Returns:
        Логгер security.log.
    """
    return LogManager.get_logger(SECURITY_LOGGER_NAME)


def get_admin_logger() -> logging.Logger:
    """
    Получить логгер административных действий.

    Используется для: админ-команды, изменение ролей, читы,
    управление сервером, просмотр логов администратором.

    Returns:
        Логгер admin.log.
    """
    return LogManager.get_logger(ADMIN_LOGGER_NAME)


def get_chat_logger() -> logging.Logger:
    """
    Получить логгер сообщений чата.

    Используется для: сообщения игроков, системные сообщения,
    модерация чата.

    Returns:
        Логгер chat.log.
    """
    return LogManager.get_logger(CHAT_LOGGER_NAME)


# ============================================================================
# ФУНКЦИЯ БЫСТРОЙ НАСТРОЙКИ
# ============================================================================

def setup_all_loggers(
    log_dir: str = "logs",
    log_level: str = "INFO",
    console_output: bool = False,
) -> None:
    """
    Быстрая настройка всех логгеров проекта.

    Рекомендуется вызывать в начале main() сервера и клиента.

    Args:
        log_dir: Путь к директории для логов.
        log_level: Уровень логирования.
        console_output: Дублировать ли логи в консоль.

    Example:
        from shared.logger_config import setup_all_loggers

        def main():
            setup_all_loggers(log_dir="logs", log_level="INFO")
            # ... остальной код
    """
    LogManager.setup(
        log_dir=log_dir,
        log_level=log_level,
        console_output=console_output,
    )