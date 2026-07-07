"""
shared/permissions.py

Система разрешений (Permissions) для проекта "Миллиардер".

Вместо жёстко заданных ролей используется гибкая система прав доступа.
Каждая роль (UserRole) состоит из набора Permission.
Это позволяет легко добавлять новые роли или изменять существующие
без модификации кода, проверяющего доступ.

Использование:
    from shared.permissions import Permission, RolePermissions, has_permission

    # Проверка наличия права
    if has_permission(user_role, Permission.ADMIN_COMMANDS):
        execute_admin_command()

    # Получение всех прав роли
    permissions = RolePermissions.get_permissions(UserRole.CREATOR)

Python: 3.13+
"""

from __future__ import annotations

from enum import StrEnum
from typing import FrozenSet

from shared.enums import UserRole


# ============================================================================
# ПРАВА ДОСТУПА (Permissions)
# ============================================================================

class Permission(StrEnum):
    """
    Отдельные права доступа в системе.

    Каждое право представляет собой атомарное действие или категорию действий,
    которые могут быть разрешены или запрещены для пользователя.

    Права сгруппированы по категориям:
    - GAME: действия в игре
    - ROOM: управление комнатами
    - CHAT: общение
    - VIEW: просмотр информации
    - ADMIN: административные функции
    - CHEAT: чит-команды (только для Creator)
    - SERVER: управление сервером
    """

    # === ИГРОВЫЕ ДЕЙСТВИЯ (Game Actions) ===
    PLAY_GAME = "play_game"                        # Участвовать в игре как игрок
    ROLL_DICE = "roll_dice"                        # Бросать кубики
    BUY_PROPERTY = "buy_property"                  # Покупать собственность
    BUILD_HOUSE = "build_house"                    # Строить дома
    BUILD_HOTEL = "build_hotel"                    # Строить отели
    MORTGAGE_PROPERTY = "mortgage_property"        # Закладывать собственность
    UNMORTGAGE_PROPERTY = "unmortgage_property"    # Выкупать из залога
    TRADE_INITIATE = "trade_initiate"              # Инициировать торговлю
    TRADE_ACCEPT = "trade_accept"                  # Принимать торговые предложения
    AUCTION_BID = "auction_bid"                    # Участвовать в аукционе
    USE_JAIL_CARD = "use_jail_card"                # Использовать карточку освобождения
    PAY_JAIL_FINE = "pay_jail_fine"                # Платить штраф за выход из тюрьмы
    PAY_VERANDA_EXIT = "pay_veranda_exit"          # Платить за выход с Веранды

    # === УПРАВЛЕНИЕ КОМНАТАМИ (Room Management) ===
    CREATE_ROOM = "create_room"                    # Создавать комнаты
    DELETE_ROOM = "delete_room"                    # Удалять комнаты
    JOIN_ROOM = "join_room"                        # Входить в комнаты
    LEAVE_ROOM = "leave_room"                      # Покидать комнаты
    KICK_PLAYER = "kick_player"                    # Выгонять игроков из комнаты
    CHANGE_ROOM_SETTINGS = "change_room_settings"  # Изменять настройки комнаты
    START_GAME = "start_game"                      # Запускать игру
    PAUSE_GAME = "pause_game"                      # Ставить игру на паузу
    RESUME_GAME = "resume_game"                    # Возобновлять игру
    END_GAME = "end_game"                          # Принудительно завершать игру

    # === ЧАТ (Chat) ===
    CHAT_SEND = "chat_send"                        # Отправлять сообщения в чат
    CHAT_DELETE = "chat_delete"                    # Удалять сообщения чата
    CHAT_SYSTEM_MESSAGE = "chat_system_message"    # Отправлять системные сообщения

    # === ПРОСМОТР ИНФОРМАЦИИ (View Permissions) ===
    VIEW_GAME = "view_game"                        # Наблюдать за игрой
    VIEW_OWN_MONEY = "view_own_money"              # Видеть свои деньги
    VIEW_ALL_MONEY = "view_all_money"              # Видеть деньги всех игроков
    VIEW_OBSERVERS = "view_observers"              # Видеть список наблюдателей
    VIEW_HIDDEN_PLAYERS = "view_hidden_players"    # Видеть скрытых игроков
    VIEW_LOGS = "view_logs"                        # Просматривать логи
    VIEW_GAME_HISTORY = "view_game_history"        # Просматривать историю игр
    VIEW_PLAYER_PROFILES = "view_player_profiles"  # Просматривать профили игроков
    VIEW_STATISTICS = "view_statistics"            # Просматривать статистику

    # === АДМИНИСТРАТИВНЫЕ ФУНКЦИИ (Admin Functions) ===
    ADMIN_COMMANDS = "admin_commands"              # Доступ к админ-панели
    MANAGE_ROLES = "manage_roles"                  # Изменять роли пользователей
    MANAGE_PERMISSIONS = "manage_permissions"      # Управлять правами
    BAN_USER = "ban_user"                          # Блокировать пользователей
    UNBAN_USER = "unban_user"                      # Разблокировать пользователей
    MODERATE_CHAT = "moderate_chat"                # Модерировать чат

    # === ЧИТ-КОМАНДЫ (Cheat Commands) ===
    CHEAT_MONEY = "cheat_money"                    # Изменять деньги игроков
    CHEAT_PROPERTY = "cheat_property"              # Изменять собственность
    CHEAT_TELEPORT = "cheat_teleport"              # Телепортировать игроков
    CHEAT_CARD = "cheat_card"                      # Выдавать карточки
    CHEAT_UNDO = "cheat_undo"                      # Отменять действия

    # === УПРАВЛЕНИЕ СЕРВЕРОМ (Server Management) ===
    SERVER_COMMANDS = "server_commands"            # Выполнять серверные команды
    SERVER_SHUTDOWN = "server_shutdown"            # Останавливать сервер
    SERVER_RESTART = "server_restart"              # Перезапускать сервер
    SERVER_BACKUP = "server_backup"                # Создавать резервные копии
    SERVER_RESTORE = "server_restore"              # Восстанавливать из копии
    RELOAD_CONFIG = "reload_config"                # Перезагружать конфигурацию
    MANAGE_SESSIONS = "manage_sessions"            # Управлять сессиями


