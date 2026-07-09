"""
server/backup/autosave.py

Менеджер автоматического сохранения игр.

Обеспечивает:
- Периодическое сохранение состояния активных игр в БД
- Сохранение при критических событиях (покупка, банкротство)
- Восстановление состояния из последнего сохранения

Python: 3.13+
"""

from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

from database.repositories.postgresql.game_repository import GameRepository
from shared.models.game import Game

logger = logging.getLogger("billionaire.server")


# ============================================================================
# МЕНЕДЖЕР АВТОСОХРАНЕНИЯ
# ============================================================================

class AutosaveManager:
    """
    Менеджер автоматического сохранения игр.

    Периодически сохраняет состояние всех активных игр в БД
    для предотвращения потери данных при сбоях.

    Usage:
        manager = AutosaveManager(game_repo)
        await manager.save_all_active(games_dict)
        game = await manager.load_latest(game_id)
    """

    def __init__(self, game_repository: GameRepository) -> None:
        """
        Инициализация менеджера автосохранения.

        Args:
            game_repository: Репозиторий игр.
        """
        self._game_repo = game_repository

        # Счётчик сохранений
        self._save_count: int = 0
        self._last_save_time: float = 0.0

    # ========================================================================
    # СОХРАНЕНИЕ
    # ========================================================================

    async def save_game(self, game: Game) -> bool:
        """
        Сохранить состояние одной игры.

        Args:
            game: Состояние игры.

        Returns:
            True, если сохранение выполнено.
        """
        try:
            await self._game_repo.save_full_game_state(game)
            logger.debug("Автосохранение игры %s выполнено", str(game.game_id)[:8])
            return True
        except Exception as e:
            logger.error(
                "Ошибка автосохранения игры %s: %s",
                str(game.game_id)[:8],
                e,
            )
            return False

    async def save_all_active(
        self,
        games: dict[UUID, Game],
    ) -> int:
        """
        Сохранить все активные игры.

        Args:
            games: Словарь {game_id: Game} активных игр.

        Returns:
            Количество успешно сохранённых игр.
        """
        import time

        count = 0
        for game_id, game in games.items():
            if game.is_active:
                if await self.save_game(game):
                    count += 1

        self._save_count += 1
        self._last_save_time = time.time()

        if count > 0:
            logger.info(
                "Автосохранение #%d: сохранено %d игр",
                self._save_count,
                count,
            )

        return count

    # ========================================================================
    # ВОССТАНОВЛЕНИЕ
    # ========================================================================

    async def load_latest(self, game_id: UUID) -> Optional[Game]:
        """
        Загрузить последнее сохранённое состояние игры.

        Args:
            game_id: ID игры.

        Returns:
            Состояние игры или None.
        """
        try:
            game = await self._game_repo.load_full_game_state(game_id)
            if game:
                logger.info(
                    "Загружено сохранение игры %s (ход #%d)",
                    str(game_id)[:8],
                    game.turn_number,
                )
            return game
        except Exception as e:
            logger.error(
                "Ошибка загрузки сохранения игры %s: %s",
                str(game_id)[:8],
                e,
            )
            return None

    async def restore_game_state(
        self,
        game_id: UUID,
        target: Game,
    ) -> bool:
        """
        Восстановить состояние игры из БД.

        Args:
            game_id: ID игры.
            target: Объект игры для восстановления.

        Returns:
            True, если восстановление выполнено.
        """
        saved = await self.load_latest(game_id)
        if saved is None:
            return False

        # Копируем состояние
        target.players = saved.players
        target.properties = saved.properties
        target.current_turn_index = saved.current_turn_index
        target.turn_number = saved.turn_number
        target.free_parking_money = saved.free_parking_money
        target.state = saved.state

        logger.info(
            "Состояние игры %s восстановлено (ход #%d)",
            str(game_id)[:8],
            saved.turn_number,
        )

        return True

    # ========================================================================
    # ИНФОРМАЦИЯ
    # ========================================================================

    @property
    def save_count(self) -> int:
        """Количество выполненных сохранений."""
        return self._save_count

    def get_stats(self) -> dict:
        """
        Получить статистику автосохранения.

        Returns:
            Словарь с метриками.
        """
        import time

        return {
            "save_count": self._save_count,
            "last_save_time": self._last_save_time,
            "seconds_since_last_save": (
                time.time() - self._last_save_time
                if self._last_save_time > 0 else -1
            ),
        }