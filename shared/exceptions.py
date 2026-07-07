"""
shared/exceptions.py

Централизованное хранилище всех исключений проекта "Миллиардер".

Все исключения наследуются от базового BillionaireException,
что позволяет единообразно перехватывать и обрабатывать ошибки
на всех уровнях приложения.

Иерархия исключений:
    BillionaireException
    ├── GameException
    │   ├── GameNotFoundError
    │   ├── GameNotActiveError
    │   ├── NotYourTurnError
    │   ├── InsufficientFundsError
    │   ├── PropertyAlreadyOwnedError
    │   ├── PropertyNotOwnedError
    │   ├── CannotBuildError
    │   ├── CannotMortgageError
    │   ├── InvalidTradeError
    │   ├── NotInJailError
    │   ├── NotOnVerandaError
    │   ├── ActionNotAllowedError
    │   └── PlayerBankruptError
    ├── RoomException
    │   ├── RoomNotFoundError
    │   ├── RoomFullError
    │   ├── RoomLockedError
    │   ├── RoomWrongPasswordError
    │   ├── RoomInGameError
    │   └── NotRoomOwnerError
    ├── AuthException
    │   ├── InvalidCredentialsError
    │   ├── UsernameTakenError
    │   ├── UserBannedError
    │   ├── TokenExpiredError
    │   └── TokenInvalidError
    ├── NetworkException
    │   ├── ConnectionError
    │   ├── PacketInvalidError
    │   ├── PacketSizeExceededError
    │   ├── HMACVerificationError
    │   ├── SequenceError
    │   └── RateLimitError
    ├── ValidationException
    │   ├── ValidationError
    │   └── SchemaValidationError
    ├── ConfigurationException
    │   └── ConfigError
    └── DatabaseException
        └── DatabaseError

Python: 3.13+
"""

from __future__ import annotations

from typing import Any, Optional
from uuid import UUID


# ============================================================================
# БАЗОВОЕ ИСКЛЮЧЕНИЕ
# ============================================================================

