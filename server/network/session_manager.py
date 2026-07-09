"""
server/network/session_manager.py

Менеджер клиентских сессий.

Управляет жизненным циклом сессий:
- Создание при подключении
- Аутентификация (привязка пользователя)
- Отслеживание активности
- Отключение по таймауту
- Переподключение

Хранит сессии в памяти с привязкой к asyncio StreamWriter.

Python: 3.13+
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional
from uuid import UUID, uuid4

from shared.constants import (
    SESSION_IDLE_TIMEOUT,
    SESSION_TOKEN_SIZE,
)
from shared.protocol.crypto import TokenGenerator

logger = logging.getLogger("billionaire.network")


# ============================================================================
# ДАННЫЕ СЕССИИ
# ============================================================================

@dataclass(slots=True)
class Session:
    """
    Данные клиентской сессии.

    Attributes:
        session_id: Уникальный идентификатор сессии.
        user_id: ID аутентифицированного пользователя.
        username: Имя пользователя.
        role: Роль пользователя.
        writer: asyncio StreamWriter для отправки данных.
        reader: asyncio StreamReader для чтения данных.
        access_token: Токен доступа.
        hmac_key: Ключ для HMAC-подписи пакетов.
        connected_at: Время подключения.
        last_activity: Время последней активности.
        sequence_number: Счётчик порядковых номеров пакетов.
        is_authenticated: Аутентифицирована ли сессия.
        is_online: Активна ли сессия.
        ip_address: IP-адрес клиента.
        room_id: ID комнаты, в которой находится пользователь.
        game_id: ID игры, в которой участвует пользователь.
    """

    session_id: UUID
    user_id: Optional[UUID] = None
    username: Optional[str] = None
    role: Optional[str] = None
    writer: Optional[asyncio.StreamWriter] = None
    reader: Optional[asyncio.StreamReader] = None
    access_token: Optional[str] = None
    hmac_key: bytes = field(default_factory=lambda: TokenGenerator.generate_session_token().encode())
    connected_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    sequence_number: int = 0
    is_authenticated: bool = False
    is_online: bool = True
    ip_address: str = ""
    room_id: Optional[UUID] = None
    game_id: Optional[UUID] = None

    @property
    def idle_seconds(self) -> float:
        """Время бездействия в секундах."""
        return time.time() - self.last_activity

    @property
    def is_idle(self) -> bool:
        """Превышен ли таймаут бездействия."""
        return self.idle_seconds > SESSION_IDLE_TIMEOUT

    def touch(self) -> None:
        """Обновить время последней активности."""
        self.last_activity = time.time()

    def get_next_sequence(self) -> int:
        """Получить следующий порядковый номер."""
        self.sequence_number += 1
        return self.sequence_number

    def to_dict(self) -> dict:
        """Сериализация для логирования."""
        return {
            "session_id": str(self.session_id),
            "user_id": str(self.user_id) if self.user_id else None,
            "username": self.username,
            "role": self.role,
            "is_authenticated": self.is_authenticated,
            "is_online": self.is_online,
            "ip_address": self.ip_address,
            "connected_seconds": int(time.time() - self.connected_at),
            "idle_seconds": int(self.idle_seconds),
            "room_id": str(self.room_id) if self.room_id else None,
            "game_id": str(self.game_id) if self.game_id else None,
        }


# ============================================================================
# МЕНЕДЖЕР СЕССИЙ
# ============================================================================

class SessionManager:
    """
    Менеджер клиентских сессий.

    Управляет всеми активными подключениями к серверу:
    создание, аутентификация, отслеживание активности,
    отключение неактивных.

    Usage:
        manager = SessionManager()
        session = manager.create_session(writer, reader, "192.168.1.1")
        manager.authenticate(session.session_id, user)
        await manager.send_to_session(session_id, packet_bytes)
    """

    def __init__(self) -> None:
        """Инициализация менеджера сессий."""
        # Основное хранилище: {session_id: Session}
        self._sessions: dict[UUID, Session] = {}

        # Индекс: {user_id: session_id} (для быстрого поиска)
        self._user_to_session: dict[UUID, UUID] = {}

        # Индекс: {access_token: session_id}
        self._token_to_session: dict[str, UUID] = {}

    # ========================================================================
    # СОЗДАНИЕ И УДАЛЕНИЕ СЕССИЙ
    # ========================================================================

    def create_session(
        self,
        writer: asyncio.StreamWriter,
        reader: asyncio.StreamReader,
        ip_address: str = "",
    ) -> Session:
        """
        Создать новую сессию при подключении клиента.

        Args:
            writer: StreamWriter для отправки данных.
            reader: StreamReader для чтения данных.
            ip_address: IP-адрес клиента.

        Returns:
            Новая сессия.
        """
        session = Session(
            session_id=uuid4(),
            writer=writer,
            reader=reader,
            ip_address=ip_address,
            connected_at=time.time(),
        )

        self._sessions[session.session_id] = session

        logger.info(
            "Новая сессия: %s (IP: %s)",
            str(session.session_id)[:8],
            ip_address,
        )

        return session

    def remove_session(self, session_id: UUID) -> Optional[Session]:
        """
        Удалить сессию (при отключении клиента).

        Args:
            session_id: ID сессии.

        Returns:
            Удалённая сессия или None.
        """
        session = self._sessions.pop(session_id, None)
        if session is None:
            return None

        # Очищаем индексы
        if session.user_id:
            self._user_to_session.pop(session.user_id, None)
        if session.access_token:
            self._token_to_session.pop(session.access_token, None)

        logger.info(
            "Сессия удалена: %s (пользователь: %s)",
            str(session_id)[:8],
            session.username or "не аутентифицирован",
        )

        return session

    # ========================================================================
    # АУТЕНТИФИКАЦИЯ
    # ========================================================================

    def authenticate_session(
        self,
        session_id: UUID,
        user_id: UUID,
        username: str,
        role: str,
        access_token: str,
    ) -> bool:
        """
        Аутентифицировать сессию (привязать к пользователю).

        Отзывает предыдущую сессию пользователя, если она была.

        Args:
            session_id: ID сессии.
            user_id: ID пользователя.
            username: Имя пользователя.
            role: Роль пользователя.
            access_token: Токен доступа.

        Returns:
            True, если аутентификация выполнена.
        """
        session = self._sessions.get(session_id)
        if session is None:
            return False

        # Отзываем предыдущую сессию пользователя
        old_session_id = self._user_to_session.get(user_id)
        if old_session_id and old_session_id != session_id:
            old_session = self._sessions.get(old_session_id)
            if old_session:
                logger.info(
                    "Отзыв предыдущей сессии пользователя %s: %s",
                    username,
                    str(old_session_id)[:8],
                )
                old_session.is_authenticated = False
                old_session.access_token = None
                # Закрываем соединение
                if old_session.writer:
                    try:
                        old_session.writer.close()
                    except Exception:
                        pass

        # Обновляем сессию
        session.user_id = user_id
        session.username = username
        session.role = role
        session.access_token = access_token
        session.is_authenticated = True
        session.touch()

        # Обновляем индексы
        self._user_to_session[user_id] = session_id
        self._token_to_session[access_token] = session_id

        logger.info(
            "Сессия %s аутентифицирована как %s (роль: %s)",
            str(session_id)[:8],
            username,
            role,
        )

        return True

    def deauthenticate_session(self, session_id: UUID) -> bool:
        """
        Деаутентифицировать сессию (logout).

        Args:
            session_id: ID сессии.

        Returns:
            True, если выполнено.
        """
        session = self._sessions.get(session_id)
        if session is None:
            return False

        # Очищаем данные аутентификации
        if session.user_id:
            self._user_to_session.pop(session.user_id, None)
        if session.access_token:
            self._token_to_session.pop(session.access_token, None)

        session.user_id = None
        session.username = None
        session.role = None
        session.access_token = None
        session.is_authenticated = False

        logger.info("Сессия %s деаутентифицирована", str(session_id)[:8])
        return True

    # ========================================================================
    # ДОСТУП К СЕССИЯМ
    # ========================================================================

    def get_session(self, session_id: UUID) -> Optional[Session]:
        """
        Получить сессию по ID.

        Args:
            session_id: ID сессии.

        Returns:
            Сессия или None.
        """
        return self._sessions.get(session_id)

    def get_session_by_token(self, access_token: str) -> Optional[Session]:
        """
        Получить сессию по токену доступа.

        Args:
            access_token: Токен доступа.

        Returns:
            Сессия или None.
        """
        session_id = self._token_to_session.get(access_token)
        if session_id:
            return self._sessions.get(session_id)
        return None

    def get_session_by_user(self, user_id: UUID) -> Optional[Session]:
        """
        Получить сессию пользователя.

        Args:
            user_id: ID пользователя.

        Returns:
            Сессия или None.
        """
        session_id = self._user_to_session.get(user_id)
        if session_id:
            return self._sessions.get(session_id)
        return None

    def is_user_online(self, user_id: UUID) -> bool:
        """
        Проверить, онлайн ли пользователь.

        Args:
            user_id: ID пользователя.

        Returns:
            True, если есть активная сессия.
        """
        session = self.get_session_by_user(user_id)
        return session is not None and session.is_online

    # ========================================================================
    # РАБОТА С КОМНАТАМИ И ИГРАМИ
    # ========================================================================

    def set_session_room(self, session_id: UUID, room_id: UUID) -> None:
        """
        Привязать сессию к комнате.

        Args:
            session_id: ID сессии.
            room_id: ID комнаты.
        """
        session = self._sessions.get(session_id)
        if session:
            session.room_id = room_id

    def set_session_game(self, session_id: UUID, game_id: UUID) -> None:
        """
        Привязать сессию к игре.

        Args:
            session_id: ID сессии.
            game_id: ID игры.
        """
        session = self._sessions.get(session_id)
        if session:
            session.game_id = game_id

    def clear_session_room(self, session_id: UUID) -> None:
        """Отвязать сессию от комнаты."""
        session = self._sessions.get(session_id)
        if session:
            session.room_id = None

    def get_sessions_in_room(self, room_id: UUID) -> list[Session]:
        """
        Получить все сессии в комнате.

        Args:
            room_id: ID комнаты.

        Returns:
            Список сессий.
        """
        return [
            s for s in self._sessions.values()
            if s.room_id == room_id and s.is_online
        ]

    def get_sessions_in_game(self, game_id: UUID) -> list[Session]:
        """
        Получить все сессии в игре.

        Args:
            game_id: ID игры.

        Returns:
            Список сессий.
        """
        return [
            s for s in self._sessions.values()
            if s.game_id == game_id and s.is_online
        ]

    # ========================================================================
    # ОТПРАВКА ДАННЫХ
    # ========================================================================

    async def send_to_session(self, session_id: UUID, data: bytes) -> bool:
        """
        Отправить данные конкретной сессии.

        Args:
            session_id: ID сессии.
            data: Байты для отправки.

        Returns:
            True, если отправка выполнена.
        """
        session = self._sessions.get(session_id)
        if session is None or session.writer is None:
            return False

        try:
            session.writer.write(data)
            await session.writer.drain()
            session.touch()
            return True
        except Exception as e:
            logger.error(
                "Ошибка отправки данных сессии %s: %s",
                str(session_id)[:8],
                e,
            )
            return False

    async def broadcast_to_room(
        self,
        room_id: UUID,
        data: bytes,
        exclude_session: Optional[UUID] = None,
    ) -> int:
        """
        Отправить данные всем сессиям в комнате.

        Args:
            room_id: ID комнаты.
            data: Байты для отправки.
            exclude_session: ID сессии для исключения.

        Returns:
            Количество получателей.
        """
        sessions = self.get_sessions_in_room(room_id)
        count = 0

        for session in sessions:
            if exclude_session and session.session_id == exclude_session:
                continue
            if await self.send_to_session(session.session_id, data):
                count += 1

        return count

    async def broadcast_to_game(
        self,
        game_id: UUID,
        data: bytes,
        exclude_session: Optional[UUID] = None,
    ) -> int:
        """
        Отправить данные всем сессиям в игре.

        Args:
            game_id: ID игры.
            data: Байты для отправки.
            exclude_session: ID сессии для исключения.

        Returns:
            Количество получателей.
        """
        sessions = self.get_sessions_in_game(game_id)
        count = 0

        for session in sessions:
            if exclude_session and session.session_id == exclude_session:
                continue
            if await self.send_to_session(session.session_id, data):
                count += 1

        return count

    # ========================================================================
    # УПРАВЛЕНИЕ НЕАКТИВНЫМИ
    # ========================================================================

    def disconnect_idle_sessions(self) -> int:
        """
        Отключить неактивные сессии.

        Закрывает соединения для сессий, превысивших
        таймаут бездействия.

        Returns:
            Количество отключённых сессий.
        """
        now = time.time()
        idle_sessions = [
            s for s in self._sessions.values()
            if s.is_idle and s.is_online
        ]

        for session in idle_sessions:
            logger.info(
                "Отключение неактивной сессии %s (бездействие: %.0f сек)",
                str(session.session_id)[:8],
                session.idle_seconds,
            )
            session.is_online = False
            if session.writer:
                try:
                    session.writer.close()
                except Exception:
                    pass

        return len(idle_sessions)

    def disconnect_session(self, session_id: UUID) -> bool:
        """
        Принудительно отключить сессию.

        Args:
            session_id: ID сессии.

        Returns:
            True, если отключение выполнено.
        """
        session = self._sessions.get(session_id)
        if session is None:
            return False

        session.is_online = False
        if session.writer:
            try:
                session.writer.close()
            except Exception:
                pass

        logger.info("Сессия %s принудительно отключена", str(session_id)[:8])
        return True

    # ========================================================================
    # ПЕРЕПОДКЛЮЧЕНИЕ
    # ========================================================================

    def prepare_reconnect(
        self,
        user_id: UUID,
        game_id: UUID,
    ) -> Optional[UUID]:
        """
        Подготовить сессию к переподключению.

        Сохраняет game_id для пользователя, чтобы при
        переподключении восстановить контекст.

        Args:
            user_id: ID пользователя.
            game_id: ID игры.

        Returns:
            ID сессии или None.
        """
        session = self.get_session_by_user(user_id)
        if session:
            session.game_id = game_id
            return session.session_id
        return None

    # ========================================================================
    # ИНФОРМАЦИЯ
    # ========================================================================

    @property
    def active_sessions_count(self) -> int:
        """Количество активных сессий."""
        return sum(1 for s in self._sessions.values() if s.is_online)

    @property
    def authenticated_sessions_count(self) -> int:
        """Количество аутентифицированных сессий."""
        return sum(
            1 for s in self._sessions.values()
            if s.is_authenticated and s.is_online
        )

    def get_all_sessions(self) -> list[dict]:
        """
        Получить список всех сессий.

        Returns:
            Список словарей с данными сессий.
        """
        return [s.to_dict() for s in self._sessions.values()]

    def get_stats(self) -> dict:
        """
        Получить статистику менеджера сессий.

        Returns:
            Словарь с метриками.
        """
        return {
            "total_sessions": len(self._sessions),
            "active_sessions": self.active_sessions_count,
            "authenticated_sessions": self.authenticated_sessions_count,
            "users_online": len(self._user_to_session),
        }