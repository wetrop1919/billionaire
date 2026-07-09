"""
client/viewmodels/chat_viewmodel.py

ViewModel для чата.

Управляет отправкой и получением сообщений чата.
Связывает NetworkClient с ChatModel.

Python: 3.13+
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional
from uuid import UUID

from PySide6.QtCore import QObject, Signal, Slot, Property

from client.network.network_client import NetworkClient
from client.models.chat_model import ChatModel

logger = logging.getLogger("billionaire.client")


# ============================================================================
# VIEWMODEL ЧАТА
# ============================================================================

class ChatViewModel(QObject):
    """
    ViewModel для чата.

    Предоставляет слоты для отправки сообщений и сигналы
    для обновления UI при получении новых сообщений.

    Сигналы:
        message_sent — сообщение отправлено
        message_received — получено новое сообщение
        history_loaded — история загружена
        error_occurred — ошибка
    """

    # Сигналы
    message_sent = Signal()
    message_received = Signal(dict)
    history_loaded = Signal()
    error_occurred = Signal(str)

    def __init__(
        self,
        network_client: NetworkClient,
        chat_model: ChatModel,
        parent: Optional[QObject] = None,
    ) -> None:
        """
        Инициализация ViewModel.

        Args:
            network_client: Сетевой клиент.
            chat_model: Модель чата.
            parent: Родительский QObject.
        """
        super().__init__(parent)

        self._network = network_client
        self._chat_model = chat_model

        # Подписываемся на обновления модели
        self._chat_model.message_received.connect(self._on_model_message)

        # Состояние
        self._is_sending: bool = False

    # ========================================================================
    # Q_PROPERTY
    # ========================================================================

    def get_unread_count(self) -> int:
        return self._chat_model.unread_count

    def get_last_message(self) -> str:
        return self._chat_model.lastMessageText

    unreadCount = Property(int, get_unread_count, notify=message_received)
    lastMessage = Property(str, get_last_message, notify=message_received)

    # ========================================================================
    # СЛОТЫ
    # ========================================================================

    @Slot(str)
    def send_message(self, text: str) -> None:
        """
        Отправить сообщение в чат.

        Args:
            text: Текст сообщения.
        """
        if not text or not text.strip():
            return

        if self._is_sending:
            return

        asyncio.ensure_future(self._do_send_message(text.strip()))

    @Slot()
    def load_history(self) -> None:
        """Загрузить историю чата."""
        asyncio.ensure_future(self._do_load_history())

    @Slot()
    def mark_as_read(self) -> None:
        """Отметить как прочитанное."""
        self._chat_model.mark_as_read()

    # ========================================================================
    # АСИНХРОННЫЕ ОПЕРАЦИИ
    # ========================================================================

    async def _do_send_message(self, text: str) -> None:
        """
        Отправить сообщение.

        Args:
            text: Текст сообщения.
        """
        self._is_sending = True

        try:
            from shared.enums import PacketType

            await self._network.send_packet(
                PacketType.CHAT_MESSAGE,
                {"content": text},
            )

            self.message_sent.emit()

        except Exception as e:
            self.error_occurred.emit(f"Ошибка отправки: {e}")
        finally:
            self._is_sending = False

    async def _do_load_history(self) -> None:
        """Загрузить историю чата."""
        try:
            from shared.enums import PacketType

            response = await self._network.send_request(
                PacketType.CHAT_HISTORY_REQUEST,
                {
                    "limit": 50,
                },
            )

            messages = response.get("messages", [])
            if messages:
                self._chat_model.set_history(messages)
                self.history_loaded.emit()

        except Exception as e:
            self.error_occurred.emit(f"Ошибка загрузки истории: {e}")

    # ========================================================================
    # ОБРАБОТКА ВХОДЯЩИХ
    # ========================================================================

    def on_chat_message(self, data: dict[str, Any]) -> None:
        """
        Обработать входящее сообщение чата.

        Args:
            data: Данные сообщения от сервера.
        """
        self._chat_model.add_message(data)

    def on_system_message(self, data: dict[str, Any]) -> None:
        """
        Обработать системное сообщение.

        Args:
            data: Данные сообщения.
        """
        content = data.get("content", "")
        message_type = data.get("message_type", "system")

        self._chat_model.add_message({
            "content": content,
            "message_type": message_type,
            "username": "Система",
        })

    def _on_model_message(self, message: dict[str, Any]) -> None:
        """
        Обработчик нового сообщения в модели.

        Args:
            message: Данные сообщения.
        """
        self.message_received.emit(message)

    # ========================================================================
    # ВСПОМОГАТЕЛЬНЫЕ
    # ========================================================================

    def set_room(self, room_id: UUID) -> None:
        """
        Установить текущую комнату.

        Args:
            room_id: ID комнаты.
        """
        self._chat_model.set_room_id(room_id)

    def clear(self) -> None:
        """Очистить чат."""
        self._chat_model.clear()