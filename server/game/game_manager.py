"""
server/game/game_manager.py

Менеджер игровых сессий.

Управляет жизненным циклом всех игр на сервере:
- Создание игры из комнаты
- Запуск, пауза, возобновление, завершение
- Обработка действий игроков
- Сохранение и восстановление состояния

Координирует работу GameEngine, GameLoop и репозиториев.

Python: 3.13+
"""

from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

from database.repositories.postgresql.game_repository import GameRepository
from database.repositories.postgresql.room_repository import RoomRepository
from shared.enums import RoomState, GameState, EventType
from shared.models.game import Game, GameConfig, PlayerState
from shared.models.position import Board
from shared.models.property import Property
from shared.models.card import Card, CardDeck
from shared.models.room import Room
from shared.game_rules import GameRules
from server.event.event_bus import EventBus
from server.game.game_engine import GameEngine
from server.game.game_loop import GameLoop
from server.game.turn_manager import TurnManager
from server.game.jail_manager import JailManager
from server.game.veranda_manager import VerandaManager
from server.game.bankruptcy_manager import BankruptcyManager
from server.game.auction_manager import AuctionManager
from server.game.trade_manager import TradeManager
from server.game.undo_stack import UndoStack

logger = logging.getLogger("billionaire.game")


# ============================================================================
# ЦВЕТА ИГРОКОВ
# ============================================================================

PLAYER_COLORS: list[str] = [
    "#e74c3c",  # Красный
    "#3498db",  # Синий
    "#2ecc71",  # Зелёный
    "#f39c12",  # Оранжевый
    "#9b59b6",  # Фиолетовый
    "#1abc9c",  # Бирюзовый
    "#e67e22",  # Тёмно-оранжевый
    "#f1c40f",  # Жёлтый
]


# ============================================================================
# МЕНЕДЖЕР ИГР
# ============================================================================

