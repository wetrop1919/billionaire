"""
client/models/room_model.py

Qt-модель данных комнат для клиента.

Хранит список доступных комнат и информацию о текущей комнате,
в которой находится игрок.

Python: 3.13+
"""

from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

from PySide6.QtCore import QObject, Signal, Property

logger = logging.getLogger("billionaire.client")


# ============================================================================
# МОДЕЛЬ КОМНАТЫ
# ============================================================================

class RoomModel(QObject):
    """
    Qt-модель данных комнат.

    Хранит список доступных комнат, информацию о текущей комнате
    и её настройках. Обновляется при получении данных от сервера.

    Сигналы:
        room_list_updated — список комнат изменился
        room_joined — игрок вошёл в комнату
        room_left — игрок покинул комнату
        room_settings_changed — настройки комнаты изменены
        players_updated — состав игроков изменился
    """

    # Сигналы
    room_list_updated = Signal()
    room_joined = Signal(str)  # room_id
    room_left = Signal()
    room_settings_changed = Signal()
    players_updated = Signal()
    game_started_in_room = Signal(str)  # game_id
    error_occurred = Signal(str)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        """
        Инициализация модели комнат.

        Args:
            parent: Родительский QObject.
        """
        super().__init__(parent)

        # Список комнат
        self._rooms: list[dict[str, Any]] = []

        # Текущая комната
        self._current_room_id: Optional[UUID] = None
        self._current_room_name: str = ""
        self._current_room_owner_id: Optional[UUID] = None
        self._current_room_state: str = ""
        self._is_in_room: bool = False

        # Игроки в комнате
        self._players: list[dict[str, Any]] = []
        self._observers: list[dict[str, Any]] = []

        # Настройки
        self._max_players: int = 4
        self._turn_timeout: int = 60
        self._is_private: bool = False

        # Фильтры
        self._filter_state: str = "all"
        self._show_private: bool = True
        self._show_full: bool = False

    # ========================================================================
    # Q_PROPERTY
    # ========================================================================

    def get_current_room_name(self) -> str:
        return self._current_room_name

    def get_is_in_room(self) -> bool:
        return self._is_in_room

    def get_players_count(self) -> int:
        return len(self._players)

    def get_max_players(self) -> int:
        return self._max_players

    currentRoomName = Property(str, get_current_room_name, notify=room_joined)
    isInRoom = Property(bool, get_is_in_room, notify=room_joined)
    playersCount = Property(int, get_players_count, notify=players_updated)
    maxPlayers = Property(int, get_max_players, notify=room_settings_changed)

    # ========================================================================
    # ОБНОВЛЕНИЕ ДАННЫХ
    # ========================================================================

    def set_room_list(self, rooms: list[dict[str, Any]]) -> None:
        """
        Обновить список комнат.

        Args:
            rooms: Список данных комнат от сервера.
        """
        self._rooms = rooms
        self.room_list_updated.emit()

    def join_room(self, room_data: dict[str, Any]) -> None:
        """
        Войти в комнату.

        Args:
            room_data: Данные комнаты от сервера.
        """
        self._current_room_id = UUID(room_data["room_id"]) if room_data.get("room_id") else None
        self._current_room_name = room_data.get("name", "")
        self._current_room_owner_id = UUID(room_data["owner_id"]) if room_data.get("owner_id") else None
        self._current_room_state = room_data.get("state", "waiting")
        self._is_in_room = True

        # Обновляем игроков
        players = room_data.get("players", [])
        self._players = players if isinstance(players, list) else list(players.values())
        self._observers = room_data.get("observers", [])

        # Настройки
        config = room_data.get("config", {})
        self._max_players = config.get("max_players", self._max_players)
        self._turn_timeout = config.get("turn_timeout", self._turn_timeout)
        self._is_private = config.get("is_private", self._is_private)

        self.room_joined.emit(str(self._current_room_id) if self._current_room_id else "")

    def leave_room(self) -> None:
        """Покинуть комнату."""
        self._current_room_id = None
        self._current_room_name = ""
        self._current_room_owner_id = None
        self._current_room_state = ""
        self._is_in_room = False
        self._players.clear()
        self._observers.clear()

        self.room_left.emit()

    def update_players(self, players: list[dict[str, Any]]) -> None:
        """
        Обновить список игроков в комнате.

        Args:
            players: Список игроков.
        """
        self._players = players
        self.players_updated.emit()

    def add_player(self, player: dict[str, Any]) -> None:
        """
        Добавить игрока.

        Args:
            player: Данные игрока.
        """
        self._players.append(player)
        self.players_updated.emit()

    def remove_player(self, user_id: UUID) -> None:
        """
        Удалить игрока.

        Args:
            user_id: ID игрока.
        """
        self._players = [p for p in self._players if UUID(p["user_id"]) != user_id]
        self.players_updated.emit()

    def update_settings(self, settings: dict[str, Any]) -> None:
        """
        Обновить настройки комнаты.

        Args:
            settings: Новые настройки.
        """
        self._max_players = settings.get("max_players", self._max_players)
        self._turn_timeout = settings.get("turn_timeout", self._turn_timeout)
        self._is_private = settings.get("is_private", self._is_private)
        self.room_settings_changed.emit()

    # ========================================================================
    # ФИЛЬТРЫ
    # ========================================================================

    def set_filter(self, state: str = "all", show_private: bool = True, show_full: bool = False) -> None:
        """
        Установить фильтры списка комнат.

        Args:
            state: Фильтр по состоянию (all, waiting, in_game, finished).
            show_private: Показывать приватные.
            show_full: Показывать заполненные.
        """
        self._filter_state = state
        self._show_private = show_private
        self._show_full = show_full

    def get_filtered_rooms(self) -> list[dict[str, Any]]:
        """
        Получить отфильтрованный список комнат.

        Returns:
            Список комнат.
        """
        result = self._rooms

        # Фильтр по состоянию
        if self._filter_state != "all":
            result = [r for r in result if r.get("state") == self._filter_state]

        # Фильтр приватных
        if not self._show_private:
            result = [r for r in result if not r.get("is_private", False)]

        # Фильтр заполненных
        if not self._show_full:
            result = [r for r in result if not r.get("is_full", False)]

        return result

    # ========================================================================
    # ДОСТУП К ДАННЫМ
    # ========================================================================

    @property
    def current_room_id(self) -> Optional[UUID]:
        return self._current_room_id

    @property
    def is_in_room(self) -> bool:
        return self._is_in_room

    @property
    def is_owner(self) -> bool:
        """Проверить, является ли текущий игрок владельцем."""
        # Проверяется извне, сравнивая с player_model.user_id
        return False

    @property
    def can_start_game(self) -> bool:
        """Можно ли начать игру (минимум 2 игрока)."""
        return len(self._players) >= 2 and self._is_in_room

    def get_players(self) -> list[dict[str, Any]]:
        return list(self._players)

    def get_rooms(self) -> list[dict[str, Any]]:
        return self.get_filtered_rooms()

    def clear(self) -> None:
        """Очистить модель."""
        self.leave_room()
        self._rooms.clear()
        self.room_list_updated.emit()