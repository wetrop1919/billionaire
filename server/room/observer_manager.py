"""
server/room/observer_manager.py

Менеджер наблюдателей комнат.

Управляет наблюдателями, которые могут следить за игрой,
но не участвуют в ней. Наблюдатели видят поле и игроков,
но не могут совершать игровые действия.

Отдельный менеджер позволяет легко добавлять функции:
- Чат наблюдателей
- Переключение камеры между игроками
- Режим комментатора
- Статистика для наблюдателей

Python: 3.13+
"""

from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

from shared.enums import UserRole
from shared.permissions import has_permission, Permission

logger = logging.getLogger("billionaire.server")


# ============================================================================
# МЕНЕДЖЕР НАБЛЮДАТЕЛЕЙ
# ============================================================================

class ObserverManager:
    """
    Менеджер наблюдателей игровых комнат.

    Отслеживает активных наблюдателей, их права доступа
    и предоставляет методы для фильтрации информации.

    Attributes:
        _observers: Словарь {room_id: {observer_id: observer_data}}.
    """

    def __init__(self) -> None:
        """Инициализация менеджера наблюдателей."""
        # {room_id: {observer_id: {"user_id", "username", "role"}}}
        self._observers: dict[UUID, dict[UUID, dict[str, Any]]] = {}

        # Настройки видимости для каждого наблюдателя
        # {observer_id: {"show_all_money": bool, "observed_player_id": UUID}}
        self._observer_settings: dict[UUID, dict[str, Any]] = {}

    # ========================================================================
    # УПРАВЛЕНИЕ НАБЛЮДАТЕЛЯМИ
    # ========================================================================

    def add_observer(
        self,
        room_id: UUID,
        user_id: UUID,
        username: str,
        role: str = "observer",
    ) -> bool:
        """
        Добавить наблюдателя в комнату.

        Args:
            room_id: ID комнаты.
            user_id: ID пользователя.
            username: Имя пользователя.
            role: Роль пользователя.

        Returns:
            True, если наблюдатель добавлен.
        """
        if room_id not in self._observers:
            self._observers[room_id] = {}

        observer_data = {
            "user_id": user_id,
            "username": username,
            "role": role,
            "joined_at": None,  # Будет установлено при входе в комнату
        }

        self._observers[room_id][user_id] = observer_data

        # Настройки по умолчанию
        self._observer_settings[user_id] = {
            "show_all_money": role == "creator",
            "observed_player_id": None,
        }

        logger.info(
            "Наблюдатель %s добавлен в комнату %s",
            username,
            str(room_id)[:8],
        )

        return True

    def remove_observer(
        self,
        room_id: UUID,
        user_id: UUID,
    ) -> bool:
        """
        Удалить наблюдателя из комнаты.

        Args:
            room_id: ID комнаты.
            user_id: ID пользователя.

        Returns:
            True, если наблюдатель удалён.
        """
        room_observers = self._observers.get(room_id)
        if room_observers is None:
            return False

        observer = room_observers.pop(user_id, None)
        if observer is None:
            return False

        self._observer_settings.pop(user_id, None)

        logger.info(
            "Наблюдатель %s удалён из комнаты %s",
            observer.get("username", "?"),
            str(room_id)[:8],
        )

        # Очищаем пустую комнату
        if not room_observers:
            del self._observers[room_id]

        return True

    def is_observer(self, room_id: UUID, user_id: UUID) -> bool:
        """
        Проверить, является ли пользователь наблюдателем в комнате.

        Args:
            room_id: ID комнаты.
            user_id: ID пользователя.

        Returns:
            True, если пользователь — наблюдатель.
        """
        room_observers = self._observers.get(room_id, {})
        return user_id in room_observers

    # ========================================================================
    # ДОСТУП К ДАННЫМ
    # ========================================================================

    def get_observers(self, room_id: UUID) -> list[dict[str, Any]]:
        """
        Получить список наблюдателей комнаты.

        Args:
            room_id: ID комнаты.

        Returns:
            Список словарей с данными наблюдателей.
        """
        return list(self._observers.get(room_id, {}).values())

    def get_observer_count(self, room_id: UUID) -> int:
        """
        Получить количество наблюдателей в комнате.

        Args:
            room_id: ID комнаты.

        Returns:
            Количество наблюдателей.
        """
        return len(self._observers.get(room_id, {}))

    def get_observer_ids(self, room_id: UUID) -> list[UUID]:
        """
        Получить список ID наблюдателей комнаты.

        Args:
            room_id: ID комнаты.

        Returns:
            Список UUID.
        """
        return list(self._observers.get(room_id, {}).keys())

    # ========================================================================
    # ПРАВА И НАСТРОЙКИ
    # ========================================================================

    def can_see_all_money(self, observer_id: UUID) -> bool:
        """
        Проверить, может ли наблюдатель видеть деньги всех игроков.

        Args:
            observer_id: ID наблюдателя.

        Returns:
            True, если разрешено видеть все деньги.
        """
        settings = self._observer_settings.get(observer_id, {})
        return settings.get("show_all_money", False)

    def can_see_observers(self, observer_id: UUID) -> bool:
        """
        Проверить, может ли наблюдатель видеть других наблюдателей.

        Только Creator и модераторы видят список наблюдателей.

        Args:
            observer_id: ID наблюдателя.

        Returns:
            True, если разрешено.
        """
        settings = self._observer_settings.get(observer_id, {})
        return settings.get("show_all_money", False)

    def set_observed_player(
        self,
        observer_id: UUID,
        player_id: Optional[UUID],
    ) -> None:
        """
        Установить игрока, за которым следит наблюдатель (камера).

        Args:
            observer_id: ID наблюдателя.
            player_id: ID игрока (None — свободная камера).
        """
        if observer_id in self._observer_settings:
            self._observer_settings[observer_id]["observed_player_id"] = player_id

    def get_observed_player(self, observer_id: UUID) -> Optional[UUID]:
        """
        Получить ID игрока, за которым следит наблюдатель.

        Args:
            observer_id: ID наблюдателя.

        Returns:
            ID игрока или None.
        """
        settings = self._observer_settings.get(observer_id, {})
        return settings.get("observed_player_id")

    # ========================================================================
    # ФИЛЬТРАЦИЯ ДАННЫХ ДЛЯ НАБЛЮДАТЕЛЕЙ
    # ========================================================================

    def filter_player_data(
        self,
        observer_id: UUID,
        player_data: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Отфильтровать данные игрока для наблюдателя.

        Скрывает деньги, если наблюдатель не имеет права их видеть.

        Args:
            observer_id: ID наблюдателя.
            player_data: Полные данные игрока.

        Returns:
            Отфильтрованные данные.
        """
        if self.can_see_all_money(observer_id):
            return player_data

        # Скрываем деньги
        filtered = dict(player_data)
        filtered.pop("money", None)
        filtered.pop("total_earned", None)
        filtered.pop("total_spent", None)
        return filtered

    def filter_game_state(
        self,
        observer_id: UUID,
        game_state: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Отфильтровать состояние игры для наблюдателя.

        Args:
            observer_id: ID наблюдателя.
            game_state: Полное состояние игры.

        Returns:
            Отфильтрованное состояние.
        """
        # Фильтруем данные игроков
        players = game_state.get("players", {})
        filtered_players = {
            str(pid): self.filter_player_data(observer_id, pdata)
            for pid, pdata in players.items()
        }

        result = dict(game_state)
        result["players"] = filtered_players
        return result

    # ========================================================================
    # ОЧИСТКА
    # ========================================================================

    def remove_all_observers(self, room_id: UUID) -> int:
        """
        Удалить всех наблюдателей из комнаты.

        Args:
            room_id: ID комнаты.

        Returns:
            Количество удалённых наблюдателей.
        """
        room_observers = self._observers.pop(room_id, {})
        for observer_id in room_observers:
            self._observer_settings.pop(observer_id, None)

        logger.info(
            "Удалены все наблюдатели из комнаты %s (%d чел.)",
            str(room_id)[:8],
            len(room_observers),
        )

        return len(room_observers)

    def cleanup(self) -> int:
        """
        Очистить данные всех наблюдателей.

        Returns:
            Количество очищенных комнат.
        """
        count = len(self._observers)
        self._observers.clear()
        self._observer_settings.clear()
        return count

    # ========================================================================
    # ИНФОРМАЦИЯ
    # ========================================================================

    def get_stats(self) -> dict:
        """
        Получить статистику менеджера наблюдателей.

        Returns:
            Словарь с метриками.
        """
        total_observers = sum(
            len(observers) for observers in self._observers.values()
        )

        return {
            "active_rooms_with_observers": len(self._observers),
            "total_observers": total_observers,
        }