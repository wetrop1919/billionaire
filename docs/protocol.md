# Сетевой протокол «Миллиардер»

## 1. Обзор

Сетевой протокол обеспечивает взаимодействие между клиентом и сервером поверх TCP с SSL/TLS шифрованием. Протокол бинарный, с JSON-нагрузкой и HMAC-подписью для обеспечения целостности.

### Ключевые характеристики

- **Транспорт**: TCP + SSL/TLS
- **Сериализация**: Бинарный заголовок + JSON (сжатый zlib при необходимости)
- **Целостность**: HMAC-SHA256 (ключ на сессию)
- **Защита от replay-атак**: Sequence Number + Timestamp
- **Версионирование**: Semantic versioning в заголовке
- **Keep-alive**: Heartbeat/Ping-Pong

---

## 2. Формат пакета

### 2.1 Структура

| Magic (4 bytes)             |
| 0x4247484D                  |
|                             |
|Version Major | Version Minor|
| (2 bytes) | (2 bytes)       |
|                             |
| Version Patch | Packet Type |
| (2 bytes) | (2 bytes)       |
|                             |
| Flags | Payload Length      |
| (2 bytes) | (4 bytes)       |
|                             |
| Sequence Number             |
| (8 bytes)                   |
|                             |
| Timestamp                   |
| (8 bytes, Unix миллисекунды)|
|                             |
| Payload (N bytes)           |
| (JSON или сжатый JSON)      |
|                             |
|                             |
| HMAC-SHA256 (32 bytes)      |
|                             |



### 2.2 Поля заголовка

| Поле | Размер | Описание |
|------|--------|----------|
| Magic | 4 байта | Магическое число `0x4247484D` ("BGHM") |
| Version Major | 2 байта | Мажорная версия протокола |
| Version Minor | 2 байта | Минорная версия протокола |
| Version Patch | 2 байта | Патч-версия протокола |
| Packet Type | 2 байта | Тип пакета (см. раздел 3) |
| Flags | 2 байта | Битовые флаги (см. раздел 2.3) |
| Payload Length | 4 байта | Длина полезной нагрузки в байтах |
| Sequence | 8 байт | Монотонно возрастающий номер |
| Timestamp | 8 байт | Время отправки в миллисекундах (Unix) |

**Общий размер заголовка: 34 байта** (исправлено относительно первоначальных 26 байт)

### 2.3 Флаги (Flags)

| Бит | Название | Описание |
|-----|----------|----------|
| 0 | COMPRESSED | Пакет сжат zlib |
| 1 | ENCRYPTED | Пакет зашифрован (зарезервировано) |
| 2 | URGENT | Приоритетный пакет |
| 3-15 | RESERVED | Зарезервировано |

### 2.4 Порядок байт

Все многобайтовые поля используют **Big Endian (сетевой порядок)**.

---

## 3. Типы пакетов

### 3.1 Категории

| Диапазон | Категория | Описание |
|----------|-----------|----------|
| 0x0100-0x01FF | AUTH | Аутентификация |
| 0x0200-0x02FF | ROOM | Управление комнатами |
| 0x0300-0x03FF | GAME | Игровые действия |
| 0x0400-0x04FF | CHAT | Чат |
| 0x0500-0x05FF | SYSTEM | Системные сообщения |
| 0x0600-0x06FF | ADMIN | Административные команды |

### 3.2 Полный список

#### AUTH (Аутентификация)

| Код | Тип | Направление | Описание |
|-----|-----|-------------|----------|
| 0x0101 | LOGIN_REQUEST | C → S | Запрос на вход |
| 0x0102 | LOGIN_RESPONSE | S → C | Ответ на вход (токены) |
| 0x0103 | REGISTER_REQUEST | C → S | Запрос на регистрацию |
| 0x0104 | REGISTER_RESPONSE | S → C | Ответ на регистрацию |
| 0x0105 | LOGOUT | C → S | Выход |
| 0x0106 | REFRESH_TOKEN_REQUEST | C → S | Обновление токена |
| 0x0107 | REFRESH_TOKEN_RESPONSE | S → C | Новые токены |

#### ROOM (Комнаты)

| Код | Тип | Направление | Описание |
|-----|-----|-------------|----------|
| 0x0201 | ROOM_LIST_REQUEST | C → S | Запрос списка комнат |
| 0x0202 | ROOM_LIST_RESPONSE | S → C | Список комнат |
| 0x0203 | ROOM_CREATE_REQUEST | C → S | Создание комнаты |
| 0x0204 | ROOM_CREATE_RESPONSE | S → C | Комната создана |
| 0x0205 | ROOM_JOIN_REQUEST | C → S | Вход в комнату |
| 0x0206 | ROOM_JOIN_RESPONSE | S → C | Подтверждение входа |
| 0x0207 | ROOM_LEAVE | C → S | Выход из комнаты |
| 0x0208 | ROOM_SETTINGS_UPDATE | C → S | Изменение настроек |
| 0x0209 | ROOM_KICK_PLAYER | C → S | Выгнать игрока |
| 0x020A | PLAYER_JOINED | S → C | Игрок вошёл (уведомление) |
| 0x020B | PLAYER_LEFT | S → C | Игрок вышел (уведомление) |

