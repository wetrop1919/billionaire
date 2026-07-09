"""
client/views/room_list.py

Виджет списка комнат.

Отображает доступные комнаты, позволяет создавать новые,
входить в существующие и настраивать фильтры.

Python: 3.13+
"""

from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QGroupBox,
    QLineEdit,
    QCheckBox,
    QComboBox,
    QMessageBox,
    QInputDialog,
    QDialog,
    QFormLayout,
    QSpinBox,
    QDialogButtonBox,
)
from PySide6.QtCore import Qt, Signal, Slot

from client.models.room_model import RoomModel
from client.viewmodels.room_viewmodel import RoomViewModel

logger = logging.getLogger("billionaire.client")


# ============================================================================
# ДИАЛОГ СОЗДАНИЯ КОМНАТЫ
# ============================================================================

class CreateRoomDialog(QDialog):
    """Диалог создания новой комнаты."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """
        Инициализация диалога.

        Args:
            parent: Родительский виджет.
        """
        super().__init__(parent)
        self.setWindowTitle("Создать комнату")
        self.setMinimumWidth(400)
        self._create_ui()

    def _create_ui(self) -> None:
        """Создать интерфейс диалога."""
        layout = QVBoxLayout(self)

        form = QFormLayout()

        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText("Введите название")
        form.addRow("Название:", self._name_input)

        self._max_players_spin = QSpinBox()
        self._max_players_spin.setRange(2, 8)
        self._max_players_spin.setValue(4)
        form.addRow("Макс. игроков:", self._max_players_spin)

        self._turn_timeout_spin = QSpinBox()
        self._turn_timeout_spin.setRange(15, 300)
        self._turn_timeout_spin.setValue(60)
        self._turn_timeout_spin.setSuffix(" сек")
        form.addRow("Таймаут хода:", self._turn_timeout_spin)

        self._start_money_spin = QSpinBox()
        self._start_money_spin.setRange(0, 100000)
        self._start_money_spin.setValue(1500)
        self._start_money_spin.setSuffix(" $")
        form.addRow("Старт. капитал:", self._start_money_spin)

        self._private_check = QCheckBox("Приватная комната")
        form.addRow(self._private_check)

        self._password_input = QLineEdit()
        self._password_input.setPlaceholderText("Пароль (если приватная)")
        self._password_input.setEnabled(False)
        form.addRow("Пароль:", self._password_input)

        self._private_check.toggled.connect(self._password_input.setEnabled)

        layout.addLayout(form)

        # Кнопки
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_room_data(self) -> dict[str, Any]:
        """
        Получить данные комнаты из диалога.

        Returns:
            Словарь с параметрами комнаты.
        """
        return {
            "name": self._name_input.text().strip(),
            "max_players": self._max_players_spin.value(),
            "turn_timeout": self._turn_timeout_spin.value(),
            "start_money": self._start_money_spin.value(),
            "is_private": self._private_check.isChecked(),
            "password": self._password_input.text() if self._private_check.isChecked() else "",
        }


# ============================================================================
# ВИДЖЕТ СПИСКА КОМНАТ
# ============================================================================

class RoomListWidget(QWidget):
    """
    Виджет списка комнат.

    Отображает комнаты, фильтры и кнопки действий.
    """

    # Сигналы
    back_clicked = Signal()

    def __init__(
        self,
        room_model: RoomModel,
        room_vm: RoomViewModel,
        parent: Optional[QWidget] = None,
    ) -> None:
        """
        Инициализация виджета.

        Args:
            room_model: Модель комнат.
            room_vm: ViewModel комнат.
            parent: Родительский виджет.
        """
        super().__init__(parent)

        self._room_model = room_model
        self._room_vm = room_vm

        self._create_ui()
        self._connect_signals()

        # Загружаем список при создании
        self._room_vm.refresh_room_list()

    # ========================================================================
    # UI
    # ========================================================================

    def _create_ui(self) -> None:
        """Создать интерфейс."""
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(20, 20, 20, 20)

        # Заголовок
        title = QLabel("📋 Список комнат")
        title.setStyleSheet("font-size: 24px; font-weight: bold;")
        layout.addWidget(title)

        # Текущая комната
        self._current_room_label = QLabel("")
        self._current_room_label.setStyleSheet("color: #2ecc71; font-weight: bold;")
        layout.addWidget(self._current_room_label)

        # Фильтры
        self._create_filters(layout)

        # Список комнат
        self._room_list = QListWidget()
        self._room_list.setMinimumHeight(300)
        self._room_list.itemDoubleClicked.connect(self._on_room_double_clicked)
        layout.addWidget(self._room_list)

        # Кнопки
        buttons_layout = QHBoxLayout()

        self._refresh_button = QPushButton("🔄 Обновить")
        self._refresh_button.clicked.connect(self._room_vm.refresh_room_list)
        buttons_layout.addWidget(self._refresh_button)

        self._create_button = QPushButton("➕ Создать комнату")
        self._create_button.clicked.connect(self._on_create_room)
        buttons_layout.addWidget(self._create_button)

        self._join_button = QPushButton("🚪 Войти")
        self._join_button.clicked.connect(self._on_join_room)
        buttons_layout.addWidget(self._join_button)

        self._leave_button = QPushButton("🚶 Выйти")
        self._leave_button.clicked.connect(self._on_leave_room)
        self._leave_button.setEnabled(False)
        buttons_layout.addWidget(self._leave_button)

        layout.addLayout(buttons_layout)

        # Кнопка назад
        self._back_button = QPushButton("← Назад")
        self._back_button.clicked.connect(self.back_clicked.emit)
        layout.addWidget(self._back_button)

    def _create_filters(self, layout: QVBoxLayout) -> None:
        """
        Создать фильтры.

        Args:
            layout: Родительский layout.
        """
        filter_layout = QHBoxLayout()

        self._state_filter = QComboBox()
        self._state_filter.addItems(["Все", "Ожидание", "В игре", "Завершена"])
        self._state_filter.currentIndexChanged.connect(self._on_filter_changed)
        filter_layout.addWidget(QLabel("Состояние:"))
        filter_layout.addWidget(self._state_filter)

        self._private_filter = QCheckBox("Приватные")
        self._private_filter.setChecked(True)
        self._private_filter.toggled.connect(self._on_filter_changed)
        filter_layout.addWidget(self._private_filter)

        self._full_filter = QCheckBox("Заполненные")
        self._full_filter.setChecked(False)
        self._full_filter.toggled.connect(self._on_filter_changed)
        filter_layout.addWidget(self._full_filter)

        filter_layout.addStretch()
        layout.addLayout(filter_layout)

    # ========================================================================
    # СИГНАЛЫ
    # ========================================================================

    def _connect_signals(self) -> None:
        """Подключить сигналы."""
        self._room_model.room_list_updated.connect(self._update_room_list)
        self._room_model.room_joined.connect(self._on_joined)
        self._room_model.room_left.connect(self._on_left)

    # ========================================================================
    # ОБРАБОТЧИКИ
    # ========================================================================

    def _on_create_room(self) -> None:
        """Создать комнату."""
        dialog = CreateRoomDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_room_data()

            if not data["name"]:
                QMessageBox.warning(self, "Ошибка", "Введите название комнаты")
                return

            self._room_vm.create_room(
                name=data["name"],
                max_players=data["max_players"],
                turn_timeout=data["turn_timeout"],
                start_money=data["start_money"],
                is_private=data["is_private"],
                password=data["password"],
            )

    def _on_join_room(self) -> None:
        """Войти в выбранную комнату."""
        current_item = self._room_list.currentItem()
        if current_item is None:
            QMessageBox.information(self, "Выбор", "Выберите комнату из списка")
            return

        room_data = current_item.data(Qt.ItemDataRole.UserRole)
        if room_data is None:
            return

        # Запрашиваем пароль, если нужно
        password = ""
        if room_data.get("has_password"):
            password, ok = QInputDialog.getText(
                self, "Пароль", "Введите пароль комнаты:",
                QLineEdit.EchoMode.Password,
            )
            if not ok:
                return

        self._room_vm.join_room(
            room_id=str(room_data["room_id"]),
            password=password,
        )

    def _on_leave_room(self) -> None:
        """Покинуть комнату."""
        reply = QMessageBox.question(
            self,
            "Выход",
            "Вы уверены, что хотите покинуть комнату?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._room_vm.leave_room()

    def _on_room_double_clicked(self, item: QListWidgetItem) -> None:
        """
        Двойной клик по комнате — вход.

        Args:
            item: Элемент списка.
        """
        self._room_list.setCurrentItem(item)
        self._on_join_room()

    def _on_filter_changed(self) -> None:
        """Обновить фильтры и список."""
        state_map = {"Все": "all", "Ожидание": "waiting", "В игре": "in_game", "Завершена": "finished"}
        state = state_map.get(self._state_filter.currentText(), "all")

        self._room_model.set_filter(
            state=state,
            show_private=self._private_filter.isChecked(),
            show_full=self._full_filter.isChecked(),
        )
        self._update_room_list()

    def _on_joined(self) -> None:
        """Обработчик входа в комнату."""
        self._leave_button.setEnabled(True)
        self._join_button.setEnabled(False)
        self._current_room_label.setText(
            f"Вы в комнате: {self._room_model.currentRoomName}"
        )

    def _on_left(self) -> None:
        """Обработчик выхода из комнаты."""
        self._leave_button.setEnabled(False)
        self._join_button.setEnabled(True)
        self._current_room_label.setText("")

    # ========================================================================
    # ОБНОВЛЕНИЕ СПИСКА
    # ========================================================================

    @Slot()
    def _update_room_list(self) -> None:
        """Обновить список комнат."""
        self._room_list.clear()

        rooms = self._room_model.get_filtered_rooms()

        if not rooms:
            item = QListWidgetItem("Нет доступных комнат")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self._room_list.addItem(item)
            return

        for room in rooms:
            status_icon = room.get("icon", "🌍")
            status_text = room.get("status_text", "")
            players = f"{room.get('players_count', 0)}/{room.get('max_players', 4)}"

            text = f"{status_icon} {room['name']} — {players} игроков — {status_text}"

            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, room)
            self._room_list.addItem(item)