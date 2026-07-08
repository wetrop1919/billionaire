"""
shared/protocol/serializer.py

Модуль сериализации и десериализации данных для сетевого протокола.

Обеспечивает:
- Преобразование dataclass-объектов в JSON-совместимые словари
- Восстановление dataclass-объектов из словарей
- Поддержку вложенных объектов, UUID, datetime, Enum
- Строгую типизацию при десериализации
- Обработку ошибок с понятными сообщениями

Использование:
    from shared.protocol.serializer import JSONSerializer

    data = JSONSerializer.serialize(my_dataclass)
    obj = JSONSerializer.deserialize(data, MyDataclass)

Python: 3.13+
"""

from __future__ import annotations

import dataclasses
import json
from datetime import datetime
from enum import Enum
from typing import Any, TypeVar, get_type_hints
from uuid import UUID

T = TypeVar("T")


# ============================================================================
# ИСКЛЮЧЕНИЯ СЕРИАЛИЗАЦИИ
# ============================================================================

class SerializationError(Exception):
    """Ошибка при сериализации объекта."""

    def __init__(self, message: str, obj: Any = None) -> None:
        self.obj = obj
        obj_info = f" (тип: {type(obj).__name__})" if obj is not None else ""
        super().__init__(f"Ошибка сериализации: {message}{obj_info}")


class DeserializationError(Exception):
    """Ошибка при десериализации данных."""

    def __init__(self, message: str, target_type: type | None = None) -> None:
        self.target_type = target_type
        type_info = f" в тип {target_type.__name__}" if target_type is not None else ""
        super().__init__(f"Ошибка десериализации: {message}{type_info}")


# ============================================================================
# СЕРИАЛИЗАТОР
# ============================================================================

