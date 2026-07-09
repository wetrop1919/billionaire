"""
server/backup/crash_recovery.py

Модуль восстановления после сбоев сервера.

Обеспечивает:
- Обнаружение незавершённых игр при старте
- Восстановление состояния из последнего автосохранения
- Уведомление игроков о возможности переподключения
- Автоматическое возобновление игры после восстановления

Python: 3.13+
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional
from uuid import UUID

from database.repositories.postgresql.game_repository import GameRepository
from database.repositories.postgresql.room_repository import RoomRepository
from shared.enums import GameState, RoomState
from shared.models.game import Game
from server.game.game_manager import GameManager

logger = logging.getLogger("billionaire.server")


# ============================================================================
# ВОССТАНОВЛЕНИЕ ПОСЛЕ СБОЯ
# ============================================================================

class CrashRecovery:
    """
    Менеджер восстановления после сбоев.

    При запуске сервера проверяет наличие незавершённых игр
    и восстанавливает их состояние.

    Usage:
        recovery = CrashRecovery(game_repo, room_repo, game_manager)
        recovered = await recovery.recover_all()
    """

    # Таймаут ожидания переподключения игроков (секунд)
    RECONNECT_TIMEOUT: int = 300  # 5 минут

    def __init__(
        self,
        game_repository: GameRepository,
        room_repository: RoomRepository,
        game_manager: GameManager,
    ) -> None:
        """
        Инициализация менеджера восстановления.

        Args:
            game_repository: Репозиторий игр.
            room_repository: Репозиторий комнат.
            game_manager: Менеджер игр.
        """
        self._game_repo = game_repository
        self._room_repo = room_repository
        self._game_manager = game_manager

        # Результаты восстановления
        self._recovered_games: list[UUID] = []
        self._failed_games: list[UUID] = []

    # ========================================================================
    # ВОССТАНОВЛЕНИЕ
    # ========================================================================

    async def recover_all(self) -> dict[str, Any]:
        """
        Восстановить все незавершённые игры.

        Вызывается при старте сервера.

        Returns:
            Словарь с результатами восстановления.
        """
        logger.info("Проверка незавершённых игр для восстановления...")

        # Находим незавершённые игры
        unfinished = await self._game_repo.get_unfinished_games()

        if not unfinished:
            logger.info("Незавершённых игр не найдено")
            return {
                "recovered": 0,
                "failed": 0,
                "games": [],
            }

        logger.info(
            "Найдено %d незавершённых игр",
            len(unfinished),
        )

        for game in unfinished:
            try:
                await self._recover_game(game)
            except Exception as e:
                logger.error(
                    "Ошибка восстановления игры %s: %s",
                    str(game.game_id)[:8],
                    e,
                )
                self._failed_games.append(game.game_id)

        # Запускаем восстановленные игры
        for game_id in self._recovered_games:
            try:
                await self._game_manager.start_game(game_id)
                logger.info("Восстановленная игра %s запущена", str(game_id)[:8])
            except Exception as e:
                logger.error(
                    "Ошибка запуска восстановленной игры %s: %s",
                    str(game_id)[:8],
                    e,
                )

        logger.info(
            "Восстановление завершено: %d успешно, %d ошибок",
            len(self._recovered_games),
            len(self._failed_games),
        )

        return {
            "recovered": len(self._recovered_games),
            "failed": len(self._failed_games),
            "games": [str(gid) for gid in self._recovered_games],
            "failed_games": [str(gid) for gid in self._failed_games],
        }

    async def _recover_game(self, game: Game) -> None:
        """
        Восстановить одну игру.

        Args:
            game: Состояние игры из БД.
        """
        game_id = game.game_id

        # Загружаем полное состояние
        full_game = await self._game_repo.load_full_game_state(game_id)
        if full_game is None:
            logger.warning(
                "Не удалось загрузить полное состояние игры %s",
                str(game_id)[:8],
            )
            self._failed_games.append(game_id)
            return

        # Восстанавливаем состояние игры
        full_game.state = GameState.PAUSED  # На паузу до переподключения

        # Отмечаем всех игроков как офлайн
        for player in full_game.players.values():
            player.is_online = False

        # Сохраняем обновлённое состояние
        await self._game_repo.save_full_game_state(full_game)

        # Обновляем комнату
        await self._room_repo.update_state(full_game.room_id, RoomState.IN_GAME)

        self._recovered_games.append(game_id)

        logger.info(
            "Игра %s восстановлена (ход #%d, игроков: %d)",
            str(game_id)[:8],
            full_game.turn_number,
            full_game.players_count,
        )

    # ========================================================================
    # ПЕРЕПОДКЛЮЧЕНИЕ ИГРОКОВ
    # ========================================================================

    async def wait_for_reconnect(self, game_id: UUID) -> dict[str, Any]:
        """
        Ожидать переподключения игроков.

        Args:
            game_id: ID восстановленной игры.

        Returns:
            Статус переподключения.
        """
        game = self._game_manager.get_game(game_id)
        if game is None:
            return {"error": "Игра не найдена"}

        logger.info(
            "Ожидание переподключения игроков для игры %s (таймаут: %d сек)",
            str(game_id)[:8],
            self.RECONNECT_TIMEOUT,
        )

        # Уведомляем игроков (через систему уведомлений)
        # В реальной реализации — отправка push-уведомлений

        # Ждём переподключения
        elapsed = 0
        check_interval = 5  # Проверка каждые 5 секунд

        while elapsed < self.RECONNECT_TIMEOUT:
            game = self._game_manager.get_game(game_id)
            if game is None:
                break

            # Проверяем, все ли онлайн
            all_online = all(p.is_online for p in game.players.values() if not p.bankrupt)

            if all_online and game.online_players_count >= 2:
                logger.info(
                    "Все игроки переподключились к игре %s",
                    str(game_id)[:8],
                )
                return {
                    "status": "all_connected",
                    "online_players": game.online_players_count,
                    "total_players": game.players_count,
                }

            await asyncio.sleep(check_interval)
            elapsed += check_interval

        # Таймаут — продолжаем с теми, кто онлайн
        game = self._game_manager.get_game(game_id)
        if game:
            # Заменяем офлайн-игроков на ботов (опционально)
            game.state = GameState.ACTIVE

            logger.info(
                "Таймаут переподключения для игры %s. Онлайн: %d/%d",
                str(game_id)[:8],
                game.online_players_count,
                game.players_count,
            )

        return {
            "status": "timeout",
            "online_players": game.online_players_count if game else 0,
            "total_players": game.players_count if game else 0,
        }

    # ========================================================================
    # ИНФОРМАЦИЯ
    # ========================================================================

    def get_recovery_status(self) -> dict[str, Any]:
        """
        Получить статус восстановления.

        Returns:
            Словарь с результатами.
        """
        return {
            "recovered_games": [str(gid) for gid in self._recovered_games],
            "failed_games": [str(gid) for gid in self._failed_games],
            "total_recovered": len(self._recovered_games),
            "total_failed": len(self._failed_games),
        }

    def get_stats(self) -> dict:
        """
        Получить статистику восстановления.

        Returns:
            Словарь с метриками.
        """
        return {
            "recovered_count": len(self._recovered_games),
            "failed_count": len(self._failed_games),
            "reconnect_timeout": self.RECONNECT_TIMEOUT,
        }