# ============================================================================
# НАБОРЫ ПРАВ ДЛЯ РОЛЕЙ (Role Permissions)
# ============================================================================

class RolePermissions:
    """
    Статическое сопоставление ролей и наборов прав.

    Каждая роль содержит строго определённый набор Permission.
    Для добавления новой роли достаточно создать новый набор прав
    и сопоставить его с UserRole в словаре _ROLE_PERMISSIONS.
    """

    # Права для роли CREATOR (Создатель) — полный доступ
    CREATOR_PERMISSIONS: FrozenSet[Permission] = frozenset({
        # Игровые действия
        Permission.PLAY_GAME,
        Permission.ROLL_DICE,
        Permission.BUY_PROPERTY,
        Permission.BUILD_HOUSE,
        Permission.BUILD_HOTEL,
        Permission.MORTGAGE_PROPERTY,
        Permission.UNMORTGAGE_PROPERTY,
        Permission.TRADE_INITIATE,
        Permission.TRADE_ACCEPT,
        Permission.AUCTION_BID,
        Permission.USE_JAIL_CARD,
        Permission.PAY_JAIL_FINE,
        Permission.PAY_VERANDA_EXIT,
        # Управление комнатами
        Permission.CREATE_ROOM,
        Permission.DELETE_ROOM,
        Permission.JOIN_ROOM,
        Permission.LEAVE_ROOM,
        Permission.KICK_PLAYER,
        Permission.CHANGE_ROOM_SETTINGS,
        Permission.START_GAME,
        Permission.PAUSE_GAME,
        Permission.RESUME_GAME,
        Permission.END_GAME,
        # Чат
        Permission.CHAT_SEND,
        Permission.CHAT_DELETE,
        Permission.CHAT_SYSTEM_MESSAGE,
        # Просмотр
        Permission.VIEW_GAME,
        Permission.VIEW_OWN_MONEY,
        Permission.VIEW_ALL_MONEY,
        Permission.VIEW_OBSERVERS,
        Permission.VIEW_HIDDEN_PLAYERS,
        Permission.VIEW_LOGS,
        Permission.VIEW_GAME_HISTORY,
        Permission.VIEW_PLAYER_PROFILES,
        Permission.VIEW_STATISTICS,
        # Администрирование
        Permission.ADMIN_COMMANDS,
        Permission.MANAGE_ROLES,
        Permission.MANAGE_PERMISSIONS,
        Permission.BAN_USER,
        Permission.UNBAN_USER,
        Permission.MODERATE_CHAT,
        # Чит-команды
        Permission.CHEAT_MONEY,
        Permission.CHEAT_PROPERTY,
        Permission.CHEAT_TELEPORT,
        Permission.CHEAT_CARD,
        Permission.CHEAT_UNDO,
        # Управление сервером
        Permission.SERVER_COMMANDS,
        Permission.SERVER_SHUTDOWN,
        Permission.SERVER_RESTART,
        Permission.SERVER_BACKUP,
        Permission.SERVER_RESTORE,
        Permission.RELOAD_CONFIG,
        Permission.MANAGE_SESSIONS,
    })

    # Права для роли PLAYER (Игрок)
    PLAYER_PERMISSIONS: FrozenSet[Permission] = frozenset({
        # Игровые действия
        Permission.PLAY_GAME,
        Permission.ROLL_DICE,
        Permission.BUY_PROPERTY,
        Permission.BUILD_HOUSE,
        Permission.BUILD_HOTEL,
        Permission.MORTGAGE_PROPERTY,
        Permission.UNMORTGAGE_PROPERTY,
        Permission.TRADE_INITIATE,
        Permission.TRADE_ACCEPT,
        Permission.AUCTION_BID,
        Permission.USE_JAIL_CARD,
        Permission.PAY_JAIL_FINE,
        Permission.PAY_VERANDA_EXIT,
        # Управление комнатами (базовое)
        Permission.CREATE_ROOM,
        Permission.JOIN_ROOM,
        Permission.LEAVE_ROOM,
        # Чат
        Permission.CHAT_SEND,
        # Просмотр
        Permission.VIEW_GAME,
        Permission.VIEW_OWN_MONEY,
        Permission.VIEW_GAME_HISTORY,
    })

    # Права для роли OBSERVER (Наблюдатель)
    OBSERVER_PERMISSIONS: FrozenSet[Permission] = frozenset({
        # Чат
        Permission.CHAT_SEND,
        # Просмотр
        Permission.VIEW_GAME,
        Permission.VIEW_OBSERVERS,
        Permission.VIEW_GAME_HISTORY,
        # Комнаты (базовое)
        Permission.JOIN_ROOM,
        Permission.LEAVE_ROOM,
    })

    # Права для роли MODERATOR (Модератор) — расширенный набор
    MODERATOR_PERMISSIONS: FrozenSet[Permission] = frozenset({
        # Игровые действия
        Permission.PLAY_GAME,
        Permission.ROLL_DICE,
        Permission.BUY_PROPERTY,
        Permission.BUILD_HOUSE,
        Permission.BUILD_HOTEL,
        Permission.MORTGAGE_PROPERTY,
        Permission.UNMORTGAGE_PROPERTY,
        Permission.TRADE_INITIATE,
        Permission.TRADE_ACCEPT,
        Permission.AUCTION_BID,
        Permission.USE_JAIL_CARD,
        Permission.PAY_JAIL_FINE,
        Permission.PAY_VERANDA_EXIT,
        # Управление комнатами
        Permission.CREATE_ROOM,
        Permission.DELETE_ROOM,
        Permission.JOIN_ROOM,
        Permission.LEAVE_ROOM,
        Permission.KICK_PLAYER,
        Permission.CHANGE_ROOM_SETTINGS,
        Permission.START_GAME,
        Permission.PAUSE_GAME,
        Permission.RESUME_GAME,
        # Чат
        Permission.CHAT_SEND,
        Permission.CHAT_DELETE,
        Permission.CHAT_SYSTEM_MESSAGE,
        Permission.MODERATE_CHAT,
        # Просмотр
        Permission.VIEW_GAME,
        Permission.VIEW_OWN_MONEY,
        Permission.VIEW_ALL_MONEY,
        Permission.VIEW_OBSERVERS,
        Permission.VIEW_LOGS,
        Permission.VIEW_GAME_HISTORY,
        Permission.VIEW_PLAYER_PROFILES,
        Permission.VIEW_STATISTICS,
        # Администрирование (ограниченное)
        Permission.BAN_USER,
        Permission.UNBAN_USER,
    })

    # Сопоставление UserRole -> FrozenSet[Permission]
    _ROLE_PERMISSIONS: dict[UserRole, FrozenSet[Permission]] = {
        UserRole.CREATOR: CREATOR_PERMISSIONS,
        UserRole.PLAYER: PLAYER_PERMISSIONS,
        UserRole.OBSERVER: OBSERVER_PERMISSIONS,
    }

    # Дополнительные роли, не входящие в UserRole (могут быть добавлены позже)
    _CUSTOM_ROLE_PERMISSIONS: dict[str, FrozenSet[Permission]] = {
        "moderator": MODERATOR_PERMISSIONS,
    }

    @classmethod
    def get_permissions(cls, role: UserRole) -> FrozenSet[Permission]:
        """
        Получить набор прав для указанной роли.

        Args:
            role: Роль пользователя.

        Returns:
            Неизменяемый набор прав (frozenset).

        Raises:
            ValueError: Если роль не найдена в сопоставлении.
        """
        if role in cls._ROLE_PERMISSIONS:
            return cls._ROLE_PERMISSIONS[role]
        raise ValueError(f"Неизвестная роль: {role}")

    @classmethod
    def get_all_roles(cls) -> list[UserRole]:
        """
        Получить список всех стандартных ролей.

        Returns:
            Список UserRole.
        """
        return list(cls._ROLE_PERMISSIONS.keys())

    @classmethod
    def get_custom_role_permissions(cls, role_name: str) -> FrozenSet[Permission] | None:
        """
        Получить права для пользовательской роли (не из UserRole).

        Args:
            role_name: Название роли (например, "moderator").

        Returns:
            Набор прав или None, если роль не найдена.
        """
        return cls._CUSTOM_ROLE_PERMISSIONS.get(role_name.lower())

    @classmethod
    def register_custom_role(
        cls,
        role_name: str,
        permissions: FrozenSet[Permission],
    ) -> None:
        """
        Зарегистрировать новую пользовательскую роль.

        Args:
            role_name: Уникальное название роли.
            permissions: Набор прав для роли.
        """
        cls._CUSTOM_ROLE_PERMISSIONS[role_name.lower()] = permissions

    @classmethod
    def get_all_permissions(cls) -> list[Permission]:
        """
        Получить список всех существующих прав.

        Returns:
            Список всех Permission.
        """
        return list(Permission)