class JSONSerializer:
    """
    Статический класс для сериализации и десериализации объектов.

    Поддерживает:
    - dataclass (включая вложенные)
    - UUID
    - datetime (ISO 8601)
    - Enum (StrEnum, IntEnum)
    - Примитивные типы: int, float, str, bool, None
    - Списки и словари
    """

    # ========================================================================
    # ПУБЛИЧНЫЕ МЕТОДЫ
    # ========================================================================

    @staticmethod
    def serialize(obj: Any) -> dict[str, Any]:
        """
        Сериализовать объект в JSON-совместимый словарь.

        Args:
            obj: Объект для сериализации (dataclass, dict, list, примитив).

        Returns:
            Словарь, готовый для преобразования в JSON.

        Raises:
            SerializationError: Если объект не может быть сериализован.
        """
        try:
            return JSONSerializer._serialize_value(obj)
        except Exception as e:
            raise SerializationError(str(e), obj) from e

    @staticmethod
    def serialize_to_json(obj: Any, indent: int | None = None) -> str:
        """
        Сериализовать объект в JSON-строку.

        Args:
            obj: Объект для сериализации.
            indent: Отступ для форматирования (None = компактный вывод).

        Returns:
            JSON-строка.
        """
        data = JSONSerializer.serialize(obj)
        return json.dumps(data, ensure_ascii=False, indent=indent)

    @staticmethod
    def deserialize(data: dict[str, Any], target_type: type[T]) -> T:
        """
        Десериализовать словарь в объект указанного типа.

        Args:
            data: Словарь с данными.
            target_type: Целевой тип (dataclass или примитивный тип).

        Returns:
            Экземпляр target_type.

        Raises:
            DeserializationError: Если десериализация невозможна.
        """
        try:
            return JSONSerializer._deserialize_value(data, target_type)
        except Exception as e:
            raise DeserializationError(str(e), target_type) from e

    @staticmethod
    def deserialize_from_json(json_string: str, target_type: type[T]) -> T:
        """
        Десериализовать JSON-строку в объект указанного типа.

        Args:
            json_string: JSON-строка.
            target_type: Целевой тип.

        Returns:
            Экземпляр target_type.
        """
        try:
            data = json.loads(json_string)
        except json.JSONDecodeError as e:
            raise DeserializationError(
                f"Некорректный JSON: {e.msg} (строка {e.lineno}, столбец {e.colno})",
                target_type,
            ) from e
        return JSONSerializer.deserialize(data, target_type)

    # ========================================================================
    # ПРИВАТНЫЕ МЕТОДЫ: СЕРИАЛИЗАЦИЯ
    # ========================================================================

    @staticmethod
    def _serialize_value(value: Any) -> Any:
        """
        Рекурсивная сериализация значения.

        Args:
            value: Значение для сериализации.

        Returns:
            JSON-совместимое представление.
        """
        # None
        if value is None:
            return None

        # Примитивные типы (int, float, str, bool)
        if isinstance(value, (int, float, str, bool)):
            return value

        # UUID
        if isinstance(value, UUID):
            return {"__type__": "UUID", "value": str(value)}

        # datetime
        if isinstance(value, datetime):
            return {"__type__": "datetime", "value": value.isoformat()}

        # Enum
        if isinstance(value, Enum):
            return JSONSerializer._serialize_enum(value)

        # Список
        if isinstance(value, list):
            return [JSONSerializer._serialize_value(item) for item in value]

        # Кортеж
        if isinstance(value, tuple):
            return {
                "__type__": "tuple",
                "items": [JSONSerializer._serialize_value(item) for item in value],
            }

        # Множество
        if isinstance(value, set):
            return {
                "__type__": "set",
                "items": [JSONSerializer._serialize_value(item) for item in sorted(value, key=str)],
            }

        # Словарь
        if isinstance(value, dict):
            return {
                key: JSONSerializer._serialize_value(val)
                for key, val in value.items()
            }

        # Dataclass
        if dataclasses.is_dataclass(value):
            return JSONSerializer._serialize_dataclass(value)

        raise SerializationError(
            f"Неподдерживаемый тип: {type(value).__name__}",
            value,
        )

    @staticmethod
    def _serialize_dataclass(obj: Any) -> dict[str, Any]:
        """
        Сериализация dataclass-объекта.

        Args:
            obj: Экземпляр dataclass.

        Returns:
            Словарь с полями объекта и метаданными типа.
        """
        result: dict[str, Any] = {
            "__type__": obj.__class__.__name__,
        }

        for field in dataclasses.fields(obj):
            value = getattr(obj, field.name)
            # Не сериализуем поля с factory по умолчанию, если значение совпадает
            # с default_factory (оптимизация размера)
            result[field.name] = JSONSerializer._serialize_value(value)

        return result

    @staticmethod
    def _serialize_enum(value: Enum) -> dict[str, Any]:
        """
        Сериализация Enum-значения.

        Args:
            value: Экземпляр Enum.

        Returns:
            Словарь с метаданными типа и значения.
        """
        return {
            "__type__": value.__class__.__name__,
            "value": value.value,
        }

    # ========================================================================
    # ПРИВАТНЫЕ МЕТОДЫ: ДЕСЕРИАЛИЗАЦИЯ
    # ========================================================================

    @staticmethod
    def _deserialize_value(data: Any, target_type: type[T]) -> T:
        """
        Рекурсивная десериализация значения.

        Args:
            data: Данные для десериализации.
            target_type: Ожидаемый тип результата.

        Returns:
            Десериализованный объект указанного типа.
        """
        # None
        if data is None:
            return None  # type: ignore[return-value]

        # Примитивные типы — прямое приведение
        if target_type in (int, float, str, bool):
            return target_type(data)

        # UUID
        if target_type is UUID:
            if isinstance(data, dict) and data.get("__type__") == "UUID":
                return UUID(data["value"])  # type: ignore[return-value]
            return UUID(str(data))  # type: ignore[return-value]

        # datetime
        if target_type is datetime:
            if isinstance(data, dict) and data.get("__type__") == "datetime":
                return datetime.fromisoformat(data["value"])  # type: ignore[return-value]
            return datetime.fromisoformat(str(data))  # type: ignore[return-value]

        # Enum
        if isinstance(target_type, type) and issubclass(target_type, Enum):
            return JSONSerializer._deserialize_enum(data, target_type)

        # Dataclass
        if dataclasses.is_dataclass(target_type):
            return JSONSerializer._deserialize_dataclass(data, target_type)

        # Список
        if target_type is list:
            if not isinstance(data, list):
                raise DeserializationError(
                    f"Ожидался список, получен {type(data).__name__}",
                    target_type,
                )
            return data  # type: ignore[return-value]

        # Словарь
        if target_type is dict:
            if not isinstance(data, dict):
                raise DeserializationError(
                    f"Ожидался словарь, получен {type(data).__name__}",
                    target_type,
                )
            return data  # type: ignore[return-value]

        # Если данные — словарь с __type__, пробуем восстановить
        if isinstance(data, dict) and "__type__" in data:
            type_name = data["__type__"]
            if type_name == "tuple":
                return tuple(data.get("items", []))  # type: ignore[return-value]
            if type_name == "set":
                return set(data.get("items", []))  # type: ignore[return-value]

        # Возвращаем как есть для неизвестных типов
        return data  # type: ignore[return-value]

    @staticmethod
    def _deserialize_dataclass(data: dict[str, Any], target_type: type[T]) -> T:
        """
        Десериализация словаря в dataclass-объект.

        Args:
            data: Словарь с данными.
            target_type: Целевой dataclass.

        Returns:
            Экземпляр target_type.
        """
        if not dataclasses.is_dataclass(target_type):
            raise DeserializationError(
                f"Тип {target_type.__name__} не является dataclass",
                target_type,
            )

        if not isinstance(data, dict):
            raise DeserializationError(
                f"Ожидался словарь для создания {target_type.__name__}, "
                f"получен {type(data).__name__}",
                target_type,
            )

        # Получаем аннотации типов полей
        try:
            type_hints = get_type_hints(target_type)
        except Exception:
            type_hints = {}

        # Собираем аргументы конструктора
        kwargs: dict[str, Any] = {}
        for field in dataclasses.fields(target_type):
            field_name = field.name

            if field_name in data:
                raw_value = data[field_name]
                field_type = type_hints.get(field_name, field.type)

                # Рекурсивная десериализация поля
                kwargs[field_name] = JSONSerializer._deserialize_value(
                    raw_value, field_type
                )
            elif field.default is not dataclasses.MISSING:
                # Используем значение по умолчанию
                kwargs[field_name] = field.default
            elif field.default_factory is not dataclasses.MISSING:
                # Используем default_factory
                kwargs[field_name] = field.default_factory()
            else:
                raise DeserializationError(
                    f"Отсутствует обязательное поле '{field_name}' "
                    f"для типа {target_type.__name__}",
                    target_type,
                )

        return target_type(**kwargs)

    @staticmethod
    def _deserialize_enum(data: Any, target_type: type[Enum]) -> Enum:
        """
        Десериализация Enum-значения.

        Args:
            data: Данные (словарь с __type__/value или просто значение).
            target_type: Целевой Enum-класс.

        Returns:
            Экземпляр Enum.
        """
        if isinstance(data, dict) and "value" in data:
            raw_value = data["value"]
        else:
            raw_value = data

        # Пытаемся найти по значению
        for member in target_type:
            if member.value == raw_value:
                return member

        raise DeserializationError(
            f"Значение '{raw_value}' не найдено в Enum {target_type.__name__}",
            target_type,
        )


