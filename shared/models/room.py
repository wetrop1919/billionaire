"""
shared/models/room.py

Модели комнат для проекта "Миллиардер".

Содержит:
- Room — комната для сбора игроков перед началом игры
- RoomConfig — конфигурация комнаты (настройки правил)
- RoomListItem — краткая информация о комнате для списка

Комнаты позволяют игрокам собираться вместе, настраивать
параметры игры и общаться до её начала.

Python: 3.13+
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Self
from uuid import UUID, uuid4

from shared.enums import RoomState, UserRole
from shared.game_rules import GameRules


# ============================================================================
# КОНФИГУРАЦИЯ КОМНАТЫ (RoomConfig)
# ============================================================================

@dataclass(slots=True)
class RoomConfig:
    """
    Конфигурация комнаты, задаваемая владельцем.

    Определяет параметры игры, которые будут использованы
    при создании игровой сессии.

    Attributes:
        max_players: Максимальное количество игроков (2-8).
        turn_timeout: Таймаут хода в секундах (15-300).
        start_money: Стартовый капитал.
        start_bonus: Бонус за прохождение Старта.
        is_private: Приватная ли комната.
        password_hash: Хеш пароля (если приватная).
        allow_spectators: Разрешены ли наблюдатели.
        game_rules: Настраиваемые правила игры.
    """

    max_players: int = 4
    turn_timeout: int = 60
    start_money: int = 1500
    start_bonus: int = 200
    is_private: bool = False
    password_hash: Optional[str] = None
    allow_spectators: bool = True
    game_rules: GameRules = field(default_factory=GameRules.defaults)

    def __post_init__(self) -> None:
        """Валидация конфигурации."""
        if not (2 <= self.max_players <= 8):
            raise ValueError(f"max_players должен быть 2-8: {self.max_players}")
        if not (15 <= self.turn_timeout <= 300):
            raise ValueError(f"turn_timeout должен быть 15-300: {self.turn_timeout}")
        if self.start_money < 0:
            raise ValueError(f"start_money не может быть отрицательным: {self.start_money}")
        if self.start_bonus < 0:
            raise ValueError(f"start_bonus не может быть отрицательным: {self.start_bonus}")

    @property
    def has_password(self) -> bool:
        """Защищена ли комната паролем."""
        return self.is_private and self.password_hash is not None

    def to_dict(self) -> dict:
        """Сериализация конфигурации в словарь."""
        return {
            "max_players": self.max_players,
            "turn_timeout": self.turn_timeout,
            "start_money": self.start_money,
            "start_bonus": self.start_bonus,
            "is_private": self.is_private,
            "allow_spectators": self.allow_spectators,
            "game_rules": self.game_rules.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> RoomConfig:
        """Создать конфигурацию из словаря."""
        game_rules = GameRules.defaults()
        if "game_rules" in data:
            game_rules = GameRules.from_dict(data["game_rules"])

        return cls(
            max_players=data.get("max_players", 4),
            turn_timeout=data.get("turn_timeout", 60),
            start_money=data.get("start_money", 1500),
            start_bonus=data.get("start_bonus", 200),
            is_private=data.get("is_private", False),
            password_hash=data.get("password_hash"),
            allow_spectators=data.get("allow_spectators", True),
            game_rules=game_rules,
        )


# ============================================================================
# МОДЕЛЬ КОМНАТЫ (Room)
# ============================================================================

@dataclass(slots=True)
class Room:
    """
    Игровая комната.

    Комната — это место сбора игроков перед началом игры.
    Владелец комнаты может настраивать параметры, приглашать
    игроков и запускать игру.

    Attributes:
        room_id: Уникальный идентификатор комнаты.
        name: Название комнаты.
        owner_id: ID владельца комнаты.
        config: Конфигурация комнаты.
        state: Состояние комнаты (WAITING, IN_GAME, FINISHED).
        players: Список ID игроков в комнате.
        observers: Список ID наблюдателей.
        created_at: Время создания.
        game_id: ID запущенной игры (если state == IN_GAME).
    """

    room_id: UUID
    name: str
    owner_id: UUID
    config: RoomConfig = field(default_factory=RoomConfig)
    state: RoomState = RoomState.WAITING
    players: list[UUID] = field(default_factory=list)
    observers: list[UUID] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    game_id: Optional[UUID] = None

    def __post_init__(self) -> None:
        """Валидация комнаты."""
        if len(self.name) < 1 or len(self.name) > 32:
            raise ValueError(f"Название комнаты должно быть 1-32 символа: '{self.name}'")

    # === СВОЙСТВА ===

    @property
    def players_count(self) -> int:
        """Текущее количество игроков."""
        return len(self.players)

    @property
    def observers_count(self) -> int:
        """Текущее количество наблюдателей."""
        return len(self.observers)

    @property
    def total_occupants(self) -> int:
        """Общее количество людей в комнате."""
        return self.players_count + self.observers_count

    @property
    def is_full(self) -> bool:
        """Заполнена ли комната."""
        return self.players_count >= self.config.max_players

    @property
    def is_empty(self) -> bool:
        """Пуста ли комната."""
        return self.players_count == 0

    @property
    def can_start_game(self) -> bool:
        """Можно ли начать игру (минимум 2 игрока)."""
        return self.players_count >= 2 and self.state == RoomState.WAITING

    @property
    def is_waiting(self) -> bool:
        """Находится ли комната в ожидании."""
        return self.state == RoomState.WAITING

    @property
    def is_in_game(self) -> bool:
        """Идёт ли игра в комнате."""
        return self.state == RoomState.IN_GAME

    @property
    def is_finished(self) -> bool:
        """Завершена ли игра."""
        return self.state == RoomState.FINISHED

    # === УПРАВЛЕНИЕ ИГРОКАМИ ===

    def add_player(self, player_id: UUID) -> None:
        """
        Добавить игрока в комнату.

        Args:
            player_id: ID добавляемого игрока.

        Raises:
            ValueError: Если комната заполнена или игрок уже в комнате.
        """
        if self.is_full:
            raise ValueError(f"Комната '{self.name}' заполнена ({self.config.max_players} макс.)")
        if player_id in self.players:
            raise ValueError(f"Игрок {player_id} уже в комнате")
        if self.state != RoomState.WAITING:
            raise ValueError(f"Нельзя войти: комната в состоянии {self.state.value}")
        self.players.append(player_id)

    def remove_player(self, player_id: UUID) -> None:
        """
        Удалить игрока из комнаты.

        Args:
            player_id: ID удаляемого игрока.

        Raises:
            ValueError: Если игрок не в комнате.
        """
        if player_id not in self.players:
            raise ValueError(f"Игрок {player_id} не в комнате")
        self.players.remove(player_id)

    def add_observer(self, observer_id: UUID) -> None:
        """
        Добавить наблюдателя.

        Args:
            observer_id: ID наблюдателя.

        Raises:
            ValueError: Если наблюдатели запрещены или уже в комнате.
        """
        if not self.config.allow_spectators:
            raise ValueError("Наблюдатели запрещены в этой комнате")
        if observer_id in self.observers:
            raise ValueError(f"Наблюдатель {observer_id} уже в комнате")
        if observer_id in self.players:
            raise ValueError(f"Игрок {observer_id} не может быть наблюдателем")
        self.observers.append(observer_id)

    def remove_observer(self, observer_id: UUID) -> None:
        """
        Удалить наблюдателя.

        Args:
            observer_id: ID наблюдателя.
        """
        if observer_id in self.observers:
            self.observers.remove(observer_id)

    def is_player_in_room(self, player_id: UUID) -> bool:
        """Проверить, находится ли игрок в комнате."""
        return player_id in self.players

    def is_observer_in_room(self, observer_id: UUID) -> bool:
        """Проверить, находится ли наблюдатель в комнате."""
        return observer_id in self.observers

    def is_occupant(self, user_id: UUID) -> bool:
        """Проверить, находится ли пользователь в комнате (игрок или наблюдатель)."""
        return self.is_player_in_room(user_id) or self.is_observer_in_room(user_id)

    # === УПРАВЛЕНИЕ ВЛАДЕЛЬЦЕМ ===

    def is_owner(self, user_id: UUID) -> bool:
        """Является ли пользователь владельцем комнаты."""
        return user_id == self.owner_id

    def transfer_ownership(self, new_owner_id: UUID) -> None:
        """
        Передать права владельца другому игроку.

        Args:
            new_owner_id: ID нового владельца.

        Raises:
            ValueError: Если новый владелец не в комнате.
        """
        if new_owner_id not in self.players:
            raise ValueError(f"Новый владелец должен быть игроком комнаты")
        self.owner_id = new_owner_id

    # === УПРАВЛЕНИЕ СОСТОЯНИЕМ ===

    def start_game(self, game_id: UUID) -> None:
        """
        Отметить комнату как "в игре".

        Args:
            game_id: ID созданной игры.

        Raises:
            ValueError: Если комната не в состоянии WAITING.
        """
        if self.state != RoomState.WAITING:
            raise ValueError(f"Нельзя начать игру: комната в состоянии {self.state.value}")
        self.state = RoomState.IN_GAME
        self.game_id = game_id

    def finish_game(self) -> None:
        """Отметить игру как завершённую."""
        self.state = RoomState.FINISHED
        self.game_id = None

    def reset_to_waiting(self) -> None:
        """Сбросить комнату в состояние ожидания (для новой игры)."""
        self.state = RoomState.WAITING
        self.game_id = None

    def update_config(self, new_config: RoomConfig) -> None:
        """
        Обновить конфигурацию комнаты.

        Args:
            new_config: Новая конфигурация.

        Raises:
            ValueError: Если игра уже идёт.
        """
        if self.is_in_game:
            raise ValueError("Нельзя менять настройки во время игры")
        self.config = new_config

    # === СЕРИАЛИЗАЦИЯ ===

    def to_dict(self) -> dict:
        """Сериализация комнаты в словарь."""
        return {
            "room_id": str(self.room_id),
            "name": self.name,
            "owner_id": str(self.owner_id),
            "config": self.config.to_dict(),
            "state": self.state.value,
            "players": [str(p) for p in self.players],
            "observers": [str(o) for o in self.observers],
            "players_count": self.players_count,
            "observers_count": self.observers_count,
            "is_full": self.is_full,
            "created_at": self.created_at.isoformat(),
            "game_id": str(self.game_id) if self.game_id else None,
        }

    def to_list_item(self) -> RoomListItem:
        """Создать краткий элемент списка комнат."""
        return RoomListItem(
            room_id=self.room_id,
            name=self.name,
            owner_id=self.owner_id,
            players_count=self.players_count,
            max_players=self.config.max_players,
            is_private=self.config.is_private,
            has_password=self.config.has_password,
            state=self.state,
        )

    @classmethod
    def from_dict(cls, data: dict) -> Room:
        """Создать комнату из словаря."""
        config = RoomConfig.from_dict(data.get("config", {}))
        return cls(
            room_id=UUID(data["room_id"]),
            name=data["name"],
            owner_id=UUID(data["owner_id"]),
            config=config,
            state=RoomState(data.get("state", "waiting")),
            players=[UUID(p) for p in data.get("players", [])],
            observers=[UUID(o) for o in data.get("observers", [])],
            created_at=datetime.fromisoformat(data["created_at"])
                if data.get("created_at")
                else datetime.now(timezone.utc),
            game_id=UUID(data["game_id"]) if data.get("game_id") else None,
        )

    @classmethod
    def create(
        cls,
        name: str,
        owner_id: UUID,
        config: RoomConfig | None = None,
    ) -> Room:
        """
        Создать новую комнату.

        Args:
            name: Название комнаты.
            owner_id: ID создателя.
            config: Конфигурация (опционально).

        Returns:
            Новый экземпляр Room.
        """
        room = cls(
            room_id=uuid4(),
            name=name,
            owner_id=owner_id,
            config=config or RoomConfig(),
        )
        room.add_player(owner_id)
        return room

    def __repr__(self) -> str:
        return (
            f"Room(id={self.room_id}, name='{self.name}', "
            f"players={self.players_count}/{self.config.max_players}, "
            f"state={self.state.value})"
        )


# ============================================================================
# ЭЛЕМЕНТ СПИСКА КОМНАТ (RoomListItem)
# ============================================================================

@dataclass(slots=True)
class RoomListItem:
    """
    Краткая информация о комнате для отображения в списке.

    Содержит только публичные данные, необходимые для выбора комнаты.
    Не раскрывает пароли, списки игроков и другие детали.

    Attributes:
        room_id: ID комнаты.
        name: Название.
        owner_id: ID владельца.
        players_count: Количество игроков.
        max_players: Максимум игроков.
        is_private: Приватная ли.
        has_password: Защищена ли паролем.
        state: Состояние.
    """

    room_id: UUID
    name: str
    owner_id: UUID
    players_count: int
    max_players: int
    is_private: bool
    has_password: bool
    state: RoomState

    @property
    def is_full(self) -> bool:
        """Заполнена ли комната."""
        return self.players_count >= self.max_players

    @property
    def can_join(self) -> bool:
        """Можно ли присоединиться."""
        return not self.is_full and self.state == RoomState.WAITING

    @property
    def status_text(self) -> str:
        """Текстовое описание статуса."""
        if self.state == RoomState.IN_GAME:
            return "В игре"
        elif self.state == RoomState.FINISHED:
            return "Завершена"
        elif self.is_full:
            return "Заполнена"
        return "Ожидание"

    @property
    def icon(self) -> str:
        """Иконка для отображения."""
        if self.is_private:
            return "🔒" if self.has_password else "🔐"
        return "🌍"

    def to_dict(self) -> dict:
        """Сериализация в словарь."""
        return {
            "room_id": str(self.room_id),
            "name": self.name,
            "owner_id": str(self.owner_id),
            "players_count": self.players_count,
            "max_players": self.max_players,
            "is_private": self.is_private,
            "has_password": self.has_password,
            "state": self.state.value,
            "is_full": self.is_full,
            "can_join": self.can_join,
            "status_text": self.status_text,
            "icon": self.icon,
        }

    def __repr__(self) -> str:
        return (
            f"RoomListItem('{self.name}', "
            f"{self.players_count}/{self.max_players}, "
            f"{self.status_text})"
        )