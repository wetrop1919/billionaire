"""
server/game/veranda_manager.py

Менеджер Веранды.

Управляет специальной клеткой «Веранда» вне игрового поля:
- Попадание на Веранду (только по карточке)
- Пропуск ходов
- Выход (платный или по карточке)

Веранда — отдельная клетка вне основного поля.
Игрок попадает туда только по карточке «Шанс» или «Фонд».
Для выхода нужно заплатить 50$ или использовать карточку.

Python: 3.13+
"""

from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

from shared.constants import VERANDA_EXIT_COST
from shared.enums import EventType
from shared.models.game import PlayerState
from server.event.event_bus import EventBus

logger = logging.getLogger("billionaire.game")


# ============================================================================
# МЕНЕДЖЕР ВЕРАНДЫ
# ============================================================================

class VerandaManager:
    """
    Менеджер Веранды.

    Управляет всеми аспектами пребывания на Веранде:
    попадание, пропуск ходов, способы выхода.

    Usage:
        manager = VerandaManager(event_bus)
        manager.send_to_veranda(player)
        result = await manager.process_veranda_turn(player)
    """

    # Идентификатор клетки Веранды (специальный, вне основного поля)
    VERANDA_CELL_ID: str = "veranda"

    def __init__(self, event_bus: EventBus) -> None:
        """
        Инициализация менеджера Веранды.

        Args:
            event_bus: Шина событий.
        """
        self._event_bus = event_bus

        # Игроки на Веранде {user_id: rounds_on_veranda}
        self._veranda_players: dict[UUID, int] = {}

    # ========================================================================
    # ПОПАДАНИЕ НА ВЕРАНДУ
    # ========================================================================

    def send_to_veranda(self, player: PlayerState) -> None:
        """
        Отправить игрока на Веранду.

        Args:
            player: Состояние игрока.
        """
        self._veranda_players[player.user_id] = 0

        logger.info(
            "Игрок %s попал на Веранду",
            player.username,
        )

    def is_on_veranda(self, player_id: UUID) -> bool:
        """
        Проверить, находится ли игрок на Веранде.

        Args:
            player_id: ID игрока.

        Returns:
            True, если на Веранде.
        """
        return player_id in self._veranda_players

    def get_veranda_players(self) -> list[UUID]:
        """
        Получить список ID игроков на Веранде.

        Returns:
            Список UUID.
        """
        return list(self._veranda_players.keys())

    # ========================================================================
    # ОБРАБОТКА ХОДА НА ВЕРАНДЕ
    # ========================================================================

    async def process_veranda_turn(
        self,
        player: PlayerState,
        game_id: UUID,
    ) -> dict[str, Any]:
        """
        Обработать ход игрока на Веранде.

        Игрок пропускает ход, пока не заплатит за выход.

        Args:
            player: Состояние игрока.
            game_id: ID игры.

        Returns:
            Словарь с результатом обработки.
        """
        # Увеличиваем счётчик кругов
        current_rounds = self._veranda_players.get(player.user_id, 0)
        self._veranda_players[player.user_id] = current_rounds + 1

        result = {
            "action": "veranda_turn",
            "on_veranda": True,
            "rounds_on_veranda": current_rounds + 1,
            "exit_cost": VERANDA_EXIT_COST,
            "can_pay_exit": player.can_afford(VERANDA_EXIT_COST),
            "has_veranda_card": self._has_veranda_exit_card(player),
        }

        await self._event_bus.publish(
            EventType.TURN_STARTED,
            {
                "game_id": game_id,
                "user_id": str(player.user_id),
                "on_veranda": True,
                "rounds": current_rounds + 1,
            },
        )

        return result

    # ========================================================================
    # ВЫХОД С ВЕРАНДЫ
    # ========================================================================

    def pay_exit(self, player: PlayerState) -> tuple[bool, Optional[str]]:
        """
        Заплатить за выход с Веранды.

        Args:
            player: Состояние игрока.

        Returns:
            Кортеж (успех, сообщение_об_ошибке).
        """
        if not self.is_on_veranda(player.user_id):
            return False, "Вы не на Веранде"

        if not player.can_afford(VERANDA_EXIT_COST):
            return False, f"Недостаточно средств: нужно {VERANDA_EXIT_COST}$"

        player.remove_money(VERANDA_EXIT_COST, "veranda_exit")
        self._veranda_players.pop(player.user_id, None)

        logger.info(
            "Игрок %s заплатил %d$ и покинул Веранду",
            player.username,
            VERANDA_EXIT_COST,
        )

        return True, None

    def use_veranda_card(self, player: PlayerState) -> tuple[bool, Optional[str]]:
        """
        Использовать карточку для выхода с Веранды.

        Args:
            player: Состояние игрока.

        Returns:
            Кортеж (успех, сообщение_об_ошибке).
        """
        if not self.is_on_veranda(player.user_id):
            return False, "Вы не на Веранде"

        if not self._has_veranda_exit_card(player):
            return False, "У вас нет карточки выхода с Веранды"

        # Ищем и используем карточку
        for card in player.cards:
            if not card.is_used and card.card_id == "chance_14":
                card.mark_used()
                self._veranda_players.pop(player.user_id, None)

                logger.info(
                    "Игрок %s использовал карточку и покинул Веранду",
                    player.username,
                )
                return True, None

        return False, "Не удалось найти карточку"

    def force_exit(self, player: PlayerState) -> None:
        """
        Принудительно убрать с Веранды (админ-команда).

        Args:
            player: Состояние игрока.
        """
        self._veranda_players.pop(player.user_id, None)
        logger.info(
            "Игрок %s принудительно убран с Веранды",
            player.username,
        )

    # ========================================================================
    # ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ
    # ========================================================================

    def _has_veranda_exit_card(self, player: PlayerState) -> bool:
        """
        Проверить, есть ли у игрока карточка выхода с Веранды.

        Args:
            player: Состояние игрока.

        Returns:
            True, если есть.
        """
        return any(
            not card.is_used and card.card_id == "chance_14"
            for card in player.cards
        )

    def get_veranda_status(self, player_id: UUID, player: PlayerState) -> dict[str, Any]:
        """
        Получить статус пребывания на Веранде.

        Args:
            player_id: ID игрока.
            player: Состояние игрока.

        Returns:
            Словарь со статусом.
        """
        on_veranda = self.is_on_veranda(player_id)
        rounds = self._veranda_players.get(player_id, 0)

        return {
            "on_veranda": on_veranda,
            "rounds_on_veranda": rounds,
            "exit_cost": VERANDA_EXIT_COST,
            "can_pay_exit": player.can_afford(VERANDA_EXIT_COST) if on_veranda else False,
            "has_veranda_card": self._has_veranda_exit_card(player) if on_veranda else False,
        }

    # ========================================================================
    # СОБЫТИЯ
    # ========================================================================

    async def notify_veranda_event(
        self,
        game_id: UUID,
        player: PlayerState,
        event_type: EventType,
    ) -> None:
        """
        Отправить событие о Веранде в EventBus.

        Args:
            game_id: ID игры.
            player: Состояние игрока.
            event_type: Тип события (VERANDA_ENTERED или VERANDA_EXITED).
        """
        await self._event_bus.publish(
            event_type,
            {
                "game_id": game_id,
                "user_id": str(player.user_id),
                "username": player.username,
            },
        )

    # ========================================================================
    # ОЧИСТКА
    # ========================================================================

    def remove_player(self, player_id: UUID) -> None:
        """
        Удалить игрока с Веранды (при выходе из игры).

        Args:
            player_id: ID игрока.
        """
        self._veranda_players.pop(player_id, None)

    def clear_all(self) -> None:
        """Очистить всех игроков с Веранды."""
        self._veranda_players.clear()

    def get_stats(self) -> dict:
        """
        Получить статистику менеджера Веранды.

        Returns:
            Словарь с метриками.
        """
        return {
            "players_on_veranda": len(self._veranda_players),
            "exit_cost": VERANDA_EXIT_COST,
        }