"""
shared/models/base.py

Базовые классы и интерфейсы для моделей данных.

Содержит:
- BaseModel — абстрактный базовый класс для всех моделей
- Identifiable — интерфейс для моделей с уникальным идентификатором
- Serializable — интерфейс для моделей с сериализацией

Python: 3.13+
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Protocol, Self, runtime_checkable
from uuid import UUID


# ============================================================================
# ИНТЕРФЕЙС СЕРИАЛИЗУЕМОГО ОБЪЕКТА
# ============================================================================

@runtime_checkable
class Serializable(Protocol):
    """
    Протокол для объектов, поддерживающих сериализацию.

    Любой класс, реализующий to_dict() и from_dict(),
    автоматически совместим с этим протоколом.
    """

    def to_dict(self) -> dict[str, Any]:
        """
        Сериализовать объект в словарь.

        Returns:
            Словарь с данными объекта.
        """
        ...

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """
        Создать объект из словаря.

        Args:
            data: Словарь с данными.

        Returns:
            Новый экземпляр класса.
        """
        ...


# ============================================================================
# ИНТЕРФЕЙС ИДЕНТИФИЦИРУЕМОГО ОБЪЕКТА
# ============================================================================

@runtime_checkable
class Identifiable(Protocol):
    """
    Протокол для объектов с уникальным идентификатором.

    Любой класс с атрибутом id (UUID) автоматически
    совместим с этим протоколом.
    """

    @property
    def id(self) -> UUID:
        """
        Уникальный идентификатор объекта.

        Returns:
            UUID объекта.
        """
        ...


# ============================================================================
# АБСТРАКТНЫЙ БАЗОВЫЙ КЛАСС МОДЕЛИ
# ============================================================================

class BaseModel(ABC):
    """
    Абстрактный базовый класс для всех моделей данных.

    Предоставляет общую функциональность:
    - Сериализация в словарь и обратно
    - Валидация данных
    - Сравнение объектов по идентификатору

    Наследники должны реализовать:
    - to_dict() — сериализация
    - from_dict() — десериализация (classmethod)
    - validate() — валидация (опционально)
    """

    @abstractmethod
    def to_dict(self) -> dict[str, Any]:
        """
        Сериализовать модель в словарь.

        Returns:
            Словарь с полями модели, готовый для JSON-сериализации.
        """
        ...

    @classmethod
    @abstractmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """
        Создать экземпляр модели из словаря.

        Args:
            data: Словарь с данными модели.

        Returns:
            Новый экземпляр модели.
        """
        ...

    def validate(self) -> list[str]:
        """
        Валидировать данные модели.

        Returns:
            Список сообщений об ошибках (пустой, если модель валидна).

        Note:
            По умолчанию возвращает пустой список.
            Переопределите в наследниках для добавления проверок.
        """
        return []

    def is_valid(self) -> bool:
        """
        Проверить, валидна ли модель.

        Returns:
            True, если модель прошла валидацию.
        """
        return len(self.validate()) == 0

    def clone(self) -> Self:
        """
        Создать глубокую копию модели через сериализацию.

        Returns:
            Новый экземпляр с теми же данными.
        """
        return self.__class__.from_dict(self.to_dict())

    def __repr__(self) -> str:
        class_name = self.__class__.__name__
        if hasattr(self, 'id'):
            return f"{class_name}(id={getattr(self, 'id')})"
        return f"{class_name}(...)"


# ============================================================================
# ПРИМЕСЬ ДЛЯ СЕРИАЛИЗАЦИИ (Mixin)
# ============================================================================

class SerializableMixin:
    """
    Примесь, добавляющая методы сериализации в dataclass.

    Автоматически сериализует все поля dataclass в словарь.
    Поддерживает вложенные объекты с методами to_dict().

    Usage:
        @dataclass(slots=True)
        class MyModel(SerializableMixin):
            name: str
            value: int
    """

    def to_dict(self) -> dict[str, Any]:
        """
        Автоматическая сериализация всех полей dataclass.

        Returns:
            Словарь с полями объекта.
        """
        result: dict[str, Any] = {}
        for field_name in self.__slots__:
            value = getattr(self, field_name)

            # Обработка специальных типов
            if isinstance(value, UUID):
                result[field_name] = str(value)
            elif hasattr(value, 'to_dict'):
                result[field_name] = value.to_dict()
            elif isinstance(value, list):
                result[field_name] = [
                    item.to_dict() if hasattr(item, 'to_dict') else item
                    for item in value
                ]
            elif isinstance(value, dict):
                result[field_name] = {
                    str(k): v.to_dict() if hasattr(v, 'to_dict') else v
                    for k, v in value.items()
                }
            elif isinstance(value, set):
                result[field_name] = list(value)
            else:
                result[field_name] = value

        return result

    @classmethod
    def _get_field_types(cls) -> dict[str, type]:
        """
        Получить словарь {имя_поля: тип} из аннотаций класса.

        Returns:
            Словарь с типами полей.
        """
        import typing
        hints = typing.get_type_hints(cls)
        return hints