#### GAME (Игровые действия)

| Код | Тип | Направление | Описание |
|-----|-----|-------------|----------|
| 0x0301 | GAME_START_REQUEST | C → S | Запуск игры |
| 0x0302 | GAME_STARTED | S → C | Игра началась |
| 0x0303 | ROLL_DICE_REQUEST | C → S | Бросок кубиков |
| 0x0304 | ROLL_DICE_RESULT | S → C | Результат броска |
| 0x0305 | BUY_PROPERTY_REQUEST | C → S | Купить собственность |
| 0x0306 | BUY_PROPERTY_RESPONSE | S → C | Подтверждение покупки |
| 0x0307 | DECLINE_PROPERTY | C → S | Отказ от покупки |
| 0x0308 | AUCTION_BID_REQUEST | C → S | Ставка на аукционе |
| 0x0309 | AUCTION_BID_RESPONSE | S → C | Подтверждение ставки |
| 0x030A | AUCTION_RESULT | S → C | Результат аукциона |
| 0x030B | BUILD_HOUSE_REQUEST | C → S | Построить дом |
| 0x030C | BUILD_HOUSE_RESPONSE | S → C | Дом построен |
| 0x030D | BUILD_HOTEL_REQUEST | C → S | Построить отель |
| 0x030E | BUILD_HOTEL_RESPONSE | S → C | Отель построен |
| 0x030F | MORTGAGE_REQUEST | C → S | Заложить |
| 0x0310 | MORTGAGE_RESPONSE | S → C | Заложено |
| 0x0311 | UNMORTGAGE_REQUEST | C → S | Выкупить из залога |
| 0x0312 | UNMORTGAGE_RESPONSE | S → C | Выкуплено |
| 0x0313 | TRADE_OFFER_REQUEST | C → S | Предложение сделки |
| 0x0314 | TRADE_OFFER_RESPONSE | S → C | Ответ на предложение |
| 0x0315 | TRADE_ACCEPT_REQUEST | C → S | Принять сделку |
| 0x0316 | TRADE_DECLINE_REQUEST | C → S | Отклонить сделку |
| 0x0317 | TRADE_RESULT | S → C | Результат сделки |
| 0x0318 | END_TURN_REQUEST | C → S | Завершить ход |
| 0x0319 | TURN_CHANGED | S → C | Ход перешёл |
| 0x031A | TURN_TIMEOUT_NOTIFY | S → C | Таймаут хода |
| 0x031B | PAY_RENT_NOTIFY | S → C | Уведомление об аренде |
| 0x031C | DRAW_CARD_RESULT | S → C | Результат карточки |
| 0x031D | JAIL_ACTION_REQUEST | C → S | Действие в тюрьме |
| 0x031E | JAIL_ACTION_RESPONSE | S → C | Результат действия |
| 0x031F | VERANDA_ACTION_REQUEST | C → S | Действие на Веранде |
| 0x0320 | VERANDA_ACTION_RESPONSE | S → C | Результат действия |
| 0x0321 | PLAYER_BANKRUPT_NOTIFY | S → C | Игрок обанкротился |
| 0x0322 | GAME_OVER | S → C | Игра завершена |

#### CHAT (Чат)

| Код | Тип | Направление | Описание |
|-----|-----|-------------|----------|
| 0x0401 | CHAT_MESSAGE | C → S / S → C | Сообщение чата |
| 0x0402 | CHAT_HISTORY_REQUEST | C → S | Запрос истории |
| 0x0403 | CHAT_HISTORY_RESPONSE | S → C | История чата |
| 0x0404 | SYSTEM_MESSAGE | S → C | Системное сообщение |

#### SYSTEM (Системные)

| Код | Тип | Направление | Описание |
|-----|-----|-------------|----------|
| 0x0501 | HEARTBEAT_REQUEST | S → C | Проверка соединения |
| 0x0502 | HEARTBEAT_RESPONSE | C → S | Ответ на heartbeat |
| 0x0503 | PING | C → S | Проверка задержки |
| 0x0504 | PONG | S → C | Ответ на ping |
| 0x0505 | STATE_SYNC | S → C | Полная синхронизация |
| 0x0506 | STATE_UPDATE | S → C | Частичное обновление |
| 0x0507 | ERROR | S → C | Ошибка |
| 0x0508 | RECONNECT_REQUEST | C → S | Переподключение |
| 0x0509 | RECONNECT_RESPONSE | S → C | Ответ на переподключение |
| 0x050A | SERVER_SHUTDOWN | S → C | Сервер выключается |

