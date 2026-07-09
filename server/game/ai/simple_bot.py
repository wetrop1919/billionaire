"""
server/game/ai/simple_bot.py

Простая реализация AI-игрока (бота).

Реализует базовую стратегию:
- Покупает любую доступную собственность, если хватает денег
- Участвует в аукционах до 70% от цены
- Строит дома при первой возможности
- Принимает выгодные торговые предложения
- Всегда платит штраф за выход из тюрьмы

Может использоваться для заполнения пустых мест в игре
или для тестирования игровой логики.

Python: 3.13+
"""

from __future__ import annotations

import logging
import random
from typing import Any, Optional
from uuid import UUID

from shared.models.game import Game, PlayerState
from shared.models.property import Property, PropertyState
from shared.models.trade import TradeOffer
from server.game.ai.base_bot import BaseBot

logger = logging.getLogger("billionaire.game")


# ============================================================================
# ПРОСТОЙ БОТ
# ============================================================================

class SimpleBot(BaseBot):
    """
    Простой AI-игрок с базовой стратегией.

    Всегда покупает доступную собственность, строит при возможности,
    участвует в аукционах, принимает выгодные сделки.

    Usage:
        bot = SimpleBot(player_id, name="Bot-1", aggression=0.6)
        should_buy = await bot.decide_property_purchase(game, player, prop_def, prop_state)
    """

    def __init__(
        self,
        player_id: UUID,
        name: str = "SimpleBot",
        aggression: float = 0.6,
    ) -> None:
        """
        Инициализация простого бота.

        Args:
            player_id: ID бота.
            name: Отображаемое имя.
            aggression: Уровень агрессивности (0.0-1.0).
        """
        super().__init__(player_id, name, aggression)

        # Минимальный остаток денег после покупки
        self._money_reserve_ratio: float = 0.15

    # ========================================================================
    # ПРИНЯТИЕ РЕШЕНИЙ
    # ========================================================================

    async def decide_property_purchase(
        self,
        game: Game,
        player: PlayerState,
        property_def: Property,
        property_state: PropertyState,
    ) -> bool:
        """
        Решить, покупать ли собственность.

        Стратегия: покупать всегда, если после покупки остаётся
        резервный запас денег (15% от текущего баланса).

        Args:
            game: Состояние игры.
            player: Состояние бота.
            property_def: Описание собственности.
            property_state: Состояние собственности.

        Returns:
            True, если покупать.
        """
        # Проверяем, занята ли
        if property_state.is_owned:
            return False

        # Проверяем, хватает ли денег с резервом
        min_reserve = int(player.money * self._money_reserve_ratio)
        can_afford_with_reserve = (player.money - property_def.price) >= min_reserve

        if can_afford_with_reserve:
            return True

        # Даже без резерва — покупаем дешёвую
        if property_def.price <= player.money * 0.3:
            return True

        # Агрессивные боты покупают чаще
        if self.aggression > 0.7 and player.money >= property_def.price:
            return True

        return False

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

        Стратегия:
        - Торговаться до 70% от цены (агрессивные до 90%)
        - Не торговаться, если ставка уже выше лимита
        - С вероятностью 20% пропустить (пас)

        Args:
            game: Состояние игры.
            player: Состояние бота.
            property_def: Описание собственности.
            current_bid: Текущая максимальная ставка.
            min_bid: Минимальная следующая ставка.

        Returns:
            Сумма ставки или None для паса.
        """
        # Максимальная цена, которую бот готов заплатить
        max_ratio = 0.7 + (self.aggression * 0.2)  # 0.7 — 0.9
        max_price = int(property_def.price * max_ratio)

        # Если текущая ставка уже выше лимита — пас
        if current_bid >= max_price:
            return None

        # Случайный пас (20% — разнообразие поведения)
        if random.random() < 0.2:
            return None

        # Вычисляем ставку
        if current_bid == 0:
            # Первая ставка — стартовая цена + случайная добавка
            bid = min_bid + random.randint(0, min_bid)
        else:
            # Перебиваем с запасом
            increment = random.randint(1, max(1, (max_price - current_bid) // 3))
            bid = current_bid + increment

        # Не превышаем лимит и баланс
        bid = min(bid, max_price, player.money)

        if bid < min_bid:
            return None

        return bid

    async def decide_building(
        self,
        game: Game,
        player: PlayerState,
        property_defs: dict[str, Property],
    ) -> list[tuple[str, str]]:
        """
        Решить, что строить.

        Стратегия:
        - Строить на самой дорогой улице в первую очередь
        - Отель строить только при большом запасе денег
        - Не строить, если после стройки останется < 100$

        Args:
            game: Состояние игры.
            player: Состояние бота.
            property_defs: Описания собственности.

        Returns:
            Список (property_id, "house"|"hotel").
        """
        decisions: list[tuple[str, str]] = []

        # Получаем свои улицы, на которых можно строить
        buildable: list[tuple[str, Property, PropertyState]] = []
        for prop_id in player.properties:
            prop_def = property_defs.get(prop_id)
            prop_state = game.properties.get(prop_id)

            if not prop_def or not prop_state:
                continue
            if not prop_def.can_build_houses:
                continue
            if prop_state.mortgaged:
                continue

            buildable.append((prop_id, prop_def, prop_state))

        # Сортируем по ценности (дорогие сначала)
        buildable.sort(
            key=lambda x: x[1].price,
            reverse=True,
        )

        for prop_id, prop_def, prop_state in buildable:
            # Проверяем возможность строительства отеля
            if prop_state.houses == 4 and not prop_state.has_hotel:
                if player.money >= prop_def.hotel_cost + 200:
                    decisions.append((prop_id, "hotel"))
                    player.money -= prop_def.hotel_cost
                    continue

            # Проверяем возможность строительства дома
            if prop_state.houses < 4:
                if player.money >= prop_def.house_cost + 100:
                    decisions.append((prop_id, "house"))
                    player.money -= prop_def.house_cost

            # Строим не больше 3 зданий за ход
            if len(decisions) >= 3:
                break

        return decisions

    async def decide_trade_response(
        self,
        game: Game,
        player: PlayerState,
        offer: TradeOffer,
    ) -> bool:
        """
        Решить, принимать ли торговое предложение.

        Стратегия:
        - Принимать, если получаем более ценную собственность
        - Отклонять запросы на деньги
        - Отклонять невыгодные обмены

        Args:
            game: Состояние игры.
            player: Состояние бота.
            offer: Предложение.

        Returns:
            True, если принять.
        """
        # Не принимаем запросы на деньги
        if offer.request_money > 0:
            return False

        # Оцениваем получаемую собственность
        incoming_value = sum(
            self._get_property_price(pid, game) for pid in offer.offer_properties
        )
        outgoing_value = sum(
            self._get_property_price(pid, game) for pid in offer.request_properties
        )

        # Принимаем, если получаем больше
        if incoming_value > outgoing_value * 1.1:  # 10% запас
            return True

        # Агрессивные боты более сговорчивы
        if self.aggression > 0.7 and incoming_value >= outgoing_value:
            return True

        return False

    async def decide_jail_exit(
        self,
        game: Game,
        player: PlayerState,
    ) -> str:
        """
        Решить, как выходить из тюрьмы.

        Стратегия:
        - Использовать карточку, если она есть
        - Иначе платить штраф (если есть деньги)
        - Оставаться, если нет ни карточки, ни денег

        Args:
            game: Состояние игры.
            player: Состояние бота.

        Returns:
            "pay_fine", "use_card", или "stay".
        """
        # Используем карточку
        if player.has_get_out_of_jail_card:
            return "use_card"

        # Платим штраф
        if player.money >= 50:
            return "pay_fine"

        # Остаёмся
        return "stay"

    # ========================================================================
    # ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ
    # ========================================================================

    def _get_property_price(
        self,
        property_id: str,
        game: Game,
    ) -> int:
        """
        Получить цену собственности.

        Args:
            property_id: ID собственности.
            game: Состояние игры.

        Returns:
            Цена (оценочная).
        """
        prop_state = game.properties.get(property_id)
        if prop_state is None:
            return 0

        # Базовая оценка
        value = 100

        # Учитываем постройки
        if prop_state.houses > 0:
            value += prop_state.houses * 50
        if prop_state.has_hotel:
            value += 200

        # Заложенная стоит меньше
        if prop_state.mortgaged:
            value = value // 3

        return value

    def get_bot_info(self) -> dict[str, Any]:
        """
        Получить информацию о боте.

        Returns:
            Словарь с параметрами.
        """
        return {
            "player_id": str(self.player_id),
            "name": self.name,
            "aggression": self.aggression,
            "strategy": "simple",
            "money_reserve_ratio": self._money_reserve_ratio,
        }