class GameManager:
    """
    Менеджер всех игровых сессий на сервере.

    Управляет созданием, запуском и контролем игр.
    Связывает комнаты с игровыми сессиями.

    Usage:
        manager = GameManager(game_repo, room_repo, event_bus, ...)
        game = await manager.create_game(room, players)
        await manager.start_game(game_id)
    """

    def __init__(
        self,
        game_repository: GameRepository,
        room_repository: RoomRepository,
        event_bus: EventBus,
        engine: GameEngine,
        turn_manager: TurnManager,
        jail_manager: JailManager,
        veranda_manager: VerandaManager,
        bankruptcy_manager: BankruptcyManager,
        auction_manager: AuctionManager,
        trade_manager: TradeManager,
        undo_stack: UndoStack,
        property_defs: dict[str, Property],
        chance_cards: list[Card],
        fund_cards: list[Card],
    ) -> None:
        """
        Инициализация менеджера игр.

        Args:
            game_repository: Репозиторий игр.
            room_repository: Репозиторий комнат.
            event_bus: Шина событий.
            engine: Игровой движок.
            turn_manager: Менеджер ходов.
            jail_manager: Менеджер тюрьмы.
            veranda_manager: Менеджер Веранды.
            bankruptcy_manager: Менеджер банкротства.
            auction_manager: Менеджер аукционов.
            trade_manager: Менеджер торговли.
            undo_stack: Стек отмены.
            property_defs: Описания всей собственности.
            chance_cards: Карточки «Шанс».
            fund_cards: Карточки «Фонд».
        """
        self._game_repo = game_repository
        self._room_repo = room_repository
        self._event_bus = event_bus
        self._engine = engine
        self._turn_manager = turn_manager
        self._jail_manager = jail_manager
        self._veranda_manager = veranda_manager
        self._bankruptcy_manager = bankruptcy_manager
        self._auction_manager = auction_manager
        self._trade_manager = trade_manager
        self._undo_stack = undo_stack

        self._property_defs = property_defs
        self._chance_cards = chance_cards
        self._fund_cards = fund_cards

        # Активные игры {game_id: GameLoop}
        self._active_games: dict[UUID, GameLoop] = {}

        # Состояния игр {game_id: Game}
        self._game_states: dict[UUID, Game] = {}

    # ========================================================================
    # СОЗДАНИЕ И ЗАПУСК ИГРЫ
    # ========================================================================

    async def create_game(
        self,
        room: Room,
        players: list[PlayerState],
        board: Board,
        game_rules: Optional[GameRules] = None,
    ) -> Game:
        """
        Создать новую игровую сессию.

        Args:
            room: Комната, из которой создаётся игра.
            players: Список состояний игроков.
            board: Игровое поле.
            game_rules: Правила игры (из конфига комнаты).

        Returns:
            Созданная игра.
        """
        # Создаём конфигурацию
        config = GameConfig(
            start_money=room.config.start_money,
            start_bonus=room.config.start_bonus,
            max_players=room.config.max_players,
            turn_timeout=room.config.turn_timeout,
            game_rules=game_rules or GameRules.defaults(),
        )

        # Создаём колоды
        chance_deck = CardDeck.create_from_list(
            card_type=self._chance_cards[0].card_type if self._chance_cards else None,
            cards_data=[c.to_dict() for c in self._chance_cards],
        )
        fund_deck = CardDeck.create_from_list(
            card_type=self._fund_cards[0].card_type if self._fund_cards else None,
            cards_data=[c.to_dict() for c in self._fund_cards],
        )

        # Создаём игру
        game = Game.create(
            room_id=room.room_id,
            config=config,
            board=board,
            chance_deck=chance_deck,
            fund_deck=fund_deck,
        )

        # Добавляем игроков
        for i, player in enumerate(players):
            player.color = PLAYER_COLORS[i % len(PLAYER_COLORS)]
            game.add_player(player)

        # Инициализируем игровой движок
        self._engine.initialize_game(
            game=game,
            property_defs=self._property_defs,
            chance_cards=self._chance_cards,
            fund_cards=self._fund_cards,
        )

        # Сохраняем в БД
        await self._game_repo.save(game)
        await self._game_repo.save_all_players(game.game_id, game.players)
        await self._game_repo.save_all_properties(game.game_id, game.properties)

        # Обновляем состояние комнаты
        await self._room_repo.update_state(room.room_id, RoomState.IN_GAME)

        self._game_states[game.game_id] = game

        logger.info(
            "Игра создана: %s (комната: %s, игроков: %d)",
            str(game.game_id)[:8],
            room.name,
            game.players_count,
        )

        return game

    async def start_game(self, game_id: UUID) -> GameLoop:
        """
        Запустить игру.

        Args:
            game_id: ID игры.

        Returns:
            Игровой цикл.

        Raises:
            ValueError: Если игра не найдена.
        """
        game = self._game_states.get(game_id)
        if game is None:
            # Пробуем загрузить из БД
            game = await self._game_repo.load_full_game_state(game_id)
            if game is None:
                raise ValueError(f"Игра не найдена: {game_id}")
            self._game_states[game_id] = game

        # Создаём игровой цикл
        loop = GameLoop(
            game=game,
            engine=self._engine,
            turn_manager=self._turn_manager,
            event_bus=self._event_bus,
            jail_manager=self._jail_manager,
            veranda_manager=self._veranda_manager,
            bankruptcy_manager=self._bankruptcy_manager,
        )

        self._active_games[game_id] = loop

        # Запускаем цикл
        await loop.start()

        logger.info("Игра %s запущена", str(game_id)[:8])

        return loop

    # ========================================================================
    # УПРАВЛЕНИЕ ИГРОЙ
    # ========================================================================

    async def pause_game(self, game_id: UUID) -> bool:
        """
        Поставить игру на паузу.

        Args:
            game_id: ID игры.

        Returns:
            True, если пауза активирована.
        """
        loop = self._active_games.get(game_id)
        if loop is None:
            return False

        await loop.pause()
        return True

    async def resume_game(self, game_id: UUID) -> bool:
        """
        Возобновить игру.

        Args:
            game_id: ID игры.

        Returns:
            True, если игра возобновлена.
        """
        loop = self._active_games.get(game_id)
        if loop is None:
            return False

        await loop.resume()
        return True

    async def stop_game(self, game_id: UUID) -> bool:
        """
        Остановить игру.

        Args:
            game_id: ID игры.

        Returns:
            True, если игра остановлена.
        """
        loop = self._active_games.get(game_id)
        if loop is None:
            return False

        await loop.stop()

        # Сохраняем финальное состояние
        game = self._game_states.get(game_id)
        if game:
            await self._game_repo.save_full_game_state(game)
            await self._game_repo.update_game_state(game_id, GameState.FINISHED)

            # Обновляем комнату
            await self._room_repo.update_state(game.room_id, RoomState.FINISHED)

        # Очищаем
        self._active_games.pop(game_id, None)
        self._game_states.pop(game_id, None)

        logger.info("Игра %s остановлена", str(game_id)[:8])
        return True

    # ========================================================================
    # ОБРАБОТКА ДЕЙСТВИЙ
    # ========================================================================

    async def process_action(
        self,
        game_id: UUID,
        player_id: UUID,
        action_type: str,
        action_data: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Обработать действие игрока.

        Args:
            game_id: ID игры.
            player_id: ID игрока.
            action_type: Тип действия.
            action_data: Данные действия.

        Returns:
            Результат действия.
        """
        loop = self._active_games.get(game_id)
        if loop is None:
            return {"error": "Игра не активна"}

        return await loop.process_action(player_id, action_type, action_data)

    # ========================================================================
    # ОТКЛЮЧЕНИЕ / ПЕРЕПОДКЛЮЧЕНИЕ
    # ========================================================================

    async def handle_player_disconnect(
        self,
        game_id: UUID,
        player_id: UUID,
    ) -> None:
        """
        Обработать отключение игрока.

        Args:
            game_id: ID игры.
            player_id: ID игрока.
        """
        loop = self._active_games.get(game_id)
        if loop:
            await loop.handle_disconnect(player_id)

    async def handle_player_reconnect(
        self,
        game_id: UUID,
        player_id: UUID,
    ) -> Optional[dict[str, Any]]:
        """
        Обработать переподключение игрока.

        Args:
            game_id: ID игры.
            player_id: ID игрока.

        Returns:
            Состояние игры для синхронизации или None.
        """
        loop = self._active_games.get(game_id)
        if loop is None:
            return None

        success = await loop.handle_reconnect(player_id)
        if not success:
            return None

        game = self._game_states.get(game_id)
        if game is None:
            return None

        return self._engine.get_game_state_for_player(game, player_id)

    # ========================================================================
    # СОХРАНЕНИЕ И ВОССТАНОВЛЕНИЕ
    # ========================================================================

    async def save_game(self, game_id: UUID) -> bool:
        """
        Сохранить состояние игры в БД.

        Args:
            game_id: ID игры.

        Returns:
            True, если сохранение выполнено.
        """
        game = self._game_states.get(game_id)
        if game is None:
            return False

        await self._game_repo.save_full_game_state(game)
        logger.debug("Игра %s сохранена", str(game_id)[:8])
        return True

    async def save_all_active_games(self) -> int:
        """
        Сохранить все активные игры.

        Returns:
            Количество сохранённых игр.
        """
        count = 0
        for game_id in list(self._active_games.keys()):
            if await self.save_game(game_id):
                count += 1

        if count > 0:
            logger.info("Сохранено %d активных игр", count)

        return count

    async def restore_game(self, game_id: UUID) -> Optional[Game]:
        """
        Восстановить игру из БД.

        Args:
            game_id: ID игры.

        Returns:
            Восстановленная игра или None.
        """
        game = await self._game_repo.load_full_game_state(game_id)
        if game is None:
            return None

        self._game_states[game_id] = game
        logger.info("Игра %s восстановлена из БД", str(game_id)[:8])
        return game

    # ========================================================================
    # ИНФОРМАЦИЯ
    # ========================================================================

    def get_game(self, game_id: UUID) -> Optional[Game]:
        """
        Получить состояние игры.

        Args:
            game_id: ID игры.

        Returns:
            Игра или None.
        """
        return self._game_states.get(game_id)

    def get_game_loop(self, game_id: UUID) -> Optional[GameLoop]:
        """
        Получить игровой цикл.

        Args:
            game_id: ID игры.

        Returns:
            GameLoop или None.
        """
        return self._active_games.get(game_id)

    def is_game_active(self, game_id: UUID) -> bool:
        """
        Проверить, активна ли игра.

        Args:
            game_id: ID игры.

        Returns:
            True, если игра запущена.
        """
        return game_id in self._active_games

    def get_player_game(self, player_id: UUID) -> Optional[UUID]:
        """
        Найти игру, в которой участвует игрок.

        Args:
            player_id: ID игрока.

        Returns:
            ID игры или None.
        """
        for game_id, game in self._game_states.items():
            if player_id in game.players:
                return game_id
        return None

    def get_active_games_count(self) -> int:
        """Количество активных игр."""
        return len(self._active_games)

    def get_stats(self) -> dict:
        """
        Получить статистику менеджера игр.

        Returns:
            Словарь с метриками.
        """
        return {
            "active_games": len(self._active_games),
            "loaded_games": len(self._game_states),
            "paused_games": sum(
                1 for loop in self._active_games.values()
                if loop.is_paused
            ),
        }