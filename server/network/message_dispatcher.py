"""
server/network/message_dispatcher.py

Диспетчер сообщений сервера.

Маршрутизирует входящие пакеты к соответствующим обработчикам
в зависимости от типа пакета (AUTH, ROOM, GAME, CHAT, SYSTEM, ADMIN).

Реализует паттерн Chain of Responsibility — каждый обработчик
может обработать пакет или передать дальше.

Python: 3.13+
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Coroutine, Optional
from uuid import UUID

from shared.enums import PacketType
from shared.protocol.packet import Packet

logger = logging.getLogger("billionaire.network")


# ============================================================================
# ТИПЫ ОБРАБОТЧИКОВ
# ============================================================================

# Обработчик пакета: (session_id, packet, user_dict) -> (response_dict, error_message)
PacketHandler = Callable[
    [UUID, Packet, Optional[dict[str, Any]]],
    Coroutine[Any, Any, tuple[Optional[dict[str, Any]], Optional[str]]],
]


# ============================================================================
# ДИСПЕТЧЕР СООБЩЕНИЙ
# ============================================================================

class MessageDispatcher:
    """
    Диспетчер входящих сообщений.

    Маршрутизирует пакеты к зарегистрированным обработчикам
    на основе категории и типа пакета.

    Поддерживает:
    - Регистрацию обработчиков для категорий (AUTH, ROOM, GAME, ...)
    - Регистрацию обработчиков для конкретных типов пакетов
    - Обработчик по умолчанию для неизвестных типов

    Usage:
        dispatcher = MessageDispatcher()
        dispatcher.register_category("AUTH", auth_handler)
        dispatcher.register_handler(PacketType.LOGIN_REQUEST, login_handler)
        
        response, error = await dispatcher.dispatch(session_id, packet, user)
    """

    def __init__(self) -> None:
        """Инициализация диспетчера."""
        # Обработчики категорий: {категория: обработчик}
        self._category_handlers: dict[str, PacketHandler] = {}

        # Обработчики конкретных типов: {PacketType: обработчик}
        self._type_handlers: dict[PacketType, PacketHandler] = {}

        # Обработчик по умолчанию
        self._default_handler: Optional[PacketHandler] = None

    # ========================================================================
    # РЕГИСТРАЦИЯ ОБРАБОТЧИКОВ
    # ========================================================================

    def register_category(
        self,
        category: str,
        handler: PacketHandler,
    ) -> None:
        """
        Зарегистрировать обработчик для категории пакетов.

        Категории: AUTH, ROOM, GAME, CHAT, SYSTEM, ADMIN.

        Args:
            category: Название категории.
            handler: Асинхронный обработчик.
        """
        self._category_handlers[category.upper()] = handler
        logger.debug(
            "Зарегистрирован обработчик категории '%s': %s",
            category,
            handler.__name__ if hasattr(handler, "__name__") else str(handler),
        )

    def register_handler(
        self,
        packet_type: PacketType,
        handler: PacketHandler,
    ) -> None:
        """
        Зарегистрировать обработчик для конкретного типа пакета.

        Args:
            packet_type: Тип пакета.
            handler: Асинхронный обработчик.
        """
        self._type_handlers[packet_type] = handler
        logger.debug(
            "Зарегистрирован обработчик %s: %s",
            packet_type.name,
            handler.__name__ if hasattr(handler, "__name__") else str(handler),
        )

    def register_default_handler(self, handler: PacketHandler) -> None:
        """
        Зарегистрировать обработчик по умолчанию.

        Вызывается для пакетов, у которых нет явного обработчика.

        Args:
            handler: Асинхронный обработчик.
        """
        self._default_handler = handler
        logger.debug(
            "Зарегистрирован обработчик по умолчанию: %s",
            handler.__name__ if hasattr(handler, "__name__") else str(handler),
        )

    def register_handlers(
        self,
        handlers: dict[PacketType, PacketHandler],
    ) -> None:
        """
        Зарегистрировать несколько обработчиков одновременно.

        Args:
            handlers: Словарь {PacketType: handler}.
        """
        for packet_type, handler in handlers.items():
            self.register_handler(packet_type, handler)

    # ========================================================================
    # ДИСПЕТЧЕРИЗАЦИЯ
    # ========================================================================

    async def dispatch(
        self,
        session_id: UUID,
        packet: Packet,
        user: Optional[dict[str, Any]] = None,
    ) -> tuple[Optional[dict[str, Any]], Optional[str]]:
        """
        Маршрутизировать пакет к нужному обработчику.

        Порядок поиска обработчика:
        1. Обработчик для конкретного типа пакета
        2. Обработчик категории (AUTH, ROOM, GAME, ...)
        3. Обработчик по умолчанию
        4. Ошибка "неизвестный тип пакета"

        Args:
            session_id: ID сессии.
            packet: Входящий пакет.
            user: Данные аутентифицированного пользователя (или None).

        Returns:
            Кортеж (response_dict, error_message).
        """
        packet_type = packet.packet_type

        # 1. Ищем точный обработчик
        handler = self._type_handlers.get(packet_type)

        # 2. Ищем обработчик категории
        if handler is None:
            category = self._get_category(packet_type)
            handler = self._category_handlers.get(category)

        # 3. Обработчик по умолчанию
        if handler is None:
            handler = self._default_handler

        # 4. Нет обработчика
        if handler is None:
            logger.warning(
                "Нет обработчика для пакета %s (сессия: %s)",
                packet_type.name,
                str(session_id)[:8],
            )
            return None, f"Неизвестный тип пакета: {packet_type.name}"

        # Вызываем обработчик
        try:
            logger.debug(
                "Диспетчеризация %s → %s",
                packet_type.name,
                handler.__name__ if hasattr(handler, "__name__") else str(handler),
            )
            return await handler(session_id, packet, user)

        except Exception as e:
            logger.error(
                "Ошибка обработки пакета %s: %s",
                packet_type.name,
                e,
            )
            return None, f"Внутренняя ошибка сервера при обработке {packet_type.name}"

    # ========================================================================
    # ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ
    # ========================================================================

    @staticmethod
    def _get_category(packet_type: PacketType) -> str:
        """
        Определить категорию пакета по его типу.

        Args:
            packet_type: Тип пакета.

        Returns:
            Строка категории (AUTH, ROOM, GAME, CHAT, SYSTEM, ADMIN).
        """
        value = packet_type.value
        category_id = (value >> 8) & 0xFF

        categories = {
            0x01: "AUTH",
            0x02: "ROOM",
            0x03: "GAME",
            0x04: "CHAT",
            0x05: "SYSTEM",
            0x06: "ADMIN",
        }

        return categories.get(category_id, "UNKNOWN")

    def has_handler(self, packet_type: PacketType) -> bool:
        """
        Проверить, есть ли обработчик для типа пакета.

        Args:
            packet_type: Тип пакета.

        Returns:
            True, если обработчик зарегистрирован.
        """
        return (
            packet_type in self._type_handlers
            or self._get_category(packet_type) in self._category_handlers
            or self._default_handler is not None
        )

    # ========================================================================
    # УПРАВЛЕНИЕ ОБРАБОТЧИКАМИ
    # ========================================================================

    def remove_handler(self, packet_type: PacketType) -> bool:
        """
        Удалить обработчик для конкретного типа.

        Args:
            packet_type: Тип пакета.

        Returns:
            True, если обработчик был удалён.
        """
        if packet_type in self._type_handlers:
            del self._type_handlers[packet_type]
            return True
        return False

    def remove_category(self, category: str) -> bool:
        """
        Удалить обработчик категории.

        Args:
            category: Название категории.

        Returns:
            True, если обработчик был удалён.
        """
        key = category.upper()
        if key in self._category_handlers:
            del self._category_handlers[key]
            return True
        return False

    def clear_all(self) -> None:
        """Удалить все обработчики."""
        self._category_handlers.clear()
        self._type_handlers.clear()
        self._default_handler = None
        logger.debug("Все обработчики удалены")

    # ========================================================================
    # ИНФОРМАЦИЯ
    # ========================================================================

    def get_registered_handlers(self) -> dict[str, list[str]]:
        """
        Получить список зарегистрированных обработчиков.

        Returns:
            Словарь {категория: [типы_пакетов]}.
        """
        result: dict[str, list[str]] = {
            category: [] for category in ["AUTH", "ROOM", "GAME", "CHAT", "SYSTEM", "ADMIN"]
        }
        result["UNKNOWN"] = []

        for packet_type in self._type_handlers:
            category = self._get_category(packet_type)
            if category in result:
                result[category].append(packet_type.name)

        for category in self._category_handlers:
            if category in result and category not in result[category]:
                result[category].append(f"* (категория)")

        return result

    def get_stats(self) -> dict:
        """
        Получить статистику диспетчера.

        Returns:
            Словарь с метриками.
        """
        return {
            "type_handlers": len(self._type_handlers),
            "category_handlers": len(self._category_handlers),
            "has_default": self._default_handler is not None,
            "total_handlers": (
                len(self._type_handlers)
                + len(self._category_handlers)
                + (1 if self._default_handler else 0)
            ),
        }