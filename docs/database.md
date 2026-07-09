# База данных «Миллиардер»

## 1. Обзор

В качестве СУБД используется **PostgreSQL 16**, доступ к данным осуществляется через **SQLAlchemy 2.x** в асинхронном режиме с драйвером **asyncpg**. Миграции выполняются с помощью **Alembic**.

### Ключевые характеристики

- **СУБД**: PostgreSQL 16
- **ORM**: SQLAlchemy 2.x (async)
- **Драйвер**: asyncpg
- **Миграции**: Alembic
- **Идентификаторы**: UUID (тип `UUID` в PostgreSQL)
- **Кодировка**: UTF-8
- **Connection Pool**: asyncpg pool (20 соединений + 10 overflow)

---

## 2. Подключение

### 2.1 Параметры подключения

Параметры загружаются из `.env` файла:
DB_HOST=localhost
DB_PORT=5432
DB_USER=billionaire
DB_PASSWORD=secret
DB_NAME=billionaire_db
DB_POOL_SIZE=20
DB_MAX_OVERFLOW=10

### 2.2 URL подключения
postgresql + asyncpg ://billionaire:secret@localhost:5432/billionaire_db

### 2.3 Настройка пула

| Параметр | Значение | Описание |
|----------|----------|----------|
| pool_size | 20 | Базовый размер пула |
| max_overflow | 10 | Дополнительные соединения |
| pool_timeout | 30 сек | Таймаут получения соединения |
| pool_recycle | 3600 сек | Время жизни соединения |
| echo | False | Логирование SQL (только в DEBUG) |

---

## 3. ER-диаграмма
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│    users     │    │    rooms     │    │    games     │
├──────────────┤    ├──────────────┤    ├──────────────┤
│ user_id   ───┼──┐ │ room_id      │    │ game_id      │
│ username     │  │ │ owner_id  ───┼──┐ │ room_id   ───┼──┐
│ pass_hash    │  │ │ name         │  │ │ state        │  │
│ role         │  │ │ config       │  │ │ turn_idx     │  │
│ created      │  │ │ state        │  │ │ turn_num     │  │
│ last_login   │  │ │ created      │  │ │ started      │  │
│ banned       │  │ └──────────────┘  │ │ finished     │  │
└──────────────┘  │                   │ └──────────────┘  │
                  │                   │                   │
    ┌─────────────┴───────────────────┴───────────────────┘
    │
    │   ┌──────────────────────────────────────────────┐
    │   │              game_players                    │
    │   ├──────────────────────────────────────────────┤
    ├───┤ game_id   ───────────────────────────────────┼──┐
    │   │ user_id   ───────────────────────────────────┼──┤
    │   │ slot_index                                   │  │
    │   │ money                                        │  │
    │   │ position                                     │  │
    │   │ properties (JSON)                            │  │
    │   │ cards (JSON)                                 │  │
    │   │ in_jail                                      │  │
    │   │ bankrupt                                     │  │
    │   │ is_online                                    │  │
    │   │ color                                        │  │
    │   └──────────────────────────────────────────────┘  │
    │                                                     │
    │   ┌──────────────────────────────────────────────┐  │
    │   │          game_properties                     │  │
    │   ├──────────────────────────────────────────────┤  │
    │   │ game_id   ───────────────────────────────────┼──┘
    │   │ property_id                                  │
    │   │ owner_id  ───────────────────────────────────┼──┐
    │   │ houses                                       │  │
    │   │ has_hotel                                    │  │
    │   │ mortgaged                                    │  │
    │   └──────────────────────────────────────────────┘  │
    │                                                     │
    │   ┌──────────────┐  ┌──────────────┐  ┌────────────┴─┐
    │   │ player_cards │  │ trade_offers │  │  chat_msgs   │
    │   ├──────────────┤  ├──────────────┤  ├──────────────┤
    ├───┤ game_id      │  │ trade_id     │  │ room_id   ───┼──┐
    │   │ user_id   ───┼──┤ game_id   ───┼──┤ user_id   ───┼──┘
    │   │ card_id      │  │ from_id   ───┼──┤ msg_type     │
    │   │ card_type    │  │ to_id     ───┼──┤ content      │
    │   │ can_be_sold  │  │ offer (JSON) │  │ created_at   │
    │   └──────────────┘  │ request(JSON)│  └──────────────┘
    │                     │ status       │
    │                     │ created_at   │  ┌──────────────┐
    │                     └──────────────┘  │ game_events  │
    │                                       ├──────────────┤
    │                                       │ game_id   ───┼──┐
    │                                       │ event_type   │  │
    │                                       │ user_id   ───┼──┤
    │                                       │ target_id    │  │
    │                                       │ data (JSON)  │  │
    │                                       │ created_at   │  │
    │                                       │ turn_number  │  │
    │                                       │ sequence     │  │
    │                                       └──────────────┘  │
    │                                                         │
    │   ┌──────────────┐                                      │
    │   │ admin_logs   │                                      │
    │   ├──────────────┤                                      │
    ├───┤ admin_id  ───┼──┐                                   │
    │   │ command      │  │                                   │
    │   │ target_id    │  │                                   │
    │   │ data (JSON)  │  │                                   │
    │   │ created_at   │  │                                   │
    │   └──────────────┘  │                                   │
    │                     │                                   │
    │   ┌──────────────┐  │                                   │
    │   │ network_logs │  │                                   │
    │   ├──────────────┤  │                                   │
    ├───┤ event_type   │  │                                   │
    │   │ user_id   ───┼──┘                                   │
    │   │ ip_address   │                                      │
    │   │ packet_type  │                                      │
    │   │ data (JSON)  │                                      │
    │   │ created_at   │                                      │
    │   └──────────────┘                                      │
    │                                                         │
    └─────────────────────────────────────────────────────────┘


