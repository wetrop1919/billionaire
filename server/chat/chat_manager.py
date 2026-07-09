"""
server/chat/chat_manager.py

Менеджер чата игровых комнат.

Обеспечивает:
- Отправку сообщений игроками
- Системные сообщения (игровые события)
- Административные объявления
- Получение истории чата
- Модерацию (удаление сообщений, мут)

Интегрируется с EventBus для автоматической публикации
игровых событий в чат.

Python: 3.13+
"""

from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

from database.repositories.postgresql.chat_repository import ChatRepository
from shared.enums import EventType, SystemMessageType
from shared.validators import validate_chat_message

logger = logging.getLogger("billionaire.chat")


# ============================================================================
# МЕНЕДЖЕР ЧАТА
# ============================================================================

class ChatManager:
    """
    Менеджер чата комнаты.

    Управляет отправкой, получением и модерацией сообщений.
    Подписывается на EventBus для автоматической публикации
    игровых событий в чат как системных сообщений.

    Usage:
        manager = ChatManager(chat_repo)
        messages = await manager.get_history(room_id, limit=50)
        await manager.send_message(room_id, user_id, "Привет!")
    """

    # Максимальная длина сообщения
    MAX_MESSAGE_LENGTH: int = 500

    # Максимальное количество сообщений в истории
    MAX_HISTORY_SIZE: int = 1000

    def __init__(self, chat_repository: ChatRepository) -> None:
        """
        Инициализация менеджера чата.

        Args:
            chat_repository: Репозиторий чата.
        """
        self._chat_repo = chat_repository

        # Мут-лист: {room_id: {user_id: until_timestamp}}
        self._muted_users: dict[UUID, dict[UUID, float]] = {}

    # ========================================================================
    # ОТПРАВКА СООБЩЕНИЙ
    # ========================================================================

    async def send_message(
        self,
        room_id: UUID,
        user_id: UUID,
        username: str,
        content: str,
    ) -> dict[str, Any]:
        """
        Отправить сообщение от игрока.

        Args:
            room_id: ID комнаты.
            user_id: ID отправителя.
            username: Имя отправителя.
            content: Текст сообщения.

        Returns:
            Словарь с данными сообщения.

        Raises:
            ValueError: Если сообщение не прошло валидацию.
        """
        # Проверка мута
        if self.is_muted(room_id, user_id):
            raise ValueError("Вы временно заглушены и не можете отправлять сообщения")

        # Валидация
        error = validate_chat_message(content)
        if error:
            raise ValueError(error)

        # Обрезаем длинные сообщения
        if len(content) > self.MAX_MESSAGE_LENGTH:
            content = content[:self.MAX_MESSAGE_LENGTH]

        # Сохраняем
        message = await self._chat_repo.send_message(
            room_id=room_id,
            user_id=user_id,
            content=content,
            message_type="player",
        )

        message["username"] = username

        logger.debug(
            "Сообщение чата: [%s] %s: %s",
            str(room_id)[:8],
            username,
            content[:50],
        )

        return message

    async def send_system_message(
        self,
        room_id: UUID,
        content: str,
        message_type: str = "system",
    ) -> dict[str, Any]:
        """
        Отправить системное сообщение.

        Args:
            room_id: ID комнаты.
            content: Текст сообщения.
            message_type: Тип (system, game_event, warning, error).

        Returns:
            Словарь с данными сообщения.
        """
        message = await self._chat_repo.send_message(
            room_id=room_id,
            user_id=None,  # type: ignore[arg-type]
            content=content,
            message_type=message_type,
        )

        logger.debug(
            "Системное сообщение в комнату %s: %s",
            str(room_id)[:8],
            content[:50],
        )

        return message

    async def send_admin_announcement(
        self,
        admin_id: UUID,
        content: str,
        room_id: Optional[UUID] = None,
    ) -> dict[str, Any]:
        """
        Отправить административное объявление.

        Args:
            admin_id: ID администратора.
            content: Текст объявления.
            room_id: ID комнаты (None — всем комнатам).

        Returns:
            Словарь с данными сообщения.
        """
        if room_id:
            message = await self._chat_repo.send_admin_message(
                room_id=room_id,
                admin_id=admin_id,
                content=content,
            )
        else:
            # Глобальное объявление (будет отправлено во все активные комнаты)
            message = {
                "admin_id": str(admin_id),
                "content": content,
                "message_type": "admin",
                "global": True,
            }

        logger.info(
            "Админ-объявление от %s: %s",
            str(admin_id)[:8],
            content[:50],
        )

        return message

    # ========================================================================
    # ПОЛУЧЕНИЕ ИСТОРИИ
    # ========================================================================

    async def get_history(
        self,
        room_id: UUID,
        limit: int = 50,
        before_id: Optional[int] = None,
    ) -> list[dict[str, Any]]:
        """
        Получить историю сообщений комнаты.

        Args:
            room_id: ID комнаты.
            limit: Максимальное количество.
            before_id: ID сообщения, до которого загружать.

        Returns:
            Список сообщений.
        """
        return await self._chat_repo.get_history(
            room_id=room_id,
            limit=limit,
            before_id=before_id,
        )

    async def get_new_messages(
        self,
        room_id: UUID,
        since_id: int,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """
        Получить новые сообщения после указанного ID.

        Args:
            room_id: ID комнаты.
            since_id: Последний известный ID.
            limit: Максимальное количество.

        Returns:
            Список новых сообщений.
        """
        return await self._chat_repo.get_history_since(
            room_id=room_id,
            since_id=since_id,
            limit=limit,
        )

    # ========================================================================
    # МОДЕРАЦИЯ
    # ========================================================================

    async def delete_message(self, message_id: int) -> bool:
        """
        Удалить сообщение.

        Args:
            message_id: ID сообщения.

        Returns:
            True, если удалено.
        """
        return await self._chat_repo.delete_message(message_id)

    async def clear_room_chat(self, room_id: UUID) -> int:
        """
        Очистить чат комнаты.

        Args:
            room_id: ID комнаты.

        Returns:
            Количество удалённых сообщений.
        """
        return await self._chat_repo.clear_room_chat(room_id)

    def mute_user(
        self,
        room_id: UUID,
        user_id: UUID,
        duration_seconds: float = 300.0,
    ) -> None:
        """
        Заглушить пользователя на время.

        Args:
            room_id: ID комнаты.
            user_id: ID пользователя.
            duration_seconds: Длительность мута в секундах (по умолчанию 5 минут).
        """
        import time

        if room_id not in self._muted_users:
            self._muted_users[room_id] = {}

        until = time.time() + duration_seconds
        self._muted_users[room_id][user_id] = until

        logger.info(
            "Пользователь %s заглушен в комнате %s на %.0f сек",
            str(user_id)[:8],
            str(room_id)[:8],
            duration_seconds,
        )

    def unmute_user(self, room_id: UUID, user_id: UUID) -> bool:
        """
        Снять мут с пользователя.

        Args:
            room_id: ID комнаты.
            user_id: ID пользователя.

        Returns:
            True, если мут снят.
        """
        room_mutes = self._muted_users.get(room_id, {})
        if user_id in room_mutes:
            del room_mutes[user_id]
            logger.info(
                "Мут снят с пользователя %s в комнате %s",
                str(user_id)[:8],
                str(room_id)[:8],
            )
            return True
        return False

    def is_muted(self, room_id: UUID, user_id: UUID) -> bool:
        """
        Проверить, заглушен ли пользователь.

        Args:
            room_id: ID комнаты.
            user_id: ID пользователя.

        Returns:
            True, если заглушен.
        """
        import time

        room_mutes = self._muted_users.get(room_id, {})
        until = room_mutes.get(user_id)

        if until is None:
            return False

        # Проверяем, не истёк ли мут
        if time.time() > until:
            del room_mutes[user_id]
            return False

        return True

    # ========================================================================
    # ОБРАБОТЧИК ДЛЯ EVENTBUS
    # ========================================================================

    async def handle_game_event(
        self,
        event_type: EventType,
        data: dict[str, Any],
        room_id: Optional[UUID] = None,
    ) -> None:
        """
        Обработать игровое событие и отправить системное сообщение.

        Args:
            event_type: Тип события.
            data: Данные события.
            room_id: ID комнаты (если известен).
        """
        if room_id is None:
            return

        message = self._format_game_event(event_type, data)
        if message:
            await self.send_system_message(
                room_id=room_id,
                content=message,
                message_type="game_event",
            )

    def _format_game_event(
        self,
        event_type: EventType,
        data: dict[str, Any],
    ) -> Optional[str]:
        """
        Форматировать игровое событие в читаемое сообщение.

        Args:
            event_type: Тип события.
            data: Данные события.

        Returns:
            Текст сообщения или None.
        """
        templates = {
            EventType.GAME_STARTED: "🎮 Игра началась! Всем удачи!",
            EventType.GAME_FINISHED: f"🏆 Игра завершена! Победитель: {data.get('winner_name', '?')}",
            EventType.PLAYER_JOINED: f"👋 {data.get('username', '?')} присоединился к игре",
            EventType.PLAYER_LEFT: f"🚪 {data.get('username', '?')} покинул игру",
            EventType.DICE_ROLLED: (
                f"🎲 {data.get('username', '?')} выбрасывает "
                f"[{data.get('die1', 0)}] + [{data.get('die2', 0)}] = {data.get('total', 0)}"
            ),
            EventType.PROPERTY_BOUGHT: (
                f"💰 {data.get('username', '?')} купил {data.get('property_name', '?')} "
                f"за {data.get('price', 0)}$"
            ),
            EventType.RENT_PAID: (
                f"💸 {data.get('from_name', '?')} заплатил {data.get('amount', 0)}$ "
                f"аренды игроку {data.get('to_name', '?')}"
            ),
            EventType.HOUSE_BUILT: (
                f"🏠 {data.get('username', '?')} построил дом на {data.get('property_name', '?')}"
            ),
            EventType.HOTEL_BUILT: (
                f"🏨 {data.get('username', '?')} построил отель на {data.get('property_name', '?')}"
            ),
            EventType.PLAYER_JAILED: f"🚔 {data.get('username', '?')} отправился в тюрьму",
            EventType.PLAYER_FREED: f"🔓 {data.get('username', '?')} освободился из тюрьмы",
            EventType.PLAYER_BANKRUPT: f"💀 {data.get('username', '?')} стал банкротом!",
            EventType.TRADE_ACCEPTED: (
                f"🤝 {data.get('from_name', '?')} и {data.get('to_name', '?')} "
                f"заключили сделку"
            ),
            EventType.CARD_DRAWN: (
                f"🃏 {data.get('username', '?')} взял карточку «{data.get('title', '?')}»"
            ),
            EventType.VERANDA_ENTERED: f"🏖️ {data.get('username', '?')} попал на Веранду",
            EventType.VERANDA_EXITED: f"🚶 {data.get('username', '?')} покинул Веранду",
        }

        return templates.get(event_type)

    # ========================================================================
    # ОЧИСТКА
    # ========================================================================

    async def cleanup_old_messages(self, room_id: UUID, keep_count: int = 1000) -> int:
        """
        Удалить старые сообщения, оставив последние N.

        Args:
            room_id: ID комнаты.
            keep_count: Количество сохраняемых сообщений.

        Returns:
            Количество удалённых.
        """
        return await self._chat_repo.delete_old_messages(room_id, keep_count)

    async def cleanup_all_old_messages(self, older_than_days: int = 30) -> int:
        """
        Удалить старые сообщения во всех комнатах.

        Args:
            older_than_days: Возраст в днях.

        Returns:
            Количество удалённых.
        """
        return await self._chat_repo.delete_old_messages_by_time(older_than_days)

    # ========================================================================
    # ИНФОРМАЦИЯ
    # ========================================================================

    async def get_message_count(self, room_id: UUID) -> int:
        """
        Получить количество сообщений в комнате.

        Args:
            room_id: ID комнаты.

        Returns:
            Количество сообщений.
        """
        return await self._chat_repo.count_messages(room_id)

    def get_stats(self) -> dict:
        """
        Получить статистику менеджера чата.

        Returns:
            Словарь с метриками.
        """
        muted_total = sum(
            len(users) for users in self._muted_users.values()
        )

        return {
            "muted_users": muted_total,
            "rooms_with_mutes": len(self._muted_users),
        }