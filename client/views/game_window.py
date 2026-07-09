"""
client/views/game_window.py

Виджет игрового окна.

Содержит игровое поле, панель игрока, панель действий и чат.
Основной экран во время игры.

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
    QGroupBox,
    QScrollArea,
    QGridLayout,
    QFrame,
    QSplitter,
    QListWidget,
    QListWidgetItem,
)
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QColor, QPainter, QBrush, QPen, QFont

from client.models.game_model import GameModel
from client.models.player_model import PlayerModel
from client.viewmodels.game_viewmodel import GameViewModel
from client.viewmodels.chat_viewmodel import ChatViewModel
from client.assets.asset_manager import AssetManager

logger = logging.getLogger("billionaire.client")


# ============================================================================
# ПРОСТОЕ ИГРОВОЕ ПОЛЕ (ЗАГЛУШКА)
# ============================================================================

class BoardWidget(QWidget):
    """
    Виджет игрового поля.

    Отображает клетки поля и фишки игроков.
    В production-версии требует детальной проработки.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(600, 600)
        self._players: dict[UUID, dict[str, Any]] = {}
        self._cells: list[dict[str, Any]] = []

    def update_players(self, players: dict[UUID, dict[str, Any]]) -> None:
        """Обновить позиции игроков."""
        self._players = players
        self.update()

    def update_cells(self, cells: list[dict[str, Any]]) -> None:
        """Обновить клетки поля."""
        self._cells = cells
        self.update()

    def paintEvent(self, event) -> None:
        """Отрисовать поле."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        margin = 40
        cell_size = 50

        # Фон
        painter.fillRect(0, 0, w, h, QColor("#c8e6c9"))

        # Отрисовка клеток по краям (упрощённо)
        painter.setPen(QPen(QColor("#333"), 1))

        # Углы
        for i, (x, y) in enumerate([
            (w - margin, h - margin),  # 0: Старт
            (margin, h - margin),      # 10: Тюрьма
            (margin, margin),          # 20: Парковка
            (w - margin, margin),      # 30: В тюрьму
        ]):
            painter.fillRect(
                int(x - cell_size/2), int(y - cell_size/2),
                cell_size, cell_size,
                QColor("#fff") if i == 0 else QColor("#eee"),
            )
            painter.drawRect(
                int(x - cell_size/2), int(y - cell_size/2),
                cell_size, cell_size,
            )

        # Фишки игроков
        for player_id, player in self._players.items():
            pos = player.get("position", {}).get("cell_id", 0)
            color = QColor(player.get("color", "#3498db"))

            # Упрощённое позиционирование
            if pos == 0:
                px, py = w - margin, h - margin
            elif pos == 10:
                px, py = margin, h - margin
            elif pos == 20:
                px, py = margin, margin
            elif pos == 30:
                px, py = w - margin, margin
            else:
                # Промежуточные позиции (упрощённо)
                side = pos // 10
                offset = pos % 10
                if side == 0:
                    px, py = w - margin - offset * 50, h - margin
                elif side == 1:
                    px, py = margin, h - margin - offset * 50
                elif side == 2:
                    px, py = margin + offset * 50, margin
                else:
                    px, py = w - margin, margin + offset * 50

            painter.setBrush(QBrush(color))
            painter.setPen(QPen(QColor("#333"), 2))
            painter.drawEllipse(int(px - 8), int(py - 8), 16, 16)

        painter.end()


# ============================================================================
# ПАНЕЛЬ ИГРОКА
# ============================================================================

class PlayerPanelWidget(QWidget):
    """Панель с информацией об игроке."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMinimumWidth(250)

        layout = QVBoxLayout(self)

        # Информация
        self._money_label = QLabel("💰 0 $")
        self._money_label.setStyleSheet("font-size: 20px; font-weight: bold;")
        layout.addWidget(self._money_label)

        self._position_label = QLabel("📍 Клетка: 0")
        layout.addWidget(self._position_label)

        self._status_label = QLabel("")
        layout.addWidget(self._status_label)

        # Собственность
        group = QGroupBox("Собственность")
        group_layout = QVBoxLayout(group)
        self._properties_list = QListWidget()
        self._properties_list.setMaximumHeight(200)
        group_layout.addWidget(self._properties_list)
        layout.addWidget(group)

        layout.addStretch()

    def update_player(self, player_data: dict[str, Any]) -> None:
        """Обновить данные игрока."""
        money = player_data.get("money", 0)
        position = player_data.get("position", {}).get("cell_id", 0)
        properties = player_data.get("properties", [])
        in_jail = player_data.get("in_jail", False)
        bankrupt = player_data.get("bankrupt", False)

        self._money_label.setText(f"💰 {money:,} $".replace(",", " "))

        self._position_label.setText(f"📍 Клетка: {position}")

        status = ""
        if bankrupt:
            status = "💀 Банкрот"
        elif in_jail:
            status = "🔒 В тюрьме"
        self._status_label.setText(status)

        self._properties_list.clear()
        for prop_id in properties:
            self._properties_list.addItem(prop_id)

    def clear(self) -> None:
        """Очистить панель."""
        self._money_label.setText("💰 0 $")
        self._position_label.setText("📍 Клетка: 0")
        self._status_label.setText("")
        self._properties_list.clear()


