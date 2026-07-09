"""
database/repositories/postgresql/user_repository.py

Репозиторий для работы с пользователями (PostgreSQL).

Реализует операции CRUD для сущности User,
используя SQLAlchemy ORM модель UserModel.

Python: 3.13+
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import UserModel
from database.repositories.base_repository import BaseRepository
from shared.models.user import User, PlayerProfile


# ============================================================================
# РЕПОЗИТОРИЙ ПОЛЬЗОВАТЕЛЕЙ
# ============================================================================

class UserRepository(BaseRepository[UserModel, User]):
    """
    Репозиторий для работы с пользователями.

    Предоставляет методы для управления учётными записями:
    поиск, создание, обновление, блокировка, статистика.

    Usage:
        repo = UserRepository(session)
        user = await repo.get_by_username("player1")
        await repo.update_last_login(user.user_id)
    """

    def __init__(self, session: AsyncSession) -> None:
        """Инициализация репозитория."""
        super().__init__(session, UserModel)

    # ========================================================================
    # ПРЕОБРАЗОВАНИЯ (абстрактные методы)
    # ========================================================================

    def _to_entity(self, model: UserModel) -> User:
        """Преобразовать ORM-модель в бизнес-сущность User."""
        return User(
            user_id=model.user_id,
            username=model.username,
            password_hash=model.password_hash,
            role=model.role,  # type: ignore[arg-type]
            created_at=model.created_at,
            last_login=model.last_login,
            is_banned=model.is_banned,
            is_online=False,  # Онлайн-статус управляется SessionManager
        )

    def _to_model(self, entity: User) -> UserModel:
        """Преобразовать бизнес-сущность User в ORM-модель."""
        return UserModel(
            user_id=entity.user_id,
            username=entity.username,
            password_hash=entity.password_hash,
            role=entity.role.value,
            created_at=entity.created_at,
            last_login=entity.last_login,
            is_banned=entity.is_banned,
        )

    def _update_model(self, model: UserModel, entity: User) -> UserModel:
        """Обновить существующую ORM-модель данными из User."""
        model.username = entity.username
        model.password_hash = entity.password_hash
        model.role = entity.role.value
        model.last_login = entity.last_login
        model.is_banned = entity.is_banned
        return model

    def _get_model_id(self, model: UserModel) -> UUID:
        """Получить ID пользователя из модели."""
        return model.user_id

    # ========================================================================
    # СПЕЦИФИЧЕСКИЕ МЕТОДЫ
    # ========================================================================

    async def get_by_username(self, username: str) -> Optional[User]:
        """
        Найти пользователя по имени.

        Args:
            username: Имя пользователя.

        Returns:
            Пользователь или None.
        """
        result = await self._session.execute(
            select(UserModel).where(UserModel.username == username)
        )
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return self._to_entity(model)

    async def username_exists(self, username: str) -> bool:
        """
        Проверить, занято ли имя пользователя.

        Args:
            username: Проверяемое имя.

        Returns:
            True, если имя уже используется.
        """
        return await self.get_by_username(username) is not None

    async def update_last_login(self, user_id: UUID) -> None:
        """
        Обновить время последнего входа.

        Args:
            user_id: ID пользователя.
        """
        user = await self.get_by_id(user_id)
        if user is not None:
            user.last_login = datetime.now(timezone.utc)
            await self.save(user)

    async def update_password(self, user_id: UUID, new_password_hash: str) -> bool:
        """
        Обновить пароль пользователя.

        Args:
            user_id: ID пользователя.
            new_password_hash: Новый хеш пароля (Argon2id).

        Returns:
            True, если обновление выполнено.
        """
        user = await self.get_by_id(user_id)
        if user is None:
            return False
        user.password_hash = new_password_hash
        await self.save(user)
        return True

    async def ban_user(self, user_id: UUID) -> bool:
        """
        Заблокировать пользователя.

        Args:
            user_id: ID пользователя.

        Returns:
            True, если блокировка выполнена.
        """
        user = await self.get_by_id(user_id)
        if user is None:
            return False
        user.ban()
        await self.save(user)
        return True

    async def unban_user(self, user_id: UUID) -> bool:
        """
        Разблокировать пользователя.

        Args:
            user_id: ID пользователя.

        Returns:
            True, если разблокировка выполнена.
        """
        user = await self.get_by_id(user_id)
        if user is None:
            return False
        user.unban()
        await self.save(user)
        return True

    async def change_role(self, user_id: UUID, new_role: str) -> bool:
        """
        Изменить роль пользователя.

        Args:
            user_id: ID пользователя.
            new_role: Новая роль (creator, player, observer).

        Returns:
            True, если роль изменена.
        """
        from shared.enums import UserRole

        user = await self.get_by_id(user_id)
        if user is None:
            return False
        user.change_role(UserRole(new_role))
        await self.save(user)
        return True

    async def get_by_role(
        self,
        role: str,
        offset: int = 0,
        limit: int = 100,
    ) -> list[User]:
        """
        Получить пользователей с определённой ролью.

        Args:
            role: Роль (creator, player, observer).
            offset: Смещение.
            limit: Лимит.

        Returns:
            Список пользователей.
        """
        return await self.get_all(
            offset=offset,
            limit=limit,
            filters={"role": role},
        )

    async def get_banned_users(
        self,
        offset: int = 0,
        limit: int = 100,
    ) -> list[User]:
        """
        Получить заблокированных пользователей.

        Args:
            offset: Смещение.
            limit: Лимит.

        Returns:
            Список заблокированных пользователей.
        """
        return await self.get_all(
            offset=offset,
            limit=limit,
            filters={"is_banned": True},
        )

    async def search_users(
        self,
        query: str,
        limit: int = 20,
    ) -> list[User]:
        """
        Поиск пользователей по имени (частичное совпадение).

        Args:
            query: Поисковый запрос.
            limit: Максимальное количество результатов.

        Returns:
            Список найденных пользователей.
        """
        result = await self._session.execute(
            select(UserModel)
            .where(UserModel.username.ilike(f"%{query}%"))
            .limit(limit)
        )
        models = result.scalars().all()
        return [self._to_entity(model) for model in models]

    # ========================================================================
    # СТАТИСТИКА
    # ========================================================================

    async def get_player_profile(self, user_id: UUID) -> Optional[PlayerProfile]:
        """
        Получить статистический профиль игрока.

        Args:
            user_id: ID пользователя.

        Returns:
            Профиль игрока или None.
        """
        result = await self._session.execute(
            select(UserModel).where(UserModel.user_id == user_id)
        )
        model = result.scalar_one_or_none()
        if model is None:
            return None

        return PlayerProfile(
            user_id=model.user_id,
            total_games=model.total_games,
            wins=model.wins,
            losses=model.total_games - model.wins,
            total_money_earned=model.total_money_earned,
        )

    async def update_game_stats(
        self,
        user_id: UUID,
        final_money: int,
        is_winner: bool,
    ) -> None:
        """
        Обновить статистику после завершения игры.

        Args:
            user_id: ID пользователя.
            final_money: Финальная сумма денег.
            is_winner: Победил ли игрок.
        """
        result = await self._session.execute(
            select(UserModel).where(UserModel.user_id == user_id)
        )
        model = result.scalar_one_or_none()
        if model is None:
            return

        model.total_games += 1
        if is_winner:
            model.wins += 1
        model.total_money_earned += final_money

        await self._session.flush()

    async def get_top_players(
        self,
        limit: int = 10,
        sort_by: str = "total_money_earned",
    ) -> list[dict]:
        """
        Получить топ игроков по указанному критерию.

        Args:
            limit: Количество игроков в топе.
            sort_by: Критерий сортировки:
                - total_money_earned — по общему заработку
                - wins — по победам
                - total_games — по количеству игр

        Returns:
            Список словарей с информацией об игроках.
        """
        column = getattr(UserModel, sort_by, UserModel.total_money_earned)

        result = await self._session.execute(
            select(UserModel)
            .order_by(column.desc())
            .limit(limit)
        )
        models = result.scalars().all()

        return [
            {
                "user_id": str(m.user_id),
                "username": m.username,
                "total_games": m.total_games,
                "wins": m.wins,
                "total_money_earned": m.total_money_earned,
            }
            for m in models
        ]