"""
client/views/history_dialog.py

Виджет истории игр.

Отображает список завершённых игр с результатами
и возможностью просмотра деталей.

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
    QListWidget,
    QListWidgetItem,
    QGroupBox,
    QMessageBox,
)
from PySide6.QtCore import Qt, Signal, Slot

from client.models.player_model import PlayerModel

logger = logging.getLogger("billionaire.client")


# ============================================================================
# ВИДЖЕТ ИСТОРИИ
# ============================================================================

class HistoryWidget(QWidget):
    """
    Виджет истории игр.

    Отображает список завершённых игр и позволяет
    просматривать детальные результаты.

    Сигналы:
        back_clicked — нажата кнопка "Назад"
    """

    back_clicked = Signal()

    def __init__(
        self,
        player_model: PlayerModel,
        parent: Optional[QWidget] = None,
    ) -> None:
        """
        Инициализация виджета истории.

        Args:
            player_model: Модель игрока.
            parent: Родительский виджет.
        """
        super().__init__(parent)

        self._player_model = player_model

        self._create_ui()

    # ========================================================================
    # UI
    # ========================================================================

    def _create_ui(self) -> None:
        """Создать интерфейс."""
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(30, 30, 30, 30)

        # Заголовок
        title = QLabel("📜 История игр")
        title.setStyleSheet("font-size: 24px; font-weight: bold;")
        layout.addWidget(title)

        # Статистика
        stats_group = self._create_stats_group()
        layout.addWidget(stats_group)

        # Список игр
        games_group = QGroupBox("Завершённые игры")
        games_layout = QVBoxLayout(games_group)

        self._games_list = QListWidget()
        self._games_list.setMinimumHeight(300)
        self._games_list.itemDoubleClicked.connect(self._on_game_selected)
        games_layout.addWidget(self._games_list)

        layout.addWidget(games_group)

        # Кнопки
        buttons_layout = QHBoxLayout()

        self._refresh_button = QPushButton("🔄 Обновить")
        self._refresh_button.clicked.connect(self._load_history)
        buttons_layout.addWidget(self._refresh_button)

        self._details_button = QPushButton("📋 Подробности")
        self._details_button.clicked.connect(self._on_show_details)
        buttons_layout.addWidget(self._details_button)

        self._back_button = QPushButton("← Назад")
        self._back_button.clicked.connect(self.back_clicked.emit)
        buttons_layout.addWidget(self._back_button)

        layout.addLayout(buttons_layout)

        # Загружаем историю
        self._load_history()

    def _create_stats_group(self) -> QGroupBox:
        """
        Создать группу статистики.

        Returns:
            Группа со статистикой.
        """
        group = QGroupBox("Статистика")
        layout = QHBoxLayout(group)

        self._total_games_label = QLabel("Игр: 0")
        self._total_games_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._total_games_label)

        self._wins_label = QLabel("Побед: 0")
        self._wins_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._wins_label)

        self._win_rate_label = QLabel("Win rate: 0%")
        self._win_rate_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._win_rate_label)

        return group

    # ========================================================================
    # ЗАГРУЗКА
    # ========================================================================

    @Slot()
    def _load_history(self) -> None:
        """Загрузить историю игр."""
        # В production-версии — запрос к серверу
        self._update_stats()

        # Заглушка: демо-данные
        self._games_list.clear()

        demo_games = [
            {"date": "2024-01-15", "players": 4, "winner": "Player1", "rank": 1, "money": 3500},
            {"date": "2024-01-14", "players": 3, "winner": "Bot-1", "rank": 2, "money": 2100},
            {"date": "2024-01-13", "players": 4, "winner": "Player1", "rank": 1, "money": 4200},
        ]

        for game in demo_games:
            text = (
                f"{game['date']} — {game['players']} игроков — "
                f"Победитель: {game['winner']} — Ваше место: {game['rank']} "
                f"({game['money']}$)"
            )
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, game)
            self._games_list.addItem(item)

    def _update_stats(self) -> None:
        """Обновить отображение статистики."""
        stats = self._player_model.get_profile_dict()

        self._total_games_label.setText(f"Игр: {stats.get('total_games', 0)}")
        self._wins_label.setText(f"Побед: {stats.get('wins', 0)}")
        self._win_rate_label.setText(f"Win rate: {stats.get('win_rate', 0):.1f}%")

    # ========================================================================
    # ОБРАБОТЧИКИ
    # ========================================================================

    @Slot()
    def _on_game_selected(self) -> None:
        """Обработчик выбора игры."""
        self._on_show_details()

    @Slot()
    def _on_show_details(self) -> None:
        """Показать детали выбранной игры."""
        current_item = self._games_list.currentItem()
        if current_item is None:
            QMessageBox.information(self, "Выбор", "Выберите игру из списка")
            return

        game_data = current_item.data(Qt.ItemDataRole.UserRole)
        if game_data is None:
            return

        details = (
            f"Дата: {game_data.get('date', '?')}\n"
            f"Игроков: {game_data.get('players', '?')}\n"
            f"Победитель: {game_data.get('winner', '?')}\n"
            f"Ваше место: {game_data.get('rank', '?')}\n"
            f"Ваш баланс: {game_data.get('money', 0)}$"
        )

        QMessageBox.information(self, "Детали игры", details)

    def clear(self) -> None:
        """Очистить виджет."""
        self._games_list.clear()