"""
database/repositories/base_repository.py

Абстрактный базовый репозиторий для всех сущностей.

Реализует паттерн Repository — абстрагирует доступ к данным,
позволяя заменить СУБД без изменения бизнес-логики.

Все репозитории наследуются от этого класса и реализуют
стандартные CRUD-операции для своего типа сущности.

Python: 3.13+
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Generic, Optional, TypeVar
from uuid import UUID

from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession


# ============================================================================
# ТИПЫ ДЛЯ GENERIC
# ============================================================================

# TModel — тип ORM-модели SQLAlchemy
TModel = TypeVar("TModel")

# TEntity — тип бизнес-сущности (dataclass из shared/models)
TEntity = TypeVar("TEntity")


# ============================================================================
# БАЗОВЫЙ РЕПОЗИТОРИЙ
# ============================================================================

class BaseRepository(ABC, Generic[TModel, TEntity]):
    """
    Абстрактный базовый репозиторий.

    Предоставляет стандартные операции для работы с сущностями:
    - get_by_id — получить по ID
    - get_all — получить все записи
    - save — создать или обновить
    - delete — удалить
    - exists — проверить существование
    - count — подсчитать количество

    Наследники должны реализовать:
    - _to_entity — преобразование ORM-модели в бизнес-сущность
    - _to_model — преобразование бизнес-сущности в ORM-модель
    - _update_model — обновление существующей ORM-модели

    Attributes:
        session: Асинхронная сессия SQLAlchemy.
        model_class: Класс ORM-модели.
    """

    def __init__(self, session: AsyncSession, model_class: type[TModel]) -> None:
        """
        Инициализация репозитория.

        Args:
            session: Асинхронная сессия БД.
            model_class: Класс ORM-модели.
        """
        self._session: AsyncSession = session
        self._model_class: type[TModel] = model_class

    # ========================================================================
    # АБСТРАКТНЫЕ МЕТОДЫ (ДОЛЖНЫ БЫТЬ РЕАЛИЗОВАНЫ В НАСЛЕДНИКАХ)
    # ========================================================================

    @abstractmethod
    def _to_entity(self, model: TModel) -> TEntity:
        """
        Преобразовать ORM-модель в бизнес-сущность.

        Args:
            model: ORM-модель из БД.

        Returns:
            Бизнес-сущность (dataclass).
        """
        ...

    @abstractmethod
    def _to_model(self, entity: TEntity) -> TModel:
        """
        Преобразовать бизнес-сущность в ORM-модель.

        Args:
            entity: Бизнес-сущность.

        Returns:
            ORM-модель для сохранения в БД.
        """
        ...

    @abstractmethod
    def _update_model(self, model: TModel, entity: TEntity) -> TModel:
        """
        Обновить существующую ORM-модель данными из бизнес-сущности.

        Args:
            model: Существующая ORM-модель.
            entity: Бизнес-сущность с новыми данными.

        Returns:
            Обновлённая ORM-модель.
        """
        ...

    @abstractmethod
    def _get_model_id(self, model: TModel) -> UUID:
        """
        Получить идентификатор ORM-модели.

        Args:
            model: ORM-модель.

        Returns:
            UUID модели.
        """
        ...

    # ========================================================================
    # CRUD-ОПЕРАЦИИ
    # ========================================================================

    async def get_by_id(self, entity_id: UUID) -> Optional[TEntity]:
        """
        Получить сущность по идентификатору.

        Args:
            entity_id: UUID сущности.

        Returns:
            Бизнес-сущность или None, если не найдена.
        """
        result = await self._session.execute(
            select(self._model_class).where(
                self._get_id_column() == entity_id
            )
        )
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return self._to_entity(model)

    async def get_all(
        self,
        offset: int = 0,
        limit: int = 100,
        filters: Optional[dict[str, Any]] = None,
    ) -> list[TEntity]:
        """
        Получить список сущностей с пагинацией и фильтрацией.

        Args:
            offset: Смещение.
            limit: Максимальное количество.
            filters: Словарь фильтров {поле: значение}.

        Returns:
            Список бизнес-сущностей.
        """
        query = select(self._model_class)

        # Применяем фильтры
        if filters:
            for field, value in filters.items():
                column = getattr(self._model_class, field, None)
                if column is not None:
                    query = query.where(column == value)

        query = query.offset(offset).limit(limit)
        result = await self._session.execute(query)
        models = result.scalars().all()
        return [self._to_entity(model) for model in models]

    async def save(self, entity: TEntity) -> TEntity:
        """
        Сохранить сущность (создать или обновить).

        Если сущность с таким ID уже существует — обновляет,
        иначе создаёт новую запись.

        Args:
            entity: Бизнес-сущность для сохранения.

        Returns:
            Сохранённая бизнес-сущность.
        """
        entity_id = self._get_entity_id(entity)

        # Проверяем существование
        existing = await self._session.execute(
            select(self._model_class).where(
                self._get_id_column() == entity_id
            )
        )
        model = existing.scalar_one_or_none()

        if model is not None:
            # Обновление
            model = self._update_model(model, entity)
        else:
            # Создание
            model = self._to_model(entity)
            self._session.add(model)

        await self._session.flush()
        return self._to_entity(model)

    async def save_many(self, entities: list[TEntity]) -> list[TEntity]:
        """
        Сохранить несколько сущностей.

        Args:
            entities: Список бизнес-сущностей.

        Returns:
            Список сохранённых сущностей.
        """
        saved: list[TEntity] = []
        for entity in entities:
            result = await self.save(entity)
            saved.append(result)
        return saved

    async def delete(self, entity_id: UUID) -> bool:
        """
        Удалить сущность по идентификатору.

        Args:
            entity_id: UUID сущности.

        Returns:
            True, если удаление выполнено.
        """
        result = await self._session.execute(
            delete(self._model_class).where(
                self._get_id_column() == entity_id
            )
        )
        await self._session.flush()
        return result.rowcount > 0

    async def exists(self, entity_id: UUID) -> bool:
        """
        Проверить существование сущности.

        Args:
            entity_id: UUID сущности.

        Returns:
            True, если сущность существует.
        """
        result = await self._session.execute(
            select(func.count()).select_from(self._model_class).where(
                self._get_id_column() == entity_id
            )
        )
        count = result.scalar_one()
        return count > 0

    async def count(self, filters: Optional[dict[str, Any]] = None) -> int:
        """
        Подсчитать количество сущностей.

        Args:
            filters: Словарь фильтров {поле: значение}.

        Returns:
            Количество записей.
        """
        query = select(func.count()).select_from(self._model_class)

        if filters:
            for field, value in filters.items():
                column = getattr(self._model_class, field, None)
                if column is not None:
                    query = query.where(column == value)

        result = await self._session.execute(query)
        return result.scalar_one()

    # ========================================================================
    # ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ
    # ========================================================================

    def _get_id_column(self):
        """
        Получить колонку с первичным ключом.

        Ищет колонку с именем, содержащим "id" или "user_id".
        Для составных ключей нужно переопределить в наследниках.

        Returns:
            Колонка первичного ключа.
        """
        # Пробуем найти колонку по имени
        for name in ["user_id", "room_id", "game_id", "trade_id", "instance_id", "id"]:
            column = getattr(self._model_class, name, None)
            if column is not None:
                return column

        # Если не нашли — берём первую primary_key колонку
        for column in self._model_class.__table__.primary_key.columns:
            return column

        raise AttributeError(
            f"Не удалось найти ID-колонку в модели {self._model_class.__name__}"
        )

    def _get_entity_id(self, entity: TEntity) -> UUID:
        """
        Получить идентификатор бизнес-сущности.

        Пытается получить атрибут id, user_id, room_id, game_id.

        Args:
            entity: Бизнес-сущность.

        Returns:
            UUID сущности.
        """
        for attr in ["user_id", "room_id", "game_id", "trade_id", "instance_id", "id"]:
            value = getattr(entity, attr, None)
            if isinstance(value, UUID):
                return value
            if attr == "id" and hasattr(entity, "id"):
                value = getattr(entity, "id")
                if isinstance(value, UUID):
                    return value

        raise AttributeError(
            f"Не удалось получить идентификатор сущности {type(entity).__name__}"
        )

    @property
    def session(self) -> AsyncSession:
        """Получить текущую сессию."""
        return self._session

    @property
    def model_class(self) -> type[TModel]:
        """Получить класс ORM-модели."""
        return self._model_class