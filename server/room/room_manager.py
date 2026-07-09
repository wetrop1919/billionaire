"""
server/room/room_manager.py

Менеджер игровых комнат.

Обеспечивает:
- Создание и удаление комнат
- Присоединение и выход игроков
- Управление настройками комнаты
- Запуск игры
- Передачу прав владельца

Координирует работу RoomRepository, ObserverManager и EventBus.

Python: 3.13+
"""

from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

from database.repositories.postgresql.room_repository import RoomRepository
from shared.enums import RoomState, UserRole
from shared.models.room import Room, RoomConfig, RoomListItem
from shared.validators import (
    validate_room_name,
    validate_room_password,
    validate_max_players,
    validate_turn_timeout,
)
from server.room.observer_manager import ObserverManager

logger = logging.getLogger("billionaire.server")


# ============================================================================
# ИСКЛЮЧЕНИЯ КОМНАТ
# ============================================================================

class RoomError(Exception):
    """Ошибка управления комнатой."""

    def __init__(self, message: str, error_code: int = 0) -> None:
        self.error_code = error_code
        super().__init__(message)


class RoomNotFoundError(RoomError):
    """Комната не найдена."""

    def __init__(self, room_id: UUID) -> None:
        super().__init__(f"Комната не найдена: {room_id}", 1010)


class RoomFullError(RoomError):
    """Комната заполнена."""

    def __init__(self) -> None:
        super().__init__("Комната заполнена", 1011)


class RoomLockedError(RoomError):
    """Комната защищена паролем."""

    def __init__(self) -> None:
        super().__init__("Комната защищена паролем", 1012)


class RoomWrongPasswordError(RoomError):
    """Неверный пароль."""

    def __init__(self) -> None:
        super().__init__("Неверный пароль комнаты", 1013)


class RoomInGameError(RoomError):
    """Игра уже идёт."""

    def __init__(self) -> None:
        super().__init__("В комнате уже идёт игра", 1014)


class NotRoomOwnerError(RoomError):
    """Не владелец комнаты."""

    def __init__(self) -> None:
        super().__init__("Только владелец комнаты может это сделать", 1015)


# ============================================================================
# МЕНЕДЖЕР КОМНАТ
# ============================================================================

