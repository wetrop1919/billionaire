"""
shared/env_config.py

Загрузка и валидация конфигурации из переменных окружения (.env файл).

Использует python-dotenv для загрузки .env файла и предоставляет
типизированный доступ ко всем переменным окружения через dataclass.

Все секреты, токены, пароли и пути настраиваются исключительно
через переменные окружения, а не хардкодятся в коде.

Использование:
    from shared.env_config import EnvConfig, load_env_config

    config = load_env_config()
    print(config.SERVER_PORT)  # 8443

Python: 3.13+
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ============================================================================
# КОНФИГУРАЦИЯ ОКРУЖЕНИЯ
# ============================================================================

@dataclass(slots=True)
class EnvConfig:
    """
    Типизированная конфигурация из переменных окружения.

    Все поля соответствуют переменным в .env файле.
    Чувствительные данные (пароли, ключи) помечены в комментариях.
    """

    # === СЕРВЕР ===
    SERVER_HOST: str = "0.0.0.0"
    SERVER_PORT: int = 8443

    # === БАЗА ДАННЫХ (PostgreSQL) ===
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_USER: str = "billionaire"
    DB_PASSWORD: str = ""  # СЕКРЕТ
    DB_NAME: str = "billionaire_db"
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10

    # === SSL / TLS ===
    SSL_ENABLED: bool = True
    SSL_CERT_PATH: str = "certs/server.crt"
    SSL_KEY_PATH: str = "certs/server.key"
    SSL_CA_PATH: str = ""  # Опционально: путь к CA-сертификату

    # === JWT / ТОКЕНЫ ===
    JWT_SECRET: str = ""  # СЕКРЕТ — секретный ключ для подписи токенов
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # === БЕЗОПАСНОСТЬ ===
    ARGON2_MEMORY_COST: int = 65536
    ARGON2_TIME_COST: int = 3
    ARGON2_PARALLELISM: int = 4
    HMAC_SECRET: str = ""  # СЕКРЕТ — ключ для HMAC-подписи пакетов

    # === ЛОГИРОВАНИЕ ===
    LOG_LEVEL: str = "INFO"
    LOG_DIR: str = "logs"

    # === БЭКАПЫ ===
    BACKUP_DIR: str = "backups"
    BACKUP_RETENTION_DAYS: int = 30

    # === ПУТИ К КОНФИГУРАЦИЯМ ===
    CONFIGS_DIR: str = "configs"
    GAME_CONFIG_DIR: str = "configs/game"
    TRANSLATIONS_DIR: str = "translations"

    # === АДМИНИСТРАТОР ПО УМОЛЧАНИЮ ===
    DEFAULT_ADMIN_USERNAME: str = "admin"
    DEFAULT_ADMIN_PASSWORD: str = ""  # СЕКРЕТ — должен быть изменён в production

    # === ПРОЧЕЕ ===
    DEBUG: bool = False
    ENVIRONMENT: str = "production"  # development, staging, production

    # === ВЫЧИСЛЯЕМЫЕ ПОЛЯ ===
    DATABASE_URL: str = field(init=False, default="")

    def __post_init__(self) -> None:
        """Формирование URL подключения к БД после инициализации."""
        self.DATABASE_URL = (
            f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )

    @property
    def is_development(self) -> bool:
        """Проверка, запущен ли сервер в режиме разработки."""
        return self.ENVIRONMENT == "development"

    @property
    def is_production(self) -> bool:
        """Проверка, запущен ли сервер в production-режиме."""
        return self.ENVIRONMENT == "production"

    @property
    def is_debug(self) -> bool:
        """Проверка, включён ли режим отладки."""
        return self.DEBUG

    def validate(self) -> list[str]:
        """
        Валидация обязательных полей конфигурации.

        Returns:
            Список сообщений об ошибках (пустой, если всё корректно).
        """
        errors: list[str] = []

        if not self.JWT_SECRET:
            errors.append(
                "JWT_SECRET не установлен. "
                "Сгенерируйте случайный ключ: python -c 'import secrets; print(secrets.token_hex(32))'"
            )

        if not self.DB_PASSWORD:
            errors.append(
                "DB_PASSWORD не установлен. Укажите пароль для подключения к PostgreSQL."
            )

        if not self.HMAC_SECRET:
            errors.append(
                "HMAC_SECRET не установлен. "
                "Сгенерируйте случайный ключ: python -c 'import secrets; print(secrets.token_hex(32))'"
            )

        if self.ENVIRONMENT == "production":
            if self.DEBUG:
                errors.append(
                    "DEBUG=True небезопасно в production-окружении."
                )
            if not self.DEFAULT_ADMIN_PASSWORD:
                errors.append(
                    "DEFAULT_ADMIN_PASSWORD не установлен в production-окружении."
                )
            if self.SSL_ENABLED:
                if not self.SSL_CERT_PATH or not os.path.exists(self.SSL_CERT_PATH):
                    errors.append(
                        f"SSL-сертификат не найден: {self.SSL_CERT_PATH}"
                    )
                if not self.SSL_KEY_PATH or not os.path.exists(self.SSL_KEY_PATH):
                    errors.append(
                        f"SSL-ключ не найден: {self.SSL_KEY_PATH}"
                    )

        if self.SERVER_PORT < 1 or self.SERVER_PORT > 65535:
            errors.append(f"Некорректный SERVER_PORT: {self.SERVER_PORT}")

        if self.DB_PORT < 1 or self.DB_PORT > 65535:
            errors.append(f"Некорректный DB_PORT: {self.DB_PORT}")

        return errors

    def mask_secrets(self) -> dict[str, str]:
        """
        Возвращает словарь всех полей с маскированием секретных данных.
        Используется для логирования конфигурации без утечки секретов.

        Returns:
            Словарь полей, где секретные значения заменены на '***'.
        """
        secret_fields = {"DB_PASSWORD", "JWT_SECRET", "HMAC_SECRET", "DEFAULT_ADMIN_PASSWORD"}
        result: dict[str, str] = {}
        for field_name in self.__slots__:
            value = str(getattr(self, field_name, ""))
            if field_name in secret_fields and value:
                result[field_name] = "***"
            else:
                result[field_name] = value
        return result


# ============================================================================
# ФУНКЦИИ ЗАГРУЗКИ
# ============================================================================

def _find_env_file() -> Optional[Path]:
    """
    Поиск .env файла в стандартных расположениях.

    Порядок поиска:
    1. Переменная окружения ENV_FILE
    2. Текущая рабочая директория
    3. Директория на уровень выше (если запущено из server/)

    Returns:
        Path к .env файлу или None, если не найден.
    """
    # Проверяем явно указанный путь
    env_file_path = os.environ.get("ENV_FILE")
    if env_file_path:
        env_path = Path(env_file_path)
        if env_path.exists():
            return env_path

    # Проверяем текущую директорию
    cwd_env = Path.cwd() / ".env"
    if cwd_env.exists():
        return cwd_env

    # Проверяем директорию выше (если запущено из server/)
    parent_env = Path.cwd().parent / ".env"
    if parent_env.exists():
        return parent_env

    return None


def load_env_config(env_file_path: Optional[str] = None) -> EnvConfig:
    """
    Загружает конфигурацию из .env файла и переменных окружения.

    Порядок приоритета:
    1. Переменные окружения (os.environ)
    2. .env файл
    3. Значения по умолчанию из EnvConfig

    Args:
        env_file_path: Опциональный путь к .env файлу.
                       Если не указан, используется автоматический поиск.

    Returns:
        Экземпляр EnvConfig с заполненными полями.

    Raises:
        FileNotFoundError: Если .env файл не найден в production-окружении.
        ValueError: Если обязательные поля не заполнены.
    """
    try:
        from dotenv import load_dotenv as _load_dotenv
    except ImportError:
        raise ImportError(
            "python-dotenv не установлен. "
            "Установите: pip install python-dotenv"
        )

    # Определяем путь к .env файлу
    dotenv_path: Optional[str] = env_file_path
    if dotenv_path is None:
        found_path = _find_env_file()
        if found_path is not None:
            dotenv_path = str(found_path)

    if dotenv_path is not None:
        _load_dotenv(dotenv_path=dotenv_path, override=False)
    else:
        # В production .env обязателен
        if os.environ.get("ENVIRONMENT", "production") == "production":
            raise FileNotFoundError(
                ".env файл не найден. "
                "Создайте его на основе .env.example или укажите путь через ENV_FILE."
            )

    # Заполняем конфигурацию из переменных окружения
    config = EnvConfig(
        # Сервер
        SERVER_HOST=os.getenv("SERVER_HOST", "0.0.0.0"),
        SERVER_PORT=int(os.getenv("SERVER_PORT", "8443")),
        # База данных
        DB_HOST=os.getenv("DB_HOST", "localhost"),
        DB_PORT=int(os.getenv("DB_PORT", "5432")),
        DB_USER=os.getenv("DB_USER", "billionaire"),
        DB_PASSWORD=os.getenv("DB_PASSWORD", ""),
        DB_NAME=os.getenv("DB_NAME", "billionaire_db"),
        DB_POOL_SIZE=int(os.getenv("DB_POOL_SIZE", "20")),
        DB_MAX_OVERFLOW=int(os.getenv("DB_MAX_OVERFLOW", "10")),
        # SSL
        SSL_ENABLED=os.getenv("SSL_ENABLED", "true").lower() == "true",
        SSL_CERT_PATH=os.getenv("SSL_CERT_PATH", "certs/server.crt"),
        SSL_KEY_PATH=os.getenv("SSL_KEY_PATH", "certs/server.key"),
        SSL_CA_PATH=os.getenv("SSL_CA_PATH", ""),
        # Токены
        JWT_SECRET=os.getenv("JWT_SECRET", ""),
        ACCESS_TOKEN_EXPIRE_MINUTES=int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60")),
        REFRESH_TOKEN_EXPIRE_DAYS=int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "30")),
        # Безопасность
        ARGON2_MEMORY_COST=int(os.getenv("ARGON2_MEMORY_COST", "65536")),
        ARGON2_TIME_COST=int(os.getenv("ARGON2_TIME_COST", "3")),
        ARGON2_PARALLELISM=int(os.getenv("ARGON2_PARALLELISM", "4")),
        HMAC_SECRET=os.getenv("HMAC_SECRET", ""),
        # Логирование
        LOG_LEVEL=os.getenv("LOG_LEVEL", "INFO"),
        LOG_DIR=os.getenv("LOG_DIR", "logs"),
        # Бэкапы
        BACKUP_DIR=os.getenv("BACKUP_DIR", "backups"),
        BACKUP_RETENTION_DAYS=int(os.getenv("BACKUP_RETENTION_DAYS", "30")),
        # Пути
        CONFIGS_DIR=os.getenv("CONFIGS_DIR", "configs"),
        GAME_CONFIG_DIR=os.getenv("GAME_CONFIG_DIR", "configs/game"),
        TRANSLATIONS_DIR=os.getenv("TRANSLATIONS_DIR", "translations"),
        # Администратор
        DEFAULT_ADMIN_USERNAME=os.getenv("DEFAULT_ADMIN_USERNAME", "admin"),
        DEFAULT_ADMIN_PASSWORD=os.getenv("DEFAULT_ADMIN_PASSWORD", ""),
        # Прочее
        DEBUG=os.getenv("DEBUG", "false").lower() == "true",
        ENVIRONMENT=os.getenv("ENVIRONMENT", "production"),
    )

    # Формируем DATABASE_URL
    config.__post_init__()

    # Валидируем конфигурацию
    errors = config.validate()
    if errors:
        error_messages = "\n  - ".join(errors)
        raise ValueError(
            f"Ошибки валидации конфигурации:\n  - {error_messages}"
        )

    return config


# ============================================================================
# ГЛОБАЛЬНЫЙ ЭКЗЕМПЛЯР (опционально)
# ============================================================================

# Создаётся при первом импорте модуля.
# В production-коде рекомендуется использовать DI-контейнер вместо глобальной переменной.
_env_config: Optional[EnvConfig] = None


def get_env_config() -> EnvConfig:
    """
    Получить глобальный экземпляр конфигурации окружения.

    При первом вызове загружает конфигурацию из .env файла.
    При последующих вызовах возвращает кешированный экземпляр.

    Returns:
        Экземпляр EnvConfig.

    Note:
        В production-коде предпочтительнее использовать DI-контейнер.
        Эта функция предназначена для упрощения доступа в небольших модулях.
    """
    global _env_config
    if _env_config is None:
        _env_config = load_env_config()
    return _env_config


def reload_env_config(env_file_path: Optional[str] = None) -> EnvConfig:
    """
    Принудительно перезагрузить конфигурацию из .env файла.

    Args:
        env_file_path: Опциональный путь к .env файлу.

    Returns:
        Новый экземпляр EnvConfig.
    """
    global _env_config
    _env_config = load_env_config(env_file_path)
    return _env_config