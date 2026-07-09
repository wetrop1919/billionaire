"""
database/repositories/postgresql/event_repository.py

Репозиторий для работы с игровыми событиями и логами (PostgreSQL).

Реализует операции для хранения и получения игровых событий,
сетевых логов и административных действий.

Python: 3.13+
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import GameEventModel, NetworkLogModel, AdminLogModel


# ============================================================================
# РЕПОЗИТОРИЙ ИГРОВЫХ СОБЫТИЙ
# ============================================================================

class EventRepository:
    """
    Репозиторий для работы с игровыми событиями.

    Предоставляет методы для записи, чтения и очистки
    журнала игровых событий, сетевых и админ-логов.

    Usage:
        repo = EventRepository(session)
        await repo.log_game_event(game_id, event_type, user_id, data)
        events = await repo.get_game_events(game_id, limit=100)
    """

    def __init__(self, session: AsyncSession) -> None:
        """
        Инициализация репозитория.

        Args:
            session: Асинхронная сессия БД.
        """
        self._session: AsyncSession = session

    # ========================================================================
    # ИГРОВЫЕ СОБЫТИЯ
    # ========================================================================

    async def log_game_event(
        self,
        game_id: UUID,
        event_type: str,
        user_id: Optional[UUID] = None,
        target_id: Optional[str] = None,
        data: Optional[dict[str, Any]] = None,
        turn_number: int = 0,
        sequence: int = 0,
    ) -> int:
        """
        Записать игровое событие в журнал.

        Args:
            game_id: ID игры.
            event_type: Тип события.
            user_id: ID инициатора.
            target_id: ID цели.
            data: Данные события.
            turn_number: Номер хода.
            sequence: Порядковый номер.

        Returns:
            ID созданной записи.
        """
        event = GameEventModel(
            game_id=game_id,
            event_type=event_type,
            user_id=user_id,
            target_id=target_id,
            data=data or {},
            turn_number=turn_number,
            sequence=sequence,
            created_at=datetime.now(timezone.utc),
        )
        self._session.add(event)
        await self._session.flush()

        return event.id

    async def log_game_events_batch(
        self,
        events: list[dict[str, Any]],
    ) -> int:
        """
        Записать несколько игровых событий одним батчем.

        Args:
            events: Список словарей с параметрами событий.

        Returns:
            Количество записанных событий.
        """
        for event_data in events:
            event = GameEventModel(
                game_id=event_data["game_id"],
                event_type=event_data["event_type"],
                user_id=event_data.get("user_id"),
                target_id=event_data.get("target_id"),
                data=event_data.get("data", {}),
                turn_number=event_data.get("turn_number", 0),
                sequence=event_data.get("sequence", 0),
                created_at=datetime.now(timezone.utc),
            )
            self._session.add(event)

        await self._session.flush()
        return len(events)

    async def get_game_events(
        self,
        game_id: UUID,
        offset: int = 0,
        limit: int = 100,
        event_type: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """
        Получить игровые события с фильтрацией.

        Args:
            game_id: ID игры.
            offset: Смещение.
            limit: Лимит.
            event_type: Фильтр по типу события.

        Returns:
            Список событий.
        """
        query = select(GameEventModel).where(
            GameEventModel.game_id == game_id
        )

        if event_type:
            query = query.where(GameEventModel.event_type == event_type)

        query = query.order_by(GameEventModel.sequence.desc())
        query = query.offset(offset).limit(limit)

        result = await self._session.execute(query)
        models = result.scalars().all()

        events: list[dict[str, Any]] = []
        for model in reversed(models):
            events.append({
                "id": model.id,
                "game_id": str(model.game_id),
                "event_type": model.event_type,
                "user_id": str(model.user_id) if model.user_id else None,
                "target_id": model.target_id,
                "data": model.data,
                "turn_number": model.turn_number,
                "sequence": model.sequence,
                "created_at": model.created_at.isoformat(),
            })

        return events

    async def get_game_events_since(
        self,
        game_id: UUID,
        since_sequence: int,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        """
        Получить события начиная с указанного порядкового номера.

        Используется для синхронизации состояния клиента.

        Args:
            game_id: ID игры.
            since_sequence: Порядковый номер, с которого начинать.
            limit: Лимит.

        Returns:
            Список новых событий.
        """
        query = (
            select(GameEventModel)
            .where(
                GameEventModel.game_id == game_id,
                GameEventModel.sequence >= since_sequence,
            )
            .order_by(GameEventModel.sequence.asc())
            .limit(limit)
        )

        result = await self._session.execute(query)
        models = result.scalars().all()

        return [
            {
                "id": model.id,
                "game_id": str(model.game_id),
                "event_type": model.event_type,
                "user_id": str(model.user_id) if model.user_id else None,
                "target_id": model.target_id,
                "data": model.data,
                "turn_number": model.turn_number,
                "sequence": model.sequence,
                "created_at": model.created_at.isoformat(),
            }
            for model in models
        ]

    async def get_last_event_sequence(self, game_id: UUID) -> int:
        """
        Получить последний порядковый номер события в игре.

        Args:
            game_id: ID игры.

        Returns:
            Последний sequence или 0.
        """
        result = await self._session.execute(
            select(func.max(GameEventModel.sequence)).where(
                GameEventModel.game_id == game_id
            )
        )
        value = result.scalar_one()
        return value if value is not None else 0

    async def count_game_events(
        self,
        game_id: UUID,
        event_type: Optional[str] = None,
    ) -> int:
        """
        Подсчитать количество событий в игре.

        Args:
            game_id: ID игры.
            event_type: Фильтр по типу.

        Returns:
            Количество событий.
        """
        query = select(func.count()).select_from(GameEventModel).where(
            GameEventModel.game_id == game_id
        )

        if event_type:
            query = query.where(GameEventModel.event_type == event_type)

        result = await self._session.execute(query)
        return result.scalar_one()

    async def delete_game_events(self, game_id: UUID) -> int:
        """
        Удалить все события игры.

        Args:
            game_id: ID игры.

        Returns:
            Количество удалённых записей.
        """
        result = await self._session.execute(
            delete(GameEventModel).where(
                GameEventModel.game_id == game_id
            )
        )
        await self._session.flush()
        return result.rowcount

    # ========================================================================
    # СЕТЕВЫЕ ЛОГИ
    # ========================================================================

    async def log_network_event(
        self,
        event_type: str,
        user_id: Optional[UUID] = None,
        ip_address: Optional[str] = None,
        packet_type: Optional[str] = None,
        data: Optional[dict[str, Any]] = None,
    ) -> int:
        """
        Записать сетевое событие.

        Args:
            event_type: Тип события (connect, disconnect, error, heartbeat).
            user_id: ID пользователя.
            ip_address: IP-адрес.
            packet_type: Тип пакета.
            data: Дополнительные данные.

        Returns:
            ID созданной записи.
        """
        log_entry = NetworkLogModel(
            event_type=event_type,
            user_id=user_id,
            ip_address=ip_address,
            packet_type=packet_type,
            data=data or {},
            created_at=datetime.now(timezone.utc),
        )
        self._session.add(log_entry)
        await self._session.flush()

        return log_entry.id

    async def get_network_logs(
        self,
        offset: int = 0,
        limit: int = 100,
        user_id: Optional[UUID] = None,
        event_type: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """
        Получить сетевые логи с фильтрацией.

        Args:
            offset: Смещение.
            limit: Лимит.
            user_id: Фильтр по пользователю.
            event_type: Фильтр по типу события.

        Returns:
            Список записей лога.
        """
        query = select(NetworkLogModel)

        if user_id:
            query = query.where(NetworkLogModel.user_id == user_id)
        if event_type:
            query = query.where(NetworkLogModel.event_type == event_type)

        query = query.order_by(NetworkLogModel.created_at.desc())
        query = query.offset(offset).limit(limit)

        result = await self._session.execute(query)
        models = result.scalars().all()

        return [
            {
                "id": model.id,
                "event_type": model.event_type,
                "user_id": str(model.user_id) if model.user_id else None,
                "ip_address": model.ip_address,
                "packet_type": model.packet_type,
                "data": model.data,
                "created_at": model.created_at.isoformat(),
            }
            for model in models
        ]

    async def delete_old_network_logs(self, older_than_days: int = 30) -> int:
        """
        Удалить старые сетевые логи.

        Args:
            older_than_days: Возраст в днях.

        Returns:
            Количество удалённых записей.
        """
        from datetime import timedelta

        cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)

        result = await self._session.execute(
            delete(NetworkLogModel).where(
                NetworkLogModel.created_at < cutoff
            )
        )
        await self._session.flush()
        return result.rowcount

    # ========================================================================
    # АДМИНИСТРАТИВНЫЕ ЛОГИ
    # ========================================================================

    async def log_admin_action(
        self,
        admin_id: UUID,
        command: str,
        target_id: Optional[str] = None,
        data: Optional[dict[str, Any]] = None,
    ) -> int:
        """
        Записать административное действие.

        Args:
            admin_id: ID администратора.
            command: Выполненная команда.
            target_id: Цель команды.
            data: Параметры команды.

        Returns:
            ID созданной записи.
        """
        log_entry = AdminLogModel(
            admin_id=admin_id,
            command=command,
            target_id=target_id,
            data=data or {},
            created_at=datetime.now(timezone.utc),
        )
        self._session.add(log_entry)
        await self._session.flush()

        return log_entry.id

    async def get_admin_logs(
        self,
        offset: int = 0,
        limit: int = 100,
        admin_id: Optional[UUID] = None,
        command: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """
        Получить административные логи с фильтрацией.

        Args:
            offset: Смещение.
            limit: Лимит.
            admin_id: Фильтр по администратору.
            command: Фильтр по команде.

        Returns:
            Список записей лога.
        """
        query = select(AdminLogModel)

        if admin_id:
            query = query.where(AdminLogModel.admin_id == admin_id)
        if command:
            query = query.where(AdminLogModel.command == command)

        query = query.order_by(AdminLogModel.created_at.desc())
        query = query.offset(offset).limit(limit)

        result = await self._session.execute(query)
        models = result.scalars().all()

        return [
            {
                "id": model.id,
                "admin_id": str(model.admin_id),
                "command": model.command,
                "target_id": model.target_id,
                "data": model.data,
                "created_at": model.created_at.isoformat(),
            }
            for model in models
        ]

    async def delete_old_admin_logs(self, older_than_days: int = 90) -> int:
        """
        Удалить старые админ-логи.

        Args:
            older_than_days: Возраст в днях.

        Returns:
            Количество удалённых записей.
        """
        from datetime import timedelta

        cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)

        result = await self._session.execute(
            delete(AdminLogModel).where(
                AdminLogModel.created_at < cutoff
            )
        )
        await self._session.flush()
        return result.rowcount

    # ========================================================================
    # ОБЩАЯ ОЧИСТКА
    # ========================================================================

    async def cleanup_all_old_logs(
        self,
        game_events_days: int = 30,
        network_logs_days: int = 30,
        admin_logs_days: int = 90,
    ) -> dict[str, int]:
        """
        Очистить все старые логи.

        Args:
            game_events_days: Возраст игровых событий в днях.
            network_logs_days: Возраст сетевых логов в днях.
            admin_logs_days: Возраст админ-логов в днях.

        Returns:
            Словарь с количеством удалённых записей по категориям.
        """
        return {
            "game_events_deleted": 0,  # Удаляются вместе с играми
            "network_logs_deleted": await self.delete_old_network_logs(network_logs_days),
            "admin_logs_deleted": await self.delete_old_admin_logs(admin_logs_days),
        }