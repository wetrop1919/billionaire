"""
client/views/admin_panel.py

Виджет административной панели.

Доступен только для пользователей с правами администратора (Creator).
Позволяет управлять игрой: изменять деньги, телепортировать,
управлять собственностью, просматривать логи.

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
    QGroupBox,
    QLineEdit,
    QSpinBox,
    QFormLayout,
    QTextEdit,
    QMessageBox,
    QTabWidget,
)
from PySide6.QtCore import Qt, Signal, Slot

from client.viewmodels.game_viewmodel import GameViewModel

logger = logging.getLogger("billionaire.client")


# ============================================================================
# АДМИН-ПАНЕЛЬ
# ============================================================================

class AdminPanelWidget(QWidget):
    """
    Виджет админ-панели.

    Предоставляет инструменты для управления игрой:
    - Чит-команды (деньги, собственность, телепортация)
    - Управление игроками (роли, бан)
    - Просмотр логов
    - Управление сервером

    Сигналы:
        back_clicked — нажата кнопка "Назад"
    """

    back_clicked = Signal()

    def __init__(
        self,
        game_vm: GameViewModel,
        parent: Optional[QWidget] = None,
    ) -> None:
        """
        Инициализация админ-панели.

        Args:
            game_vm: ViewModel игры.
            parent: Родительский виджет.
        """
        super().__init__(parent)

        self._game_vm = game_vm

        self._create_ui()

    # ========================================================================
    # UI
    # ========================================================================

    def _create_ui(self) -> None:
        """Создать интерфейс."""
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

        # Заголовок
        title = QLabel("🛡 Админ-панель")
        title.setStyleSheet("font-size: 24px; font-weight: bold; color: #e74c3c;")
        layout.addWidget(title)

        # Вкладки
        tabs = QTabWidget()
        tabs.addTab(self._create_cheats_tab(), "💰 Читы")
        tabs.addTab(self._create_players_tab(), "👥 Игроки")
        tabs.addTab(self._create_logs_tab(), "📋 Логи")
        tabs.addTab(self._create_server_tab(), "🖥 Сервер")
        layout.addWidget(tabs)

        # Кнопка назад
        self._back_button = QPushButton("← Назад")
        self._back_button.clicked.connect(self.back_clicked.emit)
        layout.addWidget(self._back_button)

    def _create_cheats_tab(self) -> QWidget:
        """Создать вкладку чит-команд."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Деньги
        money_group = QGroupBox("💰 Деньги")
        money_form = QFormLayout(money_group)

        self._money_player_input = QLineEdit()
        self._money_player_input.setPlaceholderText("ID игрока")
        money_form.addRow("Игрок:", self._money_player_input)

        self._money_amount_spin = QSpinBox()
        self._money_amount_spin.setRange(0, 100000)
        self._money_amount_spin.setValue(5000)
        money_form.addRow("Сумма:", self._money_amount_spin)

        money_buttons = QHBoxLayout()
        set_money_btn = QPushButton("Установить")
        set_money_btn.clicked.connect(self._on_set_money)
        money_buttons.addWidget(set_money_btn)

        add_money_btn = QPushButton("Добавить")
        add_money_btn.clicked.connect(self._on_add_money)
        money_buttons.addWidget(add_money_btn)

        money_form.addRow(money_buttons)
        layout.addWidget(money_group)

        # Телепортация
        teleport_group = QGroupBox("🚀 Телепортация")
        teleport_form = QFormLayout(teleport_group)

        self._teleport_player_input = QLineEdit()
        self._teleport_player_input.setPlaceholderText("ID игрока")
        teleport_form.addRow("Игрок:", self._teleport_player_input)

        self._teleport_cell_spin = QSpinBox()
        self._teleport_cell_spin.setRange(0, 39)
        teleport_form.addRow("Клетка:", self._teleport_cell_spin)

        teleport_btn = QPushButton("Телепортировать")
        teleport_btn.clicked.connect(self._on_teleport)
        teleport_form.addRow(teleport_btn)
        layout.addWidget(teleport_group)

        # Собственность
        property_group = QGroupBox("🏠 Собственность")
        property_form = QFormLayout(property_group)

        self._property_player_input = QLineEdit()
        self._property_player_input.setPlaceholderText("ID игрока")
        property_form.addRow("Игрок:", self._property_player_input)

        self._property_id_input = QLineEdit()
        self._property_id_input.setPlaceholderText("ID собственности")
        property_form.addRow("Собственность:", self._property_id_input)

        property_buttons = QHBoxLayout()
        give_prop_btn = QPushButton("Передать")
        give_prop_btn.clicked.connect(self._on_give_property)
        property_buttons.addWidget(give_prop_btn)

        clear_prop_btn = QPushButton("Вернуть банку")
        clear_prop_btn.clicked.connect(self._on_clear_property)
        property_buttons.addWidget(clear_prop_btn)

        property_form.addRow(property_buttons)
        layout.addWidget(property_group)

        # Undo
        undo_group = QGroupBox("↩ Отмена")
        undo_layout = QHBoxLayout(undo_group)

        undo_btn = QPushButton("Отменить последнее действие")
        undo_btn.clicked.connect(self._on_undo)
        undo_layout.addWidget(undo_btn)

        layout.addWidget(undo_group)
        layout.addStretch()

        return widget

    def _create_players_tab(self) -> QWidget:
        """Создать вкладку управления игроками."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Управление игроками
        players_group = QGroupBox("👥 Игроки")
        form = QFormLayout(players_group)

        self._player_id_input = QLineEdit()
        self._player_id_input.setPlaceholderText("ID игрока")
        form.addRow("Игрок:", self._player_id_input)

        buttons = QHBoxLayout()

        jail_btn = QPushButton("В тюрьму")
        jail_btn.clicked.connect(self._on_send_to_jail)
        buttons.addWidget(jail_btn)

        free_btn = QPushButton("Из тюрьмы")
        free_btn.clicked.connect(self._on_free_from_jail)
        buttons.addWidget(free_btn)

        veranda_btn = QPushButton("С Веранды")
        veranda_btn.clicked.connect(self._on_free_from_veranda)
        buttons.addWidget(veranda_btn)

        form.addRow(buttons)

        ban_btn = QPushButton("🚫 Заблокировать")
        ban_btn.setStyleSheet("QPushButton { background-color: #e74c3c; color: white; }")
        ban_btn.clicked.connect(self._on_ban_player)
        form.addRow(ban_btn)

        layout.addWidget(players_group)
        layout.addStretch()

        return widget

    def _create_logs_tab(self) -> QWidget:
        """Создать вкладку логов."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        logs_group = QGroupBox("📋 Логи")
        logs_layout = QVBoxLayout(logs_group)

        self._logs_text = QTextEdit()
        self._logs_text.setReadOnly(True)
        self._logs_text.setMinimumHeight(400)
        self._logs_text.setStyleSheet(
            "QTextEdit { background-color: #1a1a2e; color: #0f0; "
            "font-family: monospace; font-size: 12px; }"
        )
        logs_layout.addWidget(self._logs_text)

        refresh_btn = QPushButton("🔄 Обновить логи")
        refresh_btn.clicked.connect(self._on_refresh_logs)
        logs_layout.addWidget(refresh_btn)

        layout.addWidget(logs_group)

        return widget

    def _create_server_tab(self) -> QWidget:
        """Создать вкладку управления сервером."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        server_group = QGroupBox("🖥 Сервер")
        server_layout = QVBoxLayout(server_group)

        self._broadcast_input = QLineEdit()
        self._broadcast_input.setPlaceholderText("Текст объявления")
        server_layout.addWidget(self._broadcast_input)

        broadcast_btn = QPushButton("📢 Отправить всем")
        broadcast_btn.clicked.connect(self._on_broadcast)
        server_layout.addWidget(broadcast_btn)

        server_layout.addSpacing(20)

        backup_btn = QPushButton("💾 Создать бэкап")
        backup_btn.clicked.connect(self._on_backup)
        server_layout.addWidget(backup_btn)

        layout.addWidget(server_group)
        layout.addStretch()

        return widget

    # ========================================================================
    # ОБРАБОТЧИКИ
    # ========================================================================

    @Slot()
    def _on_set_money(self) -> None:
        """Установить деньги."""
        QMessageBox.information(self, "Чит", "Функция будет доступна после интеграции с сервером")

    @Slot()
    def _on_add_money(self) -> None:
        """Добавить деньги."""
        QMessageBox.information(self, "Чит", "Функция будет доступна после интеграции с сервером")

    @Slot()
    def _on_teleport(self) -> None:
        """Телепортировать игрока."""
        QMessageBox.information(self, "Чит", "Функция будет доступна после интеграции с сервером")

    @Slot()
    def _on_give_property(self) -> None:
        """Передать собственность."""
        QMessageBox.information(self, "Чит", "Функция будет доступна после интеграции с сервером")

    @Slot()
    def _on_clear_property(self) -> None:
        """Вернуть собственность банку."""
        QMessageBox.information(self, "Чит", "Функция будет доступна после интеграции с сервером")

    @Slot()
    def _on_undo(self) -> None:
        """Отменить действие."""
        QMessageBox.information(self, "Undo", "Функция будет доступна после интеграции с сервером")

    @Slot()
    def _on_send_to_jail(self) -> None:
        """Отправить в тюрьму."""
        QMessageBox.information(self, "Игроки", "Функция будет доступна после интеграции с сервером")

    @Slot()
    def _on_free_from_jail(self) -> None:
        """Освободить из тюрьмы."""
        QMessageBox.information(self, "Игроки", "Функция будет доступна после интеграции с сервером")

    @Slot()
    def _on_free_from_veranda(self) -> None:
        """Убрать с Веранды."""
        QMessageBox.information(self, "Игроки", "Функция будет доступна после интеграции с сервером")

    @Slot()
    def _on_ban_player(self) -> None:
        """Заблокировать игрока."""
        QMessageBox.information(self, "Игроки", "Функция будет доступна после интеграции с сервером")

    @Slot()
    def _on_refresh_logs(self) -> None:
        """Обновить логи."""
        self._logs_text.append("[INFO] Запрос логов...")

    @Slot()
    def _on_broadcast(self) -> None:
        """Отправить объявление."""
        text = self._broadcast_input.text().strip()
        if text:
            QMessageBox.information(self, "Сервер", f"Объявление отправлено: {text}")
            self._broadcast_input.clear()

    @Slot()
    def _on_backup(self) -> None:
        """Создать бэкап."""
        QMessageBox.information(self, "Сервер", "Бэкап создан")