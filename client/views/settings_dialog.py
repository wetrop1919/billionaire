"""
client/views/settings_dialog.py

Виджет настроек клиента.

Позволяет изменять язык, тему, громкость звука
и другие параметры клиента.

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
    QComboBox,
    QSlider,
    QCheckBox,
    QSpinBox,
    QFormLayout,
    QMessageBox,
)
from PySide6.QtCore import Qt, Signal, Slot

from client.config import ClientConfig

logger = logging.getLogger("billionaire.client")


# ============================================================================
# ВИДЖЕТ НАСТРОЕК
# ============================================================================

class SettingsWidget(QWidget):
    """
    Виджет настроек клиента.

    Позволяет изменять параметры и сохранять их в конфигурацию.

    Сигналы:
        settings_changed — настройки изменены
        back_clicked — нажата кнопка "Назад"
    """

    settings_changed = Signal()
    back_clicked = Signal()

    def __init__(
        self,
        config: ClientConfig,
        parent: Optional[QWidget] = None,
    ) -> None:
        """
        Инициализация виджета настроек.

        Args:
            config: Конфигурация клиента.
            parent: Родительский виджет.
        """
        super().__init__(parent)

        self._config = config

        self._create_ui()
        self._load_settings()

    # ========================================================================
    # UI
    # ========================================================================

    def _create_ui(self) -> None:
        """Создать интерфейс."""
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(30, 30, 30, 30)

        # Заголовок
        title = QLabel("⚙ Настройки")
        title.setStyleSheet("font-size: 24px; font-weight: bold;")
        layout.addWidget(title)

        # Общие настройки
        layout.addWidget(self._create_general_group())

        # Аудио
        layout.addWidget(self._create_audio_group())

        # Сеть
        layout.addWidget(self._create_network_group())

        # Уведомления
        layout.addWidget(self._create_notifications_group())

        # Кнопки
        buttons_layout = QHBoxLayout()

        self._save_button = QPushButton("💾 Сохранить")
        self._save_button.setMinimumHeight(40)
        self._save_button.clicked.connect(self._on_save)
        buttons_layout.addWidget(self._save_button)

        self._reset_button = QPushButton("🔄 Сбросить")
        self._reset_button.clicked.connect(self._on_reset)
        buttons_layout.addWidget(self._reset_button)

        self._back_button = QPushButton("← Назад")
        self._back_button.clicked.connect(self.back_clicked.emit)
        buttons_layout.addWidget(self._back_button)

        layout.addLayout(buttons_layout)
        layout.addStretch()

    def _create_general_group(self) -> QGroupBox:
        """Создать группу общих настроек."""
        group = QGroupBox("Общие")
        form = QFormLayout(group)

        self._language_combo = QComboBox()
        self._language_combo.addItems(["Русский", "English"])
        form.addRow("Язык:", self._language_combo)

        self._theme_combo = QComboBox()
        self._theme_combo.addItems(["Светлая", "Тёмная"])
        form.addRow("Тема:", self._theme_combo)

        return group

    def _create_audio_group(self) -> QGroupBox:
        """Создать группу настроек аудио."""
        group = QGroupBox("Аудио")
        form = QFormLayout(group)

        self._audio_check = QCheckBox("Включить звук")
        form.addRow(self._audio_check)

        self._music_slider = QSlider(Qt.Orientation.Horizontal)
        self._music_slider.setRange(0, 100)
        form.addRow("Громкость музыки:", self._music_slider)

        self._music_value_label = QLabel("50%")
        self._music_slider.valueChanged.connect(
            lambda v: self._music_value_label.setText(f"{v}%")
        )
        form.addRow("", self._music_value_label)

        self._effects_slider = QSlider(Qt.Orientation.Horizontal)
        self._effects_slider.setRange(0, 100)
        form.addRow("Громкость эффектов:", self._effects_slider)

        self._effects_value_label = QLabel("70%")
        self._effects_slider.valueChanged.connect(
            lambda v: self._effects_value_label.setText(f"{v}%")
        )
        form.addRow("", self._effects_value_label)

        return group

    def _create_network_group(self) -> QGroupBox:
        """Создать группу сетевых настроек."""
        group = QGroupBox("Сеть")
        form = QFormLayout(group)

        self._reconnect_check = QCheckBox("Автоматическое переподключение")
        form.addRow(self._reconnect_check)

        self._reconnect_spin = QSpinBox()
        self._reconnect_spin.setRange(1, 20)
        form.addRow("Попыток переподключения:", self._reconnect_spin)

        return group

    def _create_notifications_group(self) -> QGroupBox:
        """Создать группу настроек уведомлений."""
        group = QGroupBox("Уведомления")
        form = QFormLayout(group)

        self._notifications_check = QCheckBox("Показывать уведомления")
        form.addRow(self._notifications_check)

        self._auto_close_spin = QSpinBox()
        self._auto_close_spin.setRange(1, 30)
        self._auto_close_spin.setSuffix(" сек")
        form.addRow("Автозакрытие:", self._auto_close_spin)

        return group

    # ========================================================================
    # ЗАГРУЗКА / СОХРАНЕНИЕ
    # ========================================================================

    def _load_settings(self) -> None:
        """Загрузить текущие настройки."""
        # Общие
        self._language_combo.setCurrentIndex(0 if self._config.language == "ru" else 1)
        self._theme_combo.setCurrentIndex(0 if self._config.theme == "light" else 1)

        # Аудио
        self._audio_check.setChecked(self._config.audio_enabled)
        self._music_slider.setValue(self._config.music_volume)
        self._effects_slider.setValue(self._config.effects_volume)

        # Сеть
        self._reconnect_check.setChecked(self._config.auto_reconnect)
        self._reconnect_spin.setValue(self._config.reconnect_attempts)

        # Уведомления
        self._notifications_check.setChecked(self._config.notifications_enabled)
        self._auto_close_spin.setValue(self._config.notifications_auto_close)

    def _on_save(self) -> None:
        """Сохранить настройки."""
        # Общие
        self._config.language = "ru" if self._language_combo.currentIndex() == 0 else "en"
        self._config.theme = "light" if self._theme_combo.currentIndex() == 0 else "dark"

        # Аудио
        self._config.audio_enabled = self._audio_check.isChecked()
        self._config.music_volume = self._music_slider.value()
        self._config.effects_volume = self._effects_slider.value()

        # Сеть
        self._config.auto_reconnect = self._reconnect_check.isChecked()
        self._config.reconnect_attempts = self._reconnect_spin.value()

        # Уведомления
        self._config.notifications_enabled = self._notifications_check.isChecked()
        self._config.notifications_auto_close = self._auto_close_spin.value()

        # Сохраняем в файл
        self._config.save()

        self.settings_changed.emit()

        QMessageBox.information(self, "Настройки", "Настройки сохранены!")

    def _on_reset(self) -> None:
        """Сбросить настройки к значениям по умолчанию."""
        reply = QMessageBox.question(
            self,
            "Сброс",
            "Сбросить все настройки к значениям по умолчанию?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            self._config.language = "ru"
            self._config.theme = "light"
            self._config.audio_enabled = True
            self._config.music_volume = 50
            self._config.effects_volume = 70
            self._config.auto_reconnect = True
            self._config.reconnect_attempts = 5
            self._config.notifications_enabled = True
            self._config.notifications_auto_close = 5

            self._load_settings()
            self._config.save()
            self.settings_changed.emit()

            QMessageBox.information(self, "Настройки", "Настройки сброшены!")