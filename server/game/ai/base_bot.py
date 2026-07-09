"""
server/game/ai/base_bot.py

Абстрактный базовый класс для AI-игроков (ботов).

Определяет интерфейс, который должны реализовать все боты.
Позволяет легко добавлять новые типы AI с разными стратегиями.

Боты могут:
- Принимать решения о покупке собственности
- Участвовать в аукционах
- Строить дома и отели
- Отвечать на торговые предложения
- Выбирать способ выхода из тюрьмы

Python: 3.13+
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Optional
from uuid import UUID

from shared.models.game import Game, PlayerState
from shared.models.property import Property, PropertyState
from shared.models.card import Card
from shared.models.trade import TradeOffer

logger = logging.getLogger("billionaire.game")


# ============================================================================
# ИНТЕРФЕЙС БОТА
# ============================================================================

class BaseBot(ABC):
    """
    Абстрактный базовый класс для AI-игрока.

    Определяет интерфейс принятия решений.
    Наследники реализуют конкретные стратегии.

    Attributes:
        player_id: ID бота (совпадает с user_id).
        name: Имя бота.
        aggression: Уровень агрессивности (0.0 — 1.0).
    """

    def __init__(
        self,
        player_id: UUID,
        name: str = "Bot",
        aggression: float = 0.5,
    ) -> None:
        """
        Инициализация бота.

        Args:
            player_id: ID бота.
            name: Отображаемое имя.
            aggression: Уровень агрессивности (0.0 = пассивный, 1.0 = агрессивный).
        """
        self.player_id: UUID = player_id
        self.name: str = name
        self.aggression: float = max(0.0, min(1.0, aggression))

    # ========================================================================
    # АБСТРАКТНЫЕ МЕТОДЫ
    # ========================================================================

    @abstractmethod
    async def decide_property_purchase(
        self,
        game: Game,
        player: PlayerState,
        property_def: Property,
        property_state: PropertyState,
    ) -> bool:
        """
        Решить, покупать ли свободную собственность.

        Args:
            game: Состояние игры.
            player: Состояние бота.
            property_def: Описание собственности.
            property_state: Состояние собственности.

        Returns:
            True, если покупать.
        """
        ...

    @abstractmethod
    async def decide_auction_bid(
        self,
        game: Game,
        player: PlayerState,
        property_def: Property,
        current_bid: int,
        min_bid: int,
    ) -> Optional[int]:
        """
        Решить, какую ставку сделать на аукционе.

        Args:
            game: Состояние игры.
            player: Состояние бота.
            property_def: Описание собственности.
            current_bid: Текущая ставка.
            min_bid: Минимальная ставка.

        Returns:
            Сумма ставки или None (пас).
        """
        ...

    @abstractmethod
    async def decide_building(
        self,
        game: Game,
        player: PlayerState,
        property_defs: dict[str, Property],
    ) -> list[tuple[str, str]]:
        """
        Решить, что строить.

        Args:
            game: Состояние игры.
            player: Состояние бота.
            property_defs: Описания всей собственности.

        Returns:
            Список кортежей (property_id, "house"|"hotel").
        """
        ...

    @abstractmethod
    async def decide_trade_response(
        self,
        game: Game,
        player: PlayerState,
        offer: TradeOffer,
    ) -> bool:
        """
        Решить, принимать ли торговое предложение.

        Args:
            game: Состояние игры.
            player: Состояние бота.
            offer: Предложение.

        Returns:
            True, если принять.
        """
        ...

    @abstractmethod
    async def decide_jail_exit(
        self,
        game: Game,
        player: PlayerState,
    ) -> str:
        """
        Решить, как выходить из тюрьмы.

        Args:
            game: Состояние игры.
            player: Состояние бота.

        Returns:
            "pay_fine", "use_card", или "stay".
        """
        ...

    # ========================================================================
    # ОБЩИЕ ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ
    # ========================================================================

    def can_afford(self, player: PlayerState, amount: int) -> bool:
        """
        Проверить, может ли бот позволить себе трату.

        Args:
            player: Состояние бота.
            amount: Сумма.

        Returns:
            True, если достаточно денег.
        """
        return player.money >= amount

    def get_owned_properties(
        self,
        player: PlayerState,
        game: Game,
    ) -> list[tuple[str, PropertyState]]:
        """
        Получить список собственности бота.

        Args:
            player: Состояние бота.
            game: Состояние игры.

        Returns:
            Список кортежей (property_id, PropertyState).
        """
        return [
            (prop_id, game.properties[prop_id])
            for prop_id in player.properties
            if prop_id in game.properties
        ]

    def count_properties_in_group(
        self,
        player: PlayerState,
        color_group: str,
        property_defs: dict[str, Property],
    ) -> int:
        """
        Подсчитать количество собственности в цветовой группе.

        Args:
            player: Состояние бота.
            color_group: Цветовая группа.
            property_defs: Описания собственности.

        Returns:
            Количество.
        """
        count = 0
        for prop_id in player.properties:
            prop_def = property_defs.get(prop_id)
            if prop_def and prop_def.color_group and prop_def.color_group.value == color_group:
                count += 1
        return count

    def evaluate_property_value(
        self,
        property_def: Property,
        game: Game,
        player: PlayerState,
    ) -> float:
        """
        Оценить ценность собственности для бота.

        Args:
            property_def: Описание собственности.
            game: Состояние игры.
            player: Состояние бота.

        Returns:
            Оценка (чем больше, тем ценнее).
        """
        score = 0.0

        # Базовая ценность = цена / 10
        score += property_def.price / 10.0

        # Улицы ценнее
        if property_def.is_street:
            score *= 1.5

            # Проверяем монополию
            if property_def.color_group:
                owned_in_group = self.count_properties_in_group(
                    player, property_def.color_group.value, {}
                )
                total_in_group = 3 if property_def.color_group.value in ("brown", "dark_blue") else 3
                if owned_in_group >= total_in_group - 1:
                    score *= 2.0  # Почти монополия — очень ценно

        # Станции
        if property_def.is_railroad:
            railroads = sum(
                1 for ps in game.properties.values()
                if ps.owner_id == player.user_id
            )
            score *= (1.0 + railroads * 0.5)

        # Дешевле = доступнее
        if property_def.price <= player.money * 0.3:
            score *= 1.2

        return score

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.name}, aggression={self.aggression})"