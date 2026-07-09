"""
database/models.py

ORM-модели SQLAlchemy для проекта "Миллиардер".

Содержит декларативные модели, соответствующие таблицам PostgreSQL.
Использует UUID в качестве первичных ключей, JSONB для гибких данных,
TIMESTAMPTZ для временных меток с часовым поясом.

Все модели наследуются от Base (declarative base SQLAlchemy 2.x).

Python: 3.13+
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Index,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


# ============================================================================
# БАЗОВЫЙ КЛАСС
# ============================================================================

class Base(DeclarativeBase):
    """
    Базовый класс для всех ORM-моделей.

    Предоставляет общие методы и метаданные.
    """

    def to_dict(self) -> dict[str, Any]:
        """
        Сериализовать модель в словарь.

        Returns:
            Словарь с данными модели.
        """
        result: dict[str, Any] = {}
        for column in self.__table__.columns:
            value = getattr(self, column.name)
            if isinstance(value, uuid.UUID):
                result[column.name] = str(value)
            elif isinstance(value, datetime):
                result[column.name] = value.isoformat()
            else:
                result[column.name] = value
        return result

    def __repr__(self) -> str:
        class_name = self.__class__.__name__
        pk = getattr(self, "id", getattr(self, "user_id", None))
        if pk:
            return f"{class_name}(id={pk})"
        return f"{class_name}(...)"


# ============================================================================
# ТАБЛИЦА: users
# ============================================================================

class UserModel(Base):
    """
    Пользователь системы.

    Хранит учётные данные, роль и статистику игрока.
    """

    __tablename__ = "users"

    # Первичный ключ
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Уникальный идентификатор пользователя",
    )

    # Учётные данные
    username: Mapped[str] = mapped_column(
        String(32),
        unique=True,
        nullable=False,
        index=True,
        comment="Имя пользователя",
    )
    password_hash: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Хеш пароля (Argon2id)",
    )

    # Роль
    role: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="player",
        index=True,
        comment="Роль: creator, player, observer",
    )

    # Временные метки
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        comment="Дата регистрации",
    )
    last_login: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Последний вход",
    )

    # Статус
    is_banned: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Флаг блокировки",
    )

    # Статистика
    total_games: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Всего игр",
    )
    wins: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Побед",
    )
    total_money_earned: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Всего заработано денег",
    )

    __table_args__ = (
        Index("idx_users_username", "username", unique=True),
        Index("idx_users_role", "role"),
        {"comment": "Пользователи системы"},
    )


# ============================================================================
# ТАБЛИЦА: rooms
# ============================================================================

class RoomModel(Base):
    """
    Игровая комната.

    Хранит конфигурацию комнаты и список игроков/наблюдателей.
    """

    __tablename__ = "rooms"

    # Первичный ключ
    room_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Уникальный идентификатор комнаты",
    )

    # Основные поля
    name: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="Название комнаты",
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Владелец комнаты",
    )

    # Настройки
    is_private: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Приватная комната",
    )
    password_hash: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Хеш пароля комнаты",
    )
    max_players: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=4,
        comment="Максимум игроков",
    )

    # Состояние
    state: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="waiting",
        index=True,
        comment="Состояние: waiting, in_game, finished",
    )

    # Параметры игры (JSONB)
    game_params: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        comment="Параметры игры (правила, таймауты)",
    )

    # Временная метка
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        comment="Дата создания",
    )

    __table_args__ = (
        Index("idx_rooms_state", "state"),
        Index("idx_rooms_owner", "owner_id"),
        {"comment": "Игровые комнаты"},
    )


# ============================================================================
# ТАБЛИЦА: games
# ============================================================================

class GameModel(Base):
    """
    Игровая сессия.

    Хранит состояние игры, очерёдность ходов и параметры.
    """

    __tablename__ = "games"

    # Первичный ключ
    game_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Уникальный идентификатор игры",
    )

    # Связь с комнатой
    room_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rooms.room_id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        comment="Связанная комната",
    )

    # Состояние игры
    state: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="waiting_for_players",
        index=True,
        comment="Состояние игры",
    )

    # Ход
    current_turn_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Индекс текущего игрока",
    )
    turn_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Номер текущего хода",
    )

    # Состояние поля (JSONB)
    board_state: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        comment="Состояние игрового поля",
    )

    # Деньги на бесплатной парковке
    free_parking_money: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Деньги на бесплатной парковке",
    )

    # Временные метки
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Время начала игры",
    )
    finished_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Время завершения",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        comment="Дата создания",
    )

    __table_args__ = (
        Index("idx_games_room", "room_id", unique=True),
        Index("idx_games_state", "state"),
        {"comment": "Игровые сессии"},
    )


# ============================================================================
# ТАБЛИЦА: game_players
# ============================================================================

class GamePlayerModel(Base):
    """
    Состояние игрока в конкретной игре.

    Хранит деньги, позицию, собственность и статус игрока.
    """

    __tablename__ = "game_players"

    # Внешние ключи
    game_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("games.game_id", ondelete="CASCADE"),
        primary_key=True,
        comment="ID игры",
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        primary_key=True,
        comment="ID игрока",
    )

    # Игровые данные
    slot_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Порядковый номер игрока",
    )
    money: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1500,
        comment="Текущий баланс",
    )
    position: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Позиция на поле (0-39)",
    )

    # Собственность и карточки (JSONB)
    properties: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        comment="Список ID собственности",
    )
    cards: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        comment="Карточки на руках",
    )

    # Статусы
    in_jail: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="В тюрьме",
    )
    jail_rounds: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Кругов в тюрьме",
    )
    bankrupt: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Банкрот",
    )
    is_online: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="Онлайн",
    )

    # Отображение
    color: Mapped[str] = mapped_column(
        String(7),
        nullable=False,
        default="#3498db",
        comment="Цвет фишки (#XXXXXX)",
    )

    __table_args__ = (
        Index("idx_game_players_game", "game_id"),
        Index("idx_game_players_user", "user_id"),
        {"comment": "Состояния игроков в игре"},
    )


# ============================================================================
# ТАБЛИЦА: game_properties
# ============================================================================

class GamePropertyModel(Base):
    """
    Состояние собственности в конкретной игре.

    Хранит владельца, уровень застройки и статус залога.
    """

    __tablename__ = "game_properties"

    # Внешние ключи
    game_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("games.game_id", ondelete="CASCADE"),
        primary_key=True,
        comment="ID игры",
    )
    property_id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        comment="Идентификатор собственности",
    )

    # Владелец
    owner_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Владелец",
    )

    # Состояние
    houses: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Количество домов (0-4)",
    )
    has_hotel: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Есть отель",
    )
    mortgaged: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="В залоге",
    )

    __table_args__ = (
        Index("idx_game_props_game", "game_id"),
        Index("idx_game_props_owner", "owner_id"),
        {"comment": "Состояния собственности в игре"},
    )


# ============================================================================
# ТАБЛИЦА: player_cards
# ============================================================================

class PlayerCardModel(Base):
    """
    Карточки игроков (сохраняемые, продаваемые).
    """

    __tablename__ = "player_cards"

    # Первичный ключ
    instance_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Уникальный ID экземпляра карточки",
    )

    # Внешние ключи
    game_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("games.game_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="ID игры",
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Владелец",
    )

    # Данные карточки
    card_id: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="ID карточки",
    )
    card_type: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        comment="Тип: chance, fund",
    )
    can_be_sold: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Можно продать",
    )
    is_used: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Использована",
    )

    __table_args__ = (
        Index("idx_player_cards_game", "game_id"),
        Index("idx_player_cards_user", "user_id"),
        {"comment": "Карточки игроков"},
    )


# ============================================================================
# ТАБЛИЦА: trade_offers
# ============================================================================

class TradeOfferModel(Base):
    """
    Торговые предложения между игроками.
    """

    __tablename__ = "trade_offers"

    # Первичный ключ
    trade_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Уникальный ID предложения",
    )

    # Внешние ключи
    game_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("games.game_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="ID игры",
    )
    from_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        comment="Инициатор",
    )
    to_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        comment="Получатель",
    )

    # Данные предложения (JSONB)
    offer: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        comment="Предлагаемое: {properties, cards, money, loan}",
    )
    request: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        comment="Запрашиваемое: {properties, cards, money}",
    )

    # Статус
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="pending",
        index=True,
        comment="Статус: pending, accepted, declined, expired, cancelled",
    )

    # Временные метки
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        comment="Время создания",
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Время истечения",
    )

    __table_args__ = (
        Index("idx_trades_game", "game_id"),
        Index("idx_trades_status", "status"),
        {"comment": "Торговые предложения"},
    )


# ============================================================================
# ТАБЛИЦА: chat_messages
# ============================================================================

class ChatMessageModel(Base):
    """
    Сообщения чата комнаты.
    """

    __tablename__ = "chat_messages"

    # Первичный ключ
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        comment="Автоинкрементный ID",
    )

    # Внешние ключи
    room_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rooms.room_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="ID комнаты",
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
        comment="Отправитель (NULL = система)",
    )

    # Содержимое
    message_type: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="player",
        comment="Тип: player, system, admin",
    )
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Содержимое сообщения",
    )

    # Временная метка
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        comment="Время отправки",
    )

    __table_args__ = (
        Index("idx_chat_room", "room_id"),
        Index("idx_chat_created", "room_id", "created_at"),
        {"comment": "Сообщения чата"},
    )


# ============================================================================
# ТАБЛИЦА: game_events
# ============================================================================

class GameEventModel(Base):
    """
    Журнал игровых событий.
    """

    __tablename__ = "game_events"

    # Первичный ключ
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        comment="Автоинкрементный ID",
    )

    # Внешние ключи
    game_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("games.game_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="ID игры",
    )

    # Данные события
    event_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        index=True,
        comment="Тип события",
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
        comment="Инициатор",
    )
    target_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        comment="Цель (игрок, собственность)",
    )
    data: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        comment="Данные события",
    )

    # Ход
    turn_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Номер хода",
    )
    sequence: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Порядковый номер события",
    )

    # Временная метка
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        comment="Время события",
    )

    __table_args__ = (
        Index("idx_events_game", "game_id"),
        Index("idx_events_type", "event_type"),
        Index("idx_events_sequence", "game_id", "sequence"),
        {"comment": "Журнал игровых событий"},
    )


# ============================================================================
# ТАБЛИЦА: network_logs
# ============================================================================

class NetworkLogModel(Base):
    """
    Журнал сетевых событий.
    """

    __tablename__ = "network_logs"

    # Первичный ключ
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        comment="Автоинкрементный ID",
    )

    # Данные
    event_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="Тип события: connect, disconnect, error, heartbeat",
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Пользователь",
    )
    ip_address: Mapped[Optional[str]] = mapped_column(
        String(45),
        nullable=True,
        comment="IP-адрес",
    )
    packet_type: Mapped[Optional[str]] = mapped_column(
        String(32),
        nullable=True,
        comment="Тип пакета",
    )
    data: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        comment="Дополнительные данные",
    )

    # Временная метка
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
        comment="Время события",
    )

    __table_args__ = (
        Index("idx_netlog_user", "user_id"),
        Index("idx_netlog_created", "created_at"),
        {"comment": "Журнал сетевых событий"},
    )


# ============================================================================
# ТАБЛИЦА: admin_logs
# ============================================================================

class AdminLogModel(Base):
    """
    Журнал административных действий.
    """

    __tablename__ = "admin_logs"

    # Первичный ключ
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        comment="Автоинкрементный ID",
    )

    # Данные
    admin_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Администратор",
    )
    command: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="Выполненная команда",
    )
    target_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        comment="Цель команды",
    )
    data: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        comment="Параметры команды",
    )

    # Временная метка
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
        comment="Время действия",
    )

    __table_args__ = (
        Index("idx_adminlog_admin", "admin_id"),
        Index("idx_adminlog_created", "created_at"),
        {"comment": "Журнал административных действий"},
    )