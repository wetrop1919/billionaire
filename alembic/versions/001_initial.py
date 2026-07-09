"""
alembic/versions/001_initial.py

Начальная миграция — создание всех таблиц базы данных.

Создаёт 11 таблиц:
- users
- rooms
- games
- game_players
- game_properties
- player_cards
- trade_offers
- chat_messages
- game_events
- network_logs
- admin_logs

Revision ID: 001
Revises: None
Create Date: 2024-01-15 10:00:00.000000
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# Идентификаторы ревизии
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Применить миграцию: создать все таблицы."""

    # ========================================================================
    # Таблица: users
    # ========================================================================
    op.create_table(
        "users",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            comment="Уникальный идентификатор пользователя",
        ),
        sa.Column(
            "username",
            sa.String(32),
            unique=True,
            nullable=False,
            comment="Имя пользователя",
        ),
        sa.Column(
            "password_hash",
            sa.Text,
            nullable=False,
            comment="Хеш пароля (Argon2id)",
        ),
        sa.Column(
            "role",
            sa.String(16),
            nullable=False,
            server_default="player",
            comment="Роль: creator, player, observer",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            comment="Дата регистрации",
        ),
        sa.Column(
            "last_login",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Последний вход",
        ),
        sa.Column(
            "is_banned",
            sa.Boolean,
            nullable=False,
            server_default=sa.false(),
            comment="Флаг блокировки",
        ),
        sa.Column(
            "total_games",
            sa.Integer,
            nullable=False,
            server_default="0",
            comment="Всего игр",
        ),
        sa.Column(
            "wins",
            sa.Integer,
            nullable=False,
            server_default="0",
            comment="Побед",
        ),
        sa.Column(
            "total_money_earned",
            sa.Integer,
            nullable=False,
            server_default="0",
            comment="Всего заработано денег",
        ),
        comment="Пользователи системы",
    )
    op.create_index("idx_users_username", "users", ["username"], unique=True)
    op.create_index("idx_users_role", "users", ["role"])

    # ========================================================================
    # Таблица: rooms
    # ========================================================================
    op.create_table(
        "rooms",
        sa.Column(
            "room_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            comment="Уникальный идентификатор комнаты",
        ),
        sa.Column(
            "name",
            sa.String(32),
            nullable=False,
            comment="Название комнаты",
        ),
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.user_id", ondelete="CASCADE"),
            nullable=False,
            comment="Владелец комнаты",
        ),
        sa.Column(
            "is_private",
            sa.Boolean,
            nullable=False,
            server_default=sa.false(),
            comment="Приватная комната",
        ),
        sa.Column(
            "password_hash",
            sa.Text,
            nullable=True,
            comment="Хеш пароля комнаты",
        ),
        sa.Column(
            "max_players",
            sa.Integer,
            nullable=False,
            server_default="4",
            comment="Максимум игроков",
        ),
        sa.Column(
            "state",
            sa.String(16),
            nullable=False,
            server_default="waiting",
            comment="Состояние: waiting, in_game, finished",
        ),
        sa.Column(
            "game_params",
            postgresql.JSONB,
            nullable=False,
            server_default="{}",
            comment="Параметры игры (правила, таймауты)",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            comment="Дата создания",
        ),
        comment="Игровые комнаты",
    )
    op.create_index("idx_rooms_state", "rooms", ["state"])
    op.create_index("idx_rooms_owner", "rooms", ["owner_id"])

    # ========================================================================
    # Таблица: games
    # ========================================================================
    op.create_table(
        "games",
        sa.Column(
            "game_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            comment="Уникальный идентификатор игры",
        ),
        sa.Column(
            "room_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("rooms.room_id", ondelete="CASCADE"),
            unique=True,
            nullable=False,
            comment="Связанная комната",
        ),
        sa.Column(
            "state",
            sa.String(32),
            nullable=False,
            server_default="waiting_for_players",
            comment="Состояние игры",
        ),
        sa.Column(
            "current_turn_index",
            sa.Integer,
            nullable=False,
            server_default="0",
            comment="Индекс текущего игрока",
        ),
        sa.Column(
            "turn_number",
            sa.Integer,
            nullable=False,
            server_default="0",
            comment="Номер текущего хода",
        ),
        sa.Column(
            "board_state",
            postgresql.JSONB,
            nullable=False,
            server_default="{}",
            comment="Состояние игрового поля",
        ),
        sa.Column(
            "free_parking_money",
            sa.Integer,
            nullable=False,
            server_default="0",
            comment="Деньги на бесплатной парковке",
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Время начала игры",
        ),
        sa.Column(
            "finished_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Время завершения",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            comment="Дата создания",
        ),
        comment="Игровые сессии",
    )
    op.create_index("idx_games_room", "games", ["room_id"], unique=True)
    op.create_index("idx_games_state", "games", ["state"])

    # ========================================================================
    # Таблица: game_players
    # ========================================================================
    op.create_table(
        "game_players",
        sa.Column(
            "game_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("games.game_id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
            comment="ID игры",
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.user_id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
            comment="ID игрока",
        ),
        sa.Column(
            "slot_index",
            sa.Integer,
            nullable=False,
            comment="Порядковый номер игрока",
        ),
        sa.Column(
            "money",
            sa.Integer,
            nullable=False,
            server_default="1500",
            comment="Текущий баланс",
        ),
        sa.Column(
            "position",
            sa.Integer,
            nullable=False,
            server_default="0",
            comment="Позиция на поле (0-39)",
        ),
        sa.Column(
            "properties",
            postgresql.JSONB,
            nullable=False,
            server_default="[]",
            comment="Список ID собственности",
        ),
        sa.Column(
            "cards",
            postgresql.JSONB,
            nullable=False,
            server_default="[]",
            comment="Карточки на руках",
        ),
        sa.Column(
            "in_jail",
            sa.Boolean,
            nullable=False,
            server_default=sa.false(),
            comment="В тюрьме",
        ),
        sa.Column(
            "jail_rounds",
            sa.Integer,
            nullable=False,
            server_default="0",
            comment="Кругов в тюрьме",
        ),
        sa.Column(
            "bankrupt",
            sa.Boolean,
            nullable=False,
            server_default=sa.false(),
            comment="Банкрот",
        ),
        sa.Column(
            "is_online",
            sa.Boolean,
            nullable=False,
            server_default=sa.true(),
            comment="Онлайн",
        ),
        sa.Column(
            "color",
            sa.String(7),
            nullable=False,
            server_default="#3498db",
            comment="Цвет фишки (#XXXXXX)",
        ),
        comment="Состояния игроков в игре",
    )
    op.create_index("idx_game_players_game", "game_players", ["game_id"])
    op.create_index("idx_game_players_user", "game_players", ["user_id"])

    # ========================================================================
    # Таблица: game_properties
    # ========================================================================
    op.create_table(
        "game_properties",
        sa.Column(
            "game_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("games.game_id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
            comment="ID игры",
        ),
        sa.Column(
            "property_id",
            sa.String(64),
            primary_key=True,
            nullable=False,
            comment="Идентификатор собственности",
        ),
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.user_id", ondelete="SET NULL"),
            nullable=True,
            comment="Владелец",
        ),
        sa.Column(
            "houses",
            sa.Integer,
            nullable=False,
            server_default="0",
            comment="Количество домов (0-4)",
        ),
        sa.Column(
            "has_hotel",
            sa.Boolean,
            nullable=False,
            server_default=sa.false(),
            comment="Есть отель",
        ),
        sa.Column(
            "mortgaged",
            sa.Boolean,
            nullable=False,
            server_default=sa.false(),
            comment="В залоге",
        ),
        comment="Состояния собственности в игре",
    )
    op.create_index("idx_game_props_game", "game_properties", ["game_id"])
    op.create_index("idx_game_props_owner", "game_properties", ["owner_id"])

    # ========================================================================
    # Таблица: player_cards
    # ========================================================================
    op.create_table(
        "player_cards",
        sa.Column(
            "instance_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            comment="Уникальный ID экземпляра карточки",
        ),
        sa.Column(
            "game_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("games.game_id", ondelete="CASCADE"),
            nullable=False,
            comment="ID игры",
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.user_id", ondelete="CASCADE"),
            nullable=False,
            comment="Владелец",
        ),
        sa.Column(
            "card_id",
            sa.String(32),
            nullable=False,
            comment="ID карточки",
        ),
        sa.Column(
            "card_type",
            sa.String(16),
            nullable=False,
            comment="Тип: chance, fund",
        ),
        sa.Column(
            "can_be_sold",
            sa.Boolean,
            nullable=False,
            server_default=sa.false(),
            comment="Можно продать",
        ),
        sa.Column(
            "is_used",
            sa.Boolean,
            nullable=False,
            server_default=sa.false(),
            comment="Использована",
        ),
        comment="Карточки игроков",
    )
    op.create_index("idx_player_cards_game", "player_cards", ["game_id"])
    op.create_index("idx_player_cards_user", "player_cards", ["user_id"])

    # ========================================================================
    # Таблица: trade_offers
    # ========================================================================
    op.create_table(
        "trade_offers",
        sa.Column(
            "trade_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            comment="Уникальный ID предложения",
        ),
        sa.Column(
            "game_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("games.game_id", ondelete="CASCADE"),
            nullable=False,
            comment="ID игры",
        ),
        sa.Column(
            "from_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.user_id", ondelete="CASCADE"),
            nullable=False,
            comment="Инициатор",
        ),
        sa.Column(
            "to_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.user_id", ondelete="CASCADE"),
            nullable=False,
            comment="Получатель",
        ),
        sa.Column(
            "offer",
            postgresql.JSONB,
            nullable=False,
            server_default="{}",
            comment="Предлагаемое: {properties, cards, money, loan}",
        ),
        sa.Column(
            "request",
            postgresql.JSONB,
            nullable=False,
            server_default="{}",
            comment="Запрашиваемое: {properties, cards, money}",
        ),
        sa.Column(
            "status",
            sa.String(16),
            nullable=False,
            server_default="pending",
            comment="Статус: pending, accepted, declined, expired, cancelled",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            comment="Время создания",
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Время истечения",
        ),
        comment="Торговые предложения",
    )
    op.create_index("idx_trades_game", "trade_offers", ["game_id"])
    op.create_index("idx_trades_status", "trade_offers", ["status"])

    # ========================================================================
    # Таблица: chat_messages
    # ========================================================================
    op.create_table(
        "chat_messages",
        sa.Column(
            "id",
            sa.Integer,
            primary_key=True,
            autoincrement=True,
            nullable=False,
            comment="Автоинкрементный ID",
        ),
        sa.Column(
            "room_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("rooms.room_id", ondelete="CASCADE"),
            nullable=False,
            comment="ID комнаты",
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.user_id", ondelete="SET NULL"),
            nullable=True,
            comment="Отправитель (NULL = система)",
        ),
        sa.Column(
            "message_type",
            sa.String(16),
            nullable=False,
            server_default="player",
            comment="Тип: player, system, admin",
        ),
        sa.Column(
            "content",
            sa.Text,
            nullable=False,
            comment="Содержимое сообщения",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            comment="Время отправки",
        ),
        comment="Сообщения чата",
    )
    op.create_index("idx_chat_room", "chat_messages", ["room_id"])
    op.create_index("idx_chat_created", "chat_messages", ["room_id", "created_at"])

    # ========================================================================
    # Таблица: game_events
    # ========================================================================
    op.create_table(
        "game_events",
        sa.Column(
            "id",
            sa.Integer,
            primary_key=True,
            autoincrement=True,
            nullable=False,
            comment="Автоинкрементный ID",
        ),
        sa.Column(
            "game_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("games.game_id", ondelete="CASCADE"),
            nullable=False,
            comment="ID игры",
        ),
        sa.Column(
            "event_type",
            sa.String(32),
            nullable=False,
            comment="Тип события",
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.user_id", ondelete="SET NULL"),
            nullable=True,
            comment="Инициатор",
        ),
        sa.Column(
            "target_id",
            sa.String(64),
            nullable=True,
            comment="Цель (игрок, собственность)",
        ),
        sa.Column(
            "data",
            postgresql.JSONB,
            nullable=False,
            server_default="{}",
            comment="Данные события",
        ),
        sa.Column(
            "turn_number",
            sa.Integer,
            nullable=False,
            server_default="0",
            comment="Номер хода",
        ),
        sa.Column(
            "sequence",
            sa.Integer,
            nullable=False,
            server_default="0",
            comment="Порядковый номер события",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            comment="Время события",
        ),
        comment="Журнал игровых событий",
    )
    op.create_index("idx_events_game", "game_events", ["game_id"])
    op.create_index("idx_events_type", "game_events", ["event_type"])
    op.create_index("idx_events_sequence", "game_events", ["game_id", "sequence"])

    # ========================================================================
    # Таблица: network_logs
    # ========================================================================
    op.create_table(
        "network_logs",
        sa.Column(
            "id",
            sa.Integer,
            primary_key=True,
            autoincrement=True,
            nullable=False,
            comment="Автоинкрементный ID",
        ),
        sa.Column(
            "event_type",
            sa.String(32),
            nullable=False,
            comment="Тип события: connect, disconnect, error, heartbeat",
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.user_id", ondelete="SET NULL"),
            nullable=True,
            comment="Пользователь",
        ),
        sa.Column(
            "ip_address",
            sa.String(45),
            nullable=True,
            comment="IP-адрес",
        ),
        sa.Column(
            "packet_type",
            sa.String(32),
            nullable=True,
            comment="Тип пакета",
        ),
        sa.Column(
            "data",
            postgresql.JSONB,
            nullable=False,
            server_default="{}",
            comment="Дополнительные данные",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            comment="Время события",
        ),
        comment="Журнал сетевых событий",
    )
    op.create_index("idx_netlog_user", "network_logs", ["user_id"])
    op.create_index("idx_netlog_created", "network_logs", ["created_at"])

    # ========================================================================
    # Таблица: admin_logs
    # ========================================================================
    op.create_table(
        "admin_logs",
        sa.Column(
            "id",
            sa.Integer,
            primary_key=True,
            autoincrement=True,
            nullable=False,
            comment="Автоинкрементный ID",
        ),
        sa.Column(
            "admin_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.user_id", ondelete="CASCADE"),
            nullable=False,
            comment="Администратор",
        ),
        sa.Column(
            "command",
            sa.String(64),
            nullable=False,
            comment="Выполненная команда",
        ),
        sa.Column(
            "target_id",
            sa.String(64),
            nullable=True,
            comment="Цель команды",
        ),
        sa.Column(
            "data",
            postgresql.JSONB,
            nullable=False,
            server_default="{}",
            comment="Параметры команды",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            comment="Время действия",
        ),
        comment="Журнал административных действий",
    )
    op.create_index("idx_adminlog_admin", "admin_logs", ["admin_id"])
    op.create_index("idx_adminlog_created", "admin_logs", ["created_at"])


def downgrade() -> None:
    """Откатить миграцию: удалить все таблицы."""

    # Удаляем в порядке, обратном созданию (учитывая внешние ключи)
    op.drop_table("admin_logs")
    op.drop_table("network_logs")
    op.drop_table("game_events")
    op.drop_table("chat_messages")
    op.drop_table("trade_offers")
    op.drop_table("player_cards")
    op.drop_table("game_properties")
    op.drop_table("game_players")
    op.drop_table("games")
    op.drop_table("rooms")
    op.drop_table("users")