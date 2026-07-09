"""
server/game/game_loop.py

Главный игровой цикл (Game Loop).

Управляет потоком игры:
- Очерёдность ходов
- Обработка действий игроков
- Обработка отключений и переподключений
- Пауза и возобновление
- Запуск и остановка игры

GameLoop не содержит игровых правил — только управление
потоком выполнения. Правила находятся в GameEngine.

Python: 3.13+
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional
from uuid import UUID

from shared.enums import GameState, EventType
from shared.models.game import Game, PlayerState
from server.event.event_bus import EventBus
from server.game.game_engine import GameEngine
from server.game.turn_manager import TurnManager
from server.game.jail_manager import JailManager
from server.game.veranda_manager import VerandaManager
from server.game.bankruptcy_manager import BankruptcyManager

logger = logging.getLogger("billionaire.game")


# ============================================================================
# ИГРОВОЙ ЦИКЛ
# ============================================================================

class GameLoop:
    """
    Главный игровой цикл.

    Управляет жизненным циклом игры: запуск, выполнение ходов,
    пауза, возобновление, завершение.

    Usage:
        loop = GameLoop(game, engine, turn_mgr, event_bus, jail_mgr, veranda_mgr, bankruptcy_mgr)
        await loop.start()
    """

    def __init__(
        self,
        game: Game,
        engine: GameEngine,
        turn_manager: TurnManager,
        event_bus: EventBus,
        jail_manager: JailManager,
        veranda_manager: VerandaManager,
        bankruptcy_manager: BankruptcyManager,
    ) -> None:
        """
        Инициализация игрового цикла.

        Args:
            game: Состояние игры.
            engine: Игровой движок.
            turn_manager: Менеджер ходов.
            event_bus: Шина событий.
            jail_manager: Менеджер тюрьмы.
            veranda_manager: Менеджер Веранды.
            bankruptcy_manager: Менеджер банкротства.
        """
        self._game = game
        self._engine = engine
        self._turn_manager = turn_manager
        self._event_bus = event_bus
        self._jail_manager = jail_manager
        self._veranda_manager = veranda_manager
        self._bankruptcy_manager = bankruptcy_manager

        # Очередь действий игроков {player_id: asyncio.Event}
        self._player_actions: dict[UUID, asyncio.Event] = {}
        self._player_action_results: dict[UUID, Any] = {}

        # Блокировка для синхронизации
        self._action_lock = asyncio.Lock()

        self._running: bool = False
        self._paused: bool = False

    # ========================================================================
    # ЖИЗНЕННЫЙ ЦИКЛ
    # ========================================================================

    async def start(self) -> None:
        """
        Запустить игровой цикл.

        Активирует игру и начинает обработку ходов.
        """
        if self._running:
            logger.warning("Игровой цикл уже запущен")
            return

        self._game.activate()
        self._running = True

        # Публикуем событие
        await self._event_bus.publish(
            EventType.GAME_STARTED,
            {
                "game_id": self._game.game_id,
                "players": [
                    {"user_id": str(p.user_id), "username": p.username}
                    for p in self._game.players.values()
                ],
            },
        )

        logger.info(
            "Игровой цикл запущен: игра=%s, игроков=%d",
            str(self._game.game_id)[:8],
            self._game.players_count,
        )

        # Запускаем основной цикл
        asyncio.create_task(self._main_loop())

    async def stop(self) -> None:
        """
        Остановить игровой цикл.

        Завершает игру и очищает состояние.
        """
        if not self._running:
            return

        self._running = False
        self._turn_manager.cancel_all_timers()

        self._game.close()

        await self._event_bus.publish(
            EventType.GAME_FINISHED,
            {
                "game_id": self._game.game_id,
                "reason": "stopped",
            },
        )

        logger.info(
            "Игровой цикл остановлен: игра=%s",
            str(self._game.game_id)[:8],
        )

    async def pause(self) -> None:
        """
        Поставить игру на паузу.

        Останавливает таймер хода и приостанавливает обработку.
        """
        if self._paused:
            return

        self._paused = True
        self._turn_manager.cancel_all_timers()

        self._game.pause()

        await self._event_bus.publish(
            EventType.GAME_PAUSED,
            {"game_id": self._game.game_id},
        )

        logger.info("Игра %s на паузе", str(self._game.game_id)[:8])

    async def resume(self) -> None:
        """
        Возобновить игру после паузы.

        Перезапускает таймер текущего хода.
        """
        if not self._paused:
            return

        self._paused = False
        self._game.resume()

        # Перезапускаем таймер для текущего игрока
        current = self._game.current_player
        if current:
            await self._turn_manager.start_turn(self._game, current)

        await self._event_bus.publish(
            EventType.GAME_RESUMED,
            {"game_id": self._game.game_id},
        )

        logger.info("Игра %s возобновлена", str(self._game.game_id)[:8])

    # ========================================================================
    # ОСНОВНОЙ ЦИКЛ
    # ========================================================================

    async def _main_loop(self) -> None:
        """
        Основной цикл обработки ходов.

        Проходит по очереди игроков и обрабатывает их ходы.
        """
        try:
            # Начинаем с первого игрока
            first_player = self._game.current_player
            if first_player:
                await self._turn_manager.start_turn(self._game, first_player)

            while self._running and self._game.is_active:
                # Ждём паузу
                while self._paused and self._running:
                    await asyncio.sleep(0.5)

                if not self._running:
                    break

                current = self._game.current_player
                if current is None:
                    break

                # Проверка на банкрота
                if current.bankrupt:
                    await self._skip_bankrupt_player(current)
                    continue

                # Проверка на отключившегося
                if not current.is_online and not current.is_bot:
                    await self._handle_offline_player(current)
                    continue

                # Обрабатываем особые состояния
                if current.in_jail:
                    await self._handle_jail_turn(current)
                elif self._veranda_manager.is_on_veranda(current.user_id):
                    await self._handle_veranda_turn(current)
                else:
                    # Обычный ход — запускаем таймер
                    await self._turn_manager.start_turn(self._game, current)

                # Ждём завершения хода
                await self._wait_for_turn_end(current)

                # Проверка завершения игры
                if self._bankruptcy_manager.check_game_end(self._game.players):
                    await self._engine._finish_game(self._game)
                    break

        except Exception as e:
            logger.error(
                "Ошибка в игровом цикле %s: %s",
                str(self._game.game_id)[:8],
                e,
            )
        finally:
            self._running = False
            logger.info(
                "Игровой цикл завершён: игра=%s",
                str(self._game.game_id)[:8],
            )

    # ========================================================================
    # ОБРАБОТКА ОСОБЫХ СИТУАЦИЙ
    # ========================================================================

    async def _handle_jail_turn(self, player: PlayerState) -> None:
        """
        Обработать ход игрока в тюрьме.

        Args:
            player: Игрок в тюрьме.
        """
        result = await self._jail_manager.process_jail_turn(
            player=player,
            game_id=self._game.game_id,
        )

        if result.get("bankrupt"):
            await self._bankruptcy_manager.declare_bankrupt(
                player=player,
                debt_amount=0,
                game_id=self._game.game_id,
                properties=self._game.properties,
            )
            await self._skip_to_next_player(player.user_id)
        else:
            # Игрок в тюрьме — переход хода
            await self._skip_to_next_player(player.user_id)

    async def _handle_veranda_turn(self, player: PlayerState) -> None:
        """
        Обработать ход игрока на Веранде.

        Args:
            player: Игрок на Веранде.
        """
        await self._veranda_manager.process_veranda_turn(
            player=player,
            game_id=self._game.game_id,
        )
        # Пропускаем ход
        await self._skip_to_next_player(player.user_id)

    async def _handle_offline_player(self, player: PlayerState) -> None:
        """
        Обработать отключившегося игрока.

        Args:
            player: Отключившийся игрок.
        """
        logger.info(
            "Игрок %s офлайн — пропуск хода",
            player.username,
        )
        # Ждём переподключения (таймаут)
        await asyncio.sleep(5.0)

        if not player.is_online:
            await self._skip_to_next_player(player.user_id)

    async def _skip_bankrupt_player(self, player: PlayerState) -> None:
        """
        Пропустить обанкротившегося игрока.

        Args:
            player: Банкрот.
        """
        await self._skip_to_next_player(player.user_id)

    async def _skip_to_next_player(self, player_id: UUID) -> None:
        """
        Перейти к следующему игроку.

        Args:
            player_id: ID текущего игрока.
        """
        next_player = self._game.next_turn()
        if next_player:
            await self._turn_manager.start_turn(self._game, next_player)

    # ========================================================================
    # ОБРАБОТКА ДЕЙСТВИЙ
    # ========================================================================

    async def process_action(
        self,
        player_id: UUID,
        action_type: str,
        action_data: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Обработать действие игрока.

        Args:
            player_id: ID игрока.
            action_type: Тип действия.
            action_data: Данные действия.

        Returns:
            Результат действия.
        """
        async with self._action_lock:
            current = self._game.current_player
            if current is None or current.user_id != player_id:
                return {"error": "Сейчас не ваш ход"}

            try:
                match action_type:
                    case "roll_dice":
                        return await self._engine.roll_dice(self._game, player_id)

                    case "buy_property":
                        return await self._engine.buy_property(
                            self._game, player_id, action_data["property_id"],
                        )

                    case "decline_property":
                        return await self._engine.decline_property(
                            self._game, player_id, action_data["property_id"],
                        )

                    case "build_house":
                        return await self._engine.build_house(
                            self._game, player_id, action_data["property_id"],
                        )

                    case "build_hotel":
                        return await self._engine.build_hotel(
                            self._game, player_id, action_data["property_id"],
                        )

                    case "mortgage":
                        return await self._engine.mortgage_property(
                            self._game, player_id, action_data["property_id"],
                        )

                    case "unmortgage":
                        return await self._engine.unmortgage_property(
                            self._game, player_id, action_data["property_id"],
                        )

                    case "pay_jail_fine":
                        success, error = self._jail_manager.pay_fine(current)
                        if success:
                            await self._jail_manager.notify_jail_event(
                                self._game.game_id, current, EventType.PLAYER_FREED,
                            )
                        return {"success": success, "error": error}

                    case "use_jail_card":
                        success, error = self._jail_manager.use_jail_card(current)
                        if success:
                            await self._jail_manager.notify_jail_event(
                                self._game.game_id, current, EventType.PLAYER_FREED,
                            )
                        return {"success": success, "error": error}

                    case "pay_veranda_exit":
                        success, error = self._veranda_manager.pay_exit(current)
                        return {"success": success, "error": error}

                    case "end_turn":
                        was_double = action_data.get("was_double", False)
                        return await self._turn_manager.end_turn(
                            self._game, player_id, was_double,
                        )

                    case _:
                        return {"error": f"Неизвестное действие: {action_type}"}

            except ValueError as e:
                return {"error": str(e)}
            except Exception as e:
                logger.error("Ошибка обработки действия: %s", e)
                return {"error": "Внутренняя ошибка сервера"}

    async def _wait_for_turn_end(self, player: PlayerState) -> None:
        """
        Ожидать завершения хода игрока.

        Args:
            player: Текущий игрок.
        """
        # Создаём событие для ожидания
        event = asyncio.Event()
        self._player_actions[player.user_id] = event

        try:
            # Ждём с таймаутом
            timeout = self._game.config.turn_timeout or 60
            await asyncio.wait_for(event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            # Таймаут — завершаем ход принудительно
            logger.warning(
                "Таймаут ожидания хода игрока %s",
                player.username,
            )
            await self._turn_manager.end_turn(self._game, player.user_id)
        finally:
            self._player_actions.pop(player.user_id, None)

    # ========================================================================
    # ОТКЛЮЧЕНИЕ И ПЕРЕПОДКЛЮЧЕНИЕ
    # ========================================================================

    async def handle_disconnect(self, player_id: UUID) -> None:
        """
        Обработать отключение игрока.

        Args:
            player_id: ID отключившегося игрока.
        """
        player = self._game.players.get(player_id)
        if player is None:
            return

        player.is_online = False

        await self._event_bus.publish(
            EventType.PLAYER_DISCONNECTED,
            {
                "game_id": self._game.game_id,
                "user_id": str(player_id),
                "username": player.username,
            },
        )

        logger.info(
            "Игрок %s отключился от игры %s",
            player.username,
            str(self._game.game_id)[:8],
        )

    async def handle_reconnect(self, player_id: UUID) -> bool:
        """
        Обработать переподключение игрока.

        Args:
            player_id: ID переподключающегося игрока.

        Returns:
            True, если переподключение успешно.
        """
        player = self._game.players.get(player_id)
        if player is None:
            return False

        player.is_online = True

        await self._event_bus.publish(
            EventType.PLAYER_RECONNECTED,
            {
                "game_id": self._game.game_id,
                "user_id": str(player_id),
                "username": player.username,
            },
        )

        logger.info(
            "Игрок %s переподключился к игре %s",
            player.username,
            str(self._game.game_id)[:8],
        )

        return True

    # ========================================================================
    # ИНФОРМАЦИЯ
    # ========================================================================

    @property
    def is_running(self) -> bool:
        """Запущен ли игровой цикл."""
        return self._running

    @property
    def is_paused(self) -> bool:
        """На паузе ли игра."""
        return self._paused

    def get_state(self) -> dict[str, Any]:
        """
        Получить состояние игрового цикла.

        Returns:
            Словарь с данными.
        """
        return {
            "game_id": str(self._game.game_id),
            "running": self._running,
            "paused": self._paused,
            "state": self._game.state.value,
            "turn_number": self._game.turn_number,
            "current_player": (
                str(self._game.current_player_id)
                if self._game.current_player_id else None
            ),
            "players_online": self._game.online_players_count,
            "active_players": self._game.active_players_count,
        }

    def get_stats(self) -> dict:
        """
        Получить статистику игрового цикла.

        Returns:
            Словарь с метриками.
        """
        return {
            "running": self._running,
            "paused": self._paused,
            "turn_number": self._game.turn_number,
            "players_total": self._game.players_count,
            "players_online": self._game.online_players_count,
            "bankrupt_players": self._game.bankrupt_players_count,
            "turn_manager": self._turn_manager.get_stats(),
        }