"""
client/views/main_window.py

Главное окно клиента «Миллиардер».

Содержит все основные виджеты и управляет переключением
между экранами: меню, комнаты, игра, настройки, история.

Python: 3.13+
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from PySide6.QtWidgets import (
    QMainWindow,
    QStackedWidget,
    QStatusBar,
    QMenuBar,
    QMenu,
    QMessageBox,
)
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QAction, QIcon

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
# ИНДЕКСЫ ЭКРАНОВ
# ============================================================================

class ScreenIndex:
    """Индексы экранов в QStackedWidget."""
    MENU = 0
    ROOM_LIST = 1
    GAME = 2
    SETTINGS = 3
    HISTORY = 4
    PROFILE = 5
    ADMIN = 6


# ============================================================================
# ГЛАВНОЕ ОКНО
# ============================================================================

class MainWindow(QMainWindow):
    """
    Главное окно приложения.

    Управляет всеми экранами и координирует взаимодействие
    между ViewModels и Views.

    Usage:
        window = MainWindow(config, asset_manager, ...)
        window.show()
    """

    # Сигналы
    screen_changed = Signal(int)

    def __init__(
        self,
        config: ClientConfig,
        asset_manager: AssetManager,
        network_client: NetworkClient,
        reconnection_manager: ReconnectionManager,
        game_model: GameModel,
        player_model: PlayerModel,
        room_model: RoomModel,
        chat_model: ChatModel,
        connection_vm: ConnectionViewModel,
        room_vm: RoomViewModel,
        game_vm: GameViewModel,
        chat_vm: ChatViewModel,
        parent: Optional[QMainWindow] = None,
    ) -> None:
        """
        Инициализация главного окна.

        Args:
            config: Конфигурация клиента.
            asset_manager: Менеджер ресурсов.
            network_client: Сетевой клиент.
            reconnection_manager: Менеджер переподключения.
            game_model: Модель игры.
            player_model: Модель игрока.
            room_model: Модель комнат.
            chat_model: Модель чата.
            connection_vm: ViewModel подключения.
            room_vm: ViewModel комнат.
            game_vm: ViewModel игры.
            chat_vm: ViewModel чата.
            parent: Родительский виджет.
        """
        super().__init__(parent)

        self._config = config
        self._asset_manager = asset_manager
        self._network = network_client
        self._reconnection = reconnection_manager
        self._game_model = game_model
        self._player_model = player_model
        self._room_model = room_model
        self._chat_model = chat_model
        self._connection_vm = connection_vm
        self._room_vm = room_vm
        self._game_vm = game_vm
        self._chat_vm = chat_vm

        # Настройка окна
        self.setWindowTitle("Миллиардер")
        self.setMinimumSize(
            config.window_width,
            config.window_height,
        )

        if config.window_maximized:
            self.showMaximized()

        # Центральный стек
        self._stack = QStackedWidget()
        self.setCentralWidget(self._stack)

        # Статус-бар
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._status_bar.showMessage("Готов")

        # Создаём меню
        self._create_menu()

        # Создаём экраны
        self._create_screens()

        # Применяем стили
        self._apply_styles()

        # Подключаем сигналы
        self._connect_signals()

        # Показываем меню
        self.show_screen(ScreenIndex.MENU)

        logger.info("Главное окно инициализировано")

    # ========================================================================
    # МЕНЮ
    # ========================================================================

    def _create_menu(self) -> None:
        """Создать главное меню."""
        menu_bar = self.menuBar()

        # Меню "Игра"
        game_menu = menu_bar.addMenu("Игра")

        menu_action = game_menu.addAction("Главное меню")
        menu_action.triggered.connect(lambda: self.show_screen(ScreenIndex.MENU))

        game_menu.addSeparator()

        room_action = game_menu.addAction("Список комнат")
        room_action.triggered.connect(lambda: self.show_screen(ScreenIndex.ROOM_LIST))

        game_menu.addSeparator()

        settings_action = game_menu.addAction("Настройки")
        settings_action.triggered.connect(lambda: self.show_screen(ScreenIndex.SETTINGS))

        game_menu.addSeparator()

        exit_action = game_menu.addAction("Выход")
        exit_action.triggered.connect(self.close)

        # Меню "Профиль"
        profile_menu = menu_bar.addMenu("Профиль")

        profile_action = profile_menu.addAction("Мой профиль")
        profile_action.triggered.connect(lambda: self.show_screen(ScreenIndex.PROFILE))

        history_action = profile_menu.addAction("История игр")
        history_action.triggered.connect(lambda: self.show_screen(ScreenIndex.HISTORY))

        # Меню "Помощь"
        help_menu = menu_bar.addMenu("Помощь")

        about_action = help_menu.addAction("Об игре")
        about_action.triggered.connect(self._show_about)

    # ========================================================================
    # ЭКРАНЫ
    # ========================================================================

    def _create_screens(self) -> None:
        """Создать все экраны."""
        # Индекс 0: Главное меню
        from client.views.main_menu import MainMenuWidget
        self._menu_widget = MainMenuWidget(
            self._config,
            self._connection_vm,
            self._room_vm,
            self._player_model,
        )
        self._stack.addWidget(self._menu_widget)

        # Индекс 1: Список комнат
        from client.views.room_list import RoomListWidget
        self._room_list_widget = RoomListWidget(
            self._room_model,
            self._room_vm,
        )
        self._stack.addWidget(self._room_list_widget)

        # Индекс 2: Игровой экран
        from client.views.game_window import GameWindowWidget
        self._game_widget = GameWindowWidget(
            self._game_model,
            self._player_model,
            self._game_vm,
            self._chat_vm,
            self._asset_manager,
        )
        self._stack.addWidget(self._game_widget)

        # Индекс 3: Настройки
        from client.views.settings_dialog import SettingsWidget
        self._settings_widget = SettingsWidget(self._config)
        self._stack.addWidget(self._settings_widget)

        # Индекс 4: История
        from client.views.history_dialog import HistoryWidget
        self._history_widget = HistoryWidget(self._player_model)
        self._stack.addWidget(self._history_widget)

        # Индекс 5: Профиль
        from client.views.profile_dialog import ProfileWidget
        self._profile_widget = ProfileWidget(self._player_model)
        self._stack.addWidget(self._profile_widget)

        # Индекс 6: Админ-панель
        from client.views.admin_panel import AdminPanelWidget
        self._admin_widget = AdminPanelWidget(self._game_vm)
        self._stack.addWidget(self._admin_widget)

    # ========================================================================
    # НАВИГАЦИЯ
    # ========================================================================

    @Slot(int)
    def show_screen(self, index: int) -> None:
        """
        Переключиться на экран.

        Args:
            index: Индекс экрана (ScreenIndex).
        """
        if 0 <= index < self._stack.count():
            self._stack.setCurrentIndex(index)
            self.screen_changed.emit(index)
            logger.debug("Переключение на экран %d", index)

    def show_game_screen(self) -> None:
        """Показать игровой экран."""
        self.show_screen(ScreenIndex.GAME)

    def show_room_list(self) -> None:
        """Показать список комнат."""
        self.show_screen(ScreenIndex.ROOM_LIST)

    # ========================================================================
    # СТИЛИ
    # ========================================================================

    def _apply_styles(self) -> None:
        """Применить таблицы стилей."""
        stylesheet = self._asset_manager.load_stylesheet("main_style.qss")
        if stylesheet:
            self.setStyleSheet(stylesheet)

        # Применяем тему
        if self._config.theme == "dark":
            self.setStyleSheet(
                self.styleSheet() +
                "QMainWindow { background-color: #2b2b2b; color: #ffffff; }"
            )

    # ========================================================================
    # СИГНАЛЫ
    # ========================================================================

    def _connect_signals(self) -> None:
        """Подключить сигналы."""
        # При входе в комнату — показываем комнату
        self._room_model.room_joined.connect(
            lambda _: self.show_room_list()
        )

        # При начале игры — показываем игру
        self._game_model.game_started.connect(self.show_game_screen)

        # Обновление статус-бара
        self._connection_vm.connection_state_changed.connect(self._update_status)

    def _update_status(self, state: str) -> None:
        """
        Обновить статус-бар.

        Args:
            state: Состояние подключения.
        """
        status_map = {
            "connected": "Подключено",
            "disconnected": "Отключено",
            "connecting": "Подключение...",
            "reconnecting": "Переподключение...",
        }
        self._status_bar.showMessage(status_map.get(state, state))

    # ========================================================================
    # ДИАЛОГИ
    # ========================================================================

    def _show_about(self) -> None:
        """Показать окно "Об игре"."""
        QMessageBox.about(
            self,
            "О Миллиардере",
            "<h2>Миллиардер v1.0.0</h2>"
            "<p>Многопользовательская экономическая игра.</p>"
            "<p>Python 3.13+ | PySide6 | asyncio | PostgreSQL</p>",
        )

    # ========================================================================
    # ЗАКРЫТИЕ
    # ========================================================================

    def closeEvent(self, event) -> None:
        """
        Обработчик закрытия окна.

        Args:
            event: Событие закрытия.
        """
        # Сохраняем конфигурацию
        self._config.save()

        # Отключаемся
        if self._network.is_connected:
            import asyncio
            asyncio.ensure_future(self._network.disconnect())

        logger.info("Главное окно закрыто")
        super().closeEvent(event)