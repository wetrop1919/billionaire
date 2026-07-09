"""
client/models/chat_model.py

Qt-модель чата для клиента.

Хранит сообщения чата комнаты и предоставляет сигналы
для обновления UI при получении новых сообщений.

Python: 3.13+
"""

from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

from PySide6.QtCore import QObject, Signal, Property

logger = logging.getLogger("billionaire.client")


# ============================================================================
# МОДЕЛЬ ЧАТА
# ============================================================================

class ChatModel(QObject):
    """
    Qt-модель чата.

    Хранит историю сообщений текущей комнаты.
    Поддерживает различные типы сообщений:
    - player — от игрока
    - system — системное уведомление
    - game_event — игровое событие
    - admin — объявление администратора

    Сигналы:
        message_received — новое сообщение
        history_loaded — загружена история
        chat_cleared — чат очищен
    """

    # Сигналы
    message_received = Signal(dict)  # message_data
    history_loaded = Signal()
    chat_cleared = Signal()
    new_messages_count_changed = Signal(int)

    # Максимальное количество хранимых сообщений
    MAX_MESSAGES: int = 500

    def __init__(self, parent: Optional[QObject] = None) -> None:
        """
        Инициализация модели чата.

        Args:
            parent: Родительский QObject.
        """
        super().__init__(parent)

        # Сообщения
        self._messages: list[dict[str, Any]] = []

        # Последний ID сообщения (для подгрузки новых)
        self._last_message_id: int = 0

        # Количество непрочитанных
        self._unread_count: int = 0

        # ID комнаты
        self._room_id: Optional[UUID] = None

    # ========================================================================
    # Q_PROPERTY
    # ========================================================================

    def get_messages(self) -> list[dict[str, Any]]:
        return list(self._messages)

    def get_unread_count(self) -> int:
        return self._unread_count

    def get_last_message_text(self) -> str:
        if self._messages:
            last = self._messages[-1]
            content = last.get("content", "")
            return content[:100] if len(content) > 100 else content
        return ""

    messages = Property(list, get_messages, notify=message_received)
    unreadCount = Property(int, get_unread_count, notify=new_messages_count_changed)
    lastMessageText = Property(str, get_last_message_text, notify=message_received)

    # ========================================================================
    # ДОБАВЛЕНИЕ СООБЩЕНИЙ
    # ========================================================================

    def add_message(self, message: dict[str, Any]) -> None:
        """
        Добавить сообщение.

        Args:
            message: Данные сообщения от сервера.
        """
        msg = {
            "id": message.get("id", message.get("message_id", 0)),
            "user_id": message.get("user_id"),
            "username": message.get("username", "Система"),
            "content": message.get("content", ""),
            "message_type": message.get("message_type", "player"),
            "created_at": message.get("created_at", ""),
        }

        self._messages.append(msg)

        # Ограничиваем размер истории
        if len(self._messages) > self.MAX_MESSAGES:
            self._messages = self._messages[-self.MAX_MESSAGES:]

        # Обновляем последний ID
        if msg["id"] > self._last_message_id:
            self._last_message_id = msg["id"]

        # Увеличиваем счётчик непрочитанных
        self._unread_count += 1
        self.new_messages_count_changed.emit(self._unread_count)

        self.message_received.emit(msg)

    def add_system_message(self, content: str) -> None:
        """
        Добавить системное сообщение.

        Args:
            content: Текст сообщения.
        """
        self.add_message({
            "message_type": "system",
            "content": content,
            "username": "Система",
        })

    def add_game_event(self, content: str) -> None:
        """
        Добавить игровое событие.

        Args:
            content: Текст события.
        """
        self.add_message({
            "message_type": "game_event",
            "content": content,
            "username": "Игра",
        })

    # ========================================================================
    # ИСТОРИЯ
    # ========================================================================

    def set_history(self, messages: list[dict[str, Any]]) -> None:
        """
        Загрузить историю сообщений.

        Args:
            messages: Список сообщений.
        """
        self._messages = []
        for msg in messages:
            self._messages.append({
                "id": msg.get("id", msg.get("message_id", 0)),
                "user_id": msg.get("user_id"),
                "username": msg.get("username", ""),
                "content": msg.get("content", ""),
                "message_type": msg.get("message_type", "player"),
                "created_at": msg.get("created_at", ""),
            })

        if self._messages:
            self._last_message_id = self._messages[-1]["id"]

        self.history_loaded.emit()

    def get_newer_than(self, since_id: int) -> list[dict[str, Any]]:
        """
        Получить сообщения новее указанного ID.

        Args:
            since_id: ID, после которого получать.

        Returns:
            Список новых сообщений.
        """
        return [m for m in self._messages if m["id"] > since_id]

    # ========================================================================
    # УПРАВЛЕНИЕ
    # ========================================================================

    def mark_as_read(self) -> None:
        """Отметить все сообщения как прочитанные."""
        self._unread_count = 0
        self.new_messages_count_changed.emit(0)

    def clear(self) -> None:
        """Очистить чат."""
        self._messages.clear()
        self._last_message_id = 0
        self._unread_count = 0
        self.chat_cleared.emit()

    def set_room_id(self, room_id: UUID) -> None:
        """
        Установить ID комнаты.

        Args:
            room_id: ID комнаты.
        """
        self._room_id = room_id

    # ========================================================================
    # ДОСТУП К ДАННЫМ
    # ========================================================================

    @property
    def last_message_id(self) -> int:
        return self._last_message_id

    @property
    def message_count(self) -> int:
        return len(self._messages)

    @property
    def unread_count(self) -> int:
        return self._unread_count

    def get_messages_by_type(self, message_type: str) -> list[dict[str, Any]]:
        """
        Получить сообщения определённого типа.

        Args:
            message_type: Тип (player, system, game_event, admin).

        Returns:
            Отфильтрованный список.
        """
        return [m for m in self._messages if m.get("message_type") == message_type]

    def get_last_messages(self, count: int = 50) -> list[dict[str, Any]]:
        """
        Получить последние N сообщений.

        Args:
            count: Количество.

        Returns:
            Последние сообщения.
        """
        return self._messages[-count:] if self._messages else []