"""
server/game/game_engine.py

Ядро игровой логики «Миллиардер».

Содержит все правила игры и координирует работу игровых компонентов:
- Бросок кубиков и перемещение
- Обработка клеток (собственность, шанс, фонд, налоги, тюрьма, Веранда)
- Покупка и продажа собственности
- Строительство домов и отелей
- Залог и выкуп
- Торговля и аукционы
- Тюрьма и Веранда
- Банкротство и завершение игры

Использует паттерн State Machine для управления ходом игры.

Python: 3.13+
"""

from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

from shared.constants import (
    BOARD_CELLS_COUNT,
    DEFAULT_START_BONUS,
    DOUBLES_FOR_JAIL,
    JAIL_CELL_ID,
)
from shared.dice import Dice, DiceRoll, DiceHistory
from shared.enums import CellType, GameState, TurnState, EventType, CardActionType
from shared.models.card import Card, CardDeck
from shared.models.game import Game, GameConfig, PlayerState, GameResult
from shared.models.position import Board, CellPosition
from shared.models.property import Property, PropertyState
from shared.card_actions import process_card, CardActionResult
from shared.property_utils import (
    calculate_rent,
    can_build_house,
    can_build_hotel,
    can_mortgage,
    can_unmortgage,
    calculate_unmortgage_cost,
    calculate_auction_start_price,
    check_monopoly,
    group_properties_by_color,
    update_property_groups,
)
from server.event.event_bus import EventBus
from server.game.auction_manager import AuctionManager
from server.game.trade_manager import TradeManager
from server.game.jail_manager import JailManager
from server.game.veranda_manager import VerandaManager
from server.game.bankruptcy_manager import BankruptcyManager
from server.game.undo_stack import (
    UndoStack,
    BuyPropertyAction,
    BuildHouseAction,
    BuildHotelAction,
    PayRentAction,
    DiceRollAction,
)

logger = logging.getLogger("billionaire.game")


# ============================================================================
# ИГРОВОЙ ДВИЖОК
# ============================================================================