#### ADMIN (Административные)

| Код | Тип | Направление | Описание |
|-----|-----|-------------|----------|
| 0x0601 | ADMIN_COMMAND | C → S | Админ-команда |
| 0x0602 | ADMIN_RESPONSE | S → C | Ответ на команду |
| 0x0603 | ADMIN_SET_MONEY | C → S | Изменить деньги |
| 0x0604 | ADMIN_SET_PROPERTY | C → S | Изменить собственность |
| 0x0605 | ADMIN_TELEPORT | C → S | Телепортировать |
| 0x0606 | ADMIN_CHANGE_ROLE | C → S | Изменить роль |
| 0x0607 | ADMIN_VIEW_LOGS | C → S | Просмотр логов |
| 0x0608 | ADMIN_UNDO_ACTION | C → S | Отменить действие |
| 0x0609 | ADMIN_SERVER_COMMAND | C → S | Серверная команда |
| 0x060A | ADMIN_BROADCAST | C → S | Объявление всем |

---

## 4. Формат полезной нагрузки (Payload)

### 4.1 Общие правила

- Все payload — JSON-объекты
- Кодировка: UTF-8
- Ключи: camelCase
- UUID: строковый формат `"550e8400-e29b-41d4-a716-446655440000"`
- Дата/время: ISO 8601 `"2024-01-15T10:30:00Z"`
- Деньги: целые числа (доллары)

### 4.2 Примеры пакетов

#### LOGIN_REQUEST (0x0101)

```
{
  "username": "player1",
  "password_hash": "$argon2id$v=19$m=65536,t=3,p=4$..."
}
LOGIN_RESPONSE (0x0102)

{
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "username": "player1",
  "role": "player",
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "refresh_token": "dGhpcyBpcyBhIHJlZnJl...",
  "expires_in": 3600
}
ROOM_LIST_RESPONSE (0x0202)

{
  "rooms": [
    {
      "room_id": "660e8400-e29b-41d4-a716-446655440001",
      "name": "Весёлая игра",
      "owner_id": "550e8400-e29b-41d4-a716-446655440000",
      "players_count": 3,
      "max_players": 4,
      "is_private": false,
      "has_password": false,
      "state": "waiting"
    }
  ]
}
ROLL_DICE_RESULT (0x0304)

{
  "die1": 3,
  "die2": 5,
  "total": 8,
  "is_double": false,
  "new_position": 15,
  "cell_type": "property",
  "cell_name": "Русалочка"
}
STATE_SYNC (0x0505)

{
  "game_id": "770e8400-e29b-41d4-a716-446655440002",
  "state": "active",
  "turn_number": 12,
  "current_player_id": "550e8400-e29b-41d4-a716-446655440000",
  "players": {
    "550e8400-...": {
      "username": "player1",
      "money": 1250,
      "position": {"cell_id": 15, "laps_completed": 2},
      "properties": ["sivka_burka", "railroad_1"],
      "in_jail": false,
      "color": "#3498db"
    }
  },
  "properties": {
    "sivka_burka": {
      "owner_id": "550e8400-...",
      "houses": 2,
      "has_hotel": false,
      "mortgaged": false
    }
  }
}
ERROR (0x0507)

{
  "error_code": 1022,
  "message": "Сейчас не ваш ход",
  "details": {
    "current_player_id": "550e8400-..."
  }
}
```

---

## 5. Управление соединением

### 5.1 Установка соединения

Клиент устанавливает TCP-соединение с сервером
Выполняется SSL/TLS handshake
Клиент отправляет LOGIN_REQUEST
Сервер проверяет учётные данные (Argon2id)
При успехе сервер генерирует:
access_token (срок 1 час)
refresh_token (срок 30 дней)
hmac_key (сессионный ключ для подписи пакетов)
Сервер отправляет LOGIN_RESPONSE
Все последующие пакеты подписываются hmac_key

### 5.2 Heartbeat

Сервер отправляет HEARTBEAT_REQUEST каждые 15 секунд
Клиент должен ответить HEARTBEAT_RESPONSE в течение 10 секунд
После 3 пропущенных ответов соединение разрывается

### 5.3 Ping

Клиент может отправить PING для измерения задержки
Сервер немедленно отвечает PONG с той же sequence

### 5.4 Переподключение

При обрыве соединения клиент пытается переподключиться
Отправляет RECONNECT_REQUEST с refresh_token

Сервер проверяет:
Валидность refresh_token
Существует ли активная игра с этим игроком

