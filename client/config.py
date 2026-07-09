"""
client/config.py

Конфигурация клиента «Миллиардер».

Загружает настройки из JSON-файла и предоставляет
типизированный доступ к параметрам клиента.

Python: 3.13+
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("billionaire.client")


# ============================================================================
# КОНФИГУРАЦИЯ КЛИЕНТА
# ============================================================================

@dataclass(slots=True)
class ClientConfig:
    """
    Конфигурация клиента.

    Содержит все настройки: сервер, интерфейс, аудио, уведомления, чат, сеть.

    Attributes:
        server_host: Адрес сервера.
        server_port: Порт сервера.
        ssl_enabled: Использовать SSL.
        ssl_verify: Проверять сертификат.
        language: Язык интерфейса.
        theme: Тема оформления.
        window_width: Ширина окна.
        window_height: Высота окна.
        audio_enabled: Включить звук.
        music_volume: Громкость музыки (0-100).
        effects_volume: Громкость эффектов (0-100).
        auto_reconnect: Автоматическое переподключение.
        reconnect_attempts: Количество попыток.
        reconnect_delay: Задержка между попытками (сек).
        heartbeat_interval: Интервал heartbeat (сек).
        connection_timeout: Таймаут подключения (сек).
    """

    # Сервер
    server_host: str = "localhost"
    server_port: int = 8443
    ssl_enabled: bool = True
    ssl_verify: bool = True

    # Интерфейс
    language: str = "ru"
    theme: str = "light"
    window_width: int = 1024
    window_height: int = 768
    window_maximized: bool = False

    # Аудио
    audio_enabled: bool = True
    music_volume: int = 50
    effects_volume: int = 70

    # Сеть
    auto_reconnect: bool = True
    reconnect_attempts: int = 5
    reconnect_delay: float = 3.0
    heartbeat_interval: float = 10.0
    connection_timeout: float = 10.0

    # Чат
    chat_show_timestamps: bool = True
    chat_max_history: int = 200

    # Уведомления
    notifications_enabled: bool = True
    notifications_auto_close: int = 5

    @classmethod
    def load(cls, config_path: str = "configs/client/client.json") -> ClientConfig:
        """
        Загрузить конфигурацию из JSON-файла.

        Args:
            config_path: Путь к файлу конфигурации.

        Returns:
            Экземпляр ClientConfig.
        """
        path = Path(config_path)
        config = cls()

        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                config_data = data.get("data", data)

                # Сервер
                server = config_data.get("server", {})
                config.server_host = server.get("host", config.server_host)
                config.server_port = server.get("port", config.server_port)
                config.ssl_enabled = server.get("ssl_enabled", config.ssl_enabled)
                config.ssl_verify = server.get("ssl_verify", config.ssl_verify)

                # Интерфейс
                interface = config_data.get("interface", {})
                config.language = interface.get("language", config.language)
                config.theme = interface.get("theme", config.theme)
                window = interface.get("window", {})
                config.window_width = window.get("min_width", config.window_width)
                config.window_height = window.get("min_height", config.window_height)
                config.window_maximized = window.get("start_maximized", config.window_maximized)

                # Аудио
                audio = config_data.get("audio", {})
                config.audio_enabled = audio.get("enabled", config.audio_enabled)
                config.music_volume = audio.get("music_volume", config.music_volume)
                config.effects_volume = audio.get("effects_volume", config.effects_volume)

                # Сеть
                network = config_data.get("network", {})
                config.auto_reconnect = network.get("auto_reconnect", config.auto_reconnect)
                config.reconnect_attempts = network.get("max_reconnect_attempts", config.reconnect_attempts)
                config.reconnect_delay = network.get("reconnect_delay_seconds", config.reconnect_delay)
                config.heartbeat_interval = network.get("heartbeat_interval_seconds", config.heartbeat_interval)
                config.connection_timeout = network.get("connection_timeout_seconds", config.connection_timeout)

                # Чат
                chat = config_data.get("chat", {})
                config.chat_show_timestamps = chat.get("show_timestamps", config.chat_show_timestamps)
                config.chat_max_history = chat.get("max_history_display", config.chat_max_history)

                # Уведомления
                notifications = config_data.get("notifications", {})
                config.notifications_enabled = notifications.get("show_system_messages", config.notifications_enabled)
                config.notifications_auto_close = notifications.get("auto_close_delay_seconds", config.notifications_auto_close)

                logger.info("Конфигурация загружена из %s", config_path)

            except Exception as e:
                logger.warning("Ошибка загрузки конфигурации: %s. Используются значения по умолчанию.", e)
        else:
            logger.info("Файл конфигурации не найден: %s. Используются значения по умолчанию.", config_path)

        return config

    def save(self, config_path: str = "configs/client/client.json") -> None:
        """
        Сохранить конфигурацию в JSON-файл.

        Args:
            config_path: Путь к файлу.
        """
        path = Path(config_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "version": 1,
            "data": {
                "server": {
                    "host": self.server_host,
                    "port": self.server_port,
                    "ssl_enabled": self.ssl_enabled,
                    "ssl_verify": self.ssl_verify,
                },
                "interface": {
                    "language": self.language,
                    "theme": self.theme,
                    "window": {
                        "min_width": self.window_width,
                        "min_height": self.window_height,
                        "start_maximized": self.window_maximized,
                    },
                },
                "audio": {
                    "enabled": self.audio_enabled,
                    "music_volume": self.music_volume,
                    "effects_volume": self.effects_volume,
                },
                "network": {
                    "auto_reconnect": self.auto_reconnect,
                    "max_reconnect_attempts": self.reconnect_attempts,
                    "reconnect_delay_seconds": self.reconnect_delay,
                    "heartbeat_interval_seconds": self.heartbeat_interval,
                    "connection_timeout_seconds": self.connection_timeout,
                },
                "chat": {
                    "show_timestamps": self.chat_show_timestamps,
                    "max_history_display": self.chat_max_history,
                },
                "notifications": {
                    "show_system_messages": self.notifications_enabled,
                    "auto_close_delay_seconds": self.notifications_auto_close,
                },
            },
        }

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info("Конфигурация сохранена в %s", config_path)

    def to_dict(self) -> dict[str, Any]:
        """Сериализация конфигурации в словарь."""
        return {
            "server_host": self.server_host,
            "server_port": self.server_port,
            "ssl_enabled": self.ssl_enabled,
            "language": self.language,
            "theme": self.theme,
            "audio_enabled": self.audio_enabled,
            "auto_reconnect": self.auto_reconnect,
        }