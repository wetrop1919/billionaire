"""
database/repositories/postgresql/game_repository.py

Репозиторий для работы с играми (PostgreSQL).

Реализует операции CRUD для сущностей Game, PlayerState и PropertyState,
используя SQLAlchemy ORM модели GameModel, GamePlayerModel, GamePropertyModel.

Python: 3.13+
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import (
    GameModel,
    GamePlayerModel,
    GamePropertyModel,
    PlayerCardModel,
)
from database.repositories.base_repository import BaseRepository
from shared.enums import GameState
from shared.models.game import Game, GameConfig, PlayerState
from shared.models.position import Board, BoardPosition
from shared.models.property import PropertyState
from shared.models.card import PlayerCard


# ============================================================================
# РЕПОЗИТОРИЙ ИГР
# ============================================================================

class GameRepository(BaseRepository[GameModel, Game]):
    """
    Репозиторий для работы с игровыми сессиями.

    Предоставляет методы для создания, загрузки, обновления
    и сохранения состояния игры, игроков и собственности.

    Usage:
        repo = GameRepository(session)
        game = await repo.get_by_room_id(room_id)
        await repo.save_full_game_state(game)
    """

    def __init__(self, session: AsyncSession) -> None:
        """Инициализация репозитория."""
        super().__init__(session, GameModel)

    # ========================================================================
    # ПРЕОБРАЗОВАНИЯ (абстрактные методы)
    # ========================================================================

    def _to_entity(self, model: GameModel) -> Game:
        """Преобразовать ORM-модель в бизнес-сущность Game."""
        config = GameConfig()
        return Game(
            game_id=model.game_id,
            room_id=model.room_id,
            config=config,
            state=GameState(model.state),
            board=Board(),
            players={},
            turn_order=[],
            current_turn_index=model.current_turn_index,
            turn_number=model.turn_number,
            properties={},
            property_groups=[],
            started_at=model.started_at,
            finished_at=model.finished_at,
            free_parking_money=model.free_parking_money,
            event_sequence=0,
        )

    def _to_model(self, entity: Game) -> GameModel:
        """Преобразовать бизнес-сущность Game в ORM-модель."""
        return GameModel(
            game_id=entity.game_id,
            room_id=entity.room_id,
            state=entity.state.value,
            current_turn_index=entity.current_turn_index,
            turn_number=entity.turn_number,
            board_state={},
            free_parking_money=entity.free_parking_money,
            started_at=entity.started_at,
            finished_at=entity.finished_at,
        )

    def _update_model(self, model: GameModel, entity: Game) -> GameModel:
        """Обновить существующую ORM-модель данными из Game."""
        model.state = entity.state.value
        model.current_turn_index = entity.current_turn_index
        model.turn_number = entity.turn_number
        model.free_parking_money = entity.free_parking_money
        model.started_at = entity.started_at
        model.finished_at = entity.finished_at
        return model

    def _get_model_id(self, model: GameModel) -> UUID:
        """Получить ID игры из модели."""
        return model.game_id

    # ========================================================================
    # СПЕЦИФИЧЕСКИЕ МЕТОДЫ: ИГРА
    # ========================================================================

    async def get_by_room_id(self, room_id: UUID) -> Optional[Game]:
        """
        Найти игру по ID комнаты.

        Args:
            room_id: ID комнаты.

        Returns:
            Игра или None.
        """
        result = await self._session.execute(
            select(GameModel).where(GameModel.room_id == room_id)
        )
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return self._to_entity(model)

    async def get_active_games(
        self,
        offset: int = 0,
        limit: int = 100,
    ) -> list[Game]:
        """
        Получить активные игры.

        Args:
            offset: Смещение.
            limit: Лимит.

        Returns:
            Список активных игр.
        """
        return await self.get_all(
            offset=offset,
            limit=limit,
            filters={"state": GameState.ACTIVE.value},
        )

    async def get_unfinished_games(self) -> list[Game]:
        """
        Получить незавершённые игры (для crash recovery).

        Returns:
            Список игр, которые не в состоянии FINISHED или CLOSED.
        """
        result = await self._session.execute(
            select(GameModel).where(
                GameModel.state.notin_([
                    GameState.FINISHED.value,
                    GameState.CLOSED.value,
                ])
            )
        )
        models = result.scalars().all()
        return [self._to_entity(model) for model in models]

    async def update_game_state(
        self,
        game_id: UUID,
        state: GameState,
    ) -> bool:
        """
        Обновить состояние игры.

        Args:
            game_id: ID игры.
            state: Новое состояние.

        Returns:
            True, если обновление выполнено.
        """
        game = await self.get_by_id(game_id)
        if game is None:
            return False
        game.state = state

        if state == GameState.ACTIVE and game.started_at is None:
            game.started_at = datetime.now(timezone.utc)

        if state in (GameState.FINISHED, GameState.CLOSED):
            game.finished_at = datetime.now(timezone.utc)

        await self.save(game)
        return True

    # ========================================================================
    # СПЕЦИФИЧЕСКИЕ МЕТОДЫ: ИГРОКИ
    # ========================================================================

    async def get_game_players(self, game_id: UUID) -> list[PlayerState]:
        """
        Получить состояния всех игроков в игре.

        Args:
            game_id: ID игры.

        Returns:
            Список PlayerState.
        """
        result = await self._session.execute(
            select(GamePlayerModel).where(GamePlayerModel.game_id == game_id)
        )
        models = result.scalars().all()

        players: list[PlayerState] = []
        for model in models:
            player = PlayerState(
                user_id=model.user_id,
                username="",  # Имя загружается отдельно
                money=model.money,
                position=BoardPosition(cell_id=model.position),
                properties=model.properties,
                cards=[PlayerCard.from_dict(c) for c in model.cards],
                in_jail=model.in_jail,
                jail_rounds=model.jail_rounds,
                bankrupt=model.bankrupt,
                is_online=model.is_online,
                color=model.color,
            )
            players.append(player)

        return players

    async def get_game_player(
        self,
        game_id: UUID,
        user_id: UUID,
    ) -> Optional[PlayerState]:
        """
        Получить состояние конкретного игрока в игре.

        Args:
            game_id: ID игры.
            user_id: ID игрока.

        Returns:
            PlayerState или None.
        """
        result = await self._session.execute(
            select(GamePlayerModel).where(
                GamePlayerModel.game_id == game_id,
                GamePlayerModel.user_id == user_id,
            )
        )
        model = result.scalar_one_or_none()
        if model is None:
            return None

        return PlayerState(
            user_id=model.user_id,
            username="",
            money=model.money,
            position=BoardPosition(cell_id=model.position),
            properties=model.properties,
            cards=[PlayerCard.from_dict(c) for c in model.cards],
            in_jail=model.in_jail,
            jail_rounds=model.jail_rounds,
            bankrupt=model.bankrupt,
            is_online=model.is_online,
            color=model.color,
        )

    async def save_player_state(
        self,
        game_id: UUID,
        player: PlayerState,
    ) -> None:
        """
        Сохранить состояние игрока.

        Args:
            game_id: ID игры.
            player: Состояние игрока.
        """
        # Проверяем существование
        result = await self._session.execute(
            select(GamePlayerModel).where(
                GamePlayerModel.game_id == game_id,
                GamePlayerModel.user_id == player.user_id,
            )
        )
        model = result.scalar_one_or_none()

        if model is not None:
            # Обновление
            model.money = player.money
            model.position = player.position.cell_id
            model.properties = player.properties
            model.cards = [c.to_dict() for c in player.cards]
            model.in_jail = player.in_jail
            model.jail_rounds = player.jail_rounds
            model.bankrupt = player.bankrupt
            model.is_online = player.is_online
            model.color = player.color
        else:
            # Создание
            model = GamePlayerModel(
                game_id=game_id,
                user_id=player.user_id,
                slot_index=0,
                money=player.money,
                position=player.position.cell_id,
                properties=player.properties,
                cards=[c.to_dict() for c in player.cards],
                in_jail=player.in_jail,
                jail_rounds=player.jail_rounds,
                bankrupt=player.bankrupt,
                is_online=player.is_online,
                color=player.color,
            )
            self._session.add(model)

        await self._session.flush()

    async def save_all_players(
        self,
        game_id: UUID,
        players: dict[UUID, PlayerState],
    ) -> None:
        """
        Сохранить состояния всех игроков.

        Args:
            game_id: ID игры.
            players: Словарь {user_id: PlayerState}.
        """
        for player in players.values():
            await self.save_player_state(game_id, player)

    async def update_player_money(
        self,
        game_id: UUID,
        user_id: UUID,
        new_money: int,
    ) -> None:
        """
        Обновить баланс игрока.

        Args:
            game_id: ID игры.
            user_id: ID игрока.
            new_money: Новый баланс.
        """
        await self._session.execute(
            update(GamePlayerModel)
            .where(
                GamePlayerModel.game_id == game_id,
                GamePlayerModel.user_id == user_id,
            )
            .values(money=new_money)
        )
        await self._session.flush()

    async def update_player_position(
        self,
        game_id: UUID,
        user_id: UUID,
        new_position: int,
    ) -> None:
        """
        Обновить позицию игрока на поле.

        Args:
            game_id: ID игры.
            user_id: ID игрока.
            new_position: Новая позиция (0-39).
        """
        await self._session.execute(
            update(GamePlayerModel)
            .where(
                GamePlayerModel.game_id == game_id,
                GamePlayerModel.user_id == user_id,
            )
            .values(position=new_position)
        )
        await self._session.flush()

    async def set_player_online_status(
        self,
        game_id: UUID,
        user_id: UUID,
        is_online: bool,
    ) -> None:
        """
        Обновить статус онлайн игрока.

        Args:
            game_id: ID игры.
            user_id: ID игрока.
            is_online: Новый статус.
        """
        await self._session.execute(
            update(GamePlayerModel)
            .where(
                GamePlayerModel.game_id == game_id,
                GamePlayerModel.user_id == user_id,
            )
            .values(is_online=is_online)
        )
        await self._session.flush()

    # ========================================================================
    # СПЕЦИФИЧЕСКИЕ МЕТОДЫ: СОБСТВЕННОСТЬ
    # ========================================================================

    async def get_game_properties(
        self,
        game_id: UUID,
    ) -> dict[str, PropertyState]:
        """
        Получить состояния всей собственности в игре.

        Args:
            game_id: ID игры.

        Returns:
            Словарь {property_id: PropertyState}.
        """
        result = await self._session.execute(
            select(GamePropertyModel).where(
                GamePropertyModel.game_id == game_id
            )
        )
        models = result.scalars().all()

        properties: dict[str, PropertyState] = {}
        for model in models:
            properties[model.property_id] = PropertyState(
                property_id=model.property_id,
                owner_id=model.owner_id,
                houses=model.houses,
                has_hotel=model.has_hotel,
                mortgaged=model.mortgaged,
            )

        return properties

    async def save_property_state(
        self,
        game_id: UUID,
        property_state: PropertyState,
    ) -> None:
        """
        Сохранить состояние собственности.

        Args:
            game_id: ID игры.
            property_state: Состояние собственности.
        """
        result = await self._session.execute(
            select(GamePropertyModel).where(
                GamePropertyModel.game_id == game_id,
                GamePropertyModel.property_id == property_state.property_id,
            )
        )
        model = result.scalar_one_or_none()

        if model is not None:
            model.owner_id = property_state.owner_id
            model.houses = property_state.houses
            model.has_hotel = property_state.has_hotel
            model.mortgaged = property_state.mortgaged
        else:
            model = GamePropertyModel(
                game_id=game_id,
                property_id=property_state.property_id,
                owner_id=property_state.owner_id,
                houses=property_state.houses,
                has_hotel=property_state.has_hotel,
                mortgaged=property_state.mortgaged,
            )
            self._session.add(model)

        await self._session.flush()

    async def save_all_properties(
        self,
        game_id: UUID,
        properties: dict[str, PropertyState],
    ) -> None:
        """
        Сохранить состояния всей собственности.

        Args:
            game_id: ID игры.
            properties: Словарь {property_id: PropertyState}.
        """
        for prop_state in properties.values():
            await self.save_property_state(game_id, prop_state)

    # ========================================================================
    # СОХРАНЕНИЕ ПОЛНОГО СОСТОЯНИЯ
    # ========================================================================

    async def save_full_game_state(self, game: Game) -> None:
        """
        Сохранить полное состояние игры.

        Включает: игру, игроков и собственность.

        Args:
            game: Полное состояние игры.
        """
        # Сохраняем игру
        await self.save(game)

        # Сохраняем игроков
        await self.save_all_players(game.game_id, game.players)

        # Сохраняем собственность
        await self.save_all_properties(game.game_id, game.properties)

    async def load_full_game_state(self, game_id: UUID) -> Optional[Game]:
        """
        Загрузить полное состояние игры.

        Args:
            game_id: ID игры.

        Returns:
            Полное состояние игры или None.
        """
        # Загружаем игру
        game = await self.get_by_id(game_id)
        if game is None:
            return None

        # Загружаем игроков
        players = await self.get_game_players(game_id)
        game.players = {p.user_id: p for p in players}
        game.turn_order = [p.user_id for p in players]

        # Загружаем собственность
        game.properties = await self.get_game_properties(game_id)

        return game

    # ========================================================================
    # ОЧИСТКА
    # ========================================================================

    async def delete_old_games(self, older_than_days: int = 30) -> int:
        """
        Удалить игры старше N дней.

        Args:
            older_than_days: Возраст в днях.

        Returns:
            Количество удалённых игр.
        """
        from datetime import timedelta

        cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)

        result = await self._session.execute(
            delete(GameModel).where(
                GameModel.state.in_([
                    GameState.FINISHED.value,
                    GameState.CLOSED.value,
                ]),
                GameModel.finished_at < cutoff,
            )
        )
        await self._session.flush()
        return result.rowcount