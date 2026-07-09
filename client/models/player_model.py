"""
client/models/player_model.py

Qt-модель данных игрока для клиента.

Хранит информацию о текущем пользователе:
профиль, статистику, настройки.

Python: 3.13+
"""

from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

from PySide6.QtCore import QObject, Signal, Property

logger = logging.getLogger("billionaire.client")


# ============================================================================
# МОДЕЛЬ ИГРОКА
# ============================================================================

class PlayerModel(QObject):
    """
    Qt-модель данных текущего игрока.

    Хранит профиль пользователя, статистику и настройки.
    Обновляется при входе и получении данных профиля.

    Сигналы:
        profile_updated — при обновлении профиля
        stats_updated — при обновлении статистики
        logged_in — после успешного входа
        logged_out — после выхода
    """

    # Сигналы
    profile_updated = Signal()
    stats_updated = Signal()
    logged_in = Signal()
    logged_out = Signal()
    money_changed = Signal(int)  # new_amount
    error_occurred = Signal(str)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        """
        Инициализация модели игрока.

        Args:
            parent: Родительский QObject.
        """
        super().__init__(parent)

        # Основные данные
        self._user_id: Optional[UUID] = None
        self._username: str = ""
        self._role: str = ""
        self._is_logged_in: bool = False

        # Статистика
        self._total_games: int = 0
        self._wins: int = 0
        self._losses: int = 0
        self._win_rate: float = 0.0
        self._total_money_earned: int = 0
        self._highest_money: int = 0
        self._bankruptcies: int = 0
        self._properties_bought: int = 0
        self._houses_built: int = 0
        self._hotels_built: int = 0
        self._play_time_minutes: int = 0

        # Игровые данные
        self._current_money: int = 0
        self._current_position: int = 0
        self._current_properties: list[str] = []
        self._is_in_jail: bool = False
        self._is_bankrupt: bool = False
        self._color: str = "#3498db"

    # ========================================================================
    # Q_PROPERTY
    # ========================================================================

    def get_username(self) -> str:
        return self._username

    def get_role(self) -> str:
        return self._role

    def get_is_logged_in(self) -> bool:
        return self._is_logged_in

    def get_current_money(self) -> int:
        return self._current_money

    def get_color(self) -> str:
        return self._color

    username = Property(str, get_username, notify=profile_updated)
    role = Property(str, get_role, notify=profile_updated)
    isLoggedIn = Property(bool, get_is_logged_in, notify=profile_updated)
    currentMoney = Property(int, get_current_money, notify=money_changed)
    color = Property(str, get_color, notify=profile_updated)

    # ========================================================================
    # ОБНОВЛЕНИЕ ДАННЫХ
    # ========================================================================

    def set_profile(self, data: dict[str, Any]) -> None:
        """
        Установить данные профиля.

        Args:
            data: Данные профиля от сервера.
        """
        self._user_id = UUID(data["user_id"]) if data.get("user_id") else None
        self._username = data.get("username", "")
        self._role = data.get("role", "")
        self._is_logged_in = True

        self.profile_updated.emit()
        self.logged_in.emit()

    def set_stats(self, data: dict[str, Any]) -> None:
        """
        Установить статистику игрока.

        Args:
            data: Данные статистики.
        """
        self._total_games = data.get("total_games", 0)
        self._wins = data.get("wins", 0)
        self._losses = data.get("losses", 0)
        self._win_rate = data.get("win_rate", 0.0)
        self._total_money_earned = data.get("total_money_earned", 0)
        self._highest_money = data.get("highest_money", 0)
        self._bankruptcies = data.get("bankruptcies", 0)
        self._properties_bought = data.get("properties_bought", 0)
        self._houses_built = data.get("houses_built", 0)
        self._hotels_built = data.get("hotels_built", 0)
        self._play_time_minutes = data.get("total_play_time_minutes", 0)

        self.stats_updated.emit()

    def update_game_state(self, data: dict[str, Any]) -> None:
        """
        Обновить игровое состояние.

        Args:
            data: Данные состояния игрока из игры.
        """
        old_money = self._current_money

        self._current_money = data.get("money", self._current_money)
        self._current_position = data.get("position", {}).get("cell_id", self._current_position)
        self._current_properties = data.get("properties", self._current_properties)
        self._is_in_jail = data.get("in_jail", self._is_in_jail)
        self._is_bankrupt = data.get("bankrupt", self._is_bankrupt)
        self._color = data.get("color", self._color)

        if self._current_money != old_money:
            self.money_changed.emit(self._current_money)

        self.profile_updated.emit()

    def logout(self) -> None:
        """Очистить данные при выходе."""
        self._user_id = None
        self._username = ""
        self._role = ""
        self._is_logged_in = False
        self._current_money = 0
        self._current_properties.clear()
        self._is_in_jail = False
        self._is_bankrupt = False

        self.logged_out.emit()
        self.profile_updated.emit()

    # ========================================================================
    # ДОСТУП К ДАННЫМ
    # ========================================================================

    @property
    def user_id(self) -> Optional[UUID]:
        return self._user_id

    @property
    def is_logged_in(self) -> bool:
        return self._is_logged_in

    @property
    def total_games(self) -> int:
        return self._total_games

    @property
    def wins(self) -> int:
        return self._wins

    @property
    def win_rate(self) -> float:
        return self._win_rate

    @property
    def is_bankrupt(self) -> bool:
        return self._is_bankrupt

    @property
    def is_in_jail(self) -> bool:
        return self._is_in_jail

    def get_profile_dict(self) -> dict[str, Any]:
        """Получить профиль как словарь."""
        return {
            "user_id": str(self._user_id) if self._user_id else None,
            "username": self._username,
            "role": self._role,
            "total_games": self._total_games,
            "wins": self._wins,
            "losses": self._losses,
            "win_rate": self._win_rate,
            "total_money_earned": self._total_money_earned,
            "highest_money": self._highest_money,
            "bankruptcies": self._bankruptcies,
        }

    def clear(self) -> None:
        """Очистить модель."""
        self.logout()