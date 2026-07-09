"""
client/viewmodels/room_viewmodel.py

ViewModel для управления комнатами.

Обрабатывает создание, поиск, вход и выход из комнат.
Связывает NetworkClient с RoomModel.

Python: 3.13+
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional
from uuid import UUID

from PySide6.QtCore import QObject, Signal, Slot, Property

from client.network.network_client import NetworkClient
from client.models.room_model import RoomModel

logger = logging.getLogger("billionaire.client")


# ============================================================================
# VIEWMODEL КОМНАТ
# ============================================================================

class RoomViewModel(QObject):
    """
    ViewModel для управления комнатами.

    Предоставляет слоты для UI (создание, вход, выход, обновление списка)
    и сигналы для обновления состояния.

    Сигналы:
        room_list_updated — список комнат обновлён
        room_joined — вошли в комнату
        room_left — вышли из комнаты
        room_created — комната создана
        error_occurred — ошибка
    """

    # Сигналы
    room_list_updated = Signal()
    room_joined = Signal()
    room_left = Signal()
    room_created = Signal()
    error_occurred = Signal(str)

    def __init__(
        self,
        network_client: NetworkClient,
        room_model: RoomModel,
        parent: Optional[QObject] = None,
    ) -> None:
        """
        Инициализация ViewModel.

        Args:
            network_client: Сетевой клиент.
            room_model: Модель комнат.
            parent: Родительский QObject.
        """
        super().__init__(parent)

        self._network = network_client
        self._room_model = room_model

    # ========================================================================
    # СЛОТЫ
    # ========================================================================

    @Slot()
    def refresh_room_list(self) -> None:
        """Обновить список комнат."""
        asyncio.ensure_future(self._do_refresh_list())

    @Slot(str, int, int, int, bool)
    def create_room(
        self,
        name: str,
        max_players: int = 4,
        turn_timeout: int = 60,
        start_money: int = 1500,
        is_private: bool = False,
        password: str = "",
    ) -> None:
        """
        Создать комнату.

        Args:
            name: Название.
            max_players: Максимум игроков.
            turn_timeout: Таймаут хода.
            start_money: Стартовый капитал.
            is_private: Приватная.
            password: Пароль.
        """
        asyncio.ensure_future(
            self._do_create_room(name, max_players, turn_timeout, start_money, is_private, password)
        )

    @Slot(str, str, bool)
    def join_room(
        self,
        room_id: str,
        password: str = "",
        as_observer: bool = False,
    ) -> None:
        """
        Войти в комнату.

        Args:
            room_id: ID комнаты.
            password: Пароль.
            as_observer: Как наблюдатель.
        """
        asyncio.ensure_future(self._do_join_room(room_id, password, as_observer))

    @Slot()
    def leave_room(self) -> None:
        """Покинуть комнату."""
        asyncio.ensure_future(self._do_leave_room())

    @Slot(str)
    def kick_player(self, player_id: str) -> None:
        """
        Выгнать игрока.

        Args:
            player_id: ID игрока.
        """
        asyncio.ensure_future(self._do_kick_player(player_id))

    @Slot()
    def start_game(self) -> None:
        """Запустить игру."""
        asyncio.ensure_future(self._do_start_game())

    # ========================================================================
    # АСИНХРОННЫЕ ОПЕРАЦИИ
    # ========================================================================

    async def _do_refresh_list(self) -> None:
        """Загрузить список комнат."""
        try:
            from shared.enums import PacketType
            response = await self._network.send_request(
                PacketType.ROOM_LIST_REQUEST,
                {
                    "filter": "all",
                    "show_private": True,
                    "show_full": False,
                },
            )

            rooms = response.get("rooms", [])
            self._room_model.set_room_list(rooms)
            self.room_list_updated.emit()

        except Exception as e:
            self.error_occurred.emit(f"Ошибка загрузки списка: {e}")

    async def _do_create_room(
        self,
        name: str,
        max_players: int,
        turn_timeout: int,
        start_money: int,
        is_private: bool,
        password: str,
    ) -> None:
        """Создать комнату."""
        try:
            from shared.enums import PacketType

            config = {
                "max_players": max_players,
                "turn_timeout": turn_timeout,
                "start_money": start_money,
                "is_private": is_private,
                "allow_spectators": True,
            }

            if password:
                config["password"] = password

            response = await self._network.send_request(
                PacketType.ROOM_CREATE_REQUEST,
                {"name": name, "config": config},
            )

            if response and "room_id" in response:
                self._room_model.join_room(response)
                self.room_created.emit()
                self.room_joined.emit()
            else:
                self.error_occurred.emit(response.get("message", "Ошибка создания комнаты"))

        except Exception as e:
            self.error_occurred.emit(f"Ошибка создания комнаты: {e}")

    async def _do_join_room(
        self,
        room_id: str,
        password: str,
        as_observer: bool,
    ) -> None:
        """Войти в комнату."""
        try:
            from shared.enums import PacketType

            payload = {
                "room_id": room_id,
                "as_observer": as_observer,
            }
            if password:
                payload["password"] = password

            response = await self._network.send_request(
                PacketType.ROOM_JOIN_REQUEST,
                payload,
            )

            if response and "room_id" in response:
                self._room_model.join_room(response)
                self.room_joined.emit()
            else:
                self.error_occurred.emit(response.get("message", "Ошибка входа в комнату"))

        except Exception as e:
            self.error_occurred.emit(f"Ошибка входа в комнату: {e}")

    async def _do_leave_room(self) -> None:
        """Покинуть комнату."""
        try:
            from shared.enums import PacketType

            room_id = self._room_model.current_room_id
            if room_id:
                await self._network.send_packet(
                    PacketType.ROOM_LEAVE,
                    {"room_id": str(room_id)},
                )

            self._room_model.leave_room()
            self.room_left.emit()

        except Exception as e:
            self.error_occurred.emit(f"Ошибка выхода из комнаты: {e}")

    async def _do_kick_player(self, player_id: str) -> None:
        """Выгнать игрока."""
        try:
            from shared.enums import PacketType

            room_id = self._room_model.current_room_id
            if room_id:
                await self._network.send_packet(
                    PacketType.ROOM_KICK_PLAYER,
                    {
                        "room_id": str(room_id),
                        "user_id": player_id,
                    },
                )

        except Exception as e:
            self.error_occurred.emit(f"Ошибка: {e}")

    async def _do_start_game(self) -> None:
        """Запустить игру."""
        try:
            from shared.enums import PacketType

            room_id = self._room_model.current_room_id
            if room_id:
                await self._network.send_packet(
                    PacketType.GAME_START_REQUEST,
                    {"room_id": str(room_id)},
                )

        except Exception as e:
            self.error_occurred.emit(f"Ошибка запуска игры: {e}")