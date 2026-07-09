# Архитектура проекта «Миллиардер»

## 1. Обзор

«Миллиардер» — многопользовательская экономическая игра (аналог «Монополии») с клиент-серверной архитектурой. Сервер расположен на Linux VPS, клиенты работают под Windows. Взаимодействие по TCP с SSL/TLS шифрованием.

### Ключевые характеристики

- **Язык**: Python 3.13+
- **Сервер**: asyncio + asyncio Streams
- **Клиент**: PySide6 (MVVM)
- **База данных**: PostgreSQL + SQLAlchemy 2.x (async) + Alembic
- **Протокол**: Бинарный заголовок + JSON + HMAC-SHA256
- **Сжатие**: zlib (для пакетов > 512 байт)
- **Аутентификация**: JWT-подобные токены (access + refresh)
- **Хеширование паролей**: Argon2id
- **Логирование**: Раздельные файлы для server/game/network/security/admin/chat
- **Конфигурация**: JSON-файлы с версионированием + .env для секретов

---

## 2. Диаграмма развёртывания
┌──────────────────────────────────────────────────────────────────┐
│ LINUX VPS │
│ ┌────────────────────────────────────────────────────────────┐ │
│ │ SERVER (asyncio) │ │
│ │ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ │ │
│ │ │TCP Server│ │Game Mgr │ │Room Mgr │ │Auth Mgr │ │ │
│ │ │SSL/TLS │ │ │ │ │ │ │ │ │
│ │ └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ │ │
│ │ │ │ │ │ │ │
│ │ ┌────┴─────────────┴─────────────┴─────────────┴────┐ │ │
│ │ │ MESSAGE DISPATCHER │ │ │
│ │ └────┬─────────────┬─────────────┬─────────────────┘ │ │
│ │ │ │ │ │ │
│ │ ┌────┴────┐ ┌─────┴────┐ ┌─────┴─────┐ │ │
│ │ │Session │ │ Repository│ │ Backup │ │ │
│ │ │Manager │ │(PostgreSQL│ │ Manager │ │ │
│ │ │ │ │+SQLAlchemy│ │ │ │ │
│ │ └─────────┘ └──────────┘ └───────────┘ │ │
│ └────────────────────────────────────────────────────────────┘ │
│ │ │
│ ┌──────┴──────┐ │
│ │ PostgreSQL │ │
│ └─────────────┘ │
└──────────────────────────────────────────────────────────────────┘
│
SSL/TLS (TCP)
│
┌─────────────────────────────┴────────────────────────────────────┐
│ WINDOWS CLIENTS │
│ ┌──────────────────────────────────────────────────────────┐ │
│ │ CLIENT (PySide6 + MVVM) │ │
│ │ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ │ │
│ │ │Network │ │ View │ │ ViewModel│ │ Model │ │ │
│ │ │Client │ │ (GUI) │ │ │ │ │ │ │
│ │ └──────────┘ └──────────┘ └──────────┘ └──────────┘ │ │
│ └──────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘

text

---

## 3. Структура проекта
billionaire_game/
├── server/ # Серверная часть
│ ├── main.py # Точка входа
│ ├── container.py # DI-контейнер
│ ├── config/ # Управление конфигурацией
│ ├── network/ # TCP/SSL сервер, сессии, диспетчер
│ ├── auth/ # Аутентификация и токены
│ ├── game/ # Игровой движок, цикл, AI
│ ├── room/ # Управление комнатами
│ ├── chat/ # Чат
│ ├── event/ # EventBus, логирование, replay
│ ├── scheduler/ # Планировщик задач
│ ├── backup/ # Бэкапы, autosave, crash recovery
│ ├── admin/ # Админ-команды
│ └── middleware/ # Security, rate limiting, валидация
│
├── client/ # Клиентская часть
│ ├── main.py # Точка входа
│ ├── container.py # DI-контейнер
│ ├── config.py # Конфигурация клиента
│ ├── network/ # Сетевой клиент, переподключение
│ ├── models/ # Qt-модели данных
│ ├── viewmodels/ # MVVM ViewModels
│ ├── views/ # PySide6 GUI
│ └── assets/ # Ресурсы и AssetManager
│
├── shared/ # Общий код
│ ├── constants.py # Все константы
│ ├── enums.py # Все перечисления
│ ├── exceptions.py # Иерархия исключений
│ ├── permissions.py # Система прав
│ ├── env_config.py # .env конфигурация
│ ├── logger_config.py # Настройка логирования
│ ├── dice.py # Кубики
│ ├── money.py # Денежные операции
│ ├── game_rules.py # Игровые правила
│ ├── property_utils.py # Утилиты собственности
│ ├── card_actions.py # Действия карточек
│ ├── validators.py # Валидация данных
│ ├── models/ # Модели данных
│ └── protocol/ # Сетевой протокол
│
├── database/ # База данных
│ ├── connection.py # Подключение (SQLAlchemy async)
│ ├── models.py # ORM модели (SQLAlchemy)
│ ├── migrations/ # Alembic миграции
│ └── repositories/ # Репозитории (паттерн Repository)
│
├── configs/ # Конфигурационные файлы (JSON)
│ ├── server/ # Серверные настройки
│ ├── game/ # Игровые данные
│ └── client/ # Клиентские настройки
│
├── translations/ # Локализация
├── assets/ # Изображения, звуки, стили
├── deploy/ # Docker, systemd
├── tests/ # Тесты
├── docs/ # Документация
├── logs/ # Логи (создаются)
└── backups/ # Бэкапы (создаются)

---

## 4. Ключевые архитектурные решения

### 4.1 Полный асинхронный стек

- Сервер: `asyncio.start_server` (asyncio Streams)
- База данных: SQLAlchemy 2.x async + asyncpg
- Клиент: `asyncio` для сетевого взаимодействия + PySide6 для GUI
- Никакого threading — всё на `asyncio.TaskGroup`, `asyncio.Queue`, `asyncio.Lock`

### 4.2 MVVM на клиенте
View (PySide6 QWidget) ←── сигналы/слоты ──→ ViewModel ←── асинхронные вызовы ──→ Model

text

- **Model**: данные, полученные от сервера
- **ViewModel**: состояние UI, логика представления, команды
- **View**: только отображение, никакой бизнес-логики

### 4.3 Dependency Injection

- `server/container.py` — DI-контейнер сервера
- `client/container.py` — DI-контейнер клиента
- Все зависимости внедряются через конструкторы, никаких глобальных переменных

### 4.4 EventBus (Центральная шина событий)
GameEngine → EventBus → ChatManager
→ EventLogger
→ ReplayManager
→ Statistics

text

- Подписчики регистрируются на типы событий
- Асинхронная публикация (не блокирует источник)
- Возможность добавления новых подписчиков без изменения существующего кода

### 4.5 Конечный автомат (State Machine)

Игровой движок реализован как конечный автомат:
- Состояния: `WAITING_FOR_PLAYERS → STARTING → ACTIVE → FINISHING → FINISHED`
- Состояния хода: `AWAITING_DICE → MOVING → CELL_ACTION → POST_ACTION → TURN_COMPLETE`
- Переходы через `match/case` (Python 3.10+), без вложенных if/elif

### 4.6 Система разрешений

Вместо жёстких ролей — гибкая система Permission:
- `Permission` (StrEnum) — 50+ атомарных прав
- `RolePermissions` — наборы прав для CREATOR, PLAYER, OBSERVER, MODERATOR
- Проверка: `has_permission(user.role, Permission.ADMIN_COMMANDS)`
- Легко добавить новую роль: `RolePermissions.register_custom_role("vip", {...})`

### 4.7 Версионирование конфигураций

Каждый JSON-файл конфигурации содержит:
```
{
  "version": 1,
  "data": { ... }
}
```
Это позволяет изменять формат конфигураций без поломки старых файлов.

### 4.8 Безопасность
Пароли: Argon2id (победитель Password Hashing Competition)
Пакеты: HMAC-SHA256 подпись (защита целостности)
Сессии: JWT-подобные токены (access 1 час, refresh 30 дней)
Сеть: SSL/TLS + sequence numbers (защита от replay-атак)
Rate limiting: на уровне Middleware
Все проверки на сервере — клиент не доверенный

---

## 5. Поток данных

### 5.1 Подключение игрока

Client                              Server
  │── TCP Connect (SSL) ────────────>│
  │<── Connection Established ──────│
  │── LOGIN_REQUEST ───────────────>│
  │                                  │── Проверка Argon2id
  │                                  │── Генерация токенов
  │<── LOGIN_RESPONSE ──────────────│
  │── ROOM_LIST_REQUEST ───────────>│
  │<── ROOM_LIST_RESPONSE ──────────│
  │── ROOM_JOIN_REQUEST ───────────>│
  │<── ROOM_JOIN_RESPONSE ──────────│
  │<── STATE_SYNC ──────────────────│ (полное состояние)
  
### 5.2 Игровой цикл

GameLoop:
  while game.active:
    player = turn_order[current]
    
    if player.in_jail:
        process_jail_turn(player)
        continue
    
    emit TURN_STARTED
    start_timer(turn_timeout)
    
    await wait_for(player_action или timer.timeout)
    
    if timeout:
        auto_end_turn(player)
    else:
        process_action(player, action)
    
    emit TURN_ENDED
    check_game_end()
    next_turn()
	
### 5.3 Обработка действия игрока

Client Action → MessageDispatcher → SecurityMiddleware → GameManager
                                                             │
                                              ┌──────────────┴──────────────┐
                                              │    GameEngine.process()      │
                                              │    match turn_state:         │
                                              │      case AWAITING_DICE:     │
                                              │        → roll_dice()         │
                                              │      case AWAITING_ACTION:   │
                                              │        → handle_cell_action()│
                                              │      case AUCTION_ACTIVE:    │
                                              │        → place_bid()         │
                                              └──────────────┬──────────────┘
                                                             │
                                              ┌──────────────┴──────────────┐
                                              │       EventBus.publish()     │
                                              └──────────────┬──────────────┘
                                                             │
                                    ┌────────────────────────┼────────────────────────┐
                                    │                        │                         │
                              ChatManager             EventLogger              ReplayManager


---

## 6. Модель данных (основные сущности)

User ──────────────── Room ──────────────── Game
 │                      │                      │
 │                      │                      ├── PlayerState[]
 │                      ├── players[]           ├── PropertyState[]
 │                      ├── observers[]         ├── CardDeck (chance, fund)
 │                      └── RoomConfig          ├── Board
 │                                              ├── GameEvent[]
 │                                              └── TradeOffer[]
 │
 ├── PlayerProfile (статистика)
 └── PlayerCard[] (карточки на руках)
Все сущности используют UUID в качестве первичных ключей для обеспечения уникальности в распределённой среде.

---

## 7. Сетевой протокол

### 7.1 Формат пакета

┌──────────┬──────────┬──────────┬──────────┬──────────┬──────────┬──────────┐
│  Magic   │ Version  │  Type    │  Flags   │ Payload  │ Sequence │Timestamp │
│  4 bytes │  6 bytes │ 2 bytes  │ 2 bytes  │ 4 bytes  │ 8 bytes  │ 8 bytes  │
├──────────┴──────────┴──────────┴──────────┴──────────┴──────────┴──────────┤
│                           Payload (N bytes)                                │
│                              (JSON / сжатый JSON)                          │
├────────────────────────────────────────────────────────────────────────────┤
│                           HMAC-SHA256 (32 bytes)                           │
└────────────────────────────────────────────────────────────────────────────┘

### 7.2 Типы пакетов

AUTH (0x01xx): LOGIN, REGISTER, LOGOUT, REFRESH_TOKEN
ROOM (0x02xx): LIST, CREATE, JOIN, LEAVE, SETTINGS, KICK
GAME (0x03xx): START, ROLL_DICE, BUY, BUILD, TRADE, AUCTION, END_TURN
CHAT (0x04xx): MESSAGE, HISTORY
SYSTEM (0x05xx): HEARTBEAT, PING, STATE_SYNC, ERROR, RECONNECT
ADMIN (0x06xx): COMMAND, SET_MONEY, TELEPORT, UNDO, BROADCAST

### 7.3 Безопасность протокола

HMAC-SHA256: подпись заголовка + нагрузки сессионным ключом
Sequence Number: монотонно возрастающий, защита от replay-атак
Timestamp: отклонение > 30 сек → пакет отбрасывается
SSL/TLS: шифрование транспортного уровня
Сжатие: zlib для пакетов > 512 байт (экономия трафика)

---

## 8. Логирование
Раздельные файлы логов для разных аспектов системы:

Файл	Содержание
server.log	Запуск/остановка, инициализация модулей
game.log	Ходы, броски, покупки, банкротства
network.log	Подключения, отключения, пакеты, таймауты
security.log	Попытки взлома, неверные пароли, нарушения HMAC
admin.log	Админ-команды, читы, изменение ролей
chat.log	Сообщения чата, системные уведомления
Формат: %(asctime)s | %(levelname)-8s | %(name)-24s | %(funcName)-20s | %(message)s
Ротация: 10 МБ на файл, 5 архивных копий.

---

## 9. Тестирование

tests/
├── unit/
│   ├── shared/      # Тесты моделей, утилит, протокола
│   ├── server/      # Тесты игровых компонентов
│   └── client/      # Тесты ViewModel
├── integration/
│   ├── database/    # Тесты репозиториев
│   ├── network/     # Тесты клиент-серверного взаимодействия
│   └── game/        # Интеграционные тесты игры
└── performance/
    ├── load/        # Нагрузочное тестирование
    └── latency/     # Тесты задержек
	
---

## 10. Развёртывание

### 10.1 Docker

docker-compose up -d
PostgreSQL 16 в отдельном контейнере
Сервер приложения с автоматическим перезапуском
Тома для конфигов, логов и бэкапов

### 10.2 systemd

sudo systemctl enable billionaire-server
sudo systemctl start billionaire-server
Автозапуск после PostgreSQL
Перезапуск при падении (Restart=always)
Логи через journald

---

## 11. Зависимости
Сервер

python>=3.13
sqlalchemy[asyncio]>=2.0
asyncpg>=0.29
alembic>=1.13
argon2-cffi>=23.1
python-dotenv>=1.0
pydantic>=2.5
Клиент
text
python>=3.13
PySide6>=6.6
python-dotenv>=1.0

---

##  12. Принципы разработки

SOLID: каждый класс имеет одну ответственность
DRY: общий код в shared/, никакого дублирования
KISS: простые решения, избегание избыточной сложности
PEP 8: строгое соблюдение стиля кода
Type Hints: полная типизация всего кода
Immutable by default: @dataclass(slots=True, frozen=True) где возможно
No magic numbers: все константы в shared/constants.py