class GameEngine:
    """
    Ядро игровой логики.

    Содержит все правила и координирует работу компонентов.
    Не управляет таймерами и очерёдностью ходов — это задача GameLoop.

    Usage:
        engine = GameEngine(event_bus, auction_mgr, trade_mgr, jail_mgr, ...)
        result = await engine.roll_dice(game, player_id)
        result = await engine.buy_property(game, player_id, property_id)
    """

    def __init__(
        self,
        event_bus: EventBus,
        auction_manager: AuctionManager,
        trade_manager: TradeManager,
        jail_manager: JailManager,
        veranda_manager: VerandaManager,
        bankruptcy_manager: BankruptcyManager,
        undo_stack: UndoStack,
    ) -> None:
        """
        Инициализация игрового движка.

        Args:
            event_bus: Шина событий.
            auction_manager: Менеджер аукционов.
            trade_manager: Менеджер торговли.
            jail_manager: Менеджер тюрьмы.
            veranda_manager: Менеджер Веранды.
            bankruptcy_manager: Менеджер банкротства.
            undo_stack: Стек отмены действий.
        """
        self._event_bus = event_bus
        self._auction_manager = auction_manager
        self._trade_manager = trade_manager
        self._jail_manager = jail_manager
        self._veranda_manager = veranda_manager
        self._bankruptcy_manager = bankruptcy_manager
        self._undo_stack = undo_stack

        self._dice = Dice()

        # Словари property_defs для быстрого доступа
        self._property_defs: dict[str, Property] = {}

    # ========================================================================
    # ИНИЦИАЛИЗАЦИЯ ИГРЫ
    # ========================================================================

    def initialize_game(
        self,
        game: Game,
        property_defs: dict[str, Property],
        chance_cards: list[Card],
        fund_cards: list[Card],
    ) -> None:
        """
        Инициализировать игру перед началом.

        Args:
            game: Состояние игры.
            property_defs: Описания всей собственности.
            chance_cards: Карточки «Шанс».
            fund_cards: Карточки «Фонд».
        """
        self._property_defs = property_defs

        # Создаём колоды
        game.chance_deck = CardDeck.create_from_list(
            card_type=CardType.CHANCE if hasattr(CardType, 'CHANCE') else None,
            cards_data=[c.to_dict() for c in chance_cards],
        )
        game.fund_deck = CardDeck.create_from_list(
            card_type=CardType.FUND if hasattr(CardType, 'FUND') else None,
            cards_data=[c.to_dict() for c in fund_cards],
        )

        # Инициализируем состояния собственности
        for prop_id, prop_def in property_defs.items():
            game.properties[prop_id] = PropertyState(
                property_id=prop_id,
            )

        # Создаём группы собственности
        game.property_groups = group_properties_by_color(property_defs)

        # Устанавливаем первого игрока
        game.set_first_player(0)

        logger.info(
            "Игра %s инициализирована: %d игроков, %d свойств",
            str(game.game_id)[:8],
            game.players_count,
            len(game.properties),
        )

    # ========================================================================
    # БРОСОК КУБИКОВ
    # ========================================================================

    async def roll_dice(
        self,
        game: Game,
        player_id: UUID,
    ) -> dict[str, Any]:
        """
        Выполнить бросок кубиков и переместить игрока.

        Args:
            game: Состояние игры.
            player_id: ID игрока.

        Returns:
            Результат броска и перемещения.

        Raises:
            ValueError: Если не ход игрока или игрок в тюрьме/на Веранде.
        """
        player = game.players.get(player_id)
        if player is None:
            raise ValueError("Игрок не найден")

        if game.current_player_id != player_id:
            raise ValueError("Сейчас не ваш ход")

        if player.in_jail:
            raise ValueError("Вы в тюрьме — нельзя бросать кубики")

        if self._veranda_manager.is_on_veranda(player_id):
            raise ValueError("Вы на Веранде — нельзя бросать кубики")

        # Бросок
        roll = self._dice.roll()

        # Записываем в историю
        dice_history = DiceHistory()
        dice_history.add_roll(roll)

        # Сохраняем предыдущую позицию
        previous_position = player.position.cell_id

        # Перемещаем
        passed_start = player.position.move(roll.total, BOARD_CELLS_COUNT)

        # Записываем в undo-стек
        self._undo_stack.push(DiceRollAction(
            player_id=player_id,
            die1=roll.die1,
            die2=roll.die2,
            previous_position=previous_position,
        ))

        result = {
            "die1": roll.die1,
            "die2": roll.die2,
            "total": roll.total,
            "is_double": roll.is_double,
            "from_cell": previous_position,
            "to_cell": player.position.cell_id,
            "passed_start": passed_start,
        }

        # Бонус за прохождение Старта
        if passed_start:
            bonus = game.config.start_bonus or DEFAULT_START_BONUS
            player.add_money(bonus, "start_bonus")
            result["start_bonus"] = bonus

        # Проверка на три дубля
        if dice_history.should_go_to_jail:
            self._jail_manager.send_to_jail(player, "three_doubles")
            result["go_to_jail"] = True

        # Получаем информацию о клетке
        cell = game.board.get_cell(player.position.cell_id)
        if cell:
            result["cell_type"] = cell.type.value
            result["cell_name"] = cell.name
            if cell.property_id:
                result["property_id"] = cell.property_id
                prop_state = game.properties.get(cell.property_id)
                if prop_state:
                    result["property_owned"] = prop_state.is_owned
                    result["property_owner_id"] = str(prop_state.owner_id) if prop_state.owner_id else None
                    result["property_mortgaged"] = prop_state.mortgaged
                    result["can_buy"] = not prop_state.is_owned

        # Публикуем событие
        await self._event_bus.publish(
            EventType.DICE_ROLLED,
            {
                "game_id": game.game_id,
                "user_id": str(player_id),
                "username": player.username,
                "die1": roll.die1,
                "die2": roll.die2,
                "total": roll.total,
                "is_double": roll.is_double,
            },
        )

        await self._event_bus.publish(
            EventType.PLAYER_MOVED,
            {
                "game_id": game.game_id,
                "user_id": str(player_id),
                "from_cell": previous_position,
                "to_cell": player.position.cell_id,
                "passed_start": passed_start,
            },
        )

        logger.info(
            "Игрок %s бросает [%d]+[%d]=%d, клетка %d (%s)",
            player.username,
            roll.die1,
            roll.die2,
            roll.total,
            player.position.cell_id,
            cell.name if cell else "?",
        )

        return result

    # ========================================================================
    # ПОКУПКА СОБСТВЕННОСТИ
    # ========================================================================

    async def buy_property(
        self,
        game: Game,
        player_id: UUID,
        property_id: str,
    ) -> dict[str, Any]:
        """
        Купить свободную собственность.

        Args:
            game: Состояние игры.
            player_id: ID игрока.
            property_id: ID собственности.

        Returns:
            Результат покупки.

        Raises:
            ValueError: Если собственность занята или недостаточно средств.
        """
        player = game.players.get(player_id)
        if player is None:
            raise ValueError("Игрок не найден")

        prop_def = self._property_defs.get(property_id)
        if prop_def is None:
            raise ValueError(f"Собственность не найдена: {property_id}")

        prop_state = game.properties.get(property_id)
        if prop_state is None:
            raise ValueError(f"Состояние собственности не найдено: {property_id}")

        if prop_state.is_owned:
            raise ValueError("Собственность уже занята")

        if not player.can_afford(prop_def.price):
            raise ValueError(
                f"Недостаточно средств: нужно {prop_def.price}$, "
                f"доступно {player.money}$"
            )

        # Списываем деньги
        player.remove_money(prop_def.price, f"buy_{property_id}")

        # Передаём собственность
        prop_state.assign_owner(player_id)
        player.add_property(property_id)

        # Обновляем группы
        update_property_groups(game.property_groups, game.properties)

        # Записываем в undo-стек
        self._undo_stack.push(BuyPropertyAction(
            player_id=player_id,
            property_id=property_id,
            price=prop_def.price,
            previous_owner_id=None,
        ))

        result = {
            "property_id": property_id,
            "property_name": prop_def.name,
            "price": prop_def.price,
            "new_balance": player.money,
        }

        # Публикуем событие
        await self._event_bus.publish(
            EventType.PROPERTY_BOUGHT,
            {
                "game_id": game.game_id,
                "user_id": str(player_id),
                "username": player.username,
                "property_id": property_id,
                "property_name": prop_def.name,
                "price": prop_def.price,
            },
        )

        logger.info(
            "Игрок %s купил %s за %d$",
            player.username,
            prop_def.name,
            prop_def.price,
        )

        return result

    # ========================================================================
    # ОТКАЗ ОТ ПОКУПКИ (ЗАПУСК АУКЦИОНА)
    # ========================================================================

    async def decline_property(
        self,
        game: Game,
        player_id: UUID,
        property_id: str,
    ) -> dict[str, Any]:
        """
        Отказаться от покупки и запустить аукцион.

        Args:
            game: Состояние игры.
            player_id: ID игрока.
            property_id: ID собственности.

        Returns:
            Информация об аукционе.
        """
        prop_def = self._property_defs.get(property_id)
        if prop_def is None:
            raise ValueError(f"Собственность не найдена: {property_id}")

        # Запускаем аукцион
        auction = await self._auction_manager.start_auction(
            game_id=game.game_id,
            property_def=prop_def,
            players=[p.user_id for p in game.players.values() if not p.bankrupt],
        )

        await self._event_bus.publish(
            EventType.PROPERTY_DECLINED,
            {
                "game_id": game.game_id,
                "user_id": str(player_id),
                "property_id": property_id,
            },
        )

        return {
            "property_id": property_id,
            "auction_id": str(auction.auction_id),
            "start_price": auction.start_price,
        }

    # ========================================================================
    # ВЫПЛАТА АРЕНДЫ
    # ========================================================================

    async def pay_rent(
        self,
        game: Game,
        from_player_id: UUID,
        to_player_id: UUID,
        property_id: str,
        dice_total: int = 0,
    ) -> dict[str, Any]:
        """
        Выплатить арендную плату.

        Args:
            game: Состояние игры.
            from_player_id: Плательщик.
            to_player_id: Получатель.
            property_id: ID собственности.
            dice_total: Сумма кубиков (для utilities).

        Returns:
            Результат выплаты.
        """
        from_player = game.players.get(from_player_id)
        to_player = game.players.get(to_player_id)
        prop_state = game.properties.get(property_id)
        prop_def = self._property_defs.get(property_id)

        if not all([from_player, to_player, prop_state, prop_def]):
            raise ValueError("Данные не найдены")

        # Рассчитываем аренду
        rent = calculate_rent(
            property_def=prop_def,
            property_state=prop_state,
            dice_total=dice_total,
            railroads_owned=self._count_player_railroads(to_player_id, game),
            utilities_owned=self._count_player_utilities(to_player_id, game),
        )

        if rent == 0:
            return {"amount": 0, "reason": "mortgaged"}

        # Проверяем платёжеспособность
        if not from_player.can_afford(rent):
            # Проверяем полную возможность оплаты
            can_pay = self._bankruptcy_manager.can_pay_debt(
                from_player, rent, game.properties, self._property_defs,
            )
            if not can_pay:
                # Банкротство
                await self._bankruptcy_manager.declare_bankrupt(
                    player=from_player,
                    debt_amount=rent,
                    game_id=game.game_id,
                    creditor_id=to_player_id,
                    properties=game.properties,
                )
                return {"bankrupt": True, "player_id": str(from_player_id)}

        # Выплата
        from_player.remove_money(rent, f"rent_{property_id}")
        to_player.add_money(rent, f"rent_{property_id}")

        # Undo
        self._undo_stack.push(PayRentAction(
            from_player_id=from_player_id,
            to_player_id=to_player_id,
            amount=rent,
            property_id=property_id,
        ))

        await self._event_bus.publish(
            EventType.RENT_PAID,
            {
                "game_id": game.game_id,
                "from_player_id": str(from_player_id),
                "to_player_id": str(to_player_id),
                "property_id": property_id,
                "amount": rent,
            },
        )

        logger.info(
            "Аренда: %s → %s, %d$ за %s",
            from_player.username,
            to_player.username,
            rent,
            prop_def.name,
        )

        return {
            "amount": rent,
            "from_player_id": str(from_player_id),
            "to_player_id": str(to_player_id),
            "property_id": property_id,
            "property_name": prop_def.name,
        }

    # ========================================================================
    # СТРОИТЕЛЬСТВО
    # ========================================================================

    async def build_house(
        self,
        game: Game,
        player_id: UUID,
        property_id: str,
    ) -> dict[str, Any]:
        """
        Построить дом.

        Args:
            game: Состояние игры.
            player_id: ID игрока.
            property_id: ID собственности.

        Returns:
            Результат строительства.
        """
        player = game.players.get(player_id)
        prop_def = self._property_defs.get(property_id)
        prop_state = game.properties.get(property_id)

        if not all([player, prop_def, prop_state]):
            raise ValueError("Данные не найдены")

        # Проверка возможности
        can_build, error = can_build_house(prop_def, prop_state, player.money)
        if not can_build:
            raise ValueError(error or "Невозможно построить дом")

        # Строим
        previous_houses = prop_state.houses
        prop_state.build_house()
        player.remove_money(prop_def.house_cost, f"build_house_{property_id}")

        # Undo
        self._undo_stack.push(BuildHouseAction(
            player_id=player_id,
            property_id=property_id,
            cost=prop_def.house_cost,
            previous_houses=previous_houses,
        ))

        await self._event_bus.publish(
            EventType.HOUSE_BUILT,
            {
                "game_id": game.game_id,
                "user_id": str(player_id),
                "property_id": property_id,
                "property_name": prop_def.name,
                "new_level": prop_state.houses,
            },
        )

        logger.info(
            "Игрок %s построил дом на %s (уровень: %d)",
            player.username,
            prop_def.name,
            prop_state.houses,
        )

        return {
            "property_id": property_id,
            "new_houses": prop_state.houses,
            "cost": prop_def.house_cost,
            "new_balance": player.money,
        }

    async def build_hotel(
        self,
        game: Game,
        player_id: UUID,
        property_id: str,
    ) -> dict[str, Any]:
        """
        Построить отель.

        Args:
            game: Состояние игры.
            player_id: ID игрока.
            property_id: ID собственности.

        Returns:
            Результат строительства.
        """
        player = game.players.get(player_id)
        prop_def = self._property_defs.get(property_id)
        prop_state = game.properties.get(property_id)

        if not all([player, prop_def, prop_state]):
            raise ValueError("Данные не найдены")

        can_build, error = can_build_hotel(prop_def, prop_state, player.money)
        if not can_build:
            raise ValueError(error or "Невозможно построить отель")

        prop_state.build_hotel()
        player.remove_money(prop_def.hotel_cost, f"build_hotel_{property_id}")

        self._undo_stack.push(BuildHotelAction(
            player_id=player_id,
            property_id=property_id,
            cost=prop_def.hotel_cost,
        ))

        await self._event_bus.publish(
            EventType.HOTEL_BUILT,
            {
                "game_id": game.game_id,
                "user_id": str(player_id),
                "property_id": property_id,
                "property_name": prop_def.name,
            },
        )

        logger.info(
            "Игрок %s построил отель на %s",
            player.username,
            prop_def.name,
        )

        return {
            "property_id": property_id,
            "has_hotel": True,
            "cost": prop_def.hotel_cost,
            "new_balance": player.money,
        }

    # ========================================================================
    # ЗАЛОГ И ВЫКУП
    # ========================================================================

    async def mortgage_property(
        self,
        game: Game,
        player_id: UUID,
        property_id: str,
    ) -> dict[str, Any]:
        """
        Заложить собственность.

        Args:
            game: Состояние игры.
            player_id: ID игрока.
            property_id: ID собственности.

        Returns:
            Результат залога.
        """
        player = game.players.get(player_id)
        prop_def = self._property_defs.get(property_id)
        prop_state = game.properties.get(property_id)

        if not all([player, prop_def, prop_state]):
            raise ValueError("Данные не найдены")

        can_mortgage_flag, error = can_mortgage(prop_state)
        if not can_mortgage_flag:
            raise ValueError(error or "Невозможно заложить")

        prop_state.mortgage()
        player.add_money(prop_def.mortgage_value, f"mortgage_{property_id}")

        await self._event_bus.publish(
            EventType.PROPERTY_MORTGAGED,
            {
                "game_id": game.game_id,
                "user_id": str(player_id),
                "property_id": property_id,
                "property_name": prop_def.name,
                "amount": prop_def.mortgage_value,
            },
        )

        logger.info(
            "Игрок %s заложил %s за %d$",
            player.username,
            prop_def.name,
            prop_def.mortgage_value,
        )

        return {
            "property_id": property_id,
            "mortgage_value": prop_def.mortgage_value,
            "new_balance": player.money,
        }

    async def unmortgage_property(
        self,
        game: Game,
        player_id: UUID,
        property_id: str,
    ) -> dict[str, Any]:
        """
        Выкупить из залога.

        Args:
            game: Состояние игры.
            player_id: ID игрока.
            property_id: ID собственности.

        Returns:
            Результат выкупа.
        """
        player = game.players.get(player_id)
        prop_def = self._property_defs.get(property_id)
        prop_state = game.properties.get(property_id)

        if not all([player, prop_def, prop_state]):
            raise ValueError("Данные не найдены")

        can_unmortgage_flag, error = can_unmortgage(prop_state, prop_def, player.money)
        if not can_unmortgage_flag:
            raise ValueError(error or "Невозможно выкупить")

        cost = calculate_unmortgage_cost(prop_def.mortgage_value)
        player.remove_money(cost, f"unmortgage_{property_id}")
        prop_state.unmortgage()

        await self._event_bus.publish(
            EventType.PROPERTY_UNMORTGAGED,
            {
                "game_id": game.game_id,
                "user_id": str(player_id),
                "property_id": property_id,
                "property_name": prop_def.name,
                "amount": cost,
            },
        )

        logger.info(
            "Игрок %s выкупил %s из залога за %d$",
            player.username,
            prop_def.name,
            cost,
        )

        return {
            "property_id": property_id,
            "unmortgage_cost": cost,
            "new_balance": player.money,
        }

    # ========================================================================
    # КАРТОЧКИ
    # ========================================================================

    async def draw_chance_card(
        self,
        game: Game,
        player_id: UUID,
    ) -> dict[str, Any]:
        """
        Взять карточку «Шанс».

        Args:
            game: Состояние игры.
            player_id: ID игрока.

        Returns:
            Результат карточки.
        """
        return await self._draw_card(game, player_id, is_chance=True)

    async def draw_fund_card(
        self,
        game: Game,
        player_id: UUID,
    ) -> dict[str, Any]:
        """
        Взять карточку «Фонд».

        Args:
            game: Состояние игры.
            player_id: ID игрока.

        Returns:
            Результат карточки.
        """
        return await self._draw_card(game, player_id, is_chance=False)

    async def _draw_card(
        self,
        game: Game,
        player_id: UUID,
        is_chance: bool,
    ) -> dict[str, Any]:
        """
        Внутренний метод взятия карточки.

        Args:
            game: Состояние игры.
            player_id: ID игрока.
            is_chance: True — Шанс, False — Фонд.

        Returns:
            Результат карточки.
        """
        player = game.players.get(player_id)
        if player is None:
            raise ValueError("Игрок не найден")

        deck = game.chance_deck if is_chance else game.fund_deck
        if deck is None:
            raise ValueError("Колода не инициализирована")

        card = deck.draw()
        if card is None:
            return {"card": None, "message": "Колода пуста"}

        # Обрабатываем карточку
        result = process_card(card)

        # Применяем результат к игре
        await self._apply_card_result(game, player, result)

        await self._event_bus.publish(
            EventType.CARD_DRAWN,
            {
                "game_id": game.game_id,
                "user_id": str(player_id),
                "card_id": card.card_id,
                "card_type": card.card_type.value,
                "title": card.title,
            },
        )

        logger.info(
            "Игрок %s взял карточку «%s»: %s",
            player.username,
            card.title,
            card.description,
        )

        return {
            "card": card.to_dict(),
            "result": result.to_dict(),
        }

    async def _apply_card_result(
        self,
        game: Game,
        player: PlayerState,
        result: CardActionResult,
    ) -> None:
        """
        Применить результат карточки к игре.

        Args:
            game: Состояние игры.
            player: Состояние игрока.
            result: Результат обработки карточки.
        """
        # Денежные изменения
        if result.has_money_change:
            if result.money_change > 0:
                player.add_money(result.money_change, "card")
            else:
                if player.can_afford(-result.money_change):
                    player.remove_money(-result.money_change, "card")
                else:
                    # Проверка банкротства
                    can_pay = self._bankruptcy_manager.can_pay_debt(
                        player, -result.money_change, game.properties, self._property_defs,
                    )
                    if not can_pay:
                        await self._bankruptcy_manager.declare_bankrupt(
                            player=player,
                            debt_amount=-result.money_change,
                            game_id=game.game_id,
                            creditor_id=None,
                            properties=game.properties,
                        )
                        return

        # Перемещение
        if result.move_to_cell is not None:
            player.position.move_to(result.move_to_cell, BOARD_CELLS_COUNT)

        if result.move_steps is not None:
            if result.move_steps > 0:
                player.position.move(result.move_steps, BOARD_CELLS_COUNT)
            elif result.move_steps < 0:
                player.position.move_backward(-result.move_steps, BOARD_CELLS_COUNT)

        # Тюрьма
        if result.go_to_jail:
            self._jail_manager.send_to_jail(player, "card")

        if result.get_out_of_jail:
            player.release_from_jail()

        # Веранда
        if result.go_to_veranda:
            self._veranda_manager.send_to_veranda(player)

        if result.leave_veranda:
            self._veranda_manager.force_exit(player)

        # Сбор с игроков
        if result.collect_from_each is not None:
            for other in game.players.values():
                if other.user_id != player.user_id and not other.bankrupt:
                    amount = result.collect_from_each
                    if other.can_afford(amount):
                        other.remove_money(amount, "card_collect")
                        player.add_money(amount, "card_collect")

        # Выплата каждому
        if result.pay_to_each is not None:
            for other in game.players.values():
                if other.user_id != player.user_id and not other.bankrupt:
                    amount = result.pay_to_each
                    if player.can_afford(amount):
                        player.remove_money(amount, "card_pay")
                        other.add_money(amount, "card_pay")

        # Ремонт
        if result.has_repair:
            from shared.card_actions import calculate_repair_cost
            player_props = game.get_player_properties(player.user_id)
            total = calculate_repair_cost(
                result.repair_cost_per_house or 0,
                result.repair_cost_per_hotel or 0,
                player_props,
            )
            if player.can_afford(total):
                player.remove_money(total, "repair")
            else:
                can_pay = self._bankruptcy_manager.can_pay_debt(
                    player, total, game.properties, self._property_defs,
                )
                if not can_pay:
                    await self._bankruptcy_manager.declare_bankrupt(
                        player=player,
                        debt_amount=total,
                        game_id=game.game_id,
                        creditor_id=None,
                        properties=game.properties,
                    )

    # ========================================================================
    # ЗАВЕРШЕНИЕ ХОДА
    # ========================================================================

    async def end_turn(
        self,
        game: Game,
        player_id: UUID,
    ) -> dict[str, Any]:
        """
        Завершить ход игрока.

        Args:
            game: Состояние игры.
            player_id: ID игрока.

        Returns:
            Информация о следующем игроке.
        """
        if game.current_player_id != player_id:
            raise ValueError("Сейчас не ваш ход")

        # Переходим к следующему игроку
        next_player = game.next_turn()

        await self._event_bus.publish(
            EventType.TURN_ENDED,
            {
                "game_id": game.game_id,
                "user_id": str(player_id),
                "turn_number": game.turn_number,
            },
        )

        if next_player:
            await self._event_bus.publish(
                EventType.TURN_STARTED,
                {
                    "game_id": game.game_id,
                    "user_id": str(next_player.user_id),
                    "username": next_player.username,
                    "turn_number": game.turn_number,
                },
            )

        result = {
            "previous_player_id": str(player_id),
            "next_player_id": str(next_player.user_id) if next_player else None,
            "turn_number": game.turn_number,
        }

        # Проверка завершения игры
        if self._bankruptcy_manager.check_game_end(game.players):
            await self._finish_game(game)
            result["game_over"] = True

        return result

    # ========================================================================
    # ЗАВЕРШЕНИЕ ИГРЫ
    # ========================================================================

    async def _finish_game(self, game: Game) -> dict[str, Any]:
        """
        Завершить игру и подсчитать результаты.

        Args:
            game: Состояние игры.

        Returns:
            Результаты игры.
        """
        game.finish()
        results = game.calculate_results()

        winner = results[0] if results else None

        await self._event_bus.publish(
            EventType.GAME_FINISHED,
            {
                "game_id": game.game_id,
                "winner_id": str(winner.player_id) if winner else None,
                "winner_name": winner.username if winner else None,
                "results": [r.to_dict() for r in results],
                "total_turns": game.turn_number,
            },
        )

        logger.info(
            "Игра %s завершена! Победитель: %s (%d$)",
            str(game.game_id)[:8],
            winner.username if winner else "никто",
            winner.total_wealth if winner else 0,
        )

        return {
            "game_id": str(game.game_id),
            "results": [r.to_dict() for r in results],
            "winner_id": str(winner.player_id) if winner else None,
        }

    # ========================================================================
    # ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ
    # ========================================================================

    def _count_player_railroads(self, player_id: UUID, game: Game) -> int:
        """Подсчитать количество станций у игрока."""
        count = 0
        for prop_id, prop_state in game.properties.items():
            if prop_state.owner_id == player_id:
                prop_def = self._property_defs.get(prop_id)
                if prop_def and prop_def.is_railroad:
                    count += 1
        return count

    def _count_player_utilities(self, player_id: UUID, game: Game) -> int:
        """Подсчитать количество utilities у игрока."""
        count = 0
        for prop_id, prop_state in game.properties.items():
            if prop_state.owner_id == player_id:
                prop_def = self._property_defs.get(prop_id)
                if prop_def and prop_def.is_utility:
                    count += 1
        return count

    def get_game_state_for_player(
        self,
        game: Game,
        player_id: UUID,
    ) -> dict[str, Any]:
        """
        Получить состояние игры для отправки клиенту.

        Args:
            game: Состояние игры.
            player_id: ID запрашивающего игрока.

        Returns:
            Словарь с состоянием.
        """
        return game.to_sync_dict(player_id)

    def get_stats(self) -> dict:
        """
        Получить статистику игрового движка.

        Returns:
            Словарь с метриками.
        """
        return {
            "undo_stack": self._undo_stack.get_stats(),
        }