class RoomManager:
    """
    Менеджер игровых комнат.

    Управляет жизненным циклом комнат и координирует
    взаимодействие между игроками и наблюдателями.

    Usage:
        manager = RoomManager(room_repo, observer_manager)
        room = await manager.create_room("Комната", owner_id)
        await manager.join_room(room_id, player_id)
    """

    # Максимальное количество комнат на одного пользователя
    MAX_ROOMS_PER_USER: int = 5

    def __init__(
        self,
        room_repository: RoomRepository,
        observer_manager: ObserverManager,
    ) -> None:
        """
        Инициализация менеджера комнат.

        Args:
            room_repository: Репозиторий комнат.
            observer_manager: Менеджер наблюдателей.
        """
        self._room_repo = room_repository
        self._observer_manager = observer_manager

        # Кеш активных комнат в памяти {room_id: Room}
        self._active_rooms: dict[UUID, Room] = {}

    # ========================================================================
    # СОЗДАНИЕ И УДАЛЕНИЕ
    # ========================================================================

    async def create_room(
        self,
        name: str,
        owner_id: UUID,
        owner_name: str,
        config: Optional[dict[str, Any]] = None,
    ) -> Room:
        """
        Создать новую комнату.

        Args:
            name: Название комнаты.
            owner_id: ID создателя.
            owner_name: Имя создателя.
            config: Словарь с настройками комнаты.

        Returns:
            Созданная комната.

        Raises:
            RoomError: При ошибке валидации или превышении лимита.
        """
        # Валидация названия
        error = validate_room_name(name)
        if error:
            raise RoomError(error)

        # Проверка лимита комнат
        user_rooms = await self._room_repo.count_by_owner(owner_id)
        if user_rooms >= self.MAX_ROOMS_PER_USER:
            raise RoomError(
                f"Достигнут лимит комнат ({self.MAX_ROOMS_PER_USER})"
            )

        # Проверка уникальности названия
        if await self._room_repo.name_exists(name):
            raise RoomError(f"Комната с названием '{name}' уже существует")

        # Создаём конфигурацию
        room_config = RoomConfig()
        if config:
            room_config = RoomConfig.from_dict(config)

        # Создаём комнату
        room = Room.create(
            name=name,
            owner_id=owner_id,
            config=room_config,
        )

        # Сохраняем в БД
        saved_room = await self._room_repo.save(room)

        # Кешируем
        self._active_rooms[saved_room.room_id] = saved_room

        logger.info(
            "Комната '%s' создана пользователем %s (id=%s)",
            name,
            owner_name,
            str(saved_room.room_id)[:8],
        )

        return saved_room

    async def delete_room(self, room_id: UUID, user_id: UUID) -> bool:
        """
        Удалить комнату.

        Args:
            room_id: ID комнаты.
            user_id: ID пользователя (должен быть владельцем).

        Returns:
            True, если комната удалена.

        Raises:
            RoomNotFoundError: Комната не найдена.
            NotRoomOwnerError: Пользователь не владелец.
        """
        room = await self._get_room(room_id)

        if not room.is_owner(user_id):
            raise NotRoomOwnerError()

        # Удаляем наблюдателей
        self._observer_manager.remove_all_observers(room_id)

        # Удаляем из кеша
        self._active_rooms.pop(room_id, None)

        # Удаляем из БД
        await self._room_repo.delete(room_id)

        logger.info(
            "Комната '%s' удалена (id=%s)",
            room.name,
            str(room_id)[:8],
        )

        return True

    # ========================================================================
    # ПРИСОЕДИНЕНИЕ И ВЫХОД
    # ========================================================================

    async def join_room(
        self,
        room_id: UUID,
        user_id: UUID,
        username: str,
        role: str = "player",
        password: Optional[str] = None,
        as_observer: bool = False,
    ) -> Room:
        """
        Присоединиться к комнате.

        Args:
            room_id: ID комнаты.
            user_id: ID пользователя.
            username: Имя пользователя.
            role: Роль пользователя.
            password: Пароль (для приватных комнат).
            as_observer: Войти как наблюдатель.

        Returns:
            Комната после присоединения.

        Raises:
            RoomNotFoundError: Комната не найдена.
            RoomFullError: Комната заполнена.
            RoomLockedError: Требуется пароль.
            RoomWrongPasswordError: Неверный пароль.
            RoomInGameError: Игра уже идёт.
        """
        room = await self._get_room(room_id)

        # Проверка состояния
        if room.is_in_game:
            raise RoomInGameError()

        # Проверка пароля
        if room.config.is_private:
            if room.config.password_hash:
                if not password:
                    raise RoomLockedError()
                # Сравнение пароля (упрощённо — прямой хеш)
                from shared.protocol.crypto import PasswordHasher
                is_valid = await PasswordHasher.verify_password(
                    password, room.config.password_hash
                )
                if not is_valid:
                    raise RoomWrongPasswordError()

        if as_observer:
            # Вход как наблюдатель
            if not room.config.allow_spectators:
                raise RoomError("Наблюдатели запрещены в этой комнате")

            self._observer_manager.add_observer(
                room_id=room_id,
                user_id=user_id,
                username=username,
                role=role,
            )
        else:
            # Вход как игрок
            if room.is_full:
                raise RoomFullError()

            if room.is_player_in_room(user_id):
                raise RoomError("Вы уже в этой комнате")

            room.add_player(user_id)

        # Сохраняем в БД
        await self._room_repo.save(room)

        # Обновляем кеш
        self._active_rooms[room_id] = room

        logger.info(
            "Игрок %s присоединился к комнате '%s' (игроков: %d)",
            username,
            room.name,
            room.players_count,
        )

        return room

    async def leave_room(
        self,
        room_id: UUID,
        user_id: UUID,
    ) -> Optional[UUID]:
        """
        Покинуть комнату.

        Если выходит владелец — права передаются следующему игроку.
        Если комната пустеет — удаляется.

        Args:
            room_id: ID комнаты.
            user_id: ID пользователя.

        Returns:
            ID нового владельца (если был передан) или None.

        Raises:
            RoomNotFoundError: Комната не найдена.
        """
        room = await self._get_room(room_id)

        # Проверяем, является ли пользователь игроком или наблюдателем
        is_player = room.is_player_in_room(user_id)
        is_observer = self._observer_manager.is_observer(room_id, user_id)

        if not is_player and not is_observer:
            raise RoomError("Вы не в этой комнате")

        new_owner_id = None

        if is_player:
            was_owner = room.is_owner(user_id)
            room.remove_player(user_id)

            # Передача прав
            if was_owner and room.players:
                new_owner_id = room.players[0]
                room.transfer_ownership(new_owner_id)
                logger.info(
                    "Права владельца комнаты '%s' переданы %s",
                    room.name,
                    str(new_owner_id)[:8],
                )

            # Удаление пустой комнаты
            if room.is_empty:
                self._observer_manager.remove_all_observers(room_id)
                self._active_rooms.pop(room_id, None)
                await self._room_repo.delete(room_id)
                logger.info("Пустая комната '%s' удалена", room.name)
                return new_owner_id

        if is_observer:
            self._observer_manager.remove_observer(room_id, user_id)

        # Сохраняем
        await self._room_repo.save(room)
        self._active_rooms[room_id] = room

        logger.info(
            "Пользователь %s покинул комнату '%s'",
            str(user_id)[:8],
            room.name,
        )

        return new_owner_id

    # ========================================================================
    # УПРАВЛЕНИЕ КОМНАТОЙ
    # ========================================================================

    async def kick_player(
        self,
        room_id: UUID,
        owner_id: UUID,
        target_id: UUID,
    ) -> bool:
        """
        Выгнать игрока из комнаты.

        Args:
            room_id: ID комнаты.
            owner_id: ID владельца.
            target_id: ID выгоняемого.

        Returns:
            True, если игрок выгнан.

        Raises:
            NotRoomOwnerError: Пользователь не владелец.
            RoomError: Нельзя выгнать себя.
        """
        if owner_id == target_id:
            raise RoomError("Нельзя выгнать самого себя")

        room = await self._get_room(room_id)

        if not room.is_owner(owner_id):
            raise NotRoomOwnerError()

        if not room.is_player_in_room(target_id):
            raise RoomError("Игрок не в комнате")

        room.remove_player(target_id)
        await self._room_repo.save(room)
        self._active_rooms[room_id] = room

        logger.info(
            "Игрок %s выгнан из комнаты '%s'",
            str(target_id)[:8],
            room.name,
        )

        return True

    async def update_settings(
        self,
        room_id: UUID,
        user_id: UUID,
        settings: dict[str, Any],
    ) -> Room:
        """
        Обновить настройки комнаты.

        Args:
            room_id: ID комнаты.
            user_id: ID пользователя.
            settings: Новые настройки.

        Returns:
            Обновлённая комната.

        Raises:
            NotRoomOwnerError: Не владелец.
            RoomInGameError: Игра уже идёт.
        """
        room = await self._get_room(room_id)

        if not room.is_owner(user_id):
            raise NotRoomOwnerError()

        if room.is_in_game:
            raise RoomInGameError()

        # Применяем настройки
        config_dict = room.config.to_dict()
        config_dict.update(settings)
        new_config = RoomConfig.from_dict(config_dict)

        room.update_config(new_config)
        await self._room_repo.save(room)
        self._active_rooms[room_id] = room

        logger.info(
            "Настройки комнаты '%s' обновлены",
            room.name,
        )

        return room

    async def start_game(self, room_id: UUID, user_id: UUID) -> Room:
        """
        Запустить игру в комнате.

        Args:
            room_id: ID комнаты.
            user_id: ID пользователя.

        Returns:
            Комната в состоянии IN_GAME.

        Raises:
            NotRoomOwnerError: Не владелец.
            RoomError: Недостаточно игроков.
        """
        room = await self._get_room(room_id)

        if not room.is_owner(user_id):
            raise NotRoomOwnerError()

        if not room.can_start_game:
            raise RoomError(
                f"Недостаточно игроков для старта (минимум 2, сейчас {room.players_count})"
            )

        # Отмечаем комнату как "в игре"
        room.start_game(UUID("00000000-0000-0000-0000-000000000000"))  # Заглушка, game_id будет заменён

        await self._room_repo.update_state(room_id, RoomState.IN_GAME)
        self._active_rooms[room_id] = room

        logger.info(
            "Игра началась в комнате '%s' (%d игроков)",
            room.name,
            room.players_count,
        )

        return room

    # ========================================================================
    # СПИСОК КОМНАТ
    # ========================================================================

    async def list_rooms(
        self,
        state_filter: Optional[str] = None,
        show_private: bool = True,
        show_full: bool = False,
        offset: int = 0,
        limit: int = 50,
    ) -> list[RoomListItem]:
        """
        Получить список комнат для отображения.

        Args:
            state_filter: Фильтр по состоянию.
            show_private: Показывать приватные.
            show_full: Показывать заполненные.
            offset: Смещение.
            limit: Лимит.

        Returns:
            Список RoomListItem.
        """
        items = await self._room_repo.get_room_list_items(
            state_filter=state_filter,
            show_private=show_private,
            show_full=show_full,
            offset=offset,
            limit=limit,
        )

        # Дополняем информацией о наблюдателях
        for item in items:
            item.players_count = self._get_cached_player_count(item.room_id)

        return items

    # ========================================================================
    # ВНУТРЕННИЕ МЕТОДЫ
    # ========================================================================

    async def _get_room(self, room_id: UUID) -> Room:
        """
        Получить комнату (из кеша или БД).

        Args:
            room_id: ID комнаты.

        Returns:
            Комната.

        Raises:
            RoomNotFoundError: Комната не найдена.
        """
        # Проверяем кеш
        if room_id in self._active_rooms:
            return self._active_rooms[room_id]

        # Загружаем из БД
        room = await self._room_repo.get_by_id(room_id)
        if room is None:
            raise RoomNotFoundError(room_id)

        # Кешируем
        self._active_rooms[room_id] = room
        return room

    def _get_cached_player_count(self, room_id: UUID) -> int:
        """
        Получить количество игроков из кеша.

        Args:
            room_id: ID комнаты.

        Returns:
            Количество игроков (0, если комната не в кеше).
        """
        room = self._active_rooms.get(room_id)
        return room.players_count if room else 0

    # ========================================================================
    # ОЧИСТКА
    # ========================================================================

    async def cleanup_empty_rooms(self, older_than_minutes: int = 60) -> int:
        """
        Очистить пустые комнаты.

        Args:
            older_than_minutes: Возраст в минутах.

        Returns:
            Количество удалённых комнат.
        """
        count = await self._room_repo.delete_empty_rooms(older_than_minutes)

        if count > 0:
            logger.info("Очищено %d пустых комнат", count)

        return count

    # ========================================================================
    # ИНФОРМАЦИЯ
    # ========================================================================

    def get_room_info(self, room_id: UUID) -> Optional[dict]:
        """
        Получить информацию о комнате.

        Args:
            room_id: ID комнаты.

        Returns:
            Словарь с данными или None.
        """
        room = self._active_rooms.get(room_id)
        if room is None:
            return None

        observers = self._observer_manager.get_observers(room_id)

        return {
            "room": room.to_dict(),
            "observers_count": len(observers),
            "observers": [
                {"user_id": str(o["user_id"]), "username": o["username"]}
                for o in observers
            ],
        }

    def get_stats(self) -> dict:
        """
        Получить статистику менеджера комнат.

        Returns:
            Словарь с метриками.
        """
        return {
            "cached_rooms": len(self._active_rooms),
            "observers": self._observer_manager.get_stats(),
        }