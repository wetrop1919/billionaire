"""
server/admin/admin_commands.py

Модуль административных команд.

Предоставляет Creator полный контроль над игрой:
- Изменение денег игроков
- Изменение собственности
- Телепортация
- Изменение ролей
- Просмотр логов
- Отмена действий (undo)
- Управление сервером

Все команды проверяют права доступа через Permission.

Python: 3.13+
"""

from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

from shared.enums import UserRole, EventType
from shared.permissions import has_permission, Permission
from server.event.event_bus import EventBus
from server.game.game_manager import GameManager
from server.game.undo_stack import UndoStack
from server.game.jail_manager import JailManager
from server.game.veranda_manager import VerandaManager

logger = logging.getLogger("billionaire.admin")


# ============================================================================
# АДМИН-КОМАНДЫ
# ============================================================================

class AdminCommands:
    """
    Обработчик административных команд.

    Предоставляет методы для управления игрой и сервером.
    Все методы требуют соответствующих прав доступа.

    Usage:
        admin = AdminCommands(game_manager, undo_stack, event_bus)
        result = await admin.set_money(admin_id, player_id, 5000)
    """

    def __init__(
        self,
        game_manager: GameManager,
        undo_stack: UndoStack,
        event_bus: EventBus,
        jail_manager: JailManager,
        veranda_manager: VerandaManager,
    ) -> None:
        """
        Инициализация админ-команд.

        Args:
            game_manager: Менеджер игр.
            undo_stack: Стек отмены.
            event_bus: Шина событий.
            jail_manager: Менеджер тюрьмы.
            veranda_manager: Менеджер Веранды.
        """
        self._game_manager = game_manager
        self._undo_stack = undo_stack
        self._event_bus = event_bus
        self._jail_manager = jail_manager
        self._veranda_manager = veranda_manager

    # ========================================================================
    # ПРОВЕРКА ПРАВ
    # ========================================================================

    def _check_permission(
        self,
        admin_role: str,
        permission: Permission,
    ) -> Optional[str]:
        """
        Проверить права администратора.

        Args:
            admin_role: Роль администратора.
            permission: Требуемое право.

        Returns:
            Сообщение об ошибке или None.
        """
        try:
            role = UserRole(admin_role)
            if not has_permission(role, permission):
                return f"Недостаточно прав: требуется '{permission.value}'"
            return None
        except ValueError:
            return f"Неизвестная роль: {admin_role}"

    # ========================================================================
    # ДЕНЬГИ
    # ========================================================================

    async def set_money(
        self,
        admin_id: UUID,
        admin_role: str,
        game_id: UUID,
        player_id: UUID,
        amount: int,
    ) -> dict[str, Any]:
        """
        Установить количество денег игроку.

        Args:
            admin_id: ID администратора.
            admin_role: Роль администратора.
            game_id: ID игры.
            player_id: ID игрока.
            amount: Новая сумма.

        Returns:
            Результат операции.
        """
        error = self._check_permission(admin_role, Permission.CHEAT_MONEY)
        if error:
            return {"success": False, "error": error}

        game = self._game_manager.get_game(game_id)
        if game is None:
            return {"success": False, "error": "Игра не найдена"}

        player = game.players.get(player_id)
        if player is None:
            return {"success": False, "error": "Игрок не найден"}

        old_amount = player.money
        player.money = max(0, amount)

        await self._event_bus.publish(
            EventType.ADMIN_ACTION,
            {
                "admin_id": str(admin_id),
                "command": "set_money",
                "target_id": str(player_id),
                "parameters": {
                    "old_amount": old_amount,
                    "new_amount": player.money,
                },
            },
        )

        logger.info(
            "Админ %s изменил деньги игрока %s: %d$ → %d$",
            str(admin_id)[:8],
            player.username,
            old_amount,
            player.money,
        )

        return {
            "success": True,
            "player_id": str(player_id),
            "old_amount": old_amount,
            "new_amount": player.money,
        }

    async def add_money(
        self,
        admin_id: UUID,
        admin_role: str,
        game_id: UUID,
        player_id: UUID,
        amount: int,
    ) -> dict[str, Any]:
        """
        Добавить деньги игроку.

        Args:
            admin_id: ID администратора.
            admin_role: Роль администратора.
            game_id: ID игры.
            player_id: ID игрока.
            amount: Сумма для добавления.

        Returns:
            Результат операции.
        """
        error = self._check_permission(admin_role, Permission.CHEAT_MONEY)
        if error:
            return {"success": False, "error": error}

        game = self._game_manager.get_game(game_id)
        if game is None:
            return {"success": False, "error": "Игра не найдена"}

        player = game.players.get(player_id)
        if player is None:
            return {"success": False, "error": "Игрок не найден"}

        old_amount = player.money
        player.add_money(amount, "admin_gift")

        logger.info(
            "Админ %s добавил %d$ игроку %s",
            str(admin_id)[:8],
            amount,
            player.username,
        )

        return {
            "success": True,
            "player_id": str(player_id),
            "added": amount,
            "old_amount": old_amount,
            "new_amount": player.money,
        }

    # ========================================================================
    # СОБСТВЕННОСТЬ
    # ========================================================================

    async def set_property(
        self,
        admin_id: UUID,
        admin_role: str,
        game_id: UUID,
        player_id: UUID,
        property_id: str,
        houses: int = 0,
        has_hotel: bool = False,
    ) -> dict[str, Any]:
        """
        Установить собственность игроку.

        Args:
            admin_id: ID администратора.
            admin_role: Роль администратора.
            game_id: ID игры.
            player_id: ID игрока.
            property_id: ID собственности.
            houses: Количество домов (0-4).
            has_hotel: Построить отель.

        Returns:
            Результат операции.
        """
        error = self._check_permission(admin_role, Permission.CHEAT_PROPERTY)
        if error:
            return {"success": False, "error": error}

        game = self._game_manager.get_game(game_id)
        if game is None:
            return {"success": False, "error": "Игра не найдена"}

        prop_state = game.properties.get(property_id)
        if prop_state is None:
            return {"success": False, "error": "Собственность не найдена"}

        player = game.players.get(player_id)
        if player is None:
            return {"success": False, "error": "Игрок не найден"}

        old_owner = prop_state.owner_id
        prop_state.owner_id = player_id
        prop_state.houses = max(0, min(4, houses))
        prop_state.has_hotel = has_hotel
        prop_state.mortgaged = False

        if property_id not in player.properties:
            player.add_property(property_id)

        await self._event_bus.publish(
            EventType.ADMIN_ACTION,
            {
                "admin_id": str(admin_id),
                "command": "set_property",
                "target_id": str(player_id),
                "parameters": {
                    "property_id": property_id,
                    "houses": houses,
                    "has_hotel": has_hotel,
                    "previous_owner": str(old_owner) if old_owner else None,
                },
            },
        )

        logger.info(
            "Админ %s передал %s игроку %s",
            str(admin_id)[:8],
            property_id,
            player.username,
        )

        return {
            "success": True,
            "property_id": property_id,
            "player_id": str(player_id),
            "previous_owner": str(old_owner) if old_owner else None,
        }

    async def clear_property(
        self,
        admin_id: UUID,
        admin_role: str,
        game_id: UUID,
        property_id: str,
    ) -> dict[str, Any]:
        """
        Вернуть собственность банку.

        Args:
            admin_id: ID администратора.
            admin_role: Роль администратора.
            game_id: ID игры.
            property_id: ID собственности.

        Returns:
            Результат операции.
        """
        error = self._check_permission(admin_role, Permission.CHEAT_PROPERTY)
        if error:
            return {"success": False, "error": error}

        game = self._game_manager.get_game(game_id)
        if game is None:
            return {"success": False, "error": "Игра не найдена"}

        prop_state = game.properties.get(property_id)
        if prop_state is None:
            return {"success": False, "error": "Собственность не найдена"}

        old_owner = prop_state.owner_id
        prop_state.remove_owner()

        if old_owner:
            player = game.players.get(old_owner)
            if player and property_id in player.properties:
                player.remove_property(property_id)

        logger.info(
            "Админ %s вернул %s банку",
            str(admin_id)[:8],
            property_id,
        )

        return {
            "success": True,
            "property_id": property_id,
            "previous_owner": str(old_owner) if old_owner else None,
        }

    # ========================================================================
    # ТЕЛЕПОРТАЦИЯ
    # ========================================================================

    async def teleport_player(
        self,
        admin_id: UUID,
        admin_role: str,
        game_id: UUID,
        player_id: UUID,
        cell_id: int,
    ) -> dict[str, Any]:
        """
        Телепортировать игрока на указанную клетку.

        Args:
            admin_id: ID администратора.
            admin_role: Роль администратора.
            game_id: ID игры.
            player_id: ID игрока.
            cell_id: ID целевой клетки (0-39).

        Returns:
            Результат операции.
        """
        error = self._check_permission(admin_role, Permission.CHEAT_TELEPORT)
        if error:
            return {"success": False, "error": error}

        game = self._game_manager.get_game(game_id)
        if game is None:
            return {"success": False, "error": "Игра не найдена"}

        player = game.players.get(player_id)
        if player is None:
            return {"success": False, "error": "Игрок не найден"}

        old_position = player.position.cell_id
        player.position.teleport(cell_id)

        logger.info(
            "Админ %s телепортировал %s: клетка %d → %d",
            str(admin_id)[:8],
            player.username,
            old_position,
            cell_id,
        )

        return {
            "success": True,
            "player_id": str(player_id),
            "old_cell": old_position,
            "new_cell": cell_id,
        }

    # ========================================================================
    # ТЮРЬМА И ВЕРАНДА
    # ========================================================================

    async def free_from_jail(
        self,
        admin_id: UUID,
        admin_role: str,
        game_id: UUID,
        player_id: UUID,
    ) -> dict[str, Any]:
        """
        Освободить игрока из тюрьмы.

        Args:
            admin_id: ID администратора.
            admin_role: Роль администратора.
            game_id: ID игры.
            player_id: ID игрока.

        Returns:
            Результат операции.
        """
        error = self._check_permission(admin_role, Permission.CHEAT_TELEPORT)
        if error:
            return {"success": False, "error": error}

        game = self._game_manager.get_game(game_id)
        if game is None:
            return {"success": False, "error": "Игра не найдена"}

        player = game.players.get(player_id)
        if player is None:
            return {"success": False, "error": "Игрок не найден"}

        if not player.in_jail:
            return {"success": False, "error": "Игрок не в тюрьме"}

        self._jail_manager.force_release(player)

        logger.info(
            "Админ %s освободил %s из тюрьмы",
            str(admin_id)[:8],
            player.username,
        )

        return {"success": True, "player_id": str(player_id)}

    async def free_from_veranda(
        self,
        admin_id: UUID,
        admin_role: str,
        game_id: UUID,
        player_id: UUID,
    ) -> dict[str, Any]:
        """
        Убрать игрока с Веранды.

        Args:
            admin_id: ID администратора.
            admin_role: Роль администратора.
            game_id: ID игры.
            player_id: ID игрока.

        Returns:
            Результат операции.
        """
        error = self._check_permission(admin_role, Permission.CHEAT_TELEPORT)
        if error:
            return {"success": False, "error": error}

        game = self._game_manager.get_game(game_id)
        if game is None:
            return {"success": False, "error": "Игра не найдена"}

        player = game.players.get(player_id)
        if player is None:
            return {"success": False, "error": "Игрок не найден"}

        if not self._veranda_manager.is_on_veranda(player_id):
            return {"success": False, "error": "Игрок не на Веранде"}

        self._veranda_manager.force_exit(player)

        logger.info(
            "Админ %s убрал %s с Веранды",
            str(admin_id)[:8],
            player.username,
        )

        return {"success": True, "player_id": str(player_id)}

    # ========================================================================
    # UNDO
    # ========================================================================

    async def undo_action(
        self,
        admin_id: UUID,
        admin_role: str,
        game_id: UUID,
        steps: int = 1,
    ) -> dict[str, Any]:
        """
        Отменить последние действия.

        Args:
            admin_id: ID администратора.
            admin_role: Роль администратора.
            game_id: ID игры.
            steps: Количество действий для отмены.

        Returns:
            Результат операции.
        """
        error = self._check_permission(admin_role, Permission.CHEAT_UNDO)
        if error:
            return {"success": False, "error": error}

        game = self._game_manager.get_game(game_id)
        if game is None:
            return {"success": False, "error": "Игра не найдена"}

        if not self._undo_stack.can_undo():
            return {"success": False, "error": "Стек отмены пуст"}

        context = {
            "players": game.players,
            "properties": game.properties,
        }

        undone = await self._undo_stack.undo_multiple(steps, context)

        logger.info(
            "Админ %s отменил %d действий в игре %s",
            str(admin_id)[:8],
            len(undone),
            str(game_id)[:8],
        )

        return {
            "success": True,
            "undone_count": len(undone),
            "actions": [a.description for a in undone],
        }

    # ========================================================================
    # ИНФОРМАЦИЯ
    # ========================================================================

    async def get_game_data(
        self,
        admin_id: UUID,
        admin_role: str,
        game_id: UUID,
    ) -> dict[str, Any]:
        """
        Получить полные данные игры (для Creator).

        Args:
            admin_id: ID администратора.
            admin_role: Роль администратора.
            game_id: ID игры.

        Returns:
            Полные данные игры.
        """
        error = self._check_permission(admin_role, Permission.VIEW_ALL_MONEY)
        if error:
            return {"success": False, "error": error}

        game = self._game_manager.get_game(game_id)
        if game is None:
            return {"success": False, "error": "Игра не найдена"}

        return {
            "success": True,
            "game": game.to_dict(),
        }

    async def get_undo_history(
        self,
        admin_id: UUID,
        admin_role: str,
        limit: int = 20,
    ) -> dict[str, Any]:
        """
        Получить историю отмены.

        Args:
            admin_id: ID администратора.
            admin_role: Роль администратора.
            limit: Количество записей.

        Returns:
            История действий.
        """
        error = self._check_permission(admin_role, Permission.VIEW_LOGS)
        if error:
            return {"success": False, "error": error}

        history = self._undo_stack.get_history(limit=limit)

        return {
            "success": True,
            "history": history,
            "can_undo": self._undo_stack.can_undo(),
        }

    # ========================================================================
    # УПРАВЛЕНИЕ СЕРВЕРОМ
    # ========================================================================

    async def broadcast_message(
        self,
        admin_id: UUID,
        admin_role: str,
        message: str,
    ) -> dict[str, Any]:
        """
        Отправить объявление всем игрокам.

        Args:
            admin_id: ID администратора.
            admin_role: Роль администратора.
            message: Текст объявления.

        Returns:
            Результат операции.
        """
        error = self._check_permission(admin_role, Permission.CHAT_SYSTEM_MESSAGE)
        if error:
            return {"success": False, "error": error}

        await self._event_bus.publish(
            EventType.ADMIN_ACTION,
            {
                "admin_id": str(admin_id),
                "command": "broadcast",
                "parameters": {"message": message},
            },
        )

        logger.info(
            "Админ %s отправил объявление: %s",
            str(admin_id)[:8],
            message[:50],
        )

        return {
            "success": True,
            "message": message,
        }

    def get_stats(self) -> dict:
        """
        Получить статистику админ-команд.

        Returns:
            Словарь с метриками.
        """
        return {
            "undo_stack": self._undo_stack.get_stats(),
        }