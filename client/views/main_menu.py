"""
client/views/main_menu.py

Виджет главного меню.

Содержит кнопки для подключения, входа, регистрации
и перехода к другим экранам.

Python: 3.13+
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QLineEdit,
    QGroupBox,
    QFormLayout,
    QMessageBox,
    QSpacerItem,
    QSizePolicy,
)
from PySide6.QtCore import Qt, Signal, Slot

from client.config import ClientConfig
from client.viewmodels.connection_viewmodel import ConnectionViewModel
from client.viewmodels.room_viewmodel import RoomViewModel
from client.models.player_model import PlayerModel

logger = logging.getLogger("billionaire.client")


# ============================================================================
# ГЛАВНОЕ МЕНЮ
# ============================================================================

class MainMenuWidget(QWidget):
    """
    Виджет главного меню.

    Содержит форму подключения, входа/регистрации
    и основные кнопки навигации.

    Сигналы:
        play_clicked — нажата кнопка "Играть"
    """

    play_clicked = Signal()

    def __init__(
        self,
        config: ClientConfig,
        connection_vm: ConnectionViewModel,
        room_vm: RoomViewModel,
        player_model: PlayerModel,
        parent: Optional[QWidget] = None,
    ) -> None:
        """
        Инициализация главного меню.

        Args:
            config: Конфигурация клиента.
            connection_vm: ViewModel подключения.
            room_vm: ViewModel комнат.
            player_model: Модель игрока.
            parent: Родительский виджет.
        """
        super().__init__(parent)

        self._config = config
        self._connection_vm = connection_vm
        self._room_vm = room_vm
        self._player_model = player_model

        # Создаём UI
        self._create_ui()

        # Подключаем сигналы
        self._connect_signals()

    # ========================================================================
    # UI
    # ========================================================================

    def _create_ui(self) -> None:
        """Создать интерфейс."""
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(20)
        main_layout.setContentsMargins(50, 50, 50, 50)

        # Заголовок
        title = QLabel("🎩 Миллиардер")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 32px; font-weight: bold; padding: 20px;")
        main_layout.addWidget(title)

        # Вертикальный спейсер
        main_layout.addSpacerItem(
            QSpacerItem(0, 20, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)
        )

        # Группа подключения
        self._create_connection_group(main_layout)

        # Группа аутентификации
        self._create_auth_group(main_layout)

        # Кнопка "Играть"
        self._play_button = QPushButton("🎮 Играть")
        self._play_button.setMinimumHeight(50)
        self._play_button.setStyleSheet("font-size: 18px; font-weight: bold;")
        self._play_button.setEnabled(False)
        self._play_button.clicked.connect(self._on_play)
        main_layout.addWidget(self._play_button)

        # Нижний спейсер
        main_layout.addSpacerItem(
            QSpacerItem(0, 20, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)
        )

        # Статус
        self._status_label = QLabel("Не подключены")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_label.setStyleSheet("color: #888;")
        main_layout.addWidget(self._status_label)

    def _create_connection_group(self, layout: QVBoxLayout) -> None:
        """
        Создать группу подключения.

        Args:
            layout: Родительский layout.
        """
        group = QGroupBox("Подключение")
        form = QFormLayout(group)

        # Хост
        self._host_input = QLineEdit(self._config.server_host)
        self._host_input.setPlaceholderText("localhost")
        form.addRow("Сервер:", self._host_input)

        # Порт
        self._port_input = QLineEdit(str(self._config.server_port))
        self._port_input.setPlaceholderText("8443")
        form.addRow("Порт:", self._port_input)

        # Кнопка подключения
        self._connect_button = QPushButton("Подключиться")
        self._connect_button.clicked.connect(self._on_connect)
        form.addRow(self._connect_button)

        layout.addWidget(group)

    def _create_auth_group(self, layout: QVBoxLayout) -> None:
        """
        Создать группу аутентификации.

        Args:
            layout: Родительский layout.
        """
        group = QGroupBox("Вход / Регистрация")
        form = QFormLayout(group)

        # Имя пользователя
        self._username_input = QLineEdit()
        self._username_input.setPlaceholderText("Введите имя")
        form.addRow("Имя:", self._username_input)

        # Пароль
        self._password_input = QLineEdit()
        self._password_input.setPlaceholderText("Введите пароль")
        self._password_input.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Пароль:", self._password_input)

        # Кнопки
        buttons_layout = QHBoxLayout()

        self._login_button = QPushButton("Войти")
        self._login_button.clicked.connect(self._on_login)
        self._login_button.setEnabled(False)
        buttons_layout.addWidget(self._login_button)

        self._register_button = QPushButton("Регистрация")
        self._register_button.clicked.connect(self._on_register)
        self._register_button.setEnabled(False)
        buttons_layout.addWidget(self._register_button)

        form.addRow(buttons_layout)
        layout.addWidget(group)

    # ========================================================================
    # СИГНАЛЫ
    # ========================================================================

    def _connect_signals(self) -> None:
        """Подключить сигналы от ViewModel."""
        self._connection_vm.connection_state_changed.connect(self._on_connection_state)
        self._connection_vm.login_successful.connect(self._on_login_success)
        self._connection_vm.login_failed.connect(self._on_login_failed)
        self._connection_vm.register_successful.connect(self._on_register_success)
        self._connection_vm.register_failed.connect(self._on_register_failed)

    # ========================================================================
    # ОБРАБОТЧИКИ
    # ========================================================================

    def _on_connect(self) -> None:
        """Обработчик кнопки подключения."""
        host = self._host_input.text().strip() or "localhost"
        port = int(self._port_input.text().strip() or "8443")

        self._connection_vm.host = host
        self._connection_vm.port = port

        self._connect_button.setEnabled(False)
        self._connect_button.setText("Подключение...")
        self._connection_vm.connect_to_server()

    def _on_login(self) -> None:
        """Обработчик кнопки входа."""
        username = self._username_input.text().strip()
        password = self._password_input.text()

        if not username or not password:
            QMessageBox.warning(self, "Ошибка", "Введите имя и пароль")
            return

        self._login_button.setEnabled(False)
        self._connection_vm.login(username, password)

    def _on_register(self) -> None:
        """Обработчик кнопки регистрации."""
        username = self._username_input.text().strip()
        password = self._password_input.text()

        if not username or not password:
            QMessageBox.warning(self, "Ошибка", "Введите имя и пароль")
            return

        if len(password) < 8:
            QMessageBox.warning(self, "Ошибка", "Пароль должен быть не менее 8 символов")
            return

        self._register_button.setEnabled(False)
        self._connection_vm.register(username, password)

    def _on_play(self) -> None:
        """Обработчик кнопки Играть."""
        self._room_vm.refresh_room_list()
        self.play_clicked.emit()

    # ========================================================================
    # ОБРАБОТЧИКИ СОСТОЯНИЯ
    # ========================================================================

    def _on_connection_state(self, state: str) -> None:
        """
        Обработчик изменения состояния подключения.

        Args:
            state: Новое состояние.
        """
        if state == "connected":
            self._connect_button.setText("✓ Подключено")
            self._connect_button.setEnabled(False)
            self._login_button.setEnabled(True)
            self._register_button.setEnabled(True)
            self._status_label.setText("Подключено к серверу")
            self._status_label.setStyleSheet("color: #2ecc71;")

        elif state == "disconnected":
            self._connect_button.setText("Подключиться")
            self._connect_button.setEnabled(True)
            self._login_button.setEnabled(False)
            self._register_button.setEnabled(False)
            self._play_button.setEnabled(False)
            self._status_label.setText("Не подключены")
            self._status_label.setStyleSheet("color: #888;")

        elif state in ("connecting", "reconnecting"):
            self._connect_button.setText("Подключение...")
            self._connect_button.setEnabled(False)
            self._status_label.setText("Подключение...")
            self._status_label.setStyleSheet("color: #f39c12;")

    def _on_login_success(self) -> None:
        """Обработчик успешного входа."""
        self._login_button.setEnabled(True)
        self._play_button.setEnabled(True)
        self._status_label.setText(f"Вошли как: {self._player_model.username}")
        self._status_label.setStyleSheet("color: #2ecc71;")

    def _on_login_failed(self, error: str) -> None:
        """
        Обработчик ошибки входа.

        Args:
            error: Сообщение об ошибке.
        """
        self._login_button.setEnabled(True)
        QMessageBox.warning(self, "Ошибка входа", error)

    def _on_register_success(self) -> None:
        """Обработчик успешной регистрации."""
        self._register_button.setEnabled(True)
        QMessageBox.information(self, "Регистрация", "Регистрация успешна! Теперь войдите.")

    def _on_register_failed(self, error: str) -> None:
        """
        Обработчик ошибки регистрации.

        Args:
            error: Сообщение об ошибке.
        """
        self._register_button.setEnabled(True)
        QMessageBox.warning(self, "Ошибка регистрации", error)