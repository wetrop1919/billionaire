"""
shared/models/event.py

Модели игровых событий для проекта "Миллиардер".

Содержит:
- GameEvent — запись об одном игровом событии (журнал)
- EventData — базовый класс для данных события
- Конкретные типы данных событий (DiceRolledData, PropertyBoughtData, ...)

Используется EventBus, EventLogger и ReplayManager для записи
и воспроизведения истории игры.

Python: 3.13+
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional, Self
from uuid import UUID, uuid4

from shared.enums import EventType


# ============================================================================
# МОДЕЛЬ ИГРОВОГО СОБЫТИЯ (GameEvent)
# ============================================================================

@dataclass(slots=True)
class GameEvent:
    """
    Запись об одном игровом событии.

    Представляет атомарное действие или изменение состояния в игре.
    Все события сохраняются в журнале и могут быть использованы
    для воспроизведения (replay) или отмены (undo).

    Attributes:
        event_id: Уникальный идентификатор события (UUID).
        game_id: ID игры, в которой произошло событие.
        event_type: Тип события (из EventType).
        user_id: ID игрока, совершившего действие (опционально).
        target_id: ID цели действия — другой игрок, собственность (опционально).
        data: Данные события (зависят от типа).
        created_at: Время события (UTC).
        turn_number: Номер хода, на котором произошло событие.
        sequence: Порядковый номер события в игре.
    """

    event_id: UUID
    game_id: UUID
    event_type: EventType
    user_id: Optional[UUID] = None
    target_id: Optional[str] = None
    data: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    turn_number: int = 0
    sequence: int = 0

    @classmethod
    def create(
        cls,
        game_id: UUID,
        event_type: EventType,
        user_id: Optional[UUID] = None,
        target_id: Optional[str] = None,
        data: dict[str, Any] | None = None,
        turn_number: int = 0,
        sequence: int = 0,
    ) -> GameEvent:
        """
        Создать новое игровое событие с автоматической генерацией ID и времени.

        Args:
            game_id: ID игры.
            event_type: Тип события.
            user_id: ID инициатора события.
            target_id: ID цели.
            data: Данные события.
            turn_number: Номер хода.
            sequence: Порядковый номер.

        Returns:
            Новый экземпляр GameEvent.
        """
        return cls(
            event_id=uuid4(),
            game_id=game_id,
            event_type=event_type,
            user_id=user_id,
            target_id=target_id,
            data=data or {},
            created_at=datetime.now(timezone.utc),
            turn_number=turn_number,
            sequence=sequence,
        )

    @property
    def description(self) -> str:
        """
        Человекочитаемое описание события.

        Returns:
            Краткое описание на основе типа события и данных.
        """
        descriptions: dict[EventType, str] = {
            EventType.PLAYER_JOINED: "Игрок присоединился",
            EventType.PLAYER_LEFT: "Игрок покинул игру",
            EventType.PLAYER_RECONNECTED: "Игрок переподключился",
            EventType.PLAYER_DISCONNECTED: "Игрок отключился",
            EventType.TURN_STARTED: "Ход начался",
            EventType.TURN_ENDED: "Ход завершён",
            EventType.TURN_TIMEOUT: "Таймаут хода",
            EventType.DICE_ROLLED: "Бросок кубиков",
            EventType.PLAYER_MOVED: "Игрок переместился",
            EventType.PROPERTY_BOUGHT: "Собственность куплена",
            EventType.PROPERTY_DECLINED: "Покупка отклонена",
            EventType.PROPERTY_AUCTIONED: "Собственность продана на аукционе",
            EventType.RENT_PAID: "Арендная плата выплачена",
            EventType.HOUSE_BUILT: "Дом построен",
            EventType.HOTEL_BUILT: "Отель построен",
            EventType.PROPERTY_MORTGAGED: "Собственность заложена",
            EventType.PROPERTY_UNMORTGAGED: "Собственность выкуплена из залога",
            EventType.CARD_DRAWN: "Карточка взята",
            EventType.CARD_ACTION_EXECUTED: "Действие карточки выполнено",
            EventType.TRADE_OFFERED: "Торговое предложение",
            EventType.TRADE_ACCEPTED: "Сделка принята",
            EventType.TRADE_DECLINED: "Сделка отклонена",
            EventType.PLAYER_JAILED: "Игрок отправлен в тюрьму",
            EventType.PLAYER_FREED: "Игрок освобождён из тюрьмы",
            EventType.VERANDA_ENTERED: "Игрок попал на Веранду",
            EventType.VERANDA_EXITED: "Игрок покинул Веранду",
            EventType.PLAYER_BANKRUPT: "Игрок обанкротился",
            EventType.GAME_STARTED: "Игра началась",
            EventType.GAME_FINISHED: "Игра завершена",
            EventType.GAME_PAUSED: "Игра на паузе",
            EventType.GAME_RESUMED: "Игра возобновлена",
            EventType.ADMIN_ACTION: "Действие администратора",
            EventType.SYSTEM_ERROR: "Системная ошибка",
            EventType.NETWORK_ERROR: "Сетевая ошибка",
        }
        return descriptions.get(self.event_type, f"Событие: {self.event_type.value}")

    # === СЕРИАЛИЗАЦИЯ ===

    def to_dict(self) -> dict[str, Any]:
        """
        Сериализация события в словарь.

        Returns:
            Словарь с полными данными события.
        """
        return {
            "event_id": str(self.event_id),
            "game_id": str(self.game_id),
            "event_type": self.event_type.value,
            "user_id": str(self.user_id) if self.user_id else None,
            "target_id": self.target_id,
            "data": self.data,
            "created_at": self.created_at.isoformat(),
            "turn_number": self.turn_number,
            "sequence": self.sequence,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GameEvent:
        """
        Создать событие из словаря.

        Args:
            data: Словарь с данными события.

        Returns:
            Новый экземпляр GameEvent.
        """
        return cls(
            event_id=UUID(data["event_id"]),
            game_id=UUID(data["game_id"]),
            event_type=EventType(data["event_type"]),
            user_id=UUID(data["user_id"]) if data.get("user_id") else None,
            target_id=data.get("target_id"),
            data=data.get("data", {}),
            created_at=datetime.fromisoformat(data["created_at"])
                if data.get("created_at")
                else datetime.now(timezone.utc),
            turn_number=data.get("turn_number", 0),
            sequence=data.get("sequence", 0),
        )

    def __repr__(self) -> str:
        user = str(self.user_id)[:8] if self.user_id else "system"
        return (
            f"GameEvent({self.event_type.value}, "
            f"user={user}, turn={self.turn_number}, seq={self.sequence})"
        )


# ============================================================================
# ДАННЫЕ СОБЫТИЙ (Event Data Classes)
# ============================================================================

@dataclass(slots=True)
class DiceRolledData:
    """Данные события броска кубиков."""

    die1: int
    die2: int
    total: int
    is_double: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "die1": self.die1,
            "die2": self.die2,
            "total": self.total,
            "is_double": self.is_double,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DiceRolledData:
        return cls(
            die1=data["die1"],
            die2=data["die2"],
            total=data["total"],
            is_double=data["is_double"],
        )


@dataclass(slots=True)
class PlayerMovedData:
    """Данные события перемещения игрока."""

    from_cell: int
    to_cell: int
    steps: int
    passed_start: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "from_cell": self.from_cell,
            "to_cell": self.to_cell,
            "steps": self.steps,
            "passed_start": self.passed_start,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PlayerMovedData:
        return cls(
            from_cell=data["from_cell"],
            to_cell=data["to_cell"],
            steps=data["steps"],
            passed_start=data["passed_start"],
        )


@dataclass(slots=True)
class PropertyBoughtData:
    """Данные события покупки собственности."""

    property_id: str
    property_name: str
    price: int
    new_balance: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "property_id": self.property_id,
            "property_name": self.property_name,
            "price": self.price,
            "new_balance": self.new_balance,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PropertyBoughtData:
        return cls(
            property_id=data["property_id"],
            property_name=data["property_name"],
            price=data["price"],
            new_balance=data["new_balance"],
        )


@dataclass(slots=True)
class RentPaidData:
    """Данные события выплаты аренды."""

    from_player_id: UUID
    to_player_id: UUID
    property_id: str
    property_name: str
    amount: int
    from_new_balance: int
    to_new_balance: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "from_player_id": str(self.from_player_id),
            "to_player_id": str(self.to_player_id),
            "property_id": self.property_id,
            "property_name": self.property_name,
            "amount": self.amount,
            "from_new_balance": self.from_new_balance,
            "to_new_balance": self.to_new_balance,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RentPaidData:
        return cls(
            from_player_id=UUID(data["from_player_id"]),
            to_player_id=UUID(data["to_player_id"]),
            property_id=data["property_id"],
            property_name=data["property_name"],
            amount=data["amount"],
            from_new_balance=data["from_new_balance"],
            to_new_balance=data["to_new_balance"],
        )


@dataclass(slots=True)
class BuildingData:
    """Данные события строительства."""

    property_id: str
    property_name: str
    build_type: str  # "house" или "hotel"
    new_level: int
    cost: int
    new_balance: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "property_id": self.property_id,
            "property_name": self.property_name,
            "build_type": self.build_type,
            "new_level": self.new_level,
            "cost": self.cost,
            "new_balance": self.new_balance,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BuildingData:
        return cls(
            property_id=data["property_id"],
            property_name=data["property_name"],
            build_type=data["build_type"],
            new_level=data["new_level"],
            cost=data["cost"],
            new_balance=data["new_balance"],
        )


@dataclass(slots=True)
class CardDrawnData:
    """Данные события взятия карточки."""

    card_id: str
    card_type: str
    title: str
    action_type: str
    action_data: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "card_id": self.card_id,
            "card_type": self.card_type,
            "title": self.title,
            "action_type": self.action_type,
            "action_data": self.action_data,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CardDrawnData:
        return cls(
            card_id=data["card_id"],
            card_type=data["card_type"],
            title=data["title"],
            action_type=data["action_type"],
            action_data=data.get("action_data", {}),
        )


@dataclass(slots=True)
class TradeData:
    """Данные события торговли."""

    trade_id: UUID
    from_player_id: UUID
    to_player_id: UUID
    offer_properties: list[str]
    request_properties: list[str]
    offer_cards: list[str]
    request_money: int
    loan_percent: int | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "trade_id": str(self.trade_id),
            "from_player_id": str(self.from_player_id),
            "to_player_id": str(self.to_player_id),
            "offer_properties": self.offer_properties,
            "request_properties": self.request_properties,
            "offer_cards": self.offer_cards,
            "request_money": self.request_money,
            "loan_percent": self.loan_percent,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TradeData:
        return cls(
            trade_id=UUID(data["trade_id"]),
            from_player_id=UUID(data["from_player_id"]),
            to_player_id=UUID(data["to_player_id"]),
            offer_properties=data.get("offer_properties", []),
            request_properties=data.get("request_properties", []),
            offer_cards=data.get("offer_cards", []),
            request_money=data.get("request_money", 0),
            loan_percent=data.get("loan_percent"),
        )


@dataclass(slots=True)
class GameFinishedData:
    """Данные события завершения игры."""

    results: list[dict[str, Any]]  # Список {player_id, final_money, rank}
    winner_id: UUID
    total_turns: int
    duration_minutes: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "results": self.results,
            "winner_id": str(self.winner_id),
            "total_turns": self.total_turns,
            "duration_minutes": self.duration_minutes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GameFinishedData:
        return cls(
            results=data["results"],
            winner_id=UUID(data["winner_id"]),
            total_turns=data["total_turns"],
            duration_minutes=data["duration_minutes"],
        )


@dataclass(slots=True)
class AdminActionData:
    """Данные события административного действия."""

    admin_id: UUID
    command: str
    target_id: str | None
    parameters: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "admin_id": str(self.admin_id),
            "command": self.command,
            "target_id": self.target_id,
            "parameters": self.parameters,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AdminActionData:
        return cls(
            admin_id=UUID(data["admin_id"]),
            command=data["command"],
            target_id=data.get("target_id"),
            parameters=data.get("parameters", {}),
        )


# ============================================================================
# ФАБРИКА ДАННЫХ СОБЫТИЙ
# ============================================================================

_EVENT_DATA_CLASSES: dict[EventType, type] = {
    EventType.DICE_ROLLED: DiceRolledData,
    EventType.PLAYER_MOVED: PlayerMovedData,
    EventType.PROPERTY_BOUGHT: PropertyBoughtData,
    EventType.RENT_PAID: RentPaidData,
    EventType.HOUSE_BUILT: BuildingData,
    EventType.HOTEL_BUILT: BuildingData,
    EventType.CARD_DRAWN: CardDrawnData,
    EventType.CARD_ACTION_EXECUTED: CardDrawnData,
    EventType.TRADE_OFFERED: TradeData,
    EventType.TRADE_ACCEPTED: TradeData,
    EventType.GAME_FINISHED: GameFinishedData,
    EventType.ADMIN_ACTION: AdminActionData,
}


def create_event_data(
    event_type: EventType,
    data: dict[str, Any],
) -> Any:
    """
    Создать типизированный объект данных события из словаря.

    Args:
        event_type: Тип события.
        data: Словарь с данными.

    Returns:
        Экземпляр соответствующего класса данных или исходный словарь,
        если тип события не имеет специализированного класса.
    """
    data_class = _EVENT_DATA_CLASSES.get(event_type)
    if data_class is not None:
        return data_class.from_dict(data)
    return data


def event_data_to_dict(event_type: EventType, data_obj: Any) -> dict[str, Any]:
    """
    Сериализовать объект данных события в словарь.

    Args:
        event_type: Тип события.
        data_obj: Объект данных события.

    Returns:
        Словарь с данными.
    """
    if hasattr(data_obj, "to_dict"):
        return data_obj.to_dict()
    if isinstance(data_obj, dict):
        return data_obj
    return {"value": str(data_obj)}