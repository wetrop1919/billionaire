"""
server/game/turn_manager.py

Менеджер ходов игры.

Управляет очерёдностью ходов, таймерами и переходом
между игроками. Работает в связке с GameLoop.

Обеспечивает:
- Отслеживание текущего игрока
- Запуск и остановку таймера хода
- Автоматическое завершение хода по таймауту
- Обработку дублей (дополнительный ход)

Python: 3.13+
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional
from uuid import UUID

from shared.constants import DEFAULT_TURN_TIMEOUT
from shared.enums import EventType
from shared.models.game import Game, PlayerState
from server.event.event_bus import EventBus
from server.scheduler.scheduler import Scheduler

logger = logging.getLogger("billionaire.game")


# ============================================================================
# МЕНЕДЖЕР ХОДОВ
# ============================================================================

class TurnManager:
    """
    Менеджер ходов.

    Управляет таймерами ходов и переходами между игроками.
    Не содержит игровой логики — только управление потоком ходов.

    Usage:
        manager = TurnManager(event_bus, scheduler)
        await manager.start_turn(game)
        await manager.end_turn(game, player_id)
    """

    def __init__(
        self,
        event_bus: EventBus,
        scheduler: Scheduler,
    ) -> None:
        """
        Инициализация менеджера ходов.

        Args:
            event_bus: Шина событий.
            scheduler: Планировщик задач.
        """
        self._event_bus = event_bus
        self._scheduler = scheduler

        # Активные таймеры {game_id: (task_id, player_id)}
        self._active_timers: dict[UUID, tuple[UUID, UUID]] = {}

        # Таймаут хода по умолчанию
        self._default_turn_timeout: int = DEFAULT_TURN_TIMEOUT

    # ========================================================================
    # УПРАВЛЕНИЕ ХОДАМИ
    # ========================================================================

    async def start_turn(
        self,
        game: Game,
        player: PlayerState,
        timeout: Optional[int] = None,
    ) -> None:
        """
        Начать ход игрока.

        Запускает таймер и публикует событие TURN_STARTED.

        Args:
            game: Состояние игры.
            player: Игрок, чей ход начинается.
            timeout: Таймаут в секундах (по умолчанию из конфига).
        """
        turn_timeout = timeout or game.config.turn_timeout or self._default_turn_timeout

        # Сбрасываем действия хода
        player.reset_turn_actions()

        # Запускаем таймер
        task_id = self._scheduler.add_timeout_task(
            name=f"turn_timer_{game.game_id}_{player.user_id}",
            coroutine=lambda: self._on_turn_timeout(game.game_id, player.user_id),
            delay=turn_timeout,
        )

        self._active_timers[game.game_id] = (task_id, player.user_id)

        # Публикуем событие
        await self._event_bus.publish(
            EventType.TURN_STARTED,
            {
                "game_id": game.game_id,
                "user_id": str(player.user_id),
                "username": player.username,
                "turn_number": game.turn_number,
                "timeout": turn_timeout,
            },
        )

        logger.info(
            "Ход #%d: игрок %s (таймаут: %d сек)",
            game.turn_number,
            player.username,
            turn_timeout,
        )

    async def end_turn(
        self,
        game: Game,
        player_id: UUID,
        was_double: bool = False,
    ) -> dict[str, Any]:
        """
        Завершить ход игрока.

        Отменяет таймер и публикует событие TURN_ENDED.

        Args:
            game: Состояние игры.
            player_id: ID игрока.
            was_double: Был ли дубль (влияет на дополнительный ход).

        Returns:
            Информация о следующем игроке.
        """
        # Отменяем таймер
        self._cancel_timer(game.game_id)

        player = game.players.get(player_id)
        player_name = player.username if player else "?"

        # Публикуем событие
        await self._event_bus.publish(
            EventType.TURN_ENDED,
            {
                "game_id": game.game_id,
                "user_id": str(player_id),
                "turn_number": game.turn_number,
                "was_double": was_double,
            },
        )

        # Определяем следующего игрока
        next_player = None
        if was_double and player and not player.in_jail:
            # Дубль — игрок ходит ещё раз (если не в тюрьме)
            next_player = player
        else:
            # Переход к следующему
            next_player = game.next_turn()

        result = {
            "previous_player_id": str(player_id),
            "previous_player_name": player_name,
            "next_player_id": str(next_player.user_id) if next_player else None,
            "next_player_name": next_player.username if next_player else None,
            "turn_number": game.turn_number,
            "extra_turn": was_double and not (player and player.in_jail),
        }

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

        logger.info(
            "Ход #%d завершён: %s → %s%s",
            game.turn_number,
            player_name,
            next_player.username if next_player else "конец",
            " (дубль!)" if was_double else "",
        )

        return result

    # ========================================================================
    # ТАЙМЕР
    # ========================================================================

    async def _on_turn_timeout(
        self,
        game_id: UUID,
        player_id: UUID,
    ) -> None:
        """
        Обработчик таймаута хода.

        Автоматически завершает ход игрока.

        Args:
            game_id: ID игры.
            player_id: ID игрока.
        """
        # Проверяем, актуален ли ещё таймер
        timer_data = self._active_timers.get(game_id)
        if timer_data is None:
            return

        task_id, current_player = timer_data
        if current_player != player_id:
            return

        # Удаляем таймер
        self._active_timers.pop(game_id, None)

        # Публикуем событие таймаута
        await self._event_bus.publish(
            EventType.TURN_TIMEOUT,
            {
                "game_id": game_id,
                "user_id": str(player_id),
            },
        )

        logger.warning(
            "Таймаут хода: игра=%s, игрок=%s",
            str(game_id)[:8],
            str(player_id)[:8],
        )

    def _cancel_timer(self, game_id: UUID) -> None:
        """
        Отменить таймер хода.

        Args:
            game_id: ID игры.
        """
        timer_data = self._active_timers.pop(game_id, None)
        if timer_data:
            task_id, _ = timer_data
            self._scheduler.cancel_task(task_id)

    def cancel_all_timers(self) -> None:
        """Отменить все активные таймеры."""
        for game_id in list(self._active_timers.keys()):
            self._cancel_timer(game_id)

    # ========================================================================
    # ИНФОРМАЦИЯ
    # ========================================================================

    def get_current_player(self, game: Game) -> Optional[PlayerState]:
        """
        Получить текущего игрока.

        Args:
            game: Состояние игры.

        Returns:
            Текущий игрок или None.
        """
        return game.current_player

    def get_turn_info(self, game: Game) -> dict[str, Any]:
        """
        Получить информацию о текущем ходе.

        Args:
            game: Состояние игры.

        Returns:
            Словарь с данными хода.
        """
        current = game.current_player
        timer_data = self._active_timers.get(game.game_id)

        return {
            "turn_number": game.turn_number,
            "current_player_id": str(current.user_id) if current else None,
            "current_player_name": current.username if current else None,
            "has_active_timer": timer_data is not None,
            "players_order": [str(uid) for uid in game.turn_order],
            "current_index": game.current_turn_index,
        }

    def get_stats(self) -> dict:
        """
        Получить статистику менеджера ходов.

        Returns:
            Словарь с метриками.
        """
        return {
            "active_timers": len(self._active_timers),
            "default_turn_timeout": self._default_turn_timeout,
        }