# ============================================================================
# ПАНЕЛЬ ДЕЙСТВИЙ
# ============================================================================

class ActionPanelWidget(QWidget):
    """Панель с игровыми действиями."""

    def __init__(self, game_vm: GameViewModel, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._game_vm = game_vm

        layout = QVBoxLayout(self)

        group = QGroupBox("Действия")
        group_layout = QVBoxLayout(group)

        self._roll_button = QPushButton("🎲 Бросить кубики")
        self._roll_button.clicked.connect(self._game_vm.roll_dice)
        group_layout.addWidget(self._roll_button)

        self._buy_button = QPushButton("💰 Купить")
        self._buy_button.clicked.connect(self._game_vm.buy_property)
        self._buy_button.setEnabled(False)
        group_layout.addWidget(self._buy_button)

        self._decline_button = QPushButton("🚫 Отказаться")
        self._decline_button.clicked.connect(self._game_vm.decline_property)
        self._decline_button.setEnabled(False)
        group_layout.addWidget(self._decline_button)

        self._end_turn_button = QPushButton("✅ Завершить ход")
        self._end_turn_button.clicked.connect(self._game_vm.end_turn)
        self._end_turn_button.setEnabled(False)
        group_layout.addWidget(self._end_turn_button)

        # Тюрьма
        self._pay_jail_button = QPushButton("💵 Штраф (50$)")
        self._pay_jail_button.clicked.connect(self._game_vm.pay_jail_fine)
        self._pay_jail_button.setVisible(False)
        group_layout.addWidget(self._pay_jail_button)

        self._use_jail_card_button = QPushButton("🃏 Карточка")
        self._use_jail_card_button.clicked.connect(self._game_vm.use_jail_card)
        self._use_jail_card_button.setVisible(False)
        group_layout.addWidget(self._use_jail_card_button)

        layout.addWidget(group)

        # Подключаем сигналы
        self._game_vm.action_result.connect(self._on_action_result)

        layout.addStretch()

    @Slot(str, dict)
    def _on_action_result(self, action_type: str, result: dict) -> None:
        """Обработать результат действия."""
        if action_type == "turn_started":
            is_my = result.get("is_my_turn", False)
            self._roll_button.setEnabled(is_my)
            self._end_turn_button.setEnabled(False)
            self._buy_button.setEnabled(False)
            self._decline_button.setEnabled(False)

    def set_can_buy(self, can: bool) -> None:
        self._buy_button.setEnabled(can)
        self._decline_button.setEnabled(can)

    def set_can_end_turn(self, can: bool) -> None:
        self._end_turn_button.setEnabled(can)

    def show_jail_actions(self, show: bool) -> None:
        self._pay_jail_button.setVisible(show)
        self._use_jail_card_button.setVisible(show)
        self._roll_button.setEnabled(not show)


# ============================================================================
# ИГРОВОЕ ОКНО
# ============================================================================

class GameWindowWidget(QWidget):
    """
    Главный виджет игрового экрана.

    Содержит поле, панели игроков, действия и чат.
    """

    def __init__(
        self,
        game_model: GameModel,
        player_model: PlayerModel,
        game_vm: GameViewModel,
        chat_vm: ChatViewModel,
        asset_manager: AssetManager,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)

        self._game_model = game_model
        self._player_model = player_model
        self._game_vm = game_vm
        self._chat_vm = chat_vm
        self._asset_manager = asset_manager

        self._create_ui()
        self._connect_signals()

    def _create_ui(self) -> None:
        """Создать интерфейс."""
        main_layout = QHBoxLayout(self)

        # Центр: игровое поле
        self._board = BoardWidget()
        main_layout.addWidget(self._board, stretch=3)

        # Правая панель
        right_panel = QVBoxLayout()

        # Информация о ходе
        self._turn_label = QLabel("Ход: 0")
        self._turn_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        right_panel.addWidget(self._turn_label)

        self._current_player_label = QLabel("")
        right_panel.addWidget(self._current_player_label)

        # Панель игрока
        self._player_panel = PlayerPanelWidget()
        right_panel.addWidget(self._player_panel)

        # Панель действий
        self._action_panel = ActionPanelWidget(self._game_vm)
        right_panel.addWidget(self._action_panel)

        # Чат
        from client.views.chat_widget import ChatWidget
        self._chat_widget = ChatWidget(self._chat_vm)
        right_panel.addWidget(self._chat_widget, stretch=1)

        main_layout.addLayout(right_panel, stretch=1)

    def _connect_signals(self) -> None:
        """Подключить сигналы."""
        self._game_model.game_state_changed.connect(self._update_display)
        self._game_model.players_updated.connect(self._update_players)
        self._game_model.turn_changed.connect(
            lambda turn: self._turn_label.setText(f"Ход: {turn}")
        )
        self._game_model.current_player_changed.connect(
            lambda pid: self._current_player_label.setText(f"Ходит: {pid[:8]}...")
        )

    @Slot()
    def _update_display(self) -> None:
        """Обновить отображение."""
        my_player = self._game_model.get_my_player()
        if my_player:
            self._player_panel.update_player(my_player)

    @Slot()
    def _update_players(self) -> None:
        """Обновить игроков на поле."""
        self._board.update_players(self._game_model._players)