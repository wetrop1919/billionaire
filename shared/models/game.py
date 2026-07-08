"""
shared/models/game.py

Агрегационная модель игры для проекта "Миллиардер".

Содержит:
- Game — полное состояние игровой сессии
- PlayerState — состояние одного игрока в игре
- GameConfig — конфигурация игры, созданная из настроек комнаты
- GameResult — результат завершённой игры для одного игрока

Это самая сложная модель, агрегирующая все остальные:
пользователей, собственность, карточки, позиции, события.

Python: 3.13+
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Self
from uuid import UUID, uuid4

from shared.enums import GameState
from shared.game_rules import GameRules
from shared.models.card import CardDeck, PlayerCard
from shared.models.event import GameEvent
from shared.models.position import Board, BoardPosition
from shared.models.property import PropertyState, PropertyGroup
from shared.models.user import User


# ============================================================================
# СОСТОЯНИЕ ИГРОКА В ИГРЕ (PlayerState)
# ============================================================================

@dataclass(slots=True)
class PlayerState:
    """
    Состояние одного игрока в игровой сессии.

    Содержит всю информацию об игроке, его финансах,
    собственности, позиции и статусе в конкретной игре.

    Attributes:
        user_id: ID пользователя.
        username: Имя пользователя (для отображения).
        money: Текущий баланс.
        position: Позиция на игровом поле.
        properties: Список ID собственности во владении.
        cards: Карточки на руках у игрока.
        in_jail: Находится ли в тюрьме.
        jail_rounds: Сколько кругов провёл в тюрьме.
        bankrupt: Является ли банкротом.
        is_online: Подключён ли к серверу.
        is_bot: Является ли ботом.
        color: Цвет фишки (hex).
        total_earned: Всего заработано за игру.
        total_spent: Всего потрачено за игру.
        turn_actions_done: Список выполненных действий за ход.
        dice_history: История бросков кубиков за ход.
    """

    user_id: UUID
    username: str
    money: int = 1500
    position: BoardPosition = field(default_factory=BoardPosition)
    properties: list[str] = field(default_factory=list)
    cards: list[PlayerCard] = field(default_factory=list)
    in_jail: bool = False
    jail_rounds: int = 0
    bankrupt: bool = False
    is_online: bool = True
    is_bot: bool = False
    color: str = "#3498db"
    total_earned: int = 0
    total_spent: int = 0
    turn_actions_done: list[str] = field(default_factory=list)
    dice_history: list[dict] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Валидация состояния."""
        if self.money < 0:
            raise ValueError(f"Баланс не может быть отрицательным: {self.money}")

    # === СВОЙСТВА ===

    @property
    def is_owner(self) -> bool:
        """Владеет ли игрок хотя бы одной собственностью."""
        return len(self.properties) > 0

    @property
    def properties_count(self) -> int:
        """Количество собственности во владении."""
        return len(self.properties)

    @property
    def cards_count(self) -> int:
        """Количество карточек на руках."""
        return len(self.cards)

    @property
    def active_cards_count(self) -> int:
        """Количество неиспользованных карточек."""
        return sum(1 for c in self.cards if not c.is_used)

    @property
    def has_get_out_of_jail_card(self) -> bool:
        """Есть ли карточка освобождения из тюрьмы."""
        return any(
            not c.is_used and c.card_type.value in ("chance", "fund")
            for c in self.cards
        )

    @property
    def is_active(self) -> bool:
        """Активен ли игрок (не банкрот и онлайн)."""
        return not self.bankrupt and self.is_online

    @property
    def net_worth(self) -> int:
        """
        Чистая стоимость имущества (деньги + стоимость собственности).

        Returns:
            Приблизительная оценка капитала игрока.
        """
        return self.money  # Без учёта собственности (требует Property)

    # === ФИНАНСОВЫЕ ОПЕРАЦИИ ===

    def add_money(self, amount: int, reason: str = "") -> None:
        """
        Добавить деньги.

        Args:
            amount: Сумма (положительная).
            reason: Причина (для логов).

        Raises:
            ValueError: Если amount отрицательный.
        """
        if amount < 0:
            raise ValueError(f"Сумма должна быть положительной: {amount}")
        self.money += amount
        self.total_earned += amount

    def remove_money(self, amount: int, reason: str = "") -> bool:
        """
        Снять деньги.

        Args:
            amount: Сумма (положительная).
            reason: Причина.

        Returns:
            True, если операция успешна.

        Raises:
            ValueError: Если amount отрицательный.
        """
        if amount < 0:
            raise ValueError(f"Сумма должна быть положительной: {amount}")
        if self.money < amount:
            return False
        self.money -= amount
        self.total_spent += amount
        return True

    def can_afford(self, amount: int) -> bool:
        """Проверить, достаточно ли средств."""
        return self.money >= amount

    # === СОБСТВЕННОСТЬ ===

    def add_property(self, property_id: str) -> None:
        """
        Добавить собственность.

        Args:
            property_id: ID собственности.

        Raises:
            ValueError: Если уже владеет.
        """
        if property_id in self.properties:
            raise ValueError(f"Уже владеет собственностью '{property_id}'")
        self.properties.append(property_id)

    def remove_property(self, property_id: str) -> None:
        """
        Удалить собственность.

        Args:
            property_id: ID собственности.

        Raises:
            ValueError: Если не владеет.
        """
        if property_id not in self.properties:
            raise ValueError(f"Не владеет собственностью '{property_id}'")
        self.properties.remove(property_id)

    def owns_property(self, property_id: str) -> bool:
        """Проверить владение собственностью."""
        return property_id in self.properties

    # === КАРТОЧКИ ===

    def add_card(self, card: PlayerCard) -> None:
        """Добавить карточку на руку."""
        self.cards.append(card)

    def remove_card(self, instance_id: UUID) -> PlayerCard | None:
        """
        Удалить карточку с руки.

        Args:
            instance_id: ID экземпляра карточки.

        Returns:
            Удалённую карточку или None.
        """
        for i, card in enumerate(self.cards):
            if card.instance_id == instance_id:
                return self.cards.pop(i)
        return None

    # === ТЮРЬМА ===

    def send_to_jail(self, jail_cell_id: int = 10) -> None:
        """Отправить в тюрьму."""
        self.in_jail = True
        self.jail_rounds = 0
        self.position.teleport(jail_cell_id)

    def release_from_jail(self) -> None:
        """Освободить из тюрьмы."""
        self.in_jail = False
        self.jail_rounds = 0

    def increment_jail_round(self) -> None:
        """Увеличить счётчик кругов в тюрьме."""
        self.jail_rounds += 1

    # === БАНКРОТСТВО ===

    def declare_bankrupt(self) -> None:
        """Объявить банкротом."""
        self.bankrupt = True
        self.money = 0
        self.properties.clear()
        self.cards.clear()

    # === ХОД ===

    def reset_turn_actions(self) -> None:
        """Сбросить действия хода."""
        self.turn_actions_done.clear()
        self.dice_history.clear()

    def record_action(self, action: str) -> None:
        """Записать выполненное действие."""
        self.turn_actions_done.append(action)

    def has_done_action(self, action: str) -> bool:
        """Проверить, выполнено ли действие в этом ходу."""
        return action in self.turn_actions_done

    # === СЕРИАЛИЗАЦИЯ ===

    def to_dict(self) -> dict:
        """Сериализация состояния игрока."""
        return {
            "user_id": str(self.user_id),
            "username": self.username,
            "money": self.money,
            "position": self.position.to_dict(),
            "properties": self.properties,
            "cards": [c.to_dict() for c in self.cards],
            "in_jail": self.in_jail,
            "jail_rounds": self.jail_rounds,
            "bankrupt": self.bankrupt,
            "is_online": self.is_online,
            "is_bot": self.is_bot,
            "color": self.color,
            "total_earned": self.total_earned,
            "total_spent": self.total_spent,
            "properties_count": self.properties_count,
            "active_cards_count": self.active_cards_count,
        }

    def to_public_dict(self) -> dict:
        """
        Публичная информация (для других игроков).

        Скрывает деньги и карточки.
        """
        return {
            "user_id": str(self.user_id),
            "username": self.username,
            "position": self.position.to_dict(),
            "properties": self.properties,
            "in_jail": self.in_jail,
            "bankrupt": self.bankrupt,
            "is_online": self.is_online,
            "is_bot": self.is_bot,
            "color": self.color,
            "properties_count": self.properties_count,
        }

    @classmethod
    def from_dict(cls, data: dict) -> PlayerState:
        """Создать состояние из словаря."""
        position = BoardPosition.from_dict(data.get("position", {}))
        cards = [PlayerCard.from_dict(c) for c in data.get("cards", [])]

        return cls(
            user_id=UUID(data["user_id"]),
            username=data["username"],
            money=data.get("money", 1500),
            position=position,
            properties=data.get("properties", []),
            cards=cards,
            in_jail=data.get("in_jail", False),
            jail_rounds=data.get("jail_rounds", 0),
            bankrupt=data.get("bankrupt", False),
            is_online=data.get("is_online", True),
            is_bot=data.get("is_bot", False),
            color=data.get("color", "#3498db"),
            total_earned=data.get("total_earned", 0),
            total_spent=data.get("total_spent", 0),
            turn_actions_done=data.get("turn_actions_done", []),
            dice_history=data.get("dice_history", []),
        )

    @classmethod
    def create_from_user(
        cls,
        user: User,
        start_money: int = 1500,
        color: str = "#3498db",
        is_bot: bool = False,
    ) -> PlayerState:
        """
        Создать состояние игрока из модели пользователя.

        Args:
            user: Пользователь.
            start_money: Стартовый капитал.
            color: Цвет фишки.
            is_bot: Является ли ботом.

        Returns:
            Новый экземпляр PlayerState.
        """
        return cls(
            user_id=user.user_id,
            username=user.username,
            money=start_money,
            is_online=user.is_online,
            is_bot=is_bot,
            color=color,
        )

    def __repr__(self) -> str:
        status = "bankrupt" if self.bankrupt else f"{self.money}$"
        return (
            f"PlayerState({self.username}, {status}, "
            f"props={self.properties_count}, pos={self.position.cell_id})"
        )