При успехе:
Генерирует новый access_token и hmac_key

Отправляет STATE_SYNC с полным состоянием игры
Уведомляет других игроков о переподключении

### 5.5 Завершение соединения

Клиент отправляет LOGOUT
Сервер помечает сессию как неактивную
Если игрок был в игре, запускается таймер переподключения

---

## 6. Безопасность

### 6.1 Аутентификация

Пароли никогда не передаются в открытом виде
При регистрации клиент отправляет Argon2id-хеш (вычисленный на клиенте)
Сервер хранит только хеш (с солью в формате Argon2)

### 6.2 Целостность пакетов

Каждый пакет подписывается HMAC-SHA256
Ключ HMAC уникален для каждой сессии
При несовпадении подписи пакет отбрасывается, событие логируется в security.log

### 6.3 Защита от replay-атак

Sequence Number: монотонно возрастает, сервер отклоняет пакеты с seq ≤ последнего
Timestamp: пакеты с отклонением > 30 секунд отбрасываются

### 6.4 Rate Limiting

Тип пакета	Лимит
Все пакеты	50/сек на сессию
CHAT_MESSAGE	3/сек
AUTH	10/мин

### 6.5 Проверка версий

Сервер проверяет версию протокола клиента
Major должен совпадать
Minor клиента не может быть больше серверного
При несовместимости: ERROR с кодом 1060 (CLIENT_OUTDATED)

---

## 7. Сжатие
 
Пакеты с payload > 512 байт сжимаются zlib (уровень 6)
Флаг COMPRESSED в заголовке указывает на сжатие
Клиент и сервер прозрачно сжимают/распаковывают пакеты
Максимальный размер распакованного payload: 512 КБ

---

## 8. Обработка ошибок

### 8.1 Коды ошибок

Код	    Описание

1001	Некорректный пакет
1002	Неверные учётные данные
1003	Имя пользователя занято
1004	Пользователь заблокирован
1005	Токен истёк
1006	Токен недействителен
1007	Сессия не найдена
1010	Комната не найдена
1011	Комната заполнена
1012	Комната защищена паролем
1013	Неверный пароль комнаты
1020	Игра не найдена
1021	Игра не активна
1022	Не ваш ход
1023	Недостаточно средств
1024	Собственность занята
1025	Не владеете собственностью
1040	Слишком много запросов
1041	Недостаточно прав
1060	Клиент устарел
1061	Несовместимость протокола

### 8.2 Формат ответа с ошибкой

```
{
  "error_code": 1023,
  "message": "Недостаточно средств: требуется 200$, доступно 150$",
  "details": {
    "required": 200,
    "available": 150
  }
}
```

---

## 9. Диаграмма последовательностей

### 9.1 Полный цикл: вход → игра → ход

Client                         Server
  │                              │
  │── TCP Connect (SSL) ────────>│
  │── LOGIN_REQUEST ────────────>│
  │<── LOGIN_RESPONSE ──────────│ (токены)
  │── ROOM_LIST_REQUEST ───────>│
  │<── ROOM_LIST_RESPONSE ──────│
  │── ROOM_JOIN_REQUEST ───────>│
  │<── ROOM_JOIN_RESPONSE ──────│
  │<── PLAYER_JOINED ───────────│ (всем в комнате)
  │── GAME_START_REQUEST ──────>│ (владелец)
  │<── GAME_STARTED ────────────│
  │<── STATE_SYNC ──────────────│ (полное состояние)
  │<── TURN_CHANGED ────────────│
  │── ROLL_DICE_REQUEST ───────>│
  │<── ROLL_DICE_RESULT ────────│
  │── BUY_PROPERTY_REQUEST ────>│
  │<── BUY_PROPERTY_RESPONSE ───│
  │── END_TURN_REQUEST ────────>│
  │<── TURN_CHANGED ────────────│
  
---

## 10. Константы протокола

Константа               	Значение    	Описание

MAGIC_NUMBER	            0x4247484D   	Идентификатор протокола
PROTOCOL_VERSION	        1.0.0	        Текущая версия
PACKET_HEADER_SIZE	        34 байта     	Размер заголовка
HMAC_SIZE	                32 байта    	Размер подписи
MAX_PACKET_SIZE	            1 МБ	        Максимальный размер пакета
MAX_PAYLOAD_SIZE	        512 КБ      	Максимальный размер нагрузки
COMPRESSION_THRESHOLD	    512 байт    	Порог сжатия
HEARTBEAT_INTERVAL	        15 сек	        Интервал проверки
HEARTBEAT_TIMEOUT	        10 сек      	Таймаут ответа
PACKET_TIMESTAMP_TOLERANCE	30 сек	        Допуск временной метки