"""
database/repositories/postgresql/room_repository.py

Репозиторий для работы с комнатами (PostgreSQL).

Реализует операции CRUD для сущности Room,
используя SQLAlchemy ORM модель RoomModel.

Python: 3.13+
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import RoomModel
from database.repositories.base_repository import BaseRepository
from shared.enums import RoomState
from shared.models.room import Room, RoomConfig, RoomListItem


# ============================================================================
# РЕПОЗИТОРИЙ КОМНАТ
# ============================================================================

class RoomRepository(BaseRepository[RoomModel, Room]):
    """
    Репозиторий для работы с игровыми комнатами.

    Предоставляет методы для создания, поиска, обновления
    и фильтрации комнат.

    Usage:
        repo = RoomRepository(session)
        rooms = await repo.get_waiting_rooms()
        room = await repo.get_by_name("Весёлая игра")
    """

    def __init__(self, session: AsyncSession) -> None:
        """Инициализация репозитория."""
        super().__init__(session, RoomModel)

    # ========================================================================
    # ПРЕОБРАЗОВАНИЯ (абстрактные методы)
    # ========================================================================

    def _to_entity(self, model: RoomModel) -> Room:
        """Преобразовать ORM-модель в бизнес-сущность Room."""
        config = RoomConfig.from_dict(model.game_params)
        return Room(
            room_id=model.room_id,
            name=model.name,
            owner_id=model.owner_id,
            config=config,
            state=RoomState(model.state),
            players=[],  # Игроки хранятся отдельно в GamePlayerModel
            observers=[],  # Наблюдатели — в GamePlayerModel или сессиях
            created_at=model.created_at,
        )

    def _to_model(self, entity: Room) -> RoomModel:
        """Преобразовать бизнес-сущность Room в ORM-модель."""
        return RoomModel(
            room_id=entity.room_id,
            name=entity.name,
            owner_id=entity.owner_id,
            is_private=entity.config.is_private,
            password_hash=entity.config.password_hash,
            max_players=entity.config.max_players,
            state=entity.state.value,
            game_params=entity.config.to_dict(),
            created_at=entity.created_at,
        )

    def _update_model(self, model: RoomModel, entity: Room) -> RoomModel:
        """Обновить существующую ORM-модель данными из Room."""
        model.name = entity.name
        model.owner_id = entity.owner_id
        model.is_private = entity.config.is_private
        model.password_hash = entity.config.password_hash
        model.max_players = entity.config.max_players
        model.state = entity.state.value
        model.game_params = entity.config.to_dict()
        return model

    def _get_model_id(self, model: RoomModel) -> UUID:
        """Получить ID комнаты из модели."""
        return model.room_id

    # ========================================================================
    # СПЕЦИФИЧЕСКИЕ МЕТОДЫ
    # ========================================================================

    async def get_by_name(self, name: str) -> Optional[Room]:
        """
        Найти комнату по названию.

        Args:
            name: Название комнаты.

        Returns:
            Комната или None.
        """
        result = await self._session.execute(
            select(RoomModel).where(RoomModel.name == name)
        )
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return self._to_entity(model)

    async def name_exists(self, name: str) -> bool:
        """
        Проверить, занято ли название комнаты.

        Args:
            name: Проверяемое название.

        Returns:
            True, если название уже используется.
        """
        return await self.get_by_name(name) is not None

    async def get_by_owner(
        self,
        owner_id: UUID,
        offset: int = 0,
        limit: int = 100,
    ) -> list[Room]:
        """
        Получить комнаты, созданные указанным пользователем.

        Args:
            owner_id: ID владельца.
            offset: Смещение.
            limit: Лимит.

        Returns:
            Список комнат.
        """
        return await self.get_all(
            offset=offset,
            limit=limit,
            filters={"owner_id": owner_id},
        )

    async def count_by_owner(self, owner_id: UUID) -> int:
        """
        Подсчитать количество комнат пользователя.

        Args:
            owner_id: ID владельца.

        Returns:
            Количество комнат.
        """
        return await self.count(filters={"owner_id": owner_id})

    async def get_by_state(
        self,
        state: RoomState,
        offset: int = 0,
        limit: int = 100,
    ) -> list[Room]:
        """
        Получить комнаты в указанном состоянии.

        Args:
            state: Состояние комнаты.
            offset: Смещение.
            limit: Лимит.

        Returns:
            Список комнат.
        """
        return await self.get_all(
            offset=offset,
            limit=limit,
            filters={"state": state.value},
        )

    async def get_waiting_rooms(
        self,
        offset: int = 0,
        limit: int = 100,
    ) -> list[Room]:
        """
        Получить комнаты в ожидании игроков.

        Args:
            offset: Смещение.
            limit: Лимит.

        Returns:
            Список комнат в состоянии WAITING.
        """
        return await self.get_by_state(RoomState.WAITING, offset, limit)

    async def get_active_rooms(
        self,
        offset: int = 0,
        limit: int = 100,
    ) -> list[Room]:
        """
        Получить комнаты с активной игрой.

        Args:
            offset: Смещение.
            limit: Лимит.

        Returns:
            Список комнат в состоянии IN_GAME.
        """
        return await self.get_by_state(RoomState.IN_GAME, offset, limit)

    async def get_public_rooms(
        self,
        offset: int = 0,
        limit: int = 100,
    ) -> list[Room]:
        """
        Получить публичные комнаты.

        Args:
            offset: Смещение.
            limit: Лимит.

        Returns:
            Список публичных комнат.
        """
        result = await self._session.execute(
            select(RoomModel)
            .where(
                RoomModel.is_private == False,  # noqa: E712
                RoomModel.state == RoomState.WAITING.value,
            )
            .offset(offset)
            .limit(limit)
        )
        models = result.scalars().all()
        return [self._to_entity(model) for model in models]

    async def update_state(self, room_id: UUID, new_state: RoomState) -> bool:
        """
        Обновить состояние комнаты.

        Args:
            room_id: ID комнаты.
            new_state: Новое состояние.

        Returns:
            True, если обновление выполнено.
        """
        room = await self.get_by_id(room_id)
        if room is None:
            return False
        room.state = new_state
        await self.save(room)
        return True

    async def update_owner(self, room_id: UUID, new_owner_id: UUID) -> bool:
        """
        Сменить владельца комнаты.

        Args:
            room_id: ID комнаты.
            new_owner_id: ID нового владельца.

        Returns:
            True, если смена выполнена.
        """
        await self._session.execute(
            update(RoomModel)
            .where(RoomModel.room_id == room_id)
            .values(owner_id=new_owner_id)
        )
        await self._session.flush()
        return True

    async def update_config(self, room_id: UUID, config: RoomConfig) -> bool:
        """
        Обновить конфигурацию комнаты.

        Args:
            room_id: ID комнаты.
            config: Новая конфигурация.

        Returns:
            True, если обновление выполнено.
        """
        room = await self.get_by_id(room_id)
        if room is None:
            return False
        room.config = config
        await self.save(room)
        return True

    async def get_room_list_items(
        self,
        state_filter: Optional[str] = None,
        show_private: bool = True,
        show_full: bool = False,
        offset: int = 0,
        limit: int = 50,
    ) -> list[RoomListItem]:
        """
        Получить список комнат для отображения в GUI.

        Args:
            state_filter: Фильтр по состоянию (waiting, in_game, finished, all).
            show_private: Показывать ли приватные комнаты.
            show_full: Показывать ли заполненные комнаты.
            offset: Смещение.
            limit: Лимит.

        Returns:
            Список RoomListItem.
        """
        query = select(RoomModel)

        # Фильтр по состоянию
        if state_filter and state_filter != "all":
            query = query.where(RoomModel.state == state_filter)

        # Фильтр приватных
        if not show_private:
            query = query.where(RoomModel.is_private == False)  # noqa: E712

        query = query.offset(offset).limit(limit)
        result = await self._session.execute(query)
        models = result.scalars().all()

        items: list[RoomListItem] = []
        for model in models:
            item = RoomListItem(
                room_id=model.room_id,
                name=model.name,
                owner_id=model.owner_id,
                players_count=0,  # Заполняется отдельным запросом
                max_players=model.max_players,
                is_private=model.is_private,
                has_password=model.password_hash is not None,
                state=RoomState(model.state),
            )
            items.append(item)

        return items

    async def delete_empty_rooms(self, older_than_minutes: int = 60) -> int:
        """
        Удалить пустые комнаты, созданные более N минут назад.

        Args:
            older_than_minutes: Возраст в минутах.

        Returns:
            Количество удалённых комнат.
        """
        from datetime import timedelta

        cutoff = datetime.now(timezone.utc) - timedelta(minutes=older_than_minutes)

        result = await self._session.execute(
            delete(RoomModel).where(
                RoomModel.state == RoomState.WAITING.value,
                RoomModel.created_at < cutoff,
            )
        )
        await self._session.flush()
        return result.rowcount