class BillionaireException(Exception):
    """
    Базовое исключение для всего проекта.

    Все специализированные исключения должны наследоваться от этого класса.
    Это позволяет перехватывать любое исключение проекта одной конструкцией:

        try:
            ...
        except BillionaireException as e:
            logger.error(f"Ошибка: {e.message} [код: {e.error_code}]")
    """

    def __init__(
        self,
        message: str,
        error_code: Optional[int] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        """
        Инициализация базового исключения.

        Args:
            message: Человекочитаемое сообщение об ошибке.
            error_code: Числовой код ошибки (из ErrorCode enum).
            details: Дополнительные детали (для логирования/отладки).
        """
        self.message: str = message
        self.error_code: Optional[int] = error_code
        self.details: Optional[dict[str, Any]] = details
        super().__init__(message)

    def __str__(self) -> str:
        if self.error_code is not None:
            return f"[{self.error_code}] {self.message}"
        return self.message

    def to_dict(self) -> dict[str, Any]:
        """
        Сериализация исключения в словарь для отправки клиенту.

        Returns:
            Словарь с полями message, error_code и details.
        """
        result: dict[str, Any] = {
            "message": self.message,
            "error_code": self.error_code,
        }
        if self.details:
            result["details"] = self.details
        return result


# ============================================================================
# ИГРОВЫЕ ИСКЛЮЧЕНИЯ (Game Exceptions)
# ============================================================================

class GameException(BillionaireException):
    """Базовое исключение для игровых ошибок."""

    def __init__(
        self,
        message: str,
        error_code: Optional[int] = None,
        game_id: Optional[UUID] = None,
        player_id: Optional[UUID] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        self.game_id: Optional[UUID] = game_id
        self.player_id: Optional[UUID] = player_id
        super().__init__(message, error_code, details)


class GameNotFoundError(GameException):
    """Игра не найдена."""

    def __init__(self, game_id: UUID) -> None:
        super().__init__(
            message=f"Игра с ID {game_id} не найдена",
            error_code=1020,
            game_id=game_id,
        )


class GameNotActiveError(GameException):
    """Игра не находится в активном состоянии."""

    def __init__(self, game_id: UUID, current_state: str) -> None:
        super().__init__(
            message=f"Игра {game_id} не активна (текущее состояние: {current_state})",
            error_code=1021,
            game_id=game_id,
            details={"current_state": current_state},
        )


class NotYourTurnError(GameException):
    """Попытка совершить действие не в свой ход."""

    def __init__(self, player_id: UUID, current_player_id: UUID) -> None:
        super().__init__(
            message="Сейчас не ваш ход",
            error_code=1022,
            player_id=player_id,
            details={"current_player_id": str(current_player_id)},
        )


class InsufficientFundsError(GameException):
    """Недостаточно средств для выполнения операции."""

    def __init__(
        self,
        player_id: UUID,
        required: int,
        available: int,
    ) -> None:
        super().__init__(
            message=f"Недостаточно средств: требуется {required}$, доступно {available}$",
            error_code=1023,
            player_id=player_id,
            details={"required": required, "available": available},
        )
        self.required: int = required
        self.available: int = available


class PropertyAlreadyOwnedError(GameException):
    """Собственность уже принадлежит другому игроку."""

    def __init__(
        self,
        property_id: str,
        owner_id: UUID,
        player_id: UUID,
    ) -> None:
        super().__init__(
            message=f"Собственность '{property_id}' уже принадлежит игроку {owner_id}",
            error_code=1024,
            player_id=player_id,
            details={"property_id": property_id, "owner_id": str(owner_id)},
        )


class PropertyNotOwnedError(GameException):
    """Игрок не владеет указанной собственностью."""

    def __init__(self, player_id: UUID, property_id: str) -> None:
        super().__init__(
            message=f"Вы не владеете собственностью '{property_id}'",
            error_code=1025,
            player_id=player_id,
            details={"property_id": property_id},
        )


class CannotBuildError(GameException):
    """Невозможно построить дом/отель."""

    def __init__(
        self,
        player_id: UUID,
        property_id: str,
        reason: str,
    ) -> None:
        super().__init__(
            message=f"Невозможно построить на '{property_id}': {reason}",
            error_code=1026,
            player_id=player_id,
            details={"property_id": property_id, "reason": reason},
        )


class CannotMortgageError(GameException):
    """Невозможно заложить собственность."""

    def __init__(
        self,
        player_id: UUID,
        property_id: str,
        reason: str,
    ) -> None:
        super().__init__(
            message=f"Невозможно заложить '{property_id}': {reason}",
            error_code=1027,
            player_id=player_id,
            details={"property_id": property_id, "reason": reason},
        )


class InvalidTradeError(GameException):
    """Некорректное торговое предложение."""

    def __init__(
        self,
        from_id: UUID,
        to_id: UUID,
        reason: str,
    ) -> None:
        super().__init__(
            message=f"Некорректная сделка между {from_id} и {to_id}: {reason}",
            error_code=1028,
            details={"from_id": str(from_id), "to_id": str(to_id), "reason": reason},
        )


class NotInJailError(GameException):
    """Игрок не находится в тюрьме."""

    def __init__(self, player_id: UUID) -> None:
        super().__init__(
            message="Вы не находитесь в тюрьме",
            error_code=1029,
            player_id=player_id,
        )


class NotOnVerandaError(GameException):
    """Игрок не находится на Веранде."""

    def __init__(self, player_id: UUID) -> None:
        super().__init__(
            message="Вы не находитесь на Веранде",
            error_code=1030,
            player_id=player_id,
        )


class ActionNotAllowedError(GameException):
    """Действие не разрешено в текущем состоянии."""

    def __init__(
        self,
        player_id: UUID,
        action: str,
        reason: str,
    ) -> None:
        super().__init__(
            message=f"Действие '{action}' не разрешено: {reason}",
            error_code=1031,
            player_id=player_id,
            details={"action": action, "reason": reason},
        )


class PlayerBankruptError(GameException):
    """Игрок объявлен банкротом."""

    def __init__(
        self,
        player_id: UUID,
        reason: str,
    ) -> None:
        super().__init__(
            message=f"Игрок {player_id} стал банкротом: {reason}",
            player_id=player_id,
            details={"reason": reason},
        )


# ============================================================================
# ИСКЛЮЧЕНИЯ КОМНАТ (Room Exceptions)
# ============================================================================

class RoomException(BillionaireException):
    """Базовое исключение для ошибок, связанных с комнатами."""

    def __init__(
        self,
        message: str,
        error_code: Optional[int] = None,
        room_id: Optional[UUID] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        self.room_id: Optional[UUID] = room_id
        super().__init__(message, error_code, details)


class RoomNotFoundError(RoomException):
    """Комната не найдена."""

    def __init__(self, room_id: UUID) -> None:
        super().__init__(
            message=f"Комната с ID {room_id} не найдена",
            error_code=1010,
            room_id=room_id,
        )


class RoomFullError(RoomException):
    """Комната заполнена."""

    def __init__(self, room_id: UUID, max_players: int) -> None:
        super().__init__(
            message=f"Комната заполнена (максимум {max_players} игроков)",
            error_code=1011,
            room_id=room_id,
            details={"max_players": max_players},
        )


class RoomLockedError(RoomException):
    """Комната защищена паролем."""

    def __init__(self, room_id: UUID) -> None:
        super().__init__(
            message="Комната защищена паролем. Введите пароль для подключения.",
            error_code=1012,
            room_id=room_id,
        )


class RoomWrongPasswordError(RoomException):
    """Неверный пароль комнаты."""

    def __init__(self, room_id: UUID) -> None:
        super().__init__(
            message="Неверный пароль комнаты",
            error_code=1013,
            room_id=room_id,
        )


class RoomInGameError(RoomException):
    """Нельзя выполнить действие: в комнате уже идёт игра."""

    def __init__(self, room_id: UUID) -> None:
        super().__init__(
            message="В комнате уже идёт игра",
            error_code=1014,
            room_id=room_id,
        )


class NotRoomOwnerError(RoomException):
    """Пользователь не является владельцем комнаты."""

    def __init__(self, room_id: UUID, user_id: UUID) -> None:
        super().__init__(
            message="Только владелец комнаты может выполнить это действие",
            error_code=1015,
            room_id=room_id,
            details={"user_id": str(user_id)},
        )


# ============================================================================
# ИСКЛЮЧЕНИЯ АУТЕНТИФИКАЦИИ (Auth Exceptions)
# ============================================================================

class AuthException(BillionaireException):
    """Базовое исключение для ошибок аутентификации."""

    def __init__(
        self,
        message: str,
        error_code: Optional[int] = None,
        username: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        self.username: Optional[str] = username
        super().__init__(message, error_code, details)


class InvalidCredentialsError(AuthException):
    """Неверные учётные данные."""

    def __init__(self, username: str) -> None:
        super().__init__(
            message="Неверное имя пользователя или пароль",
            error_code=1002,
            username=username,
        )


class UsernameTakenError(AuthException):
    """Имя пользователя уже занято."""

    def __init__(self, username: str) -> None:
        super().__init__(
            message=f"Имя пользователя '{username}' уже занято",
            error_code=1003,
            username=username,
        )


class UserBannedError(AuthException):
    """Пользователь заблокирован."""

    def __init__(self, username: str, reason: Optional[str] = None) -> None:
        msg = "Ваш аккаунт заблокирован"
        if reason:
            msg += f": {reason}"
        super().__init__(
            message=msg,
            error_code=1004,
            username=username,
            details={"reason": reason} if reason else None,
        )


class TokenExpiredError(AuthException):
    """Токен доступа истёк."""

    def __init__(self) -> None:
        super().__init__(
            message="Токен доступа истёк. Выполните повторный вход.",
            error_code=1005,
        )


class TokenInvalidError(AuthException):
    """Токен недействителен."""

    def __init__(self, reason: str = "Токен недействителен") -> None:
        super().__init__(
            message=reason,
            error_code=1006,
        )


# ============================================================================
# СЕТЕВЫЕ ИСКЛЮЧЕНИЯ (Network Exceptions)
# ============================================================================

class NetworkException(BillionaireException):
    """Базовое исключение для сетевых ошибок."""

    def __init__(
        self,
        message: str,
        error_code: Optional[int] = None,
        session_id: Optional[UUID] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        self.session_id: Optional[UUID] = session_id
        super().__init__(message, error_code, details)


class ConnectionError(NetworkException):
    """Ошибка соединения."""

    def __init__(self, message: str, session_id: Optional[UUID] = None) -> None:
        super().__init__(
            message=f"Ошибка соединения: {message}",
            session_id=session_id,
        )


class PacketInvalidError(NetworkException):
    """Некорректный пакет."""

    def __init__(self, reason: str, session_id: Optional[UUID] = None) -> None:
        super().__init__(
            message=f"Некорректный пакет: {reason}",
            error_code=1001,
            session_id=session_id,
            details={"reason": reason},
        )


class PacketSizeExceededError(NetworkException):
    """Превышен максимальный размер пакета."""

    def __init__(
        self,
        actual_size: int,
        max_size: int,
        session_id: Optional[UUID] = None,
    ) -> None:
        super().__init__(
            message=f"Размер пакета ({actual_size} байт) превышает лимит ({max_size} байт)",
            session_id=session_id,
            details={"actual_size": actual_size, "max_size": max_size},
        )


class HMACVerificationError(NetworkException):
    """Ошибка проверки HMAC-подписи."""

    def __init__(self, session_id: Optional[UUID] = None) -> None:
        super().__init__(
            message="Ошибка проверки целостности пакета (HMAC)",
            session_id=session_id,
        )


class SequenceError(NetworkException):
    """Ошибка порядкового номера пакета (возможна replay-атака)."""

    def __init__(
        self,
        expected: int,
        received: int,
        session_id: Optional[UUID] = None,
    ) -> None:
        super().__init__(
            message=f"Нарушение последовательности пакетов: ожидался {expected}, получен {received}",
            session_id=session_id,
            details={"expected": expected, "received": received},
        )


class RateLimitError(NetworkException):
    """Превышен лимит запросов."""

    def __init__(
        self,
        session_id: Optional[UUID] = None,
        limit: int = 0,
        window: float = 0.0,
    ) -> None:
        super().__init__(
            message="Слишком много запросов. Пожалуйста, подождите.",
            error_code=1040,
            session_id=session_id,
            details={"limit": limit, "window_seconds": window},
        )


# ============================================================================
# ИСКЛЮЧЕНИЯ ВАЛИДАЦИИ (Validation Exceptions)
# ============================================================================

class ValidationException(BillionaireException):
    """Базовое исключение для ошибок валидации данных."""

    def __init__(
        self,
        message: str,
        field: Optional[str] = None,
        value: Optional[Any] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        self.field: Optional[str] = field
        self.value: Optional[Any] = value
        super().__init__(message, details=details)


class ValidationError(ValidationException):
    """Ошибка валидации значения."""

    def __init__(
        self,
        message: str,
        field: Optional[str] = None,
        value: Optional[Any] = None,
    ) -> None:
        super().__init__(message, field=field, value=value)
        if field:
            self.message = f"Поле '{field}': {message}"


class SchemaValidationError(ValidationException):
    """Ошибка валидации JSON-схемы конфигурации."""

    def __init__(
        self,
        config_path: str,
        errors: list[str],
    ) -> None:
        super().__init__(
            message=f"Ошибка валидации конфигурации '{config_path}'",
            details={"config_path": config_path, "errors": errors},
        )
        self.config_path: str = config_path
        self.errors: list[str] = errors


# ============================================================================
# ИСКЛЮЧЕНИЯ КОНФИГУРАЦИИ (Configuration Exceptions)
# ============================================================================

class ConfigurationException(BillionaireException):
    """Базовое исключение для ошибок конфигурации."""

    pass


class ConfigError(ConfigurationException):
    """Ошибка загрузки или обработки конфигурации."""

    def __init__(self, config_path: str, reason: str) -> None:
        super().__init__(
            message=f"Ошибка конфигурации '{config_path}': {reason}",
            details={"config_path": config_path, "reason": reason},
        )
        self.config_path: str = config_path
        self.reason: str = reason


# ============================================================================
# ИСКЛЮЧЕНИЯ БАЗЫ ДАННЫХ (Database Exceptions)
# ============================================================================

class DatabaseException(BillionaireException):
    """Базовое исключение для ошибок базы данных."""

    def __init__(
        self,
        message: str,
        original_error: Optional[Exception] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        self.original_error: Optional[Exception] = original_error
        super().__init__(message, details=details)


class DatabaseError(DatabaseException):
    """Ошибка выполнения операции с базой данных."""

    def __init__(
        self,
        operation: str,
        original_error: Optional[Exception] = None,
    ) -> None:
        msg = f"Ошибка базы данных при выполнении '{operation}'"
        if original_error:
            msg += f": {original_error}"
        super().__init__(
            message=msg,
            original_error=original_error,
            details={"operation": operation},
        )
        self.operation: str = operation


# ============================================================================
# ИСКЛЮЧЕНИЕ ДЛЯ НЕСОВМЕСТИМОСТИ ВЕРСИЙ (Version Mismatch)
# ============================================================================

class VersionMismatchError(BillionaireException):
    """Клиент и сервер имеют несовместимые версии протокола."""

    def __init__(
        self,
        client_version: str,
        server_version: str,
        reason: str,
    ) -> None:
        super().__init__(
            message=f"Несовместимость версий: клиент={client_version}, сервер={server_version}. {reason}",
            error_code=1060,
            details={
                "client_version": client_version,
                "server_version": server_version,
                "reason": reason,
            },
        )
        self.client_version: str = client_version
        self.server_version: str = server_version


# ============================================================================
# ИСКЛЮЧЕНИЕ ДЛЯ НЕДОСТАТОЧНОСТИ ПРАВ (Permission Denied)
# ============================================================================

class PermissionDeniedError(BillionaireException):
    """Недостаточно прав для выполнения действия."""

    def __init__(
        self,
        user_id: UUID,
        required_permission: str,
        action: str,
    ) -> None:
        super().__init__(
            message=f"Недостаточно прав: требуется '{required_permission}' для '{action}'",
            error_code=1041,
            details={
                "user_id": str(user_id),
                "required_permission": required_permission,
                "action": action,
            },
        )
        self.user_id: UUID = user_id
        self.required_permission: str = required_permission
        self.action: str = action