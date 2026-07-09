"""
client/viewmodels/connection_viewmodel.py

ViewModel для подключения и аутентификации.

Управляет состоянием подключения к серверу, входа и регистрации.
Связывает NetworkClient с UI через сигналы Qt.

Python: 3.13+
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from PySide6.QtCore import QObject, Signal, Slot, Property

from client.network.network_client import NetworkClient
from client.network.reconnection_manager import ReconnectionManager
from client.models.player_model import PlayerModel

logger = logging.getLogger("billionaire.client")


# ============================================================================
# VIEWMODEL ПОДКЛЮЧЕНИЯ
# ============================================================================

class ConnectionViewModel(QObject):
    """
    ViewModel для управления подключением и аутентификацией.

    Предоставляет слоты для UI (connect, login, register, disconnect)
    и сигналы для обновления состояния.

    Сигналы:
        connection_state_changed — изменилось состояние подключения
        login_successful — вход выполнен
        login_failed — ошибка входа
        register_successful — регистрация выполнена
        register_failed — ошибка регистрации
    """

    # Сигналы
    connection_state_changed = Signal(str)  # connected, disconnected, connecting, reconnecting
    login_successful = Signal()
    login_failed = Signal(str)  # error_message
    register_successful = Signal()
    register_failed = Signal(str)

    def __init__(
        self,
        network_client: NetworkClient,
        reconnection_manager: ReconnectionManager,
        player_model: PlayerModel,
        parent: Optional[QObject] = None,
    ) -> None:
        """
        Инициализация ViewModel.

        Args:
            network_client: Сетевой клиент.
            reconnection_manager: Менеджер переподключения.
            player_model: Модель игрока.
            parent: Родительский QObject.
        """
        super().__init__(parent)

        self._network = network_client
        self._reconnection = reconnection_manager
        self._player_model = player_model

        # Состояние
        self._connection_state: str = "disconnected"
        self._host: str = "localhost"
        self._port: int = 8443
        self._use_ssl: bool = True
        self._is_connecting: bool = False

        # Настройка callback-ов переподключения
        self._reconnection.set_reconnect_callback(self._do_reconnect)
        self._reconnection.set_state_callback(self._on_reconnect_state)

    # ========================================================================
    # Q_PROPERTY
    # ========================================================================

    def get_connection_state(self) -> str:
        return self._connection_state

    def get_host(self) -> str:
        return self._host

    def set_host(self, host: str) -> None:
        self._host = host

    def get_port(self) -> int:
        return self._port

    def set_port(self, port: int) -> None:
        self._port = port

    def get_is_connected(self) -> bool:
        return self._connection_state == "connected"

    connectionState = Property(str, get_connection_state, notify=connection_state_changed)
    host = Property(str, get_host, set_host)
    port = Property(int, get_port, set_port)
    isConnected = Property(bool, get_is_connected, notify=connection_state_changed)

    # ========================================================================
    # СЛОТЫ (ВЫЗЫВАЮТСЯ ИЗ UI)
    # ========================================================================

    @Slot()
    def connect_to_server(self) -> None:
        """Подключиться к серверу."""
        if self._is_connecting:
            return

        self._is_connecting = True
        self._set_state("connecting")

        asyncio.ensure_future(self._do_connect())

    @Slot(str, str)
    def login(self, username: str, password: str) -> None:
        """
        Выполнить вход.

        Args:
            username: Имя пользователя.
            password: Пароль (открытый текст).
        """
        asyncio.ensure_future(self._do_login(username, password))

    @Slot(str, str)
    def register(self, username: str, password: str) -> None:
        """
        Зарегистрироваться.

        Args:
            username: Имя пользователя.
            password: Пароль.
        """
        asyncio.ensure_future(self._do_register(username, password))

    @Slot()
    def disconnect(self) -> None:
        """Отключиться."""
        asyncio.ensure_future(self._do_disconnect())

    # ========================================================================
    # АСИНХРОННЫЕ ОПЕРАЦИИ
    # ========================================================================

    async def _do_connect(self) -> None:
        """Выполнить подключение."""
        try:
            success = await self._network.connect(
                host=self._host,
                port=self._port,
                use_ssl=self._use_ssl,
            )

            self._is_connecting = False

            if success:
                self._set_state("connected")
                # Запускаем цикл получения
                asyncio.ensure_future(self._network.receive_loop())
            else:
                self._set_state("disconnected")
                self.login_failed.emit("Не удалось подключиться к серверу")

        except Exception as e:
            self._is_connecting = False
            self._set_state("disconnected")
            self.login_failed.emit(str(e))

    async def _do_login(self, username: str, password: str) -> None:
        """
        Выполнить вход.

        Args:
            username: Имя пользователя.
            password: Пароль.
        """
        try:
            # Хешируем пароль (Argon2id) — в реальном клиенте
            from shared.protocol.crypto import PasswordHasher
            password_hash = await PasswordHasher.hash_password(password)

            response = await self._network.login(username, password_hash)

            if response and "access_token" in response:
                self._player_model.set_profile(response)
                self.login_successful.emit()
            else:
                self.login_failed.emit(response.get("message", "Ошибка входа"))

        except Exception as e:
            self.login_failed.emit(str(e))

    async def _do_register(self, username: str, password: str) -> None:
        """
        Выполнить регистрацию.

        Args:
            username: Имя пользователя.
            password: Пароль.
        """
        try:
            from shared.protocol.crypto import PasswordHasher
            password_hash = await PasswordHasher.hash_password(password)

            response = await self._network.register(username, password_hash)

            if response and "user_id" in response:
                self.register_successful.emit()
            else:
                self.register_failed.emit(response.get("message", "Ошибка регистрации"))

        except Exception as e:
            self.register_failed.emit(str(e))

    async def _do_disconnect(self) -> None:
        """Выполнить отключение."""
        self._reconnection.cancel()
        await self._network.disconnect()
        self._player_model.logout()
        self._set_state("disconnected")

    async def _do_reconnect(self) -> bool:
        """
        Попытка переподключения (callback для ReconnectionManager).

        Returns:
            True, если подключение восстановлено.
        """
        return await self._network.connect(
            host=self._host,
            port=self._port,
            use_ssl=self._use_ssl,
        )

    async def _on_reconnect_state(self, state: str) -> None:
        """
        Обработчик изменения состояния переподключения.

        Args:
            state: Новое состояние.
        """
        self._set_state(state)

    # ========================================================================
    # ВСПОМОГАТЕЛЬНЫЕ
    # ========================================================================

    def _set_state(self, state: str) -> None:
        """
        Установить состояние подключения.

        Args:
            state: Новое состояние.
        """
        if self._connection_state != state:
            self._connection_state = state
            self.connection_state_changed.emit(state)

    def on_connection_lost(self) -> None:
        """Вызвать при потере соединения."""
        self._set_state("disconnected")
        asyncio.ensure_future(self._reconnection.on_disconnect())