# ============================================================================
# ФУНКЦИИ ПРОВЕРКИ ПРАВ
# ============================================================================

def has_permission(role: UserRole, permission: Permission) -> bool:
    """
    Проверить, имеет ли указанная роль заданное право.

    Args:
        role: Роль пользователя.
        permission: Проверяемое право.

    Returns:
        True, если роль имеет право, иначе False.

    Example:
        if has_permission(user.role, Permission.CHEAT_MONEY):
            set_player_money(player_id, amount)
    """
    permissions = RolePermissions.get_permissions(role)
    return permission in permissions


def has_all_permissions(role: UserRole, permissions: set[Permission]) -> bool:
    """
    Проверить, имеет ли роль все указанные права.

    Args:
        role: Роль пользователя.
        permissions: Набор проверяемых прав.

    Returns:
        True, если роль имеет все указанные права.
    """
    role_permissions = RolePermissions.get_permissions(role)
    return permissions.issubset(role_permissions)


def has_any_permission(role: UserRole, permissions: set[Permission]) -> bool:
    """
    Проверить, имеет ли роль хотя бы одно из указанных прав.

    Args:
        role: Роль пользователя.
        permissions: Набор проверяемых прав.

    Returns:
        True, если роль имеет хотя бы одно из прав.
    """
    role_permissions = RolePermissions.get_permissions(role)
    return not permissions.isdisjoint(role_permissions)


def require_permission(role: UserRole, permission: Permission) -> None:
    """
    Проверить наличие права и вызвать исключение, если его нет.

    Args:
        role: Роль пользователя.
        permission: Требуемое право.

    Raises:
        PermissionError: Если роль не имеет требуемого права.
    """
    if not has_permission(role, permission):
        raise PermissionError(
            f"Роль '{role.value}' не имеет права '{permission.value}'"
        )


def get_missing_permissions(
    role: UserRole,
    required_permissions: set[Permission],
) -> set[Permission]:
    """
    Получить список прав, которых не хватает роли.

    Args:
        role: Роль пользователя.
        required_permissions: Требуемый набор прав.

    Returns:
        Множество недостающих прав.
    """
    role_permissions = RolePermissions.get_permissions(role)
    return required_permissions - role_permissions