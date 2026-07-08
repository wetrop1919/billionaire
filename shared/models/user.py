"""
shared/models/user.py

Модель пользователя для проекта "Миллиардер".

Содержит:
- User — основная модель пользователя системы
- PlayerProfile — статистика игрока (игры, победы, заработок)

Все идентификаторы используют UUID для обеспечения уникальности
в распределённой многопользовательской среде.

Python: 3.13+
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Self
from uuid import UUID, uuid4

from shared.enums import UserRole


# ============================================================================
# МОДЕЛЬ ПОЛЬЗОВАТЕЛЯ
# ============================================================================

@dataclass(slots=True)
class User:
    """
    Пользователь системы.

    Представляет зарегистрированного пользователя с учётными данными,
    ролью и статусом. Используется для аутентификации, авторизации
    и отслеживания активности.

    Attributes:
        user_id: Уникальный идентификатор (UUID).
        username: Имя пользователя (уникальное, 3-32 символа).
        password_hash: Хеш пароля (Argon2id).
        role: Роль пользователя в системе.
        created_at: Дата и время регистрации (UTC).
        last_login: Дата и время последнего входа (UTC).
        is_banned: Флаг блокировки пользователя.
        is_online: Флаг текущего присутствия на сервере.
    """

    user_id: UUID
    username: str
    password_hash: str
    role: UserRole = UserRole.PLAYER
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_login: datetime | None = None
    is_banned: bool = False
    is_online: bool = False

    @classmethod
    def create(
        cls,
        username: str,
        password_hash: str,
        role: UserRole = UserRole.PLAYER,
    ) -> User:
        """
        Создать нового пользователя с автоматической генерацией ID и временных меток.

        Args:
            username: Имя пользователя.
            password_hash: Хеш пароля (Argon2id).
            role: Роль пользователя (по умолчанию PLAYER).

        Returns:
            Новый экземпляр User.
        """
        now = datetime.now(timezone.utc)
        return cls(
            user_id=uuid4(),
            username=username,
            password_hash=password_hash,
            role=role,
            created_at=now,
            last_login=now,
            is_banned=False,
            is_online=True,
        )

    def update_last_login(self) -> None:
        """Обновить время последнего входа текущим временем UTC."""
        self.last_login = datetime.now(timezone.utc)
        self.is_online = True

    def set_offline(self) -> None:
        """Отметить пользователя как офлайн."""
        self.is_online = False

    def ban(self) -> None:
        """Заблокировать пользователя."""
        self.is_banned = True
        self.is_online = False

    def unban(self) -> None:
        """Разблокировать пользователя."""
        self.is_banned = False

    def change_role(self, new_role: UserRole) -> None:
        """
        Изменить роль пользователя.

        Args:
            new_role: Новая роль.
        """
        self.role = new_role

    @property
    def is_creator(self) -> bool:
        """Является ли пользователь создателем/администратором."""
        return self.role == UserRole.CREATOR

    @property
    def is_player(self) -> bool:
        """Является ли пользователь обычным игроком."""
        return self.role == UserRole.PLAYER

    @property
    def is_observer(self) -> bool:
        """Является ли пользователь наблюдателем."""
        return self.role == UserRole.OBSERVER

    @property
    def can_play(self) -> bool:
        """Может ли пользователь участвовать в игре."""
        return not self.is_banned and self.role != UserRole.OBSERVER

    @property
    def display_name(self) -> str:
        """
        Отображаемое имя пользователя.

        Returns:
            Имя пользователя с префиксом роли для Creator.
        """
        if self.is_creator:
            return f"[👑] {self.username}"
        return self.username

    def to_dict(self) -> dict:
        """
        Сериализация пользователя в словарь.

        Returns:
            Словарь с основными полями пользователя.
        """
        return {
            "user_id": str(self.user_id),
            "username": self.username,
            "role": self.role.value,
            "created_at": self.created_at.isoformat(),
            "last_login": self.last_login.isoformat() if self.last_login else None,
            "is_banned": self.is_banned,
            "is_online": self.is_online,
        }

    def to_safe_dict(self) -> dict:
        """
        Сериализация без чувствительных данных (для отправки другим игрокам).

        Returns:
            Словарь без password_hash.
        """
        return {
            "user_id": str(self.user_id),
            "username": self.username,
            "role": self.role.value,
            "is_online": self.is_online,
        }

    @classmethod
    def from_dict(cls, data: dict) -> User:
        """
        Создать пользователя из словаря.

        Args:
            data: Словарь с данными пользователя.

        Returns:
            Новый экземпляр User.
        """
        return cls(
            user_id=UUID(data["user_id"]),
            username=data["username"],
            password_hash=data.get("password_hash", ""),
            role=UserRole(data.get("role", "player")),
            created_at=datetime.fromisoformat(data["created_at"])
                if data.get("created_at")
                else datetime.now(timezone.utc),
            last_login=datetime.fromisoformat(data["last_login"])
                if data.get("last_login")
                else None,
            is_banned=data.get("is_banned", False),
            is_online=data.get("is_online", False),
        )

    def __repr__(self) -> str:
        return (
            f"User(id={self.user_id}, username='{self.username}', "
            f"role={self.role.value}, online={self.is_online})"
        )


# ============================================================================
# ПРОФИЛЬ ИГРОКА (СТАТИСТИКА)
# ============================================================================

@dataclass(slots=True)
class PlayerProfile:
    """
    Статистический профиль игрока.

    Хранит агрегированную статистику по всем сыгранным играм.
    Не содержит чувствительных данных, может быть доступен всем.

    Attributes:
        user_id: ID пользователя.
        total_games: Общее количество игр.
        wins: Количество побед (1-е место).
        losses: Количество поражений (не 1-е место).
        total_money_earned: Общая сумма заработанных денег за все игры.
        highest_money: Максимальная сумма денег за одну игру.
        bankruptcies: Количество банкротств.
        properties_bought: Всего куплено собственности.
        houses_built: Всего построено домов.
        hotels_built: Всего построено отелей.
        total_play_time_minutes: Общее время в игре (минут).
    """

    user_id: UUID
    total_games: int = 0
    wins: int = 0
    losses: int = 0
    total_money_earned: int = 0
    highest_money: int = 0
    bankruptcies: int = 0
    properties_bought: int = 0
    houses_built: int = 0
    hotels_built: int = 0
    total_play_time_minutes: int = 0

    @classmethod
    def create_default(cls, user_id: UUID) -> PlayerProfile:
        """
        Создать пустой профиль для нового игрока.

        Args:
            user_id: ID пользователя.

        Returns:
            Новый профиль с нулевой статистикой.
        """
        return cls(user_id=user_id)

    @property
    def win_rate(self) -> float:
        """
        Процент побед.

        Returns:
            Процент побед (0.0 - 100.0), 0.0 если игр не было.
        """
        if self.total_games == 0:
            return 0.0
        return (self.wins / self.total_games) * 100.0

    @property
    def average_money_per_game(self) -> int:
        """
        Средний заработок за игру.

        Returns:
            Средняя сумма денег за игру, 0 если игр не было.
        """
        if self.total_games == 0:
            return 0
        return self.total_money_earned // self.total_games

    def record_game_result(
        self,
        final_money: int,
        rank: int,
        play_time_minutes: int,
        properties_count: int,
        houses_count: int,
        hotels_count: int,
        is_bankrupt: bool,
    ) -> None:
        """
        Записать результат завершённой игры.

        Args:
            final_money: Финальная сумма денег.
            rank: Занятое место (1 — победа).
            play_time_minutes: Длительность игры в минутах.
            properties_count: Количество купленной собственности.
            houses_count: Количество построенных домов.
            hotels_count: Количество построенных отелей.
            is_bankrupt: Стал ли игрок банкротом.
        """
        self.total_games += 1

        if rank == 1:
            self.wins += 1
        else:
            self.losses += 1

        self.total_money_earned += final_money
        self.highest_money = max(self.highest_money, final_money)
        self.total_play_time_minutes += play_time_minutes
        self.properties_bought += properties_count
        self.houses_built += houses_count
        self.hotels_built += hotels_count

        if is_bankrupt:
            self.bankruptcies += 1

    def to_dict(self) -> dict:
        """
        Сериализация профиля в словарь.

        Returns:
            Словарь с полной статистикой игрока.
        """
        return {
            "user_id": str(self.user_id),
            "total_games": self.total_games,
            "wins": self.wins,
            "losses": self.losses,
            "win_rate": round(self.win_rate, 1),
            "total_money_earned": self.total_money_earned,
            "highest_money": self.highest_money,
            "average_money_per_game": self.average_money_per_game,
            "bankruptcies": self.bankruptcies,
            "properties_bought": self.properties_bought,
            "houses_built": self.houses_built,
            "hotels_built": self.hotels_built,
            "total_play_time_minutes": self.total_play_time_minutes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> PlayerProfile:
        """
        Создать профиль из словаря.

        Args:
            data: Словарь с данными профиля.

        Returns:
            Новый экземпляр PlayerProfile.
        """
        return cls(
            user_id=UUID(data["user_id"]),
            total_games=data.get("total_games", 0),
            wins=data.get("wins", 0),
            losses=data.get("losses", 0),
            total_money_earned=data.get("total_money_earned", 0),
            highest_money=data.get("highest_money", 0),
            bankruptcies=data.get("bankruptcies", 0),
            properties_bought=data.get("properties_bought", 0),
            houses_built=data.get("houses_built", 0),
            hotels_built=data.get("hotels_built", 0),
            total_play_time_minutes=data.get("total_play_time_minutes", 0),
        )

    def __repr__(self) -> str:
        return (
            f"PlayerProfile(user={self.user_id}, games={self.total_games}, "
            f"wins={self.wins}, win_rate={self.win_rate:.1f}%)"
        )