# ============================================================================
# КОНФИГУРАЦИЯ ИГРЫ (GameConfig)
# ============================================================================

@dataclass(slots=True)
class GameConfig:
    """
    Конфигурация игровой сессии.

    Создаётся из настроек комнаты при старте игры
    и не меняется в процессе.

    Attributes:
        start_money: Стартовый капитал.
        start_bonus: Бонус за прохождение Старта.
        max_players: Максимум игроков.
        turn_timeout: Таймаут хода в секундах.
        game_rules: Правила игры.
    """

    start_money: int = 1500
    start_bonus: int = 200
    max_players: int = 4
    turn_timeout: int = 60
    game_rules: GameRules = field(default_factory=GameRules.defaults)

    def to_dict(self) -> dict:
        """Сериализация конфигурации."""
        return {
            "start_money": self.start_money,
            "start_bonus": self.start_bonus,
            "max_players": self.max_players,
            "turn_timeout": self.turn_timeout,
            "game_rules": self.game_rules.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> GameConfig:
        """Создать конфигурацию из словаря."""
        game_rules = GameRules.defaults()
        if "game_rules" in data:
            game_rules = GameRules.from_dict(data["game_rules"])

        return cls(
            start_money=data.get("start_money", 1500),
            start_bonus=data.get("start_bonus", 200),
            max_players=data.get("max_players", 4),
            turn_timeout=data.get("turn_timeout", 60),
            game_rules=game_rules,
        )


# ============================================================================
# МОДЕЛЬ ИГРЫ (Game)
# ============================================================================

@dataclass(slots=True)
class Game:
    """
    Полное состояние игровой сессии.

    Агрегирует все компоненты игры: игроков, поле, собственность,
    карточки, события. Является единым источником истины для
    игрового движка.

    Attributes:
        game_id: Уникальный идентификатор игры.
        room_id: ID комнаты, из которой создана игра.
        config: Конфигурация игры.
        state: Состояние игры.
        board: Игровое поле.
        players: Словарь состояний игроков {user_id: PlayerState}.
        turn_order: Порядок ходов (список user_id).
        current_turn_index: Индекс текущего игрока в turn_order.
        turn_number: Номер текущего хода.
        properties: Состояния всей собственности {property_id: PropertyState}.
        property_groups: Группы собственности.
        chance_deck: Колода карточек "Шанс".
        fund_deck: Колода карточек "Фонд".
        events: Журнал игровых событий.
        event_sequence: Счётчик событий.
        started_at: Время начала игры.
        finished_at: Время завершения.
        free_parking_money: Деньги на бесплатной парковке.
    """

    game_id: UUID
    room_id: UUID
    config: GameConfig = field(default_factory=GameConfig)
    state: GameState = GameState.WAITING_FOR_PLAYERS
    board: Board = field(default_factory=Board)
    players: dict[UUID, PlayerState] = field(default_factory=dict)
    turn_order: list[UUID] = field(default_factory=list)
    current_turn_index: int = 0
    turn_number: int = 0
    properties: dict[str, PropertyState] = field(default_factory=dict)
    property_groups: list[PropertyGroup] = field(default_factory=list)
    chance_deck: Optional[CardDeck] = None
    fund_deck: Optional[CardDeck] = None
    events: list[GameEvent] = field(default_factory=list)
    event_sequence: int = 0
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    free_parking_money: int = 0

    # === СВОЙСТВА ===

    @property
    def players_count(self) -> int:
        """Количество игроков."""
        return len(self.players)

    @property
    def active_players_count(self) -> int:
        """Количество активных (не банкротов) игроков."""
        return sum(1 for p in self.players.values() if not p.bankrupt)

    @property
    def bankrupt_players_count(self) -> int:
        """Количество обанкротившихся игроков."""
        return sum(1 for p in self.players.values() if p.bankrupt)

    @property
    def online_players_count(self) -> int:
        """Количество онлайн-игроков."""
        return sum(1 for p in self.players.values() if p.is_online)

    @property
    def current_player(self) -> PlayerState | None:
        """Текущий игрок, чей сейчас ход."""
        if not self.turn_order or self.current_turn_index >= len(self.turn_order):
            return None
        player_id = self.turn_order[self.current_turn_index]
        return self.players.get(player_id)

    @property
    def current_player_id(self) -> UUID | None:
        """ID текущего игрока."""
        player = self.current_player
        return player.user_id if player else None

    @property
    def is_active(self) -> bool:
        """Активна ли игра."""
        return self.state == GameState.ACTIVE

    @property
    def is_finished(self) -> bool:
        """Завершена ли игра."""
        return self.state in (GameState.FINISHED, GameState.CLOSED)

    @property
    def duration_seconds(self) -> float | None:
        """
        Длительность игры в секундах.

        Returns:
            Количество секунд от начала до завершения (или до текущего момента).
        """
        if self.started_at is None:
            return None
        end = self.finished_at or datetime.now(timezone.utc)
        return (end - self.started_at).total_seconds()

    # === УПРАВЛЕНИЕ ИГРОКАМИ ===

    def add_player(self, player: PlayerState) -> None:
        """
        Добавить игрока в игру.

        Args:
            player: Состояние игрока.

        Raises:
            ValueError: Если игра уже активна или игрок уже в игре.
        """
        if self.is_active:
            raise ValueError("Нельзя добавить игрока во время игры")
        if player.user_id in self.players:
            raise ValueError(f"Игрок {player.user_id} уже в игре")
        self.players[player.user_id] = player
        self.turn_order.append(player.user_id)

    def remove_player(self, player_id: UUID) -> None:
        """
        Удалить игрока из игры.

        Args:
            player_id: ID игрока.
        """
        if player_id in self.players:
            del self.players[player_id]
        if player_id in self.turn_order:
            self.turn_order.remove(player_id)

    def get_player(self, player_id: UUID) -> PlayerState | None:
        """Получить состояние игрока."""
        return self.players.get(player_id)

    # === УПРАВЛЕНИЕ ХОДАМИ ===

    def next_turn(self) -> PlayerState | None:
        """
        Перейти к следующему ходу.

        Пропускает обанкротившихся игроков.
        Возвращает следующего активного игрока.

        Returns:
            Следующий игрок или None, если игра завершена.
        """
        if not self.turn_order:
            return None

        self.turn_number += 1

        # Ищем следующего активного игрока
        for _ in range(len(self.turn_order)):
            self.current_turn_index = (self.current_turn_index + 1) % len(self.turn_order)
            player = self.current_player
            if player and not player.bankrupt:
                return player

        return None

    def set_first_player(self, index: int = 0) -> None:
        """Установить первого игрока."""
        if 0 <= index < len(self.turn_order):
            self.current_turn_index = index

    # === УПРАВЛЕНИЕ СОБСТВЕННОСТЬЮ ===

    def get_property_state(self, property_id: str) -> PropertyState | None:
        """Получить состояние собственности."""
        return self.properties.get(property_id)

    def get_player_properties(self, player_id: UUID) -> list[PropertyState]:
        """Получить всю собственность игрока."""
        return [
            ps for ps in self.properties.values()
            if ps.owner_id == player_id
        ]

    def get_ungrouped_properties(self) -> list[str]:
        """Получить список ID собственности без владельца."""
        return [
            pid for pid, ps in self.properties.items()
            if not ps.is_owned
        ]

    # === УПРАВЛЕНИЕ КАРТОЧКАМИ ===

    def draw_chance_card(self) -> Optional[dict]:
        """Взять карточку Шанс."""
        if self.chance_deck is None:
            return None
        card = self.chance_deck.draw()
        return card.to_dict() if card else None

    def draw_fund_card(self) -> Optional[dict]:
        """Взять карточку Фонд."""
        if self.fund_deck is None:
            return None
        card = self.fund_deck.draw()
        return card.to_dict() if card else None

    # === УПРАВЛЕНИЕ СОБЫТИЯМИ ===

    def add_event(self, event: GameEvent) -> None:
        """
        Добавить событие в журнал.

        Args:
            event: Игровое событие.
        """
        event.sequence = self.event_sequence
        self.event_sequence += 1
        self.events.append(event)

    def get_events_since(self, sequence: int) -> list[GameEvent]:
        """
        Получить события начиная с указанного порядкового номера.

        Args:
            sequence: Порядковый номер, с которого начинать.

        Returns:
            Список новых событий.
        """
        return [e for e in self.events if e.sequence >= sequence]

    # === УПРАВЛЕНИЕ СОСТОЯНИЕМ ===

    def start(self) -> None:
        """Начать игру."""
        self.state = GameState.STARTING
        self.started_at = datetime.now(timezone.utc)

    def activate(self) -> None:
        """Активировать игру (после инициализации)."""
        self.state = GameState.ACTIVE

    def pause(self) -> None:
        """Поставить на паузу."""
        if self.state == GameState.ACTIVE:
            self.state = GameState.PAUSED

    def resume(self) -> None:
        """Возобновить."""
        if self.state == GameState.PAUSED:
            self.state = GameState.ACTIVE

    def finish(self) -> None:
        """Завершить игру."""
        self.state = GameState.FINISHING
        self.finished_at = datetime.now(timezone.utc)

    def close(self) -> None:
        """Закрыть игру (окончательно)."""
        self.state = GameState.CLOSED

    # === ПОДСЧЁТ РЕЗУЛЬТАТОВ ===

    def calculate_results(self) -> list[GameResult]:
        """
        Подсчитать результаты игры.

        Сортирует игроков по количеству денег (по убыванию).
        При равенстве — сравнивает количество собственности.

        Returns:
            Список GameResult, отсортированный по месту.
        """
        results: list[GameResult] = []

        for player in self.players.values():
            # Вычисляем стоимость собственности
            properties_value = 0
            for prop_id in player.properties:
                prop_state = self.properties.get(prop_id)
                if prop_state:
                    # Приблизительная оценка
                    properties_value += 100  # Упрощение

            total_wealth = player.money + properties_value

            results.append(GameResult(
                player_id=player.user_id,
                username=player.username,
                final_money=player.money,
                properties_value=properties_value,
                total_wealth=total_wealth,
                is_bankrupt=player.bankrupt,
            ))

        # Сортировка: больше денег = выше место
        results.sort(key=lambda r: r.total_wealth, reverse=True)

        # Присваиваем места
        for i, result in enumerate(results):
            result.rank = i + 1

        return results

    # === СЕРИАЛИЗАЦИЯ ===

    def to_dict(self) -> dict:
        """Сериализация полного состояния игры."""
        return {
            "game_id": str(self.game_id),
            "room_id": str(self.room_id),
            "config": self.config.to_dict(),
            "state": self.state.value,
            "board": self.board.to_dict(),
            "players": {
                str(uid): ps.to_dict() for uid, ps in self.players.items()
            },
            "turn_order": [str(uid) for uid in self.turn_order],
            "current_turn_index": self.current_turn_index,
            "turn_number": self.turn_number,
            "properties": {
                pid: ps.to_dict() for pid, ps in self.properties.items()
            },
            "property_groups": [pg.to_dict() for pg in self.property_groups],
            "chance_deck": self.chance_deck.to_dict() if self.chance_deck else None,
            "fund_deck": self.fund_deck.to_dict() if self.fund_deck else None,
            "events_count": len(self.events),
            "event_sequence": self.event_sequence,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "free_parking_money": self.free_parking_money,
            "players_count": self.players_count,
            "active_players_count": self.active_players_count,
            "duration_seconds": self.duration_seconds,
        }

    def to_sync_dict(self, player_id: UUID) -> dict:
        """
        Создать словарь для синхронизации с конкретным игроком.

        Включает публичную информацию о других игроках
        и полную информацию о запрашивающем игроке.

        Args:
            player_id: ID игрока, запрашивающего синхронизацию.

        Returns:
            Словарь с данными для отправки клиенту.
        """
        players_data = {}
        for uid, ps in self.players.items():
            if uid == player_id:
                players_data[str(uid)] = ps.to_dict()
            else:
                players_data[str(uid)] = ps.to_public_dict()

        return {
            "game_id": str(self.game_id),
            "state": self.state.value,
            "board": self.board.to_dict(),
            "players": players_data,
            "turn_order": [str(uid) for uid in self.turn_order],
            "current_turn_index": self.current_turn_index,
            "turn_number": self.turn_number,
            "properties": {
                pid: ps.to_dict() for pid, ps in self.properties.items()
            },
            "current_player_id": str(self.current_player_id) if self.current_player_id else None,
            "free_parking_money": self.free_parking_money,
            "started_at": self.started_at.isoformat() if self.started_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Game:
        """Создать игру из словаря."""
        config = GameConfig.from_dict(data.get("config", {}))
        board = Board.from_dict(data.get("board", {"cells": []}))

        players = {}
        for uid_str, ps_data in data.get("players", {}).items():
            players[UUID(uid_str)] = PlayerState.from_dict(ps_data)

        properties = {}
        for pid, ps_data in data.get("properties", {}).items():
            properties[pid] = PropertyState.from_dict(ps_data)

        property_groups = [
            PropertyGroup.from_dict(pg)
            for pg in data.get("property_groups", [])
        ]

        chance_deck = None
        if data.get("chance_deck"):
            chance_deck = CardDeck.from_dict(data["chance_deck"])

        fund_deck = None
        if data.get("fund_deck"):
            fund_deck = CardDeck.from_dict(data["fund_deck"])

        return cls(
            game_id=UUID(data["game_id"]),
            room_id=UUID(data["room_id"]),
            config=config,
            state=GameState(data.get("state", "waiting_for_players")),
            board=board,
            players=players,
            turn_order=[UUID(uid) for uid in data.get("turn_order", [])],
            current_turn_index=data.get("current_turn_index", 0),
            turn_number=data.get("turn_number", 0),
            properties=properties,
            property_groups=property_groups,
            chance_deck=chance_deck,
            fund_deck=fund_deck,
            event_sequence=data.get("event_sequence", 0),
            started_at=datetime.fromisoformat(data["started_at"])
                if data.get("started_at") else None,
            finished_at=datetime.fromisoformat(data["finished_at"])
                if data.get("finished_at") else None,
            free_parking_money=data.get("free_parking_money", 0),
        )

    @classmethod
    def create(
        cls,
        room_id: UUID,
        config: GameConfig,
        board: Board,
        chance_deck: CardDeck,
        fund_deck: CardDeck,
    ) -> Game:
        """
        Создать новую игру.

        Args:
            room_id: ID комнаты.
            config: Конфигурация игры.
            board: Игровое поле.
            chance_deck: Колода Шанс.
            fund_deck: Колода Фонд.

        Returns:
            Новый экземпляр Game.
        """
        return cls(
            game_id=uuid4(),
            room_id=room_id,
            config=config,
            state=GameState.WAITING_FOR_PLAYERS,
            board=board,
            chance_deck=chance_deck,
            fund_deck=fund_deck,
        )

    def __repr__(self) -> str:
        return (
            f"Game(id={self.game_id}, state={self.state.value}, "
            f"players={self.players_count}/{self.config.max_players}, "
            f"turn={self.turn_number})"
        )


# ============================================================================
# РЕЗУЛЬТАТ ИГРЫ (GameResult)
# ============================================================================

@dataclass(slots=True)
class GameResult:
    """
    Результат игры для одного игрока.

    Attributes:
        player_id: ID игрока.
        username: Имя игрока.
        final_money: Финальный баланс.
        properties_value: Стоимость собственности.
        total_wealth: Общая стоимость (деньги + собственность).
        rank: Занятое место (1 = победитель).
        is_bankrupt: Стал ли банкротом.
    """

    player_id: UUID
    username: str
    final_money: int
    properties_value: int = 0
    total_wealth: int = 0
    rank: int = 0
    is_bankrupt: bool = False

    @property
    def is_winner(self) -> bool:
        """Является ли победителем."""
        return self.rank == 1

    def to_dict(self) -> dict:
        """Сериализация результата."""
        return {
            "player_id": str(self.player_id),
            "username": self.username,
            "final_money": self.final_money,
            "properties_value": self.properties_value,
            "total_wealth": self.total_wealth,
            "rank": self.rank,
            "is_bankrupt": self.is_bankrupt,
            "is_winner": self.is_winner,
        }

    def __repr__(self) -> str:
        return (
            f"GameResult(#{self.rank} {self.username}: "
            f"{self.total_wealth}$)"
        )