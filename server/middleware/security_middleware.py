"""
server/middleware/security_middleware.py

Главный security middleware сервера.

Объединяет все проверки безопасности для входящих пакетов:
- Аутентификацию (проверка токена)
- Авторизацию (проверка прав доступа)
- Валидацию пакетов (HMAC, sequence, timestamp)
- Rate limiting (ограничение частоты запросов)

Работает как единая точка входа для всех входящих сообщений
перед их передачей в MessageDispatcher.

Python: 3.13+
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional
from uuid import UUID

from shared.enums import PacketType, UserRole
from shared.permissions import has_permission, Permission
from shared.protocol.packet import Packet
from server.auth.auth_manager import AuthManager
from server.auth.token_manager import TokenManager
from server.middleware.packet_validator import PacketValidator
from server.middleware.rate_limiter import RateLimiter

logger = logging.getLogger("billionaire.security")


# ============================================================================
# ТРЕБОВАНИЯ К ПРАВАМ ДЛЯ ТИПОВ ПАКЕТОВ
# ============================================================================

# Сопоставление типа пакета → необходимое право
PACKET_PERMISSION_REQUIRED: dict[PacketType, Permission] = {
    # Административные команды
    PacketType.ADMIN_COMMAND: Permission.ADMIN_COMMANDS,
    PacketType.ADMIN_SET_MONEY: Permission.CHEAT_MONEY,
    PacketType.ADMIN_SET_PROPERTY: Permission.CHEAT_PROPERTY,
    PacketType.ADMIN_TELEPORT: Permission.CHEAT_TELEPORT,
    PacketType.ADMIN_CHANGE_ROLE: Permission.MANAGE_ROLES,
    PacketType.ADMIN_VIEW_LOGS: Permission.VIEW_LOGS,
    PacketType.ADMIN_UNDO_ACTION: Permission.CHEAT_UNDO,
    PacketType.ADMIN_SERVER_COMMAND: Permission.SERVER_COMMANDS,
    PacketType.ADMIN_BROADCAST: Permission.CHAT_SYSTEM_MESSAGE,
    # Управление комнатами
    PacketType.ROOM_CREATE_REQUEST: Permission.CREATE_ROOM,
    PacketType.ROOM_SETTINGS_UPDATE: Permission.CHANGE_ROOM_SETTINGS,
    PacketType.ROOM_KICK_PLAYER: Permission.KICK_PLAYER,
    # Игровые действия (базовые — проверяются дополнительно в GameEngine)
}

# Типы пакетов, не требующие аутентификации
UNAUTHENTICATED_PACKETS: set[PacketType] = {
    PacketType.LOGIN_REQUEST,
    PacketType.REGISTER_REQUEST,
    PacketType.PING,
}


# ============================================================================
# MIDDLEWARE БЕЗОПАСНОСТИ
# ============================================================================

class SecurityMiddleware:
    """
    Главный middleware безопасности.

    Проверяет каждый входящий пакет перед его обработкой:
    1. Rate limiting (не чаще N запросов в секунду)
    2. Валидация пакета (HMAC, sequence, timestamp)
    3. Аутентификация (проверка токена)
    4. Авторизация (проверка прав доступа)

    Usage:
        middleware = SecurityMiddleware(token_manager, auth_manager)
        user = await middleware.process(session_id, packet, hmac_key)
    """

    def __init__(
        self,
        token_manager: TokenManager,
        auth_manager: AuthManager,
    ) -> None:
        """
        Инициализация middleware.

        Args:
            token_manager: Менеджер токенов.
            auth_manager: Менеджер аутентификации.
        """
        self._token_manager = token_manager
        self._auth_manager = auth_manager
        self._packet_validator = PacketValidator()
        self._rate_limiter = RateLimiter()

    # ========================================================================
    # ОСНОВНОЙ МЕТОД
    # ========================================================================

    async def process(
        self,
        session_id: str,
        packet: Packet,
        hmac_key: bytes,
    ) -> tuple[Optional[dict], Optional[str]]:
        """
        Проверить пакет через все слои безопасности.

        Args:
            session_id: ID сессии.
            packet: Входящий пакет.
            hmac_key: HMAC-ключ сессии.

        Returns:
            Кортеж (user_dict, error_message).
            Если error_message is None — пакет прошёл проверку.
            Если error_message не None — пакет отклонён.
        """
        # Шаг 1: Rate limiting
        error = self._check_rate_limit(session_id, packet.packet_type)
        if error:
            return None, error

        # Шаг 2: Валидация пакета
        if self._is_authenticated_packet(packet.packet_type):
            error = self._packet_validator.validate(
                packet, session_id, hmac_key
            )
        else:
            error = self._packet_validator.validate_packet_only(packet)

        if error:
            return None, error

        # Шаг 3: Аутентификация
        user = await self._authenticate(packet)

        # Для неаутентифицированных пакетов — пропускаем
        if packet.packet_type in UNAUTHENTICATED_PACKETS:
            return user, None

        if user is None:
            return None, "Требуется аутентификация"

        # Шаг 4: Авторизация
        error = self._authorize(packet.packet_type, user.get("role", "player"))
        if error:
            return None, error

        return user, None

    # ========================================================================
    # ПРОВЕРКИ БЕЗОПАСНОСТИ
    # ========================================================================

    def _check_rate_limit(
        self,
        session_id: str,
        packet_type: PacketType,
    ) -> Optional[str]:
        """
        Проверить ограничения частоты запросов.

        Args:
            session_id: ID сессии.
            packet_type: Тип пакета.

        Returns:
            Сообщение об ошибке или None.
        """
        if not self._rate_limiter.is_allowed(session_id, packet_type.value):
            logger.warning(
                "Rate limit превышен для сессии %s, тип пакета %s",
                session_id,
                packet_type.name,
            )
            return "Слишком много запросов. Пожалуйста, подождите."

        return None

    async def _authenticate(self, packet: Packet) -> Optional[dict]:
        """
        Проверить аутентификацию пакета.

        Извлекает access_token из полезной нагрузки и проверяет его.

        Args:
            packet: Пакет.

        Returns:
            Словарь с данными пользователя или None.
        """
        # Пропускаем пакеты, не требующие аутентификации
        if packet.packet_type in UNAUTHENTICATED_PACKETS:
            return None

        # Извлекаем токен
        access_token = packet.get_payload_field("access_token", "")
        if not access_token:
            access_token = packet.get_payload_field("token", "")

        if not access_token:
            return None

        # Проверяем токен
        user = await self._auth_manager.validate_session(access_token)
        if user is None:
            return None

        return user.to_dict()

    def _authorize(
        self,
        packet_type: PacketType,
        user_role: str,
    ) -> Optional[str]:
        """
        Проверить права доступа для действия.

        Args:
            packet_type: Тип пакета.
            user_role: Роль пользователя.

        Returns:
            Сообщение об ошибке или None.
        """
        # Получаем необходимое право
        required_permission = PACKET_PERMISSION_REQUIRED.get(packet_type)

        if required_permission is None:
            # Для этого типа пакета не требуется специальных прав
            return None

        # Проверяем право
        try:
            role = UserRole(user_role)
            if not has_permission(role, required_permission):
                logger.warning(
                    "Отказано в доступе: роль=%s, требуется=%s, пакет=%s",
                    user_role,
                    required_permission.value,
                    packet_type.name,
                )
                return f"Недостаточно прав: требуется '{required_permission.value}'"
        except ValueError:
            return f"Неизвестная роль: {user_role}"

        return None

    # ========================================================================
    # ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ
    # ========================================================================

    def _is_authenticated_packet(self, packet_type: PacketType) -> bool:
        """
        Проверить, требует ли пакет полной валидации.

        Args:
            packet_type: Тип пакета.

        Returns:
            True для аутентифицированных пакетов.
        """
        return packet_type not in UNAUTHENTICATED_PACKETS

    # ========================================================================
    # УПРАВЛЕНИЕ СЕССИЯМИ
    # ========================================================================

    def register_session(self, session_id: str) -> None:
        """
        Зарегистрировать новую сессию в middleware.

        Args:
            session_id: ID сессии.
        """
        pass  # Сессии регистрируются автоматически при первом запросе

    def remove_session(self, session_id: str) -> None:
        """
        Удалить данные сессии.

        Args:
            session_id: ID сессии.
        """
        self._packet_validator.remove_session(session_id)
        self._rate_limiter.reset_session(session_id)

    def reset_session_sequence(self, session_id: str) -> None:
        """
        Сбросить счётчик последовательности (при переподключении).

        Args:
            session_id: ID сессии.
        """
        self._packet_validator.reset_sequence(session_id)

    # ========================================================================
    # ОЧИСТКА И СТАТИСТИКА
    # ========================================================================

    def cleanup(self) -> None:
        """Очистить устаревшие данные."""
        self._rate_limiter.cleanup_expired()

    def get_stats(self) -> dict:
        """
        Получить статистику middleware.

        Returns:
            Словарь с метриками.
        """
        return {
            "packet_validator": self._packet_validator.get_stats(),
            "rate_limiter": self._rate_limiter.get_stats(),
        }

    def get_session_info(self, session_id: str) -> dict:
        """
        Получить информацию о сессии.

        Args:
            session_id: ID сессии.

        Returns:
            Словарь с данными сессии.
        """
        return {
            "session_id": session_id,
            "last_sequence": self._packet_validator.get_last_sequence(session_id),
            "rate_usage": self._rate_limiter.get_session_usage(session_id),
        }