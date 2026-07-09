"""
server/game/jail_manager.py

Менеджер тюрьмы.

Управляет механикой тюрьмы:
- Отправка в тюрьму
- Пропуск ходов
- Способы выхода (штраф, карточка)
- Таймаут (2 круга без денег → банкротство)

Игрок попадает в тюрьму через:
- Клетку «Отправляйся в тюрьму»
- Карточку «Шанс»/«Фонд»
- Три дубля подряд

Python: 3.13+
"""

from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

from shared.constants import (
    JAIL_CELL_ID,
    JAIL_FINE,
    JAIL_MAX_ROUNDS,
)
from shared.enums import EventType, JailExitMethod
from shared.models.game import PlayerState
from server.event.event_bus import EventBus

logger = logging.getLogger("billionaire.game")


# ============================================================================
# МЕНЕДЖЕР ТЮРЬМЫ
# ============================================================================

class JailManager:
    """
    Менеджер тюрьмы.

    Управляет всеми аспектами тюремного заключения:
    отправка, пропуск ходов, способы выхода, банкротство.

    Usage:
        manager = JailManager(event_bus)
        manager.send_to_jail(player)
        result = await manager.process_jail_turn(player)
    """

    def __init__(self, event_bus: EventBus) -> None:
        """
        Инициализация менеджера тюрьмы.

        Args:
            event_bus: Шина событий.
        """
        self._event_bus = event_bus

    # ========================================================================
    # ОТПРАВКА В ТЮРЬМУ
    # ========================================================================

    def send_to_jail(
        self,
        player: PlayerState,
        reason: str = "go_to_jail_cell",
    ) -> None:
        """
        Отправить игрока в тюрьму.

        Args:
            player: Состояние игрока.
            reason: Причина (go_to_jail_cell, card, three_doubles).
        """
        player.send_to_jail(JAIL_CELL_ID)

        logger.info(
            "Игрок %s отправлен в тюрьму (причина: %s)",
            player.username,
            reason,
        )

    def is_in_jail(self, player: PlayerState) -> bool:
        """
        Проверить, находится ли игрок в тюрьме.

        Args:
            player: Состояние игрока.

        Returns:
            True, если в тюрьме.
        """
        return player.in_jail

    # ========================================================================
    # ОБРАБОТКА ХОДА В ТЮРЬМЕ
    # ========================================================================

    async def process_jail_turn(
        self,
        player: PlayerState,
        game_id: UUID,
    ) -> dict[str, Any]:
        """
        Обработать ход игрока в тюрьме.

        Игрок пропускает ход (не бросает кубики).
        Увеличивается счётчик кругов.

        Args:
            player: Состояние игрока.
            game_id: ID игры.

        Returns:
            Словарь с результатом обработки.
        """
        player.increment_jail_round()

        result = {
            "action": "jail_turn",
            "in_jail": True,
            "jail_rounds": player.jail_rounds,
            "max_rounds": JAIL_MAX_ROUNDS,
            "can_pay_fine": player.can_afford(JAIL_FINE),
            "has_jail_card": player.has_get_out_of_jail_card,
        }

        # Проверка на таймаут (2 круга)
        if player.jail_rounds >= JAIL_MAX_ROUNDS:
            if not player.can_afford(JAIL_FINE) and not player.has_get_out_of_jail_card:
                # Банкротство
                result["bankrupt"] = True
                result["bankrupt_reason"] = "jail_timeout"
                logger.info(
                    "Игрок %s провёл %d кругов в тюрьме без денег — банкротство",
                    player.username,
                    player.jail_rounds,
                )

        await self._event_bus.publish(
            EventType.TURN_STARTED,
            {
                "game_id": game_id,
                "user_id": str(player.user_id),
                "in_jail": True,
                "jail_rounds": player.jail_rounds,
            },
        )

        return result

    # ========================================================================
    # ВЫХОД ИЗ ТЮРЬМЫ
    # ========================================================================

    def pay_fine(self, player: PlayerState) -> tuple[bool, Optional[str]]:
        """
        Заплатить штраф за выход из тюрьмы.

        Args:
            player: Состояние игрока.

        Returns:
            Кортеж (успех, сообщение_об_ошибке).
        """
        if not player.in_jail:
            return False, "Вы не в тюрьме"

        if not player.can_afford(JAIL_FINE):
            return False, f"Недостаточно средств: нужно {JAIL_FINE}$"

        player.remove_money(JAIL_FINE, "jail_fine")
        player.release_from_jail()

        logger.info(
            "Игрок %s заплатил %d$ и вышел из тюрьмы",
            player.username,
            JAIL_FINE,
        )

        return True, None

    def use_jail_card(self, player: PlayerState) -> tuple[bool, Optional[str]]:
        """
        Использовать карточку освобождения из тюрьмы.

        Args:
            player: Состояние игрока.

        Returns:
            Кортеж (успех, сообщение_об_ошибке).
        """
        if not player.in_jail:
            return False, "Вы не в тюрьме"

        if not player.has_get_out_of_jail_card:
            return False, "У вас нет карточки освобождения"

        # Находим и используем карточку
        for card in player.cards:
            if not card.is_used and card.card_type.value in ("chance", "fund"):
                card.mark_used()
                player.release_from_jail()

                logger.info(
                    "Игрок %s использовал карточку и вышел из тюрьмы",
                    player.username,
                )
                return True, None

        return False, "Не удалось найти неиспользованную карточку"

    def force_release(self, player: PlayerState) -> None:
        """
        Принудительно освободить из тюрьмы (админ-команда).

        Args:
            player: Состояние игрока.
        """
        player.release_from_jail()
        logger.info(
            "Игрок %s принудительно освобождён из тюрьмы",
            player.username,
        )

    # ========================================================================
    # ПРОВЕРКИ
    # ========================================================================

    def can_leave_jail(self, player: PlayerState) -> bool:
        """
        Проверить, может ли игрок покинуть тюрьму.

        Args:
            player: Состояние игрока.

        Returns:
            True, если есть способ выхода.
        """
        if not player.in_jail:
            return True

        return (
            player.can_afford(JAIL_FINE)
            or player.has_get_out_of_jail_card
        )

    def get_jail_status(self, player: PlayerState) -> dict[str, Any]:
        """
        Получить статус тюремного заключения.

        Args:
            player: Состояние игрока.

        Returns:
            Словарь со статусом.
        """
        return {
            "in_jail": player.in_jail,
            "jail_rounds": player.jail_rounds,
            "max_rounds": JAIL_MAX_ROUNDS,
            "can_pay_fine": player.can_afford(JAIL_FINE),
            "fine_amount": JAIL_FINE,
            "has_jail_card": player.has_get_out_of_jail_card,
            "rounds_remaining": max(0, JAIL_MAX_ROUNDS - player.jail_rounds),
        }

    # ========================================================================
    # СОБЫТИЯ
    # ========================================================================

    async def notify_jail_event(
        self,
        game_id: UUID,
        player: PlayerState,
        event_type: EventType,
    ) -> None:
        """
        Отправить событие о тюрьме в EventBus.

        Args:
            game_id: ID игры.
            player: Состояние игрока.
            event_type: Тип события (PLAYER_JAILED или PLAYER_FREED).
        """
        await self._event_bus.publish(
            event_type,
            {
                "game_id": game_id,
                "user_id": str(player.user_id),
                "username": player.username,
            },
        )

    def get_stats(self) -> dict:
        """
        Получить статистику менеджера тюрьмы.

        Returns:
            Словарь с метриками.
        """
        return {
            "jail_fine": JAIL_FINE,
            "max_rounds": JAIL_MAX_ROUNDS,
        }