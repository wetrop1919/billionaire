"""
client/views/profile_dialog.py

Виджет профиля игрока.

Отображает информацию о текущем пользователе,
его статистику и достижения.

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
    QFormLayout,
    QMessageBox,
)
from PySide6.QtCore import Qt, Signal, Slot

from client.models.player_model import PlayerModel

logger = logging.getLogger("billionaire.client")


# ============================================================================
# ВИДЖЕТ ПРОФИЛЯ
# ============================================================================

class ProfileWidget(QWidget):
    """
    Виджет профиля игрока.

    Отображает данные профиля и статистику.

    Сигналы:
        back_clicked — нажата кнопка "Назад"
        logout_clicked — нажата кнопка "Выйти"
    """

    back_clicked = Signal()
    logout_clicked = Signal()

    def __init__(
        self,
        player_model: PlayerModel,
        parent: Optional[QWidget] = None,
    ) -> None:
        """
        Инициализация виджета профиля.

        Args:
            player_model: Модель игрока.
            parent: Родительский виджет.
        """
        super().__init__(parent)

        self._player_model = player_model

        self._create_ui()
        self._connect_signals()
        self._load_profile()

    # ========================================================================
    # UI
    # ========================================================================

    def _create_ui(self) -> None:
        """Создать интерфейс."""
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(30, 30, 30, 30)

        # Заголовок
        title = QLabel("👤 Профиль")
        title.setStyleSheet("font-size: 24px; font-weight: bold;")
        layout.addWidget(title)

        # Информация о пользователе
        layout.addWidget(self._create_user_info_group())

        # Статистика
        layout.addWidget(self._create_stats_group())

        # Достижения (заглушка)
        layout.addWidget(self._create_achievements_group())

        # Кнопки
        buttons_layout = QHBoxLayout()

        self._edit_button = QPushButton("✏ Изменить профиль")
        self._edit_button.clicked.connect(self._on_edit_profile)
        buttons_layout.addWidget(self._edit_button)

        self._change_password_button = QPushButton("🔑 Сменить пароль")
        self._change_password_button.clicked.connect(self._on_change_password)
        buttons_layout.addWidget(self._change_password_button)

        self._logout_button = QPushButton("🚪 Выйти")
        self._logout_button.clicked.connect(self._on_logout)
        self._logout_button.setStyleSheet(
            "QPushButton { background-color: #e74c3c; color: white; }"
            "QPushButton:hover { background-color: #c0392b; }"
        )
        buttons_layout.addWidget(self._logout_button)

        self._back_button = QPushButton("← Назад")
        self._back_button.clicked.connect(self.back_clicked.emit)
        buttons_layout.addWidget(self._back_button)

        layout.addLayout(buttons_layout)
        layout.addStretch()

    def _create_user_info_group(self) -> QGroupBox:
        """Создать группу информации о пользователе."""
        group = QGroupBox("Информация")
        form = QFormLayout(group)

        self._username_label = QLabel("—")
        self._username_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        form.addRow("Имя:", self._username_label)

        self._role_label = QLabel("—")
        form.addRow("Роль:", self._role_label)

        self._registered_label = QLabel("—")
        form.addRow("Зарегистрирован:", self._registered_label)

        self._last_login_label = QLabel("—")
        form.addRow("Последний вход:", self._last_login_label)

        return group

    def _create_stats_group(self) -> QGroupBox:
        """Создать группу статистики."""
        group = QGroupBox("Статистика")
        form = QFormLayout(group)

        self._total_games_label = QLabel("0")
        form.addRow("Всего игр:", self._total_games_label)

        self._wins_label = QLabel("0")
        form.addRow("Побед:", self._wins_label)

        self._losses_label = QLabel("0")
        form.addRow("Поражений:", self._losses_label)

        self._win_rate_label = QLabel("0%")
        form.addRow("Процент побед:", self._win_rate_label)

        self._total_money_label = QLabel("0 $")
        form.addRow("Всего заработано:", self._total_money_label)

        self._highest_money_label = QLabel("0 $")
        form.addRow("Рекордная сумма:", self._highest_money_label)

        self._bankruptcies_label = QLabel("0")
        form.addRow("Банкротств:", self._bankruptcies_label)

        self._play_time_label = QLabel("0 мин")
        form.addRow("Время в игре:", self._play_time_label)

        return group

    def _create_achievements_group(self) -> QGroupBox:
        """Создать группу достижений (заглушка)."""
        group = QGroupBox("Достижения")
        layout = QVBoxLayout(group)

        achievements = [
            "🏆 Первая победа — Выиграйте свою первую игру",
            "💰 Миллионер — Накопите 10 000$ за игру",
            "🏗 Застройщик — Постройте 10 отелей",
            "🚂 Монополист — Владейте всеми станциями",
        ]

        for achievement in achievements:
            label = QLabel(achievement)
            label.setStyleSheet("color: #888; padding: 2px;")
            layout.addWidget(label)

        return group

    # ========================================================================
    # СИГНАЛЫ
    # ========================================================================

    def _connect_signals(self) -> None:
        """Подключить сигналы."""
        self._player_model.profile_updated.connect(self._load_profile)
        self._player_model.stats_updated.connect(self._load_profile)

    # ========================================================================
    # ЗАГРУЗКА
    # ========================================================================

    @Slot()
    def _load_profile(self) -> None:
        """Загрузить данные профиля."""
        profile = self._player_model.get_profile_dict()

        self._username_label.setText(profile.get("username", "—"))
        self._role_label.setText(profile.get("role", "—"))

        self._total_games_label.setText(str(profile.get("total_games", 0)))
        self._wins_label.setText(str(profile.get("wins", 0)))
        self._losses_label.setText(str(profile.get("losses", 0)))
        self._win_rate_label.setText(f"{profile.get('win_rate', 0):.1f}%")
        self._total_money_label.setText(f"{profile.get('total_money_earned', 0):,} $".replace(",", " "))
        self._highest_money_label.setText(f"{profile.get('highest_money', 0):,} $".replace(",", " "))
        self._bankruptcies_label.setText(str(profile.get("bankruptcies", 0)))

    # ========================================================================
    # ОБРАБОТЧИКИ
    # ========================================================================

    @Slot()
    def _on_edit_profile(self) -> None:
        """Редактировать профиль."""
        QMessageBox.information(self, "Профиль", "Редактирование профиля будет доступно в следующей версии.")

    @Slot()
    def _on_change_password(self) -> None:
        """Сменить пароль."""
        QMessageBox.information(self, "Пароль", "Смена пароля будет доступна в следующей версии.")

    @Slot()
    def _on_logout(self) -> None:
        """Выйти из аккаунта."""
        reply = QMessageBox.question(
            self,
            "Выход",
            "Вы уверены, что хотите выйти?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            self._player_model.logout()
            self.logout_clicked.emit()