# ============================================================================
# УТИЛИТЫ ДЛЯ РАБОТЫ С JSON
# ============================================================================

def json_dumps_compact(obj: Any) -> str:
    """
    Сериализация объекта в компактную JSON-строку (без пробелов).

    Args:
        obj: Объект для сериализации.

    Returns:
        Компактная JSON-строка.
    """
    return JSONSerializer.serialize_to_json(obj, indent=None)


def json_dumps_pretty(obj: Any) -> str:
    """
    Сериализация объекта в читаемую JSON-строку (с отступами).

    Args:
        obj: Объект для сериализации.

    Returns:
        Форматированная JSON-строка.
    """
    return JSONSerializer.serialize_to_json(obj, indent=2)


def json_loads_strict(json_string: str, target_type: type[T]) -> T:
    """
    Строгая десериализация JSON-строки с проверкой типа.

    Args:
        json_string: JSON-строка.
        target_type: Ожидаемый тип результата.

    Returns:
        Экземпляр target_type.

    Raises:
        DeserializationError: При любой ошибке десериализации.
    """
    return JSONSerializer.deserialize_from_json(json_string, target_type)


def validate_json(data: str) -> bool:
    """
    Проверить, является ли строка корректным JSON.

    Args:
        data: Проверяемая строка.

    Returns:
        True, если строка является валидным JSON.
    """
    try:
        json.loads(data)
        return True
    except json.JSONDecodeError:
        return False


def safe_json_loads(data: str) -> dict[str, Any] | None:
    """
    Безопасная загрузка JSON-строки.

    Args:
        data: JSON-строка.

    Returns:
        Словарь с данными или None, если строка некорректна.
    """
    try:
        result = json.loads(data)
        if isinstance(result, dict):
            return result
        return None
    except json.JSONDecodeError:
        return None