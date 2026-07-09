"""
server/middleware/rate_limiter.py

Ограничитель частоты запросов (Rate Limiter).

Защищает сервер от:
- DoS/DDoS атак
- Спама (чат, аукцион)
- Брутфорса (попытки входа)

Использует алгоритм скользящего окна (sliding window)
для подсчёта количества запросов за интервал времени.

Python: 3.13+
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

from shared.constants import (
    MAX_PACKETS_PER_SECOND,
    MAX_CHAT_MESSAGES_PER_SECOND,
    MAX_AUTH_ATTEMPTS_PER_MINUTE,
)

logger = logging.getLogger("billionaire.security")


# ============================================================================
# КОНФИГУРАЦИЯ ЛИМИТОВ
# ============================================================================

@dataclass(slots=True)
class RateLimit:
    """
    Описание одного лимита.

    Attributes:
        max_requests: Максимальное количество запросов.
        window_seconds: Временное окно в секундах.
        name: Название лимита для логирования.
    """

    max_requests: int
    window_seconds: float
    name: str = "unknown"


# Предопределённые лимиты
DEFAULT_RATE_LIMITS = {
    "packet": RateLimit(MAX_PACKETS_PER_SECOND, 1.0, "packet"),
    "chat": RateLimit(MAX_CHAT_MESSAGES_PER_SECOND, 1.0, "chat"),
    "auth": RateLimit(MAX_AUTH_ATTEMPTS_PER_MINUTE, 60.0, "auth"),
}

# Типы пакетов, которые считаются чат-сообщениями
CHAT_PACKET_TYPES = {0x0401}  # CHAT_MESSAGE

# Типы пакетов, которые считаются попытками аутентификации
AUTH_PACKET_TYPES = {0x0101, 0x0103}  # LOGIN_REQUEST, REGISTER_REQUEST


# ============================================================================
# ОГРАНИЧИТЕЛЬ (Rate Limiter)
# ============================================================================

class RateLimiter:
    """
    Ограничитель частоты запросов.

    Отслеживает количество запросов от каждой сессии/IP
    за заданные временные окна и блокирует превышающие лимит.

    Attributes:
        _limits: Словарь лимитов {имя: RateLimit}.
        _requests: Словарь {session_id: {limit_name: [timestamps]}}.
    """

    def __init__(self) -> None:
        """Инициализация ограничителя с предустановленными лимитами."""
        self._limits: dict[str, RateLimit] = dict(DEFAULT_RATE_LIMITS)
        self._requests: dict[str, dict[str, list[float]]] = defaultdict(
            lambda: defaultdict(list)
        )

    # ========================================================================
    # ПРОВЕРКА ЛИМИТОВ
    # ========================================================================

    def is_allowed(
        self,
        session_id: str,
        packet_type: int = 0,
    ) -> bool:
        """
        Проверить, разрешён ли запрос от сессии.

        Проверяет общий лимит пакетов и специфические лимиты
        для чата и аутентификации.

        Args:
            session_id: ID сессии.
            packet_type: Тип пакета (для специфических лимитов).

        Returns:
            True, если запрос разрешён.
        """
        now = time.time()

        # Проверка общего лимита пакетов
        if not self._check_limit(session_id, "packet", now):
            logger.debug(
                "Rate limit превышен: session=%s, limit=packet",
                session_id,
            )
            return False

        # Проверка лимита чата
        if packet_type in CHAT_PACKET_TYPES:
            if not self._check_limit(session_id, "chat", now):
                logger.debug(
                    "Rate limit превышен: session=%s, limit=chat",
                    session_id,
                )
                return False

        # Проверка лимита аутентификации
        if packet_type in AUTH_PACKET_TYPES:
            if not self._check_limit(session_id, "auth", now):
                logger.debug(
                    "Rate limit превышен: session=%s, limit=auth",
                    session_id,
                )
                return False

        return True

    def is_chat_allowed(self, session_id: str) -> bool:
        """
        Проверить, разрешено ли отправлять сообщение чата.

        Args:
            session_id: ID сессии.

        Returns:
            True, если сообщение разрешено.
        """
        now = time.time()
        return self._check_limit(session_id, "chat", now)

    def is_auth_allowed(self, session_id: str) -> bool:
        """
        Проверить, разрешена ли попытка аутентификации.

        Args:
            session_id: ID сессии.

        Returns:
            True, если попытка разрешена.
        """
        now = time.time()
        return self._check_limit(session_id, "auth", now)

    # ========================================================================
    # УПРАВЛЕНИЕ ЛИМИТАМИ
    # ========================================================================

    def add_limit(
        self,
        name: str,
        max_requests: int,
        window_seconds: float,
    ) -> None:
        """
        Добавить новый лимит.

        Args:
            name: Уникальное имя лимита.
            max_requests: Максимум запросов.
            window_seconds: Временное окно.
        """
        self._limits[name] = RateLimit(
            max_requests=max_requests,
            window_seconds=window_seconds,
            name=name,
        )
        logger.info(
            "Добавлен rate limit: %s (%d запросов за %.1f сек)",
            name,
            max_requests,
            window_seconds,
        )

    def remove_limit(self, name: str) -> bool:
        """
        Удалить лимит.

        Args:
            name: Имя лимита.

        Returns:
            True, если лимит был удалён.
        """
        if name in self._limits:
            del self._limits[name]
            return True
        return False

    def update_limit(
        self,
        name: str,
        max_requests: int,
        window_seconds: float,
    ) -> bool:
        """
        Обновить существующий лимит.

        Args:
            name: Имя лимита.
            max_requests: Новый максимум.
            window_seconds: Новое окно.

        Returns:
            True, если лимит обновлён.
        """
        if name in self._limits:
            self._limits[name] = RateLimit(
                max_requests=max_requests,
                window_seconds=window_seconds,
                name=name,
            )
            return True
        return False

    # ========================================================================
    # ОЧИСТКА
    # ========================================================================

    def reset_session(self, session_id: str) -> None:
        """
        Сбросить счётчики для сессии.

        Args:
            session_id: ID сессии.
        """
        self._requests.pop(session_id, None)

    def cleanup_expired(self) -> int:
        """
        Очистить истёкшие записи.

        Удаляет временные метки, вышедшие за пределы
        максимального окна среди всех лимитов.

        Returns:
            Количество очищенных сессий.
        """
        now = time.time()
        max_window = max(
            (limit.window_seconds for limit in self._limits.values()),
            default=60.0,
        )
        cutoff = now - max_window

        cleaned = 0
        sessions_to_delete: list[str] = []

        for session_id, limits in self._requests.items():
            # Очищаем старые записи
            for limit_name in list(limits.keys()):
                timestamps = limits[limit_name]
                # Оставляем только записи в пределах окна
                limits[limit_name] = [ts for ts in timestamps if ts > cutoff]

            # Проверяем, остались ли записи
            if not any(limits.values()):
                sessions_to_delete.append(session_id)
                cleaned += 1

        for session_id in sessions_to_delete:
            del self._requests[session_id]

        if cleaned > 0:
            logger.debug("Очищено %d неактивных сессий в RateLimiter", cleaned)

        return cleaned

    # ========================================================================
    # ВНУТРЕННИЕ МЕТОДЫ
    # ========================================================================

    def _check_limit(
        self,
        session_id: str,
        limit_name: str,
        now: float,
    ) -> bool:
        """
        Проверить конкретный лимит.

        Args:
            session_id: ID сессии.
            limit_name: Имя лимита.
            now: Текущее время.

        Returns:
            True, если лимит не превышен.
        """
        limit = self._limits.get(limit_name)
        if limit is None:
            return True  # Нет лимита — всё разрешено

        timestamps = self._requests[session_id][limit_name]
        window_start = now - limit.window_seconds

        # Удаляем старые записи за пределами окна
        while timestamps and timestamps[0] <= window_start:
            timestamps.pop(0)

        # Проверяем лимит
        if len(timestamps) >= limit.max_requests:
            return False

        # Добавляем новую запись
        timestamps.append(now)
        return True

    # ========================================================================
    # ИНФОРМАЦИЯ
    # ========================================================================

    def get_session_usage(self, session_id: str) -> dict[str, int]:
        """
        Получить текущее использование лимитов сессией.

        Args:
            session_id: ID сессии.

        Returns:
            Словарь {limit_name: request_count}.
        """
        session_data = self._requests.get(session_id, {})
        return {
            name: len(session_data.get(name, []))
            for name in self._limits
        }

    def get_limits(self) -> dict[str, dict]:
        """
        Получить информацию о всех лимитах.

        Returns:
            Словарь с конфигурацией лимитов.
        """
        return {
            name: {
                "max_requests": limit.max_requests,
                "window_seconds": limit.window_seconds,
            }
            for name, limit in self._limits.items()
        }

    def get_stats(self) -> dict:
        """
        Получить статистику ограничителя.

        Returns:
            Словарь с метриками.
        """
        return {
            "active_sessions": len(self._requests),
            "limits": self.get_limits(),
        }