---

## 4. Описание таблиц

### 4.1 users

Пользователи системы.

| Поле | Тип | Ограничения | Описание |
|------|-----|-------------|----------|
| user_id | UUID | PK | Уникальный идентификатор |
| username | VARCHAR(32) | UNIQUE, NOT NULL | Имя пользователя |
| password_hash | TEXT | NOT NULL | Хеш пароля (Argon2id) |
| role | VARCHAR(16) | NOT NULL, DEFAULT 'player' | Роль (creator/player/observer) |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | Дата регистрации |
| last_login | TIMESTAMPTZ | NULL | Последний вход |
| is_banned | BOOLEAN | NOT NULL, DEFAULT FALSE | Флаг блокировки |
| total_games | INTEGER | NOT NULL, DEFAULT 0 | Всего игр |
| wins | INTEGER | NOT NULL, DEFAULT 0 | Побед |
| total_money_earned | BIGINT | NOT NULL, DEFAULT 0 | Всего заработано |

**Индексы:**
- `idx_users_username` UNIQUE на `username`
- `idx_users_role` на `role`

### 4.2 rooms

Игровые комнаты.

| Поле | Тип | Ограничения | Описание |
|------|-----|-------------|----------|
| room_id | UUID | PK | Уникальный идентификатор |
| name | VARCHAR(32) | NOT NULL | Название комнаты |
| owner_id | UUID | FK → users.user_id, NOT NULL | Владелец |
| is_private | BOOLEAN | NOT NULL, DEFAULT FALSE | Приватная |
| password_hash | TEXT | NULL | Хеш пароля |
| max_players | INTEGER | NOT NULL, DEFAULT 4 | Максимум игроков |
| state | VARCHAR(16) | NOT NULL, DEFAULT 'waiting' | Состояние |
| game_params | JSONB | NOT NULL, DEFAULT '{}' | Параметры игры |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | Дата создания |

**Индексы:**
- `idx_rooms_state` на `state`
- `idx_rooms_owner` на `owner_id`

### 4.3 games

Игровые сессии.

| Поле | Тип | Ограничения | Описание |
|------|-----|-------------|----------|
| game_id | UUID | PK | Уникальный идентификатор |
| room_id | UUID | FK → rooms.room_id, UNIQUE | Связанная комната |
| state | VARCHAR(32) | NOT NULL, DEFAULT 'waiting_for_players' | Состояние игры |
| current_turn_index | INTEGER | NOT NULL, DEFAULT 0 | Индекс текущего игрока |
| turn_number | INTEGER | NOT NULL, DEFAULT 0 | Номер хода |
| board_state | JSONB | NOT NULL, DEFAULT '{}' | Состояние поля |
| free_parking_money | INTEGER | NOT NULL, DEFAULT 0 | Деньги на парковке |
| started_at | TIMESTAMPTZ | NULL | Время начала |
| finished_at | TIMESTAMPTZ | NULL | Время завершения |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | Дата создания |

**Индексы:**
- `idx_games_room` UNIQUE на `room_id`
- `idx_games_state` на `state`

### 4.4 game_players

Состояния игроков в игре.

| Поле | Тип | Ограничения | Описание |
|------|-----|-------------|----------|
| game_id | UUID | FK → games.game_id | Игра |
| user_id | UUID | FK → users.user_id | Игрок |
| slot_index | INTEGER | NOT NULL | Порядковый номер |
| money | INTEGER | NOT NULL | Текущий баланс |
| position | INTEGER | NOT NULL, DEFAULT 0 | Позиция на поле (0-39) |
| properties | JSONB | NOT NULL, DEFAULT '[]' | Список ID собственности |
| cards | JSONB | NOT NULL, DEFAULT '[]' | Карточки на руках |
| in_jail | BOOLEAN | NOT NULL, DEFAULT FALSE | В тюрьме |
| jail_rounds | INTEGER | NOT NULL, DEFAULT 0 | Кругов в тюрьме |
| bankrupt | BOOLEAN | NOT NULL, DEFAULT FALSE | Банкрот |
| is_online | BOOLEAN | NOT NULL, DEFAULT TRUE | Онлайн |
| color | VARCHAR(7) | NOT NULL | Цвет фишки (#XXXXXX) |

**Первичный ключ:** составной (`game_id`, `user_id`)

**Индексы:**
- `idx_game_players_game` на `game_id`
- `idx_game_players_user` на `user_id`

### 4.5 game_properties

Состояния собственности в игре.

| Поле | Тип | Ограничения | Описание |
|------|-----|-------------|----------|
| game_id | UUID | FK → games.game_id | Игра |
| property_id | VARCHAR(64) | NOT NULL | Идентификатор собственности |
| owner_id | UUID | FK → users.user_id, NULL | Владелец |
| houses | INTEGER | NOT NULL, DEFAULT 0 | Количество домов (0-4) |
| has_hotel | BOOLEAN | NOT NULL, DEFAULT FALSE | Есть отель |
| mortgaged | BOOLEAN | NOT NULL, DEFAULT FALSE | В залоге |

**Первичный ключ:** составной (`game_id`, `property_id`)

**Индексы:**
- `idx_game_props_game` на `game_id`
- `idx_game_props_owner` на `owner_id`

### 4.6 player_cards

Карточки игроков (которые можно хранить и продавать).

| Поле | Тип | Ограничения | Описание |
|------|-----|-------------|----------|
| instance_id | UUID | PK | Уникальный ID экземпляра |
| game_id | UUID | FK → games.game_id | Игра |
| user_id | UUID | FK → users.user_id | Владелец |
| card_id | VARCHAR(32) | NOT NULL | ID карточки |
| card_type | VARCHAR(16) | NOT NULL | Тип (chance/fund) |
| can_be_sold | BOOLEAN | NOT NULL, DEFAULT FALSE | Можно продать |
| is_used | BOOLEAN | NOT NULL, DEFAULT FALSE | Использована |

**Индексы:**
- `idx_player_cards_game` на `game_id`
- `idx_player_cards_user` на `user_id`

### 4.7 trade_offers

Торговые предложения.

| Поле | Тип | Ограничения | Описание |
|------|-----|-------------|----------|
| trade_id | UUID | PK | Уникальный ID |
| game_id | UUID | FK → games.game_id | Игра |
| from_id | UUID | FK → users.user_id | Инициатор |
| to_id | UUID | FK → users.user_id | Получатель |
| offer | JSONB | NOT NULL | Предлагаемое |
| request | JSONB | NOT NULL | Запрашиваемое |
| status | VARCHAR(16) | NOT NULL, DEFAULT 'pending' | Статус |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | Создано |
| expires_at | TIMESTAMPTZ | NULL | Истекает |

**Индексы:**
- `idx_trades_game` на `game_id`
- `idx_trades_status` на `status`

### 4.8 chat_messages

Сообщения чата.

| Поле | Тип | Ограничения | Описание |
|------|-----|-------------|----------|
| id | BIGSERIAL | PK | Автоинкремент |
| room_id | UUID | FK → rooms.room_id | Комната |
| user_id | UUID | FK → users.user_id, NULL | Отправитель (NULL = система) |
| message_type | VARCHAR(16) | NOT NULL | Тип (player/system/admin) |
| content | TEXT | NOT NULL | Содержимое |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | Время |

**Индексы:**
- `idx_chat_room` на `room_id`
- `idx_chat_created` на `room_id, created_at`

### 4.9 game_events

Журнал игровых событий.

| Поле | Тип | Ограничения | Описание |
|------|-----|-------------|----------|
| id | BIGSERIAL | PK | Автоинкремент |
| game_id | UUID | FK → games.game_id | Игра |
| event_type | VARCHAR(32) | NOT NULL | Тип события |
| user_id | UUID | FK → users.user_id, NULL | Инициатор |
| target_id | VARCHAR(64) | NULL | Цель |
| data | JSONB | NOT NULL, DEFAULT '{}' | Данные события |
| turn_number | INTEGER | NOT NULL, DEFAULT 0 | Номер хода |
| sequence | INTEGER | NOT NULL | Порядковый номер |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | Время |

**Индексы:**
- `idx_events_game` на `game_id`
- `idx_events_type` на `event_type`
- `idx_events_sequence` на `game_id, sequence`

### 4.10 network_logs

Журнал сетевых событий.

| Поле | Тип | Ограничения | Описание |
|------|-----|-------------|----------|
| id | BIGSERIAL | PK | Автоинкремент |
| event_type | VARCHAR(32) | NOT NULL | Тип события |
| user_id | UUID | FK → users.user_id, NULL | Пользователь |
| ip_address | VARCHAR(45) | NULL | IP-адрес |
| packet_type | VARCHAR(32) | NULL | Тип пакета |
| data | JSONB | NOT NULL, DEFAULT '{}' | Данные |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | Время |

**Индексы:**
- `idx_netlog_user` на `user_id`
- `idx_netlog_created` на `created_at`

### 4.11 admin_logs

Журнал административных действий.

| Поле | Тип | Ограничения | Описание |
|------|-----|-------------|----------|
| id | BIGSERIAL | PK | Автоинкремент |
| admin_id | UUID | FK → users.user_id | Администратор |
| command | VARCHAR(64) | NOT NULL | Команда |
| target_id | VARCHAR(64) | NULL | Цель |
| data | JSONB | NOT NULL, DEFAULT '{}' | Параметры |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | Время |

**Индексы:**
- `idx_adminlog_admin` на `admin_id`
- `idx_adminlog_created` на `created_at`

---

## 5. JSONB-поля

### 5.1 game_players.properties

```
["sivka_burka", "railroad_1", "utility_1"]
```
Массив строковых идентификаторов собственности.

### 5.2 game_players.cards
```
[
  {
    "instance_id": "uuid",
    "card_id": "chance_03",
    "card_type": "chance",
    "is_used": false
  }
]
```
### 5.3 games.board_state

```
{
  "free_parking_money": 0
}
```
Полное состояние поля (клетки загружаются из JSON-конфигурации, хранить их в БД избыточно).

### 5.4 trade_offers.offer / trade_offers.request

```
{
  "properties": ["sivka_burka"],
  "cards": [],
  "money": 0,
  "loan": {
    "amount": 200,
    "percent": 10
  }
}
```
---

## 6. Миграции (Alembic)

### 6.1 Настройка

```
# alembic.ini
[alembic]
script_location = alembic
sqlalchemy.url = postgresql+asyncpg://billionaire:secret@localhost:5432/billionaire_db
```

### 6.2 Версии миграций

Версия	Описание
001	Начальная схема (все 11 таблиц)

### 6.3 Команды

```
# Создать новую миграцию
alembic revision --autogenerate -m "description"

# Применить миграции
alembic upgrade head

# Откатить на одну версию
alembic downgrade -1

# Просмотреть историю
alembic history
```

--- 

## 7. Репозитории

Паттерн Repository абстрагирует доступ к данным. Все репозитории наследуются от BaseRepository[T]:

```
class BaseRepository[T](ABC, Generic[T]):
    async def get_by_id(self, id: UUID) -> Optional[T]
    async def save(self, entity: T) -> T
    async def delete(self, id: UUID) -> bool
    async def list_all(self, filters: dict) -> list[T]
    async def exists(self, id: UUID) -> bool
```

Конкретные реализации используют SQLAlchemy 2.x async:

```
database/repositories/
├── base_repository.py
└── postgresql/
    ├── user_repository.py
    ├── room_repository.py
    ├── game_repository.py
    ├── chat_repository.py
    └── event_repository.py
```

Замена PostgreSQL на другую СУБД потребует только создания новых реализаций репозиториев (например, mysql/user_repository.py) без изменения бизнес-логики.

---

## 8. Резервное копирование

### 8.1 Автоматическое

Интервал: каждые 5 минут (настраивается)
Сохраняются все таблицы
Хранятся 30 дней
Максимум 100 файлов

### 8.2 Формат

```
backups/
├── backup_2024_01_15_10_30_00.sql
├── backup_2024_01_15_10_35_00.sql
└── ...
```

### 8.3 Восстановление

```
psql -U billionaire -d billionaire_db < backups/backup_2024_01_15_10_30_00.sql
```
---
 
## 9. Производительность

### 9.1 Connection Pool

20 постоянных соединений
До 10 дополнительных при пиковой нагрузке
Автоматический recycle каждые 60 минут

### 9.2 Индексы

Все внешние ключи и часто запрашиваемые поля проиндексированы.

### 9.3 JSONB

Индексы GIN для JSONB-полей при необходимости
Запросы с -> и ->> операторами

### 9.4 VACUUM

Автовакуум PostgreSQL (настройки по умолчанию)  8yuh
При необходимости: ручной VACUUM ANALYZE при простое