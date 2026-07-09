"""
client/views/chat_widget.py

Виджет чата.

Отображает сообщения чата и позволяет отправлять новые.
Поддерживает различные типы сообщений (игрок, система, игра, админ).

Python: 3.13+
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTextEdit,
    QLineEdit,
    QPushButton,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QGroupBox,
)
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QColor, QTextCursor

from client.viewmodels.chat_viewmodel import ChatViewModel

logger = logging.getLogger("billionaire.client")


# ============================================================================
# ВИДЖЕТ ЧАТА
# ============================================================================

class ChatWidget(QWidget):
    """
    Виджет чата.

    Отображает историю сообщений и поле ввода.
    Поддерживает цветовое выделение разных типов сообщений.

    Сигналы:
        message_sent — сообщение отправлено
    """

    message_sent = Signal(str)

    # Цвета для типов сообщений
    COLORS = {
        "player": "#ffffff",
        "system": "#f39c12",
        "game_event": "#2ecc71",
        "admin": "#e74c3c",
        "error": "#e74c3c",
    }

    def __init__(
        self,
        chat_vm: ChatViewModel,
        parent: Optional[QWidget] = None,
    ) -> None:
        """
        Инициализация виджета чата.

        Args:
            chat_vm: ViewModel чата.
            parent: Родительский виджет.
        """
        super().__init__(parent)

        self._chat_vm = chat_vm

        self._create_ui()
        self._connect_signals()

    # ========================================================================
    # UI
    # ========================================================================

    def _create_ui(self) -> None:
        """Создать интерфейс."""
        layout = QVBoxLayout(self)
        layout.setSpacing(5)

        # Заголовок
        header = QLabel("💬 Чат")
        header.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(header)

        # Область сообщений
        self._chat_display = QTextEdit()
        self._chat_display.setReadOnly(True)
        self._chat_display.setMinimumHeight(150)
        self._chat_display.setMaximumHeight(300)
        self._chat_display.setStyleSheet(
            "QTextEdit { background-color: #1a1a2e; color: #ffffff; "
            "border: 1px solid #333; border-radius: 4px; padding: 5px; }"
        )
        layout.addWidget(self._chat_display)

        # Поле ввода
        input_layout = QHBoxLayout()

        self._message_input = QLineEdit()
        self._message_input.setPlaceholderText("Введите сообщение...")
        self._message_input.setStyleSheet(
            "QLineEdit { padding: 8px; border: 1px solid #555; "
            "border-radius: 4px; background-color: #2a2a3e; color: #fff; }"
        )
        self._message_input.returnPressed.connect(self._send_message)
        input_layout.addWidget(self._message_input)

        self._send_button = QPushButton("📤")
        self._send_button.setFixedWidth(40)
        self._send_button.clicked.connect(self._send_message)
        self._send_button.setStyleSheet(
            "QPushButton { background-color: #3498db; color: white; "
            "border: none; border-radius: 4px; padding: 8px; }"
            "QPushButton:hover { background-color: #2980b9; }"
        )
        input_layout.addWidget(self._send_button)

        layout.addLayout(input_layout)

    # ========================================================================
    # СИГНАЛЫ
    # ========================================================================

    def _connect_signals(self) -> None:
        """Подключить сигналы."""
        self._chat_vm.message_received.connect(self._on_message_received)
        self._chat_vm.message_sent.connect(self._on_message_sent)

    # ========================================================================
    # ОТПРАВКА
    # ========================================================================

    @Slot()
    def _send_message(self) -> None:
        """Отправить сообщение."""
        text = self._message_input.text().strip()
        if not text:
            return

        if len(text) > 500:
            text = text[:500]

        self._chat_vm.send_message(text)
        self._message_input.clear()

    @Slot()
    def _on_message_sent(self) -> None:
        """Обработчик успешной отправки."""
        pass  # Сообщение появится при получении от сервера

    # ========================================================================
    # ПОЛУЧЕНИЕ
    # ========================================================================

    @Slot(dict)
    def _on_message_received(self, message: dict[str, Any]) -> None:
        """
        Обработать входящее сообщение.

        Args:
            message: Данные сообщения.
        """
        self._append_message(message)

    # ========================================================================
    # ОТОБРАЖЕНИЕ
    # ========================================================================

    def _append_message(self, message: dict[str, Any]) -> None:
        """
        Добавить сообщение в чат.

        Args:
            message: Данные сообщения.
        """
        msg_type = message.get("message_type", "player")
        username = message.get("username", "Система")
        content = message.get("content", "")
        timestamp = message.get("created_at", "")

        # Форматируем время
        time_str = ""
        if timestamp:
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                time_str = dt.strftime("%H:%M:%S")
            except Exception:
                pass

        # Выбираем цвет
        color = self.COLORS.get(msg_type, "#ffffff")

        # Формируем HTML
        if msg_type in ("system", "game_event"):
            # Системные сообщения — без имени
            html = (
                f'<div style="margin: 2px 0;">'
                f'<span style="color: #888; font-size: 10px;">{time_str}</span> '
                f'<span style="color: {color};">⚠ {content}</span>'
                f'</div>'
            )
        else:
            # Сообщения игроков
            html = (
                f'<div style="margin: 2px 0;">'
                f'<span style="color: #888; font-size: 10px;">{time_str}</span> '
                f'<span style="color: #3498db; font-weight: bold;">{username}:</span> '
                f'<span style="color: {color};">{content}</span>'
                f'</div>'
            )

        # Добавляем в чат
        cursor = self._chat_display.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self._chat_display.setTextCursor(cursor)
        self._chat_display.insertHtml(html)

        # Автопрокрутка
        scrollbar = self._chat_display.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def add_system_message(self, text: str) -> None:
        """
        Добавить системное сообщение напрямую.

        Args:
            text: Текст сообщения.
        """
        self._append_message({
            "message_type": "system",
            "content": text,
            "username": "Система",
        })

    # ========================================================================
    # УПРАВЛЕНИЕ
    # ========================================================================

    def clear(self) -> None:
        """Очистить чат."""
        self._chat_display.clear()

    def set_enabled(self, enabled: bool) -> None:
        """
        Включить/отключить ввод.

        Args:
            enabled: Доступность.
        """
        self._message_input.setEnabled(enabled)
        self._send_button.setEnabled(enabled)