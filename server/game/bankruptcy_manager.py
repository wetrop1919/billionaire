"""
server/game/bankruptcy_manager.py

Менеджер банкротства игроков.

Управляет процессом банкротства:
- Проверка возможности оплаты долга
- Объявление банкротом
- Распределение имущества банкрота
- Аукцион имущества (если долг банку)

Правила банкротства:
- Игрок не может заплатить долг + всё продано → банкрот
- Имущество возвращается системе (банку)
- Долг перед игроком → часть имущества передаётся кредитору
- Долг перед банком → имущество уходит на аукцион

Python: 3.13+
"""

from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

from shared.enums import EventType
from shared.models.game import PlayerState
from shared.models.property import PropertyState, Property
from server.event.event_bus import EventBus

logger = logging.getLogger("billionaire.game")


# ============================================================================
# МЕНЕДЖЕР БАНКРОТСТВА
# ============================================================================

class BankruptcyManager:
    """
    Менеджер банкротства.

    Управляет процессом банкротства игроков и распределением
    их имущества между кредиторами или банком.

    Usage:
        manager = BankruptcyManager(event_bus)
        can_pay = manager.can_pay_debt(player, debt_amount)
        if not can_pay:
            await manager.declare_bankrupt(player, debt_amount, creditor_id)
    """

    def __init__(self, event_bus: EventBus) -> None:
        """
        Инициализация менеджера банкротства.

        Args:
            event_bus: Шина событий.
        """
        self._event_bus = event_bus

    # ========================================================================
    # ПРОВЕРКИ
    # ========================================================================

    def can_pay_debt(
        self,
        player: PlayerState,
        amount: int,
        properties: Optional[dict[str, PropertyState]] = None,
        property_defs: Optional[dict[str, Property]] = None,
    ) -> bool:
        """
        Проверить, может ли игрок оплатить долг.

        Учитывает:
        - Наличные деньги
        - Возможность продажи построек
        - Возможность залога собственности

        Args:
            player: Состояние игрока.
            amount: Сумма долга.
            properties: Состояния всей собственности в игре.
            property_defs: Описания собственности.

        Returns:
            True, если может оплатить.
        """
        # Достаточно наличных
        if player.money >= amount:
            return True

        total_available = player.money

        # Оцениваем стоимость построек
        if properties and property_defs:
            for prop_id in player.properties:
                prop_state = properties.get(prop_id)
                prop_def = property_defs.get(prop_id)

                if prop_state and prop_def and not prop_state.mortgaged:
                    # Стоимость продажи построек (полцены)
                    if prop_state.houses > 0:
                        total_available += (prop_state.houses * prop_def.house_cost) // 2
                    if prop_state.has_hotel:
                        hotel_value = (
                            (4 * prop_def.house_cost + prop_def.hotel_cost) // 2
                        )
                        total_available += hotel_value

                    # Залоговая стоимость (если без построек)
                    if prop_state.houses == 0 and not prop_state.has_hotel:
                        total_available += prop_def.mortgage_value

        return total_available >= amount

    def get_total_liquidation_value(
        self,
        player: PlayerState,
        properties: dict[str, PropertyState],
        property_defs: dict[str, Property],
    ) -> int:
        """
        Получить общую стоимость имущества при ликвидации.

        Args:
            player: Состояние игрока.
            properties: Состояния собственности.
            property_defs: Описания собственности.

        Returns:
            Общая стоимость при продаже всего.
        """
        total = player.money

        for prop_id in player.properties:
            prop_state = properties.get(prop_id)
            prop_def = property_defs.get(prop_id)

            if prop_state and prop_def:
                # Стоимость построек (полцены)
                if prop_state.houses > 0:
                    total += (prop_state.houses * prop_def.house_cost) // 2
                if prop_state.has_hotel:
                    total += (4 * prop_def.house_cost + prop_def.hotel_cost) // 2

                # Залоговая стоимость (если нет построек)
                if prop_state.houses == 0 and not prop_state.has_hotel:
                    total += prop_def.mortgage_value

        return total

    # ========================================================================
    # ОБЪЯВЛЕНИЕ БАНКРОТОМ
    # ========================================================================

    async def declare_bankrupt(
        self,
        player: PlayerState,
        debt_amount: int,
        game_id: UUID,
        creditor_id: Optional[UUID] = None,
        properties: Optional[dict[str, PropertyState]] = None,
    ) -> dict[str, Any]:
        """
        Объявить игрока банкротом и распределить имущество.

        Args:
            player: Состояние игрока.
            debt_amount: Сумма долга.
            game_id: ID игры.
            creditor_id: ID кредитора (None — долг банку).
            properties: Состояния всей собственности (для обновления).

        Returns:
            Словарь с результатами банкротства.
        """
        player.declare_bankrupt()

        result: dict[str, Any] = {
            "player_id": str(player.user_id),
            "username": player.username,
            "debt_amount": debt_amount,
            "creditor_id": str(creditor_id) if creditor_id else None,
            "debt_to_bank": creditor_id is None,
            "properties_lost": list(player.properties),
            "properties_to_auction": [],
            "properties_to_creditor": [],
        }

        if creditor_id is not None:
            # Долг перед игроком — передаётся часть имущества, равная долгу
            if properties:
                transferred = self._transfer_properties_to_creditor(
                    player=player,
                    creditor_id=creditor_id,
                    debt_amount=debt_amount,
                    properties=properties,
                )
                result["properties_to_creditor"] = transferred
        else:
            # Долг перед банком — имущество на аукцион
            result["properties_to_auction"] = list(player.properties)

        # Очищаем имущество банкрота
        if properties:
            for prop_id in list(player.properties):
                prop_state = properties.get(prop_id)
                if prop_state and prop_id not in result["properties_to_creditor"]:
                    prop_state.remove_owner()

        # Публикуем событие
        await self._event_bus.publish(
            EventType.PLAYER_BANKRUPT,
            {
                "game_id": game_id,
                "user_id": str(player.user_id),
                "username": player.username,
                "debt_amount": debt_amount,
                "creditor_id": str(creditor_id) if creditor_id else None,
                "properties_lost": result["properties_lost"],
            },
        )

        logger.info(
            "Игрок %s объявлен банкротом! Долг: %d$, кредитор: %s",
            player.username,
            debt_amount,
            str(creditor_id)[:8] if creditor_id else "банк",
        )

        return result

    # ========================================================================
    # РАСПРЕДЕЛЕНИЕ ИМУЩЕСТВА
    # ========================================================================

    def _transfer_properties_to_creditor(
        self,
        player: PlayerState,
        creditor_id: UUID,
        debt_amount: int,
        properties: dict[str, PropertyState],
    ) -> list[str]:
        """
        Передать часть имущества кредитору в счёт долга.

        Args:
            player: Состояние банкрота.
            creditor_id: ID кредитора.
            debt_amount: Сумма долга.
            properties: Состояния собственности.

        Returns:
            Список ID переданной собственности.
        """
        transferred: list[str] = []
        remaining_debt = debt_amount

        # Сортируем собственность по стоимости (самые дорогие сначала)
        sorted_props = sorted(
            player.properties,
            key=lambda pid: self._get_property_value(pid, properties),
            reverse=True,
        )

        for prop_id in sorted_props:
            if remaining_debt <= 0:
                break

            prop_state = properties.get(prop_id)
            if prop_state is None:
                continue

            # Оцениваем стоимость
            value = self._get_property_value(prop_id, properties)

            # Передаём собственность
            prop_state.owner_id = creditor_id
            prop_state.mortgaged = False  # Сбрасываем залог
            transferred.append(prop_id)
            remaining_debt -= value

        return transferred

    def _get_property_value(
        self,
        property_id: str,
        properties: dict[str, PropertyState],
    ) -> int:
        """
        Оценить стоимость собственности.

        Args:
            property_id: ID собственности.
            properties: Состояния собственности.

        Returns:
            Оценочная стоимость.
        """
        prop_state = properties.get(property_id)
        if prop_state is None:
            return 0

        # Базовая стоимость — как mortgage value (50% от цены)
        value = 100  # Значение по умолчанию

        # Увеличиваем за постройки
        if prop_state.houses > 0:
            value += prop_state.houses * 50
        if prop_state.has_hotel:
            value += 200

        return value

    # ========================================================================
    # ПРОВЕРКА ЗАВЕРШЕНИЯ ИГРЫ
    # ========================================================================

    def check_game_end(
        self,
        players: dict[UUID, PlayerState],
    ) -> bool:
        """
        Проверить, завершена ли игра после банкротства.

        Игра заканчивается, когда остался 1 активный игрок
        или любой игрок стал банкротом.

        Args:
            players: Словарь состояний всех игроков.

        Returns:
            True, если игра должна завершиться.
        """
        active_players = [
            p for p in players.values()
            if not p.bankrupt
        ]

        bankrupt_players = [
            p for p in players.values()
            if p.bankrupt
        ]

        # Игра заканчивается при первом банкротстве
        if bankrupt_players:
            return True

        # Или если остался только 1 игрок
        if len(active_players) <= 1:
            return True

        return False

    def get_winner(
        self,
        players: dict[UUID, PlayerState],
    ) -> Optional[PlayerState]:
        """
        Определить победителя (игрок с наибольшим количеством денег).

        Args:
            players: Словарь состояний всех игроков.

        Returns:
            Состояние победителя или None.
        """
        if not players:
            return None

        return max(
            players.values(),
            key=lambda p: p.money if not p.bankrupt else -1,
        )

    # ========================================================================
    # ИНФОРМАЦИЯ
    # ========================================================================

    def get_stats(self) -> dict:
        """
        Получить статистику менеджера банкротства.

        Returns:
            Словарь с метриками.
        """
        return {
            "status": "active",
        }