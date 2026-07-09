"""
database/repositories/postgresql/chat_repository.py

Репозиторий для работы с чатом (PostgreSQL).

Реализует операции для хранения и получения сообщений чата,
используя SQLAlchemy ORM модель ChatMessageModel.

Python: 3.13+
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import ChatMessageModel


# ============================================================================
# РЕПОЗИТОРИЙ ЧАТА
# ============================================================================

class ChatRepository:
    """
    Репозиторий для работы с сообщениями чата.

    Предоставляет методы для отправки, получения истории
    и управления сообщениями чата комнаты.

    Usage:
        repo = ChatRepository(session)
        messages = await repo.get_history(room_id, limit=50)
        await repo.send_message(room_id, user_id, "Привет!")
    """

    def __init__(self, session: AsyncSession) -> None:
        """
        Инициализация репозитория.

        Args:
            session: Асинхронная сессия БД.
        """
        self._session: AsyncSession = session

    # ========================================================================
    # ОТПРАВКА СООБЩЕНИЙ
    # ========================================================================

    async def send_message(
        self,
        room_id: UUID,
        user_id: UUID,
        content: str,
        message_type: str = "player",
    ) -> dict:
        """
        Отправить сообщение в чат комнаты.

        Args:
            room_id: ID комнаты.
            user_id: ID отправителя.
            content: Текст сообщения.
            message_type: Тип сообщения (player, system, admin).

        Returns:
            Словарь с данными сохранённого сообщения.
        """
        message = ChatMessageModel(
            room_id=room_id,
            user_id=user_id,
            content=content,
            message_type=message_type,
            created_at=datetime.now(timezone.utc),
        )
        self._session.add(message)
        await self._session.flush()

        return {
            "id": message.id,
            "room_id": str(message.room_id),
            "user_id": str(message.user_id) if message.user_id else None,
            "content": message.content,
            "message_type": message.message_type,
            "created_at": message.created_at.isoformat(),
        }

    async def send_system_message(
        self,
        room_id: UUID,
        content: str,
    ) -> dict:
        """
        Отправить системное сообщение (от имени сервера).

        Args:
            room_id: ID комнаты.
            content: Текст сообщения.

        Returns:
            Словарь с данными сообщения.
        """
        return await self.send_message(
            room_id=room_id,
            user_id=None,  # type: ignore[arg-type]
            content=content,
            message_type="system",
        )

    async def send_admin_message(
        self,
        room_id: UUID,
        admin_id: UUID,
        content: str,
    ) -> dict:
        """
        Отправить сообщение от администратора.

        Args:
            room_id: ID комнаты.
            admin_id: ID администратора.
            content: Текст сообщения.

        Returns:
            Словарь с данными сообщения.
        """
        return await self.send_message(
            room_id=room_id,
            user_id=admin_id,
            content=content,
            message_type="admin",
        )

    # ========================================================================
    # ПОЛУЧЕНИЕ ИСТОРИИ
    # ========================================================================

    async def get_history(
        self,
        room_id: UUID,
        limit: int = 50,
        before_id: Optional[int] = None,
    ) -> list[dict]:
        """
        Получить историю сообщений комнаты.

        Args:
            room_id: ID комнаты.
            limit: Максимальное количество сообщений.
            before_id: Получить сообщения до указанного ID (пагинация назад).

        Returns:
            Список словарей с данными сообщений.
        """
        query = select(ChatMessageModel).where(
            ChatMessageModel.room_id == room_id
        )

        if before_id is not None:
            query = query.where(ChatMessageModel.id < before_id)

        query = query.order_by(ChatMessageModel.id.desc()).limit(limit)

        result = await self._session.execute(query)
        models = result.scalars().all()

        # Возвращаем в хронологическом порядке (старые сверху)
        messages: list[dict] = []
        for model in reversed(models):
            messages.append({
                "id": model.id,
                "room_id": str(model.room_id),
                "user_id": str(model.user_id) if model.user_id else None,
                "content": model.content,
                "message_type": model.message_type,
                "created_at": model.created_at.isoformat(),
            })

        return messages

    async def get_history_since(
        self,
        room_id: UUID,
        since_id: int,
        limit: int = 100,
    ) -> list[dict]:
        """
        Получить сообщения после указанного ID (для подгрузки новых).

        Args:
            room_id: ID комнаты.
            since_id: Получить сообщения после этого ID.
            limit: Максимальное количество.

        Returns:
            Список новых сообщений.
        """
        query = (
            select(ChatMessageModel)
            .where(
                ChatMessageModel.room_id == room_id,
                ChatMessageModel.id > since_id,
            )
            .order_by(ChatMessageModel.id.asc())
            .limit(limit)
        )

        result = await self._session.execute(query)
        models = result.scalars().all()

        return [
            {
                "id": model.id,
                "room_id": str(model.room_id),
                "user_id": str(model.user_id) if model.user_id else None,
                "content": model.content,
                "message_type": model.message_type,
                "created_at": model.created_at.isoformat(),
            }
            for model in models
        ]

    async def get_last_message_id(self, room_id: UUID) -> Optional[int]:
        """
        Получить ID последнего сообщения в комнате.

        Args:
            room_id: ID комнаты.

        Returns:
            ID последнего сообщения или None.
        """
        result = await self._session.execute(
            select(func.max(ChatMessageModel.id)).where(
                ChatMessageModel.room_id == room_id
            )
        )
        return result.scalar_one()

    # ========================================================================
    # УПРАВЛЕНИЕ СООБЩЕНИЯМИ
    # ========================================================================

    async def delete_message(self, message_id: int) -> bool:
        """
        Удалить сообщение по ID.

        Args:
            message_id: ID сообщения.

        Returns:
            True, если удаление выполнено.
        """
        result = await self._session.execute(
            delete(ChatMessageModel).where(
                ChatMessageModel.id == message_id
            )
        )
        await self._session.flush()
        return result.rowcount > 0

    async def delete_user_messages(
        self,
        room_id: UUID,
        user_id: UUID,
    ) -> int:
        """
        Удалить все сообщения пользователя в комнате.

        Args:
            room_id: ID комнаты.
            user_id: ID пользователя.

        Returns:
            Количество удалённых сообщений.
        """
        result = await self._session.execute(
            delete(ChatMessageModel).where(
                ChatMessageModel.room_id == room_id,
                ChatMessageModel.user_id == user_id,
            )
        )
        await self._session.flush()
        return result.rowcount

    async def clear_room_chat(self, room_id: UUID) -> int:
        """
        Очистить весь чат комнаты.

        Args:
            room_id: ID комнаты.

        Returns:
            Количество удалённых сообщений.
        """
        result = await self._session.execute(
            delete(ChatMessageModel).where(
                ChatMessageModel.room_id == room_id
            )
        )
        await self._session.flush()
        return result.rowcount

    async def count_messages(self, room_id: UUID) -> int:
        """
        Подсчитать количество сообщений в комнате.

        Args:
            room_id: ID комнаты.

        Returns:
            Количество сообщений.
        """
        result = await self._session.execute(
            select(func.count()).select_from(ChatMessageModel).where(
                ChatMessageModel.room_id == room_id
            )
        )
        return result.scalar_one()

    # ========================================================================
    # ОЧИСТКА СТАРЫХ СООБЩЕНИЙ
    # ========================================================================

    async def delete_old_messages(
        self,
        room_id: UUID,
        keep_count: int = 1000,
    ) -> int:
        """
        Удалить старые сообщения, оставив только N последних.

        Args:
            room_id: ID комнаты.
            keep_count: Количество сохраняемых сообщений.

        Returns:
            Количество удалённых сообщений.
        """
        # Находим ID сообщения, до которого нужно удалить
        result = await self._session.execute(
            select(ChatMessageModel.id)
            .where(ChatMessageModel.room_id == room_id)
            .order_by(ChatMessageModel.id.desc())
            .offset(keep_count)
            .limit(1)
        )
        threshold = result.scalar_one_or_none()

        if threshold is None:
            return 0  # Сообщений меньше лимита

        # Удаляем всё, что старше
        result = await self._session.execute(
            delete(ChatMessageModel).where(
                ChatMessageModel.room_id == room_id,
                ChatMessageModel.id <= threshold,
            )
        )
        await self._session.flush()
        return result.rowcount

    async def delete_old_messages_by_time(
        self,
        older_than_days: int = 30,
    ) -> int:
        """
        Удалить сообщения старше N дней во всех комнатах.

        Args:
            older_than_days: Возраст в днях.

        Returns:
            Количество удалённых сообщений.
        """
        from datetime import timedelta

        cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)

        result = await self._session.execute(
            delete(ChatMessageModel).where(
                ChatMessageModel.created_at < cutoff
            )
        )
        await self._session.flush()
        return result.rowcount