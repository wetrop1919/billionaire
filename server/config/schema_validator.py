"""
server/config/schema_validator.py

Валидатор JSON-схем для конфигурационных файлов.

Проверяет структуру и типы данных в JSON-конфигурациях
перед их загрузкой. Использует простой декларативный подход
без внешних зависимостей.

Python: 3.13+
"""

from __future__ import annotations

from typing import Any, Optional


# ============================================================================
# ИСКЛЮЧЕНИЯ ВАЛИДАЦИИ
# ============================================================================

class SchemaValidationError(Exception):
    """Ошибка валидации JSON-схемы."""

    def __init__(self, message: str, path: str = "") -> None:
        self.path = path
        prefix = f"Ошибка в '{path}': " if path else ""
        super().__init__(f"{prefix}{message}")


# ============================================================================
# ОПИСАНИЕ СХЕМЫ
# ============================================================================

@dataclass(slots=True)
class SchemaField:
    """Описание одного поля схемы."""

    name: str
    field_type: type
    required: bool = False
    default: Any = None
    min_value: Optional[int | float] = None
    max_value: Optional[int | float] = None
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    allowed_values: Optional[list] = None
    children: Optional[dict[str, SchemaField]] = None


@dataclass(slots=True)
class Schema:
    """Описание JSON-схемы."""

    version: int
    fields: dict[str, SchemaField]
    allow_extra_fields: bool = False


# ============================================================================
# ВАЛИДАТОР
# ============================================================================

class SchemaValidator:
    """
    Статический валидатор JSON-конфигураций по схеме.

    Проверяет:
    - Версию конфигурации
    - Наличие обязательных полей
    - Типы данных полей
    - Диапазоны числовых значений
    - Длину строк
    - Допустимые значения (enum-like)
    - Вложенные объекты
    """

    @staticmethod
    def validate(data: dict[str, Any], schema: Schema) -> list[str]:
        """
        Проверить данные по схеме.

        Args:
            data: Данные для проверки.
            schema: Схема валидации.

        Returns:
            Список сообщений об ошибках (пустой, если всё корректно).
        """
        errors: list[str] = []

        # Проверка версии
        version = data.get("version", 0)
        if version < schema.version:
            errors.append(
                f"Устаревшая версия конфигурации: {version} < {schema.version}"
            )

        # Извлекаем данные (поддерживаем формат с обёрткой "data")
        config_data = data.get("data", data)
        if "data" not in data:
            config_data = data

        if not isinstance(config_data, dict):
            errors.append("Конфигурация должна быть словарём")
            return errors

        # Проверяем поля
        errors.extend(
            SchemaValidator._validate_object(config_data, schema.fields, "")
        )

        # Проверяем лишние поля
        if not schema.allow_extra_fields:
            allowed_keys = set(schema.fields.keys())
            actual_keys = set(config_data.keys())
            extra_keys = actual_keys - allowed_keys
            for key in extra_keys:
                errors.append(f"Неизвестное поле: '{key}'")

        return errors

    @staticmethod
    def _validate_object(
        data: dict[str, Any],
        fields: dict[str, SchemaField],
        path: str,
    ) -> list[str]:
        """
        Рекурсивная валидация объекта.

        Args:
            data: Проверяемые данные.
            fields: Описание полей.
            path: Текущий путь (для сообщений об ошибках).

        Returns:
            Список ошибок.
        """
        errors: list[str] = []

        for field_name, field_def in fields.items():
            field_path = f"{path}.{field_name}" if path else field_name

            # Проверка наличия обязательного поля
            if field_name not in data:
                if field_def.required:
                    errors.append(f"Отсутствует обязательное поле '{field_path}'")
                continue

            value = data[field_name]
            errors.extend(
                SchemaValidator._validate_field(value, field_def, field_path)
            )

        return errors

    @staticmethod
    def _validate_field(
        value: Any,
        field_def: SchemaField,
        path: str,
    ) -> list[str]:
        """
        Валидация одного поля.

        Args:
            value: Значение поля.
            field_def: Описание поля.
            path: Путь к полю.

        Returns:
            Список ошибок.
        """
        errors: list[str] = []

        # Проверка типа
        if not isinstance(value, field_def.field_type):
            errors.append(
                f"Поле '{path}' должно быть типа {field_def.field_type.__name__}, "
                f"получен {type(value).__name__}"
            )
            return errors

        # Числовые диапазоны
        if isinstance(value, (int, float)):
            if field_def.min_value is not None and value < field_def.min_value:
                errors.append(
                    f"Поле '{path}' должно быть >= {field_def.min_value}, "
                    f"получено {value}"
                )
            if field_def.max_value is not None and value > field_def.max_value:
                errors.append(
                    f"Поле '{path}' должно быть <= {field_def.max_value}, "
                    f"получено {value}"
                )

        # Длина строк
        if isinstance(value, str):
            if field_def.min_length is not None and len(value) < field_def.min_length:
                errors.append(
                    f"Поле '{path}' должно быть не короче {field_def.min_length} символов"
                )
            if field_def.max_length is not None and len(value) > field_def.max_length:
                errors.append(
                    f"Поле '{path}' должно быть не длиннее {field_def.max_length} символов"
                )

        # Допустимые значения
        if field_def.allowed_values is not None and value not in field_def.allowed_values:
            errors.append(
                f"Поле '{path}' имеет недопустимое значение '{value}'. "
                f"Допустимые: {field_def.allowed_values}"
            )

        # Вложенные поля
        if field_def.children is not None and isinstance(value, dict):
            errors.extend(
                SchemaValidator._validate_object(value, field_def.children, path)
            )

        return errors

    @staticmethod
    def validate_server_config(data: dict[str, Any]) -> list[str]:
        """
        Проверить конфигурацию сервера.

        Args:
            data: Данные server.json.

        Returns:
            Список ошибок.
        """
        schema = Schema(
            version=1,
            fields={
                "host": SchemaField("host", str, required=False, default="0.0.0.0"),
                "port": SchemaField("port", int, required=False, min_value=1, max_value=65535),
                "log_level": SchemaField("log_level", str, required=False,
                                         allowed_values=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]),
                "log_dir": SchemaField("log_dir", str, required=False),
                "backup_dir": SchemaField("backup_dir", str, required=False),
                "backup_retention_days": SchemaField("backup_retention_days", int, required=False, min_value=1),
                "max_rooms_per_user": SchemaField("max_rooms_per_user", int, required=False, min_value=1),
                "room_cleanup_timeout_seconds": SchemaField("room_cleanup_timeout_seconds", int, required=False, min_value=60),
                "debug": SchemaField("debug", bool, required=False),
                "environment": SchemaField("environment", str, required=False,
                                           allowed_values=["development", "staging", "production"]),
            },
        )
        return SchemaValidator.validate(data, schema)

    @staticmethod
    def validate_network_config(data: dict[str, Any]) -> list[str]:
        """
        Проверить конфигурацию сети.

        Args:
            data: Данные network.json.

        Returns:
            Список ошибок.
        """
        schema = Schema(
            version=1,
            fields={
                "ssl": SchemaField("ssl", dict, required=False, children={
                    "enabled": SchemaField("enabled", bool, required=False),
                    "cert_path": SchemaField("cert_path", str, required=False),
                    "key_path": SchemaField("key_path", str, required=False),
                    "ca_path": SchemaField("ca_path", str, required=False),
                }),
                "connection": SchemaField("connection", dict, required=False, children={
                    "max_connections": SchemaField("max_connections", int, required=False, min_value=1),
                    "buffer_size": SchemaField("buffer_size", int, required=False, min_value=1024),
                    "connection_timeout_seconds": SchemaField("connection_timeout_seconds", float, required=False, min_value=1.0),
                    "read_timeout_seconds": SchemaField("read_timeout_seconds", float, required=False, min_value=1.0),
                    "write_timeout_seconds": SchemaField("write_timeout_seconds", float, required=False, min_value=1.0),
                    "session_idle_timeout_seconds": SchemaField("session_idle_timeout_seconds", float, required=False, min_value=30.0),
                }),
                "heartbeat": SchemaField("heartbeat", dict, required=False, children={
                    "interval_seconds": SchemaField("interval_seconds", float, required=False, min_value=5.0),
                    "timeout_seconds": SchemaField("timeout_seconds", float, required=False, min_value=1.0),
                    "max_missed_heartbeats": SchemaField("max_missed_heartbeats", int, required=False, min_value=1),
                }),
                "reconnection": SchemaField("reconnection", dict, required=False, children={
                    "window_seconds": SchemaField("window_seconds", float, required=False, min_value=5.0),
                    "max_attempts": SchemaField("max_attempts", int, required=False, min_value=1),
                    "initial_delay_seconds": SchemaField("initial_delay_seconds", float, required=False, min_value=1.0),
                    "backoff_multiplier": SchemaField("backoff_multiplier", float, required=False, min_value=1.0),
                    "max_delay_seconds": SchemaField("max_delay_seconds", float, required=False, min_value=1.0),
                }),
                "rate_limiting": SchemaField("rate_limiting", dict, required=False, children={
                    "max_packets_per_second": SchemaField("max_packets_per_second", int, required=False, min_value=1),
                    "max_chat_messages_per_second": SchemaField("max_chat_messages_per_second", int, required=False, min_value=1),
                    "max_auth_attempts_per_minute": SchemaField("max_auth_attempts_per_minute", int, required=False, min_value=1),
                    "window_seconds": SchemaField("window_seconds", float, required=False, min_value=0.1),
                }),
            },
        )
        return SchemaValidator.validate(data, schema)

    @staticmethod
    def validate_security_config(data: dict[str, Any]) -> list[str]:
        """
        Проверить конфигурацию безопасности.

        Args:
            data: Данные security.json.

        Returns:
            Список ошибок.
        """
        schema = Schema(
            version=1,
            fields={
                "hmac": SchemaField("hmac", dict, required=False, children={
                    "key_size": SchemaField("key_size", int, required=False, min_value=16),
                    "hash_algorithm": SchemaField("hash_algorithm", str, required=False,
                                                  allowed_values=["sha256", "sha384", "sha512"]),
                }),
                "passwords": SchemaField("passwords", dict, required=False, children={
                    "algorithm": SchemaField("algorithm", str, required=False,
                                             allowed_values=["argon2id"]),
                    "memory_cost_kb": SchemaField("memory_cost_kb", int, required=False, min_value=8192),
                    "time_cost": SchemaField("time_cost", int, required=False, min_value=1),
                    "parallelism": SchemaField("parallelism", int, required=False, min_value=1),
                    "hash_length": SchemaField("hash_length", int, required=False, min_value=16),
                    "salt_length": SchemaField("salt_length", int, required=False, min_value=8),
                    "min_length": SchemaField("min_length", int, required=False, min_value=4),
                    "max_length": SchemaField("max_length", int, required=False, min_value=8),
                }),
                "tokens": SchemaField("tokens", dict, required=False, children={
                    "access_token_expire_seconds": SchemaField("access_token_expire_seconds", int, required=False, min_value=60),
                    "refresh_token_expire_seconds": SchemaField("refresh_token_expire_seconds", int, required=False, min_value=3600),
                    "session_token_size": SchemaField("session_token_size", int, required=False, min_value=16),
                }),
                "login": SchemaField("login", dict, required=False, children={
                    "max_attempts": SchemaField("max_attempts", int, required=False, min_value=1),
                    "block_time_seconds": SchemaField("block_time_seconds", int, required=False, min_value=30),
                    "min_username_length": SchemaField("min_username_length", int, required=False, min_value=2),
                    "max_username_length": SchemaField("max_username_length", int, required=False, min_value=3),
                }),
                "packet": SchemaField("packet", dict, required=False, children={
                    "timestamp_tolerance_seconds": SchemaField("timestamp_tolerance_seconds", float, required=False, min_value=1.0),
                    "max_payload_size": SchemaField("max_payload_size", int, required=False, min_value=1024),
                    "compression_threshold": SchemaField("compression_threshold", int, required=False, min_value=64),
                }),
            },
        )
        return SchemaValidator.validate(data, schema)

    @staticmethod
    def validate_game_board(data: dict[str, Any]) -> list[str]:
        """
        Проверить конфигурацию игрового поля.

        Args:
            data: Данные board.json.

        Returns:
            Список ошибок.
        """
        cell_schema = {
            "cell_id": SchemaField("cell_id", int, required=True, min_value=0),
            "name": SchemaField("name", str, required=True, min_length=1),
            "type": SchemaField("type", str, required=True),
            "property_id": SchemaField("property_id", str, required=False),
            "action": SchemaField("action", str, required=False),
            "action_data": SchemaField("action_data", dict, required=False),
            "position_x": SchemaField("position_x", int, required=False, min_value=0),
            "position_y": SchemaField("position_y", int, required=False, min_value=0),
            "side": SchemaField("side", int, required=False, min_value=0, max_value=3),
        }

        schema = Schema(
            version=1,
            fields={
                "board_size": SchemaField("board_size", int, required=True, min_value=4),
                "cells": SchemaField("cells", list, required=True),
                "special_cells": SchemaField("special_cells", dict, required=False),
            },
        )
        return SchemaValidator.validate(data, schema)

    @staticmethod
    def validate_game_rules(data: dict[str, Any]) -> list[str]:
        """
        Проверить конфигурацию правил игры.

        Args:
            data: Данные rules.json.

        Returns:
            Список ошибок.
        """
        schema = Schema(
            version=1,
            fields={
                "economy": SchemaField("economy", dict, required=False, children={
                    "start_money": SchemaField("start_money", int, required=False, min_value=0),
                    "start_bonus": SchemaField("start_bonus", int, required=False, min_value=0),
                    "max_players": SchemaField("max_players", int, required=False, min_value=2, max_value=8),
                    "min_players": SchemaField("min_players", int, required=False, min_value=2),
                    "turn_timeout_seconds": SchemaField("turn_timeout_seconds", int, required=False, min_value=15),
                }),
                "jail": SchemaField("jail", dict, required=False, children={
                    "jail_fine": SchemaField("jail_fine", int, required=False, min_value=0),
                    "max_rounds_in_jail": SchemaField("max_rounds_in_jail", int, required=False, min_value=1),
                    "doubles_for_jail": SchemaField("doubles_for_jail", int, required=False, min_value=1),
                }),
                "auction": SchemaField("auction", dict, required=False, children={
                    "enabled": SchemaField("enabled", bool, required=False),
                    "start_price_ratio": SchemaField("start_price_ratio", float, required=False, min_value=0.1, max_value=1.0),
                    "timeout_seconds": SchemaField("timeout_seconds", int, required=False, min_value=10),
                }),
                "trade": SchemaField("trade", dict, required=False, children={
                    "enabled": SchemaField("enabled", bool, required=False),
                    "timeout_seconds": SchemaField("timeout_seconds", int, required=False, min_value=10),
                    "min_loan_percent": SchemaField("min_loan_percent", int, required=False, min_value=0, max_value=50),
                    "max_loan_percent": SchemaField("max_loan_percent", int, required=False, min_value=0, max_value=50),
                }),
                "building": SchemaField("building", dict, required=False, children={
                    "enabled": SchemaField("enabled", bool, required=False),
                    "max_houses_per_property": SchemaField("max_houses_per_property", int, required=False, min_value=1),
                    "hotel_requires_houses": SchemaField("hotel_requires_houses", int, required=False, min_value=1),
                    "even_build_required": SchemaField("even_build_required", bool, required=False),
                }),
                "spectators": SchemaField("spectators", dict, required=False, children={
                    "allow_spectators": SchemaField("allow_spectators", bool, required=False),
                    "spectator_chat": SchemaField("spectator_chat", bool, required=False),
                }),
            },
        )
        return SchemaValidator.validate(data, schema)