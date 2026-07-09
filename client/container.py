"""
client/container.py

Dependency Injection контейнер клиента.

Создаёт и связывает все компоненты клиента:
- Конфигурация и ресурсы
- Сетевой слой
- Модели данных
- ViewModels
- Главное окно

Обеспечивает централизованное управление зависимостями.

Python: 3.13+
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from client.config import ClientConfig
from client.assets.asset_manager import AssetManager

from client.network.network_client import NetworkClient
from client.network.reconnection_manager import ReconnectionManager

from client.models.game_model import GameModel
from client.models.player_model import PlayerModel
from client.models.room_model import RoomModel
from client.models.chat_model import ChatModel

from client.viewmodels.connection_viewmodel import ConnectionViewModel
from client.viewmodels.room_viewmodel import RoomViewModel
from client.viewmodels.game_viewmodel import GameViewModel
from client.viewmodels.chat_viewmodel import ChatViewModel

logger = logging.getLogger("billionaire.client")


# ============================================================================
# DI-КОНТЕЙНЕР КЛИЕНТА
# ============================================================================

@dataclass(slots=True)
class ClientContainer:
    """
    Контейнер зависимостей клиента.

    Создаёт и хранит все компоненты клиента.
    Компоненты создаются лениво при первом обращении.
    """

    # Конфигурация
    config: ClientConfig = field(default_factory=ClientConfig.load)
    asset_manager: AssetManager = field(default_factory=AssetManager)

    # Сеть
    network_client: NetworkClient = field(default_factory=NetworkClient)
    reconnection_manager: ReconnectionManager = field(default_factory=ReconnectionManager)

    # Модели
    game_model: GameModel = field(default_factory=GameModel)
    player_model: PlayerModel = field(default_factory=PlayerModel)
    room_model: RoomModel = field(default_factory=RoomModel)
    chat_model: ChatModel = field(default_factory=ChatModel)

    # ViewModels
    connection_vm: Optional[ConnectionViewModel] = None
    room_vm: Optional[RoomViewModel] = None
    game_vm: Optional[GameViewModel] = None
    chat_vm: Optional[ChatViewModel] = None

    # Главное окно
    main_window: Optional[Any] = None

    # Статус
    _initialized: bool = False

    # ========================================================================
    # ИНИЦИАЛИЗАЦИЯ
    # ========================================================================

    def init(self) -> None:
        """
        Инициализировать все компоненты клиента.

        Создаёт ViewModels и связывает их с моделями и сетью.
        """
        if self._initialized:
            logger.warning("Контейнер клиента уже инициализирован")
            return

        logger.info("Инициализация компонентов клиента...")

        # Создаём ViewModels
        self._init_viewmodels()

        self._initialized = True
        logger.info("Все компоненты клиента инициализированы")

    def _init_viewmodels(self) -> None:
        """Создать и связать ViewModels."""
        # Connection ViewModel
        self.connection_vm = ConnectionViewModel(
            network_client=self.network_client,
            reconnection_manager=self.reconnection_manager,
            player_model=self.player_model,
        )

        # Room ViewModel
        self.room_vm = RoomViewModel(
            network_client=self.network_client,
            room_model=self.room_model,
        )

        # Game ViewModel
        self.game_vm = GameViewModel(
            network_client=self.network_client,
            game_model=self.game_model,
            player_model=self.player_model,
        )

        # Chat ViewModel
        self.chat_vm = ChatViewModel(
            network_client=self.network_client,
            chat_model=self.chat_model,
        )

    def create_main_window(self) -> Any:
        """
        Создать главное окно приложения.

        Returns:
            Экземпляр MainWindow.
        """
        from client.views.main_window import MainWindow

        self.main_window = MainWindow(
            config=self.config,
            asset_manager=self.asset_manager,
            network_client=self.network_client,
            reconnection_manager=self.reconnection_manager,
            game_model=self.game_model,
            player_model=self.player_model,
            room_model=self.room_model,
            chat_model=self.chat_model,
            connection_vm=self.connection_vm,
            room_vm=self.room_vm,
            game_vm=self.game_vm,
            chat_vm=self.chat_vm,
        )

        logger.info("Главное окно создано")
        return self.main_window

    def shutdown(self) -> None:
        """Корректно завершить работу клиента."""
        logger.info("Завершение работы клиента...")

        # Сохраняем конфигурацию
        if self.config:
            self.config.save()

        self._initialized = False
        logger.info("Клиент остановлен")