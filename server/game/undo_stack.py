"""
server/game/undo_stack.py

Стек отмены действий (Undo).

Позволяет администратору отменять последние игровые действия.
Каждое действие сохраняется в стеке с возможностью обратного выполнения.

Поддерживает отмену:
- Покупки собственности
- Строительства домов/отелей
- Выплаты аренды
- Торговых сделок
- Бросков кубиков
- Действий карточек

Python: 3.13+
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

logger = logging.getLogger("billionaire.game")


# ============================================================================
# АБСТРАКТНОЕ ДЕЙСТВИЕ
# ============================================================================

class GameAction(ABC):
    """
    Абстрактное игровое действие, которое можно отменить.

    Каждое действие хранит достаточно информации для восстановления
    предыдущего состояния игры.
    """

    def __init__(self, description: str = "") -> None:
        self.action_id: UUID = uuid4()
        self.description: str = description
        self.timestamp: datetime = datetime.now(timezone.utc)
        self.player_id: Optional[UUID] = None
        self.game_id: Optional[UUID] = None

    @abstractmethod
    async def execute(self, game_context: dict[str, Any]) -> None:
        """
        Выполнить действие.

        Args:
            game_context: Контекст игры (состояние, игроки, свойства).
        """
        ...

    @abstractmethod
    async def undo(self, game_context: dict[str, Any]) -> None:
        """
        Отменить действие и восстановить предыдущее состояние.

        Args:
            game_context: Контекст игры.
        """
        ...

    def to_dict(self) -> dict[str, Any]:
        """Сериализация действия."""
        return {
            "action_id": str(self.action_id),
            "description": self.description,
            "timestamp": self.timestamp.isoformat(),
            "player_id": str(self.player_id) if self.player_id else None,
            "game_id": str(self.game_id) if self.game_id else None,
        }


# ============================================================================
# КОНКРЕТНЫЕ ДЕЙСТВИЯ
# ============================================================================

class BuyPropertyAction(GameAction):
    """Покупка собственности."""

    def __init__(
        self,
        player_id: UUID,
        property_id: str,
        price: int,
        previous_owner_id: Optional[UUID] = None,
    ) -> None:
        super().__init__(f"Покупка {property_id} за {price}$")
        self.player_id = player_id
        self.property_id = property_id
        self.price = price
        self.previous_owner_id = previous_owner_id

    async def execute(self, game_context: dict[str, Any]) -> None:
        """Выполняется игровым движком."""
        pass

    async def undo(self, game_context: dict[str, Any]) -> None:
        """Возврат собственности и денег."""
        players = game_context.get("players", {})
        properties = game_context.get("properties", {})

        # Возвращаем деньги
        player = players.get(self.player_id)
        if player:
            player.money += self.price

        # Возвращаем собственность
        prop_state = properties.get(self.property_id)
        if prop_state:
            prop_state.owner_id = self.previous_owner_id
            prop_state.houses = 0
            prop_state.has_hotel = False
            prop_state.mortgaged = False

        logger.info("Отмена покупки: %s", self.property_id)

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data.update({
            "action_type": "buy_property",
            "property_id": self.property_id,
            "price": self.price,
            "previous_owner_id": str(self.previous_owner_id) if self.previous_owner_id else None,
        })
        return data


class BuildHouseAction(GameAction):
    """Строительство дома."""

    def __init__(
        self,
        player_id: UUID,
        property_id: str,
        cost: int,
        previous_houses: int,
    ) -> None:
        super().__init__(f"Строительство дома на {property_id} за {cost}$")
        self.player_id = player_id
        self.property_id = property_id
        self.cost = cost
        self.previous_houses = previous_houses

    async def execute(self, game_context: dict[str, Any]) -> None:
        pass

    async def undo(self, game_context: dict[str, Any]) -> None:
        players = game_context.get("players", {})
        properties = game_context.get("properties", {})

        player = players.get(self.player_id)
        if player:
            player.money += self.cost

        prop_state = properties.get(self.property_id)
        if prop_state:
            prop_state.houses = self.previous_houses

        logger.info("Отмена строительства: %s", self.property_id)

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data.update({
            "action_type": "build_house",
            "property_id": self.property_id,
            "cost": self.cost,
            "previous_houses": self.previous_houses,
        })
        return data


class BuildHotelAction(GameAction):
    """Строительство отеля."""

    def __init__(
        self,
        player_id: UUID,
        property_id: str,
        cost: int,
    ) -> None:
        super().__init__(f"Строительство отеля на {property_id} за {cost}$")
        self.player_id = player_id
        self.property_id = property_id
        self.cost = cost

    async def execute(self, game_context: dict[str, Any]) -> None:
        pass

    async def undo(self, game_context: dict[str, Any]) -> None:
        players = game_context.get("players", {})
        properties = game_context.get("properties", {})

        player = players.get(self.player_id)
        if player:
            player.money += self.cost

        prop_state = properties.get(self.property_id)
        if prop_state:
            prop_state.has_hotel = False
            prop_state.houses = 4

        logger.info("Отмена строительства отеля: %s", self.property_id)

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data.update({
            "action_type": "build_hotel",
            "property_id": self.property_id,
            "cost": self.cost,
        })
        return data


class PayRentAction(GameAction):
    """Выплата арендной платы."""

    def __init__(
        self,
        from_player_id: UUID,
        to_player_id: UUID,
        amount: int,
        property_id: str,
    ) -> None:
        super().__init__(f"Аренда {amount}$ от {from_player_id} → {to_player_id}")
        self.player_id = from_player_id
        self.from_player_id = from_player_id
        self.to_player_id = to_player_id
        self.amount = amount
        self.property_id = property_id

    async def execute(self, game_context: dict[str, Any]) -> None:
        pass

    async def undo(self, game_context: dict[str, Any]) -> None:
        players = game_context.get("players", {})

        from_player = players.get(self.from_player_id)
        to_player = players.get(self.to_player_id)

        if from_player:
            from_player.money += self.amount
        if to_player:
            to_player.money -= self.amount

        logger.info("Отмена аренды: %d$", self.amount)

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data.update({
            "action_type": "pay_rent",
            "from_player_id": str(self.from_player_id),
            "to_player_id": str(self.to_player_id),
            "amount": self.amount,
            "property_id": self.property_id,
        })
        return data


class DiceRollAction(GameAction):
    """Бросок кубиков."""

    def __init__(
        self,
        player_id: UUID,
        die1: int,
        die2: int,
        previous_position: int,
    ) -> None:
        super().__init__(f"Бросок кубиков: {die1}+{die2}")
        self.player_id = player_id
        self.die1 = die1
        self.die2 = die2
        self.previous_position = previous_position

    async def execute(self, game_context: dict[str, Any]) -> None:
        pass

    async def undo(self, game_context: dict[str, Any]) -> None:
        players = game_context.get("players", {})

        player = players.get(self.player_id)
        if player:
            player.position.cell_id = self.previous_position

        logger.info("Отмена броска кубиков: позиция %d", self.previous_position)

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data.update({
            "action_type": "dice_roll",
            "die1": self.die1,
            "die2": self.die2,
            "previous_position": self.previous_position,
        })
        return data


class TradeAction(GameAction):
    """Торговая сделка."""

    def __init__(
        self,
        trade_id: UUID,
        from_player_id: UUID,
        to_player_id: UUID,
        properties_exchanged: dict[str, tuple[Optional[UUID], Optional[UUID]]],
        money_transferred: int = 0,
    ) -> None:
        super().__init__(f"Сделка {trade_id}")
        self.player_id = from_player_id
        self.trade_id = trade_id
        self.from_player_id = from_player_id
        self.to_player_id = to_player_id
        self.properties_exchanged = properties_exchanged
        self.money_transferred = money_transferred

    async def execute(self, game_context: dict[str, Any]) -> None:
        pass

    async def undo(self, game_context: dict[str, Any]) -> None:
        properties = game_context.get("properties", {})
        players = game_context.get("players", {})

        # Возвращаем собственность владельцам
        for prop_id, (from_owner, to_owner) in self.properties_exchanged.items():
            prop_state = properties.get(prop_id)
            if prop_state:
                prop_state.owner_id = from_owner

        # Возвращаем деньги
        if self.money_transferred > 0:
            from_player = players.get(self.from_player_id)
            to_player = players.get(self.to_player_id)
            if from_player:
                from_player.money += self.money_transferred
            if to_player:
                to_player.money -= self.money_transferred

        logger.info("Отмена сделки: %s", str(self.trade_id)[:8])

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data.update({
            "action_type": "trade",
            "trade_id": str(self.trade_id),
            "from_player_id": str(self.from_player_id),
            "to_player_id": str(self.to_player_id),
        })
        return data


# ============================================================================
# СТЕК ОТМЕНЫ
# ============================================================================

class UndoStack:
    """
    Стек отмены игровых действий.

    Хранит историю действий с возможностью отмены
    последних N операций.

    Usage:
        stack = UndoStack(max_size=100)
        stack.push(BuyPropertyAction(...))
        await stack.undo_last(game_context)
    """

    def __init__(self, max_size: int = 100) -> None:
        """
        Инициализация стека отмены.

        Args:
            max_size: Максимальное количество хранимых действий.
        """
        self._max_size: int = max_size
        self._stack: list[GameAction] = []

    # ========================================================================
    # ОПЕРАЦИИ СО СТЕКОМ
    # ========================================================================

    def push(self, action: GameAction) -> None:
        """
        Добавить действие в стек.

        Если стек переполнен — удаляется самое старое действие.

        Args:
            action: Выполненное действие.
        """
        self._stack.append(action)

        if len(self._stack) > self._max_size:
            removed = self._stack.pop(0)
            logger.debug(
                "Удалено старое действие из стека: %s",
                removed.description,
            )

        logger.debug(
            "Добавлено в стек отмены: %s (всего: %d)",
            action.description,
            len(self._stack),
        )

    async def undo_last(self, game_context: dict[str, Any]) -> Optional[GameAction]:
        """
        Отменить последнее действие.

        Args:
            game_context: Контекст игры.

        Returns:
            Отменённое действие или None, если стек пуст.
        """
        if not self._stack:
            logger.warning("Стек отмены пуст")
            return None

        action = self._stack.pop()

        try:
            await action.undo(game_context)
            logger.info("Отменено действие: %s", action.description)
            return action
        except Exception as e:
            logger.error("Ошибка отмены действия: %s", e)
            # Возвращаем действие обратно в стек
            self._stack.append(action)
            raise

    async def undo_multiple(
        self,
        count: int,
        game_context: dict[str, Any],
    ) -> list[GameAction]:
        """
        Отменить несколько последних действий.

        Args:
            count: Количество действий для отмены.
            game_context: Контекст игры.

        Returns:
            Список отменённых действий.
        """
        undone: list[GameAction] = []

        for _ in range(min(count, len(self._stack))):
            action = await self.undo_last(game_context)
            if action:
                undone.append(action)

        return undone

    # ========================================================================
    # ИНФОРМАЦИЯ
    # ========================================================================

    def can_undo(self) -> bool:
        """Проверить, можно ли отменить действие."""
        return len(self._stack) > 0

    def peek_last(self) -> Optional[GameAction]:
        """
        Посмотреть последнее действие без удаления.

        Returns:
            Последнее действие или None.
        """
        return self._stack[-1] if self._stack else None

    def get_history(
        self,
        limit: int = 20,
        player_id: Optional[UUID] = None,
    ) -> list[dict[str, Any]]:
        """
        Получить историю действий.

        Args:
            limit: Максимальное количество.
            player_id: Фильтр по игроку.

        Returns:
            Список словарей с действиями.
        """
        actions = self._stack

        if player_id:
            actions = [a for a in actions if a.player_id == player_id]

        # Последние действия сверху
        actions = list(reversed(actions[-limit:]))

        return [action.to_dict() for action in actions]

    def get_stats(self) -> dict:
        """
        Получить статистику стека.

        Returns:
            Словарь с метриками.
        """
        return {
            "stack_size": len(self._stack),
            "max_size": self._max_size,
            "can_undo": self.can_undo(),
        }

    def clear(self) -> None:
        """Очистить стек."""
        count = len(self._stack)
        self._stack.clear()
        logger.debug("Стек отмены очищен (%d действий)", count)