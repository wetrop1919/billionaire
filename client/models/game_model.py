"""
client/models/game_model.py

Qt-модель состояния игры для клиента.

Хранит состояние игры, полученное от сервера, и предоставляет
сигналы для обновления UI при изменении данных.

Используется в MVVM-архитектуре как Model-слой.

Python: 3.13+
"""

from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

from PySide6.QtCore import QObject, Signal, Property

logger = logging.getLogger("billionaire.client")


# ============================================================================
# МОДЕЛЬ ИГРЫ
# ============================================================================

class GameModel(QObject):
    """
    Qt-модель состояния игры.

    Хранит данные, полученные от сервера через STATE_SYNC
    и STATE_UPDATE пакеты. При изменении данных испускает сигналы
    для обновления ViewModel и View.

    Attributes:
        game_id: ID текущей игры.
        state: Состояние игры (waiting, active, finished).
        turn_number: Номер текущего хода.
        current_player_id: ID игрока, чей сейчас ход.
        my_player_id: ID текущего клиента.
    """

    # Сигналы
    game_state_changed = Signal()
    players_updated = Signal()
    properties_updated = Signal()
    turn_changed = Signal(int)  # turn_number
    current_player_changed = Signal(str)  # player_id
    game_started = Signal()
    game_finished = Signal(dict)  # results
    dice_rolled = Signal(dict)  # dice_result
    error_occurred = Signal(str)  # error_message

    def __init__(self, parent: Optional[QObject] = None) -> None:
        """
        Инициализация модели игры.

        Args:
            parent: Родительский QObject.
        """
        super().__init__(parent)

        # Основные данные
        self._game_id: Optional[UUID] = None
        self._state: str = "waiting"
        self._turn_number: int = 0
        self._current_player_id: Optional[UUID] = None
        self._my_player_id: Optional[UUID] = None

        # Игроки {user_id: player_data}
        self._players: dict[UUID, dict[str, Any]] = {}

        # Собственность {property_id: property_data}
        self._properties: dict[str, dict[str, Any]] = {}

        # Порядок ходов
        self._turn_order: list[UUID] = []

        # Информация о клетках поля
        self._board_cells: list[dict[str, Any]] = []

        # Результаты игры
        self._results: list[dict[str, Any]] = []

        # Сообщения чата (игровые события)
        self._game_messages: list[str] = []

    # ========================================================================
    # Q_PROPERTY (ДЛЯ QML)
    # ========================================================================

    def get_state(self) -> str:
        return self._state

    def get_turn_number(self) -> int:
        return self._turn_number

    def get_current_player_id(self) -> str:
        return str(self._current_player_id) if self._current_player_id else ""

    def get_my_player_id(self) -> str:
        return str(self._my_player_id) if self._my_player_id else ""

    state = Property(str, get_state, notify=game_state_changed)
    turnNumber = Property(int, get_turn_number, notify=turn_changed)
    currentPlayerId = Property(str, get_current_player_id, notify=current_player_changed)

    # ========================================================================
    # ОБНОВЛЕНИЕ ДАННЫХ
    # ========================================================================

    def update_from_sync(self, data: dict[str, Any]) -> None:
        """
        Обновить модель из данных STATE_SYNC.

        Args:
            data: Полное состояние игры от сервера.
        """
        self._game_id = UUID(data["game_id"]) if data.get("game_id") else None
        self._state = data.get("state", self._state)
        self._turn_number = data.get("turn_number", self._turn_number)

        # Обновляем текущего игрока
        current_id = data.get("current_player_id")
        if current_id:
            new_current = UUID(current_id)
            if new_current != self._current_player_id:
                self._current_player_id = new_current
                self.current_player_changed.emit(str(new_current))
        else:
            self._current_player_id = None

        # Обновляем игроков
        players_data = data.get("players", {})
        if players_data:
            self._players.clear()
            for pid_str, pdata in players_data.items():
                self._players[UUID(pid_str)] = pdata
            self.players_updated.emit()

        # Обновляем собственность
        props_data = data.get("properties", {})
        if props_data:
            self._properties = props_data
            self.properties_updated.emit()

        # Порядок ходов
        turn_order = data.get("turn_order", [])
        if turn_order:
            self._turn_order = [UUID(uid) for uid in turn_order]

        self.game_state_changed.emit()

    def update_player(self, player_id: UUID, data: dict[str, Any]) -> None:
        """
        Обновить данные одного игрока.

        Args:
            player_id: ID игрока.
            data: Новые данные.
        """
        if player_id in self._players:
            self._players[player_id].update(data)
            self.players_updated.emit()

    def update_property(self, property_id: str, data: dict[str, Any]) -> None:
        """
        Обновить данные собственности.

        Args:
            property_id: ID собственности.
            data: Новые данные.
        """
        self._properties[property_id] = data
        self.properties_updated.emit()

    def set_my_player_id(self, player_id: UUID) -> None:
        """
        Установить ID текущего клиента.

        Args:
            player_id: ID игрока-клиента.
        """
        self._my_player_id = player_id

    def add_game_message(self, message: str) -> None:
        """
        Добавить игровое сообщение.

        Args:
            message: Текст сообщения.
        """
        self._game_messages.append(message)
        if len(self._game_messages) > 200:
            self._game_messages.pop(0)

    # ========================================================================
    # ДОСТУП К ДАННЫМ
    # ========================================================================

    def get_player(self, player_id: UUID) -> Optional[dict[str, Any]]:
        """Получить данные игрока."""
        return self._players.get(player_id)

    def get_my_player(self) -> Optional[dict[str, Any]]:
        """Получить данные текущего клиента."""
        if self._my_player_id:
            return self._players.get(self._my_player_id)
        return None

    def get_property(self, property_id: str) -> Optional[dict[str, Any]]:
        """Получить данные собственности."""
        return self._properties.get(property_id)

    def get_all_players(self) -> list[dict[str, Any]]:
        """Получить список всех игроков."""
        return list(self._players.values())

    def get_all_properties(self) -> dict[str, dict[str, Any]]:
        """Получить всю собственность."""
        return dict(self._properties)

    def get_turn_order(self) -> list[UUID]:
        """Получить порядок ходов."""
        return list(self._turn_order)

    def is_my_turn(self) -> bool:
        """Проверить, мой ли сейчас ход."""
        return self._my_player_id is not None and self._my_player_id == self._current_player_id

    def get_my_money(self) -> int:
        """Получить мои деньги."""
        player = self.get_my_player()
        if player:
            return player.get("money", 0)
        return 0

    def get_my_properties(self) -> list[str]:
        """Получить список моей собственности."""
        player = self.get_my_player()
        if player:
            return player.get("properties", [])
        return []

    def get_results(self) -> list[dict[str, Any]]:
        """Получить результаты игры."""
        return list(self._results)

    def set_results(self, results: list[dict[str, Any]]) -> None:
        """
        Установить результаты игры.

        Args:
            results: Список результатов.
        """
        self._results = results
        self.game_finished.emit({"results": results})

    # ========================================================================
    # ИНФОРМАЦИЯ
    # ========================================================================

    def clear(self) -> None:
        """Очистить модель."""
        self._game_id = None
        self._state = "waiting"
        self._turn_number = 0
        self._current_player_id = None
        self._players.clear()
        self._properties.clear()
        self._turn_order.clear()
        self._results.clear()
        self._game_messages.clear()
        self.game_state_changed.emit()

    @property
    def game_id(self) -> Optional[UUID]:
        return self._game_id

    @property
    def players_count(self) -> int:
        return len(self._players)

    @property
    def properties_count(self) -> int:
        return len(self._properties)