# API «Миллиардер»

## 1. Обзор

API сервера построено на основе бинарного сетевого протокола (см. `protocol.md`). Все запросы и ответы передаются в виде пакетов с JSON-нагрузкой. Ниже описаны все конечные точки, сгруппированные по категориям.

### Нотация

- `C → S` — клиент отправляет серверу
- `S → C` — сервер отправляет клиенту
- Все UUID передаются как строки в формате `"550e8400-e29b-41d4-a716-446655440000"`
- Все денежные суммы — целые числа (доллары)
- Дата/время — ISO 8601 `"2024-01-15T10:30:00Z"`

---

## 2. Аутентификация (AUTH)

### 2.1 Регистрация

**REGISTER_REQUEST** (0x0103) `C → S`

```
{
  "username": "player1",
  "password_hash": "$argon2id$v=19$m=65536,t=3,p=4$abc123...",
  "language": "ru"
}
```

Поле	        Тип	    Обязательное	Описание

username	    string	Да	            Имя пользователя (3-32 символа)
password_hash	string	Да	            Argon2id хеш пароля
language	    string	Нет	            Язык интерфейса (ru/en, по умолчанию ru)

REGISTER_RESPONSE (0x0104) S → C

```
{
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "username": "player1",
  "role": "player",
  "created_at": "2024-01-15T10:30:00Z"
}
```

Ошибки:

1003 — имя пользователя занято
1041 — недостаточно прав (если регистрация отключена)

### 2.2 Вход

LOGIN_REQUEST (0x0101) C → S

```
{
  "username": "player1",
  "password_hash": "$argon2id$v=19$m=65536,t=3,p=4$abc123..."
}
```

LOGIN_RESPONSE (0x0102) S → C

```
{
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "username": "player1",
  "role": "player",
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "refresh_token": "dGhpcyBpcyBhIHJlZnJl...",
  "expires_in": 3600
}
```

Поле	        Описание

access_token	Токен доступа (срок 1 час)
refresh_token	Токен обновления (срок 30 дней)
expires_in	    Время жизни access_token в секундах

Ошибки:

1002 — неверные учётные данные
1004 — пользователь заблокирован

### 2.3 Обновление токена

REFRESH_TOKEN_REQUEST (0x0106) C → S

```
{
  "refresh_token": "dGhpcyBpcyBhIHJlZnJl..."
}
```

REFRESH_TOKEN_RESPONSE (0x0107) S → C

```
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "refresh_token": "bmV3IHJlZnJlc2ggdG9r...",
  "expires_in": 3600
}
```

Ошибки:

1005 — токен истёк
1006 — токен недействителен

### 2.4 Выход

LOGOUT (0x0105) C → S

```
{}
```

Ответ не требуется (соединение закрывается сервером).

---

## 3. Комнаты (ROOM)

### 3.1 Список комнат

ROOM_LIST_REQUEST (0x0201) C → S

```
{
  "filter": "waiting",
  "show_private": true,
  "show_full": false
}
```

Поле	        Тип  	По умолчанию	Описание

filter	string	 "all"	Фильтр: all, waiting, in_game, finished
show_private	 bool	true	        Показывать приватные комнаты
show_full	     bool	false	        Показывать заполненные

ROOM_LIST_RESPONSE (0x0202) S → C

```
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
      "state": "waiting",
      "status_text": "Ожидание",
      "icon": "🌍"
    }
  ],
  "total": 5
}
```

### 3.2 Создание комнаты

ROOM_CREATE_REQUEST (0x0203) C → S

```
{
  "name": "Весёлая игра",
  "config": {
    "max_players": 4,
    "turn_timeout": 60,
    "start_money": 1500,
    "start_bonus": 200,
    "is_private": false,
    "password": "",
    "allow_spectators": true,
    "game_rules": {
      "auction_enabled": true,
      "trade_enabled": true,
      "building_enabled": true
    }
  }
}
```

Поле	                  Тип	    Обязательное	Описание

name	                  string	Да	             Название (1-32 символа)
config.max_players	      int	    Нет	             Максимум игроков (2-8, по умолчанию 4)
config.turn_timeout	      int	    Нет	             Таймаут хода в секундах (15-300)
config.start_money	      int	    Нет	             Стартовый капитал
config.start_bonus	      int	    Нет	             Бонус за Старт
config.is_private	      bool	    Нет	             Приватная комната
config.password        	  string	Нет	             Пароль (если приватная)
config.allow_spectators	  bool	    Нет	             Разрешить наблюдателей
config.game_rules	      object	Нет	             Настраиваемые правила

ROOM_CREATE_RESPONSE (0x0204) S → C

```
{
  "room_id": "660e8400-e29b-41d4-a716-446655440001",
  "name": "Весёлая игра",
  "owner_id": "550e8400-e29b-41d4-a716-446655440000",
  "config": { "...": "..." },
  "state": "waiting",
  "players": ["550e8400-..."],
  "created_at": "2024-01-15T10:30:00Z"
}
```

### 3.3 Присоединение к комнате

ROOM_JOIN_REQUEST (0x0205) C → S

```
{
  "room_id": "660e8400-e29b-41d4-a716-446655440001",
  "password": "secret",
  "as_observer": false
}
```

Поле	      Тип	  Обязательное	Описание

room_id	      UUID	   Да	         ID комнаты
password	  string   Нет	         Пароль (для приватных)
as_observer	  bool	   Нет	         Войти как наблюдатель

ROOM_JOIN_RESPONSE (0x0206) S → C

```
{
  "room_id": "660e8400-...",
  "state": "waiting",
  "players": [
    {"user_id": "550e8400-...", "username": "player1", "role": "creator", "color": "#e74c3c"},
    {"user_id": "660e8400-...", "username": "player2", "role": "player", "color": "#3498db"}
  ],
  "config": { "...": "..." }
}
```

Уведомление другим игрокам:

PLAYER_JOINED (0x020A) S → C (broadcast)

```
{
  "user_id": "660e8400-...",
  "username": "player2",
  "color": "#3498db"
}
```

Ошибки:

1010 — комната не найдена
1011 — комната заполнена
1012 — требуется пароль
1013 — неверный пароль
1014 — в комнате уже идёт игра

### 3.4 Выход из комнаты

ROOM_LEAVE (0x0207) C → S

```
{
  "room_id": "660e8400-..."
}
```

PLAYER_LEFT (0x020B) S → C (broadcast)

```
{
  "user_id": "660e8400-...",
  "username": "player2",
  "new_owner_id": null
}
```

### 3.5 Обновление настроек комнаты

ROOM_SETTINGS_UPDATE (0x0208) C → S

```
{
  "room_id": "660e8400-...",
  "config": {
    "max_players": 6,
    "turn_timeout": 90
  }
}
```

Ошибки:

1015 — не владелец комнаты
1014 — игра уже идёт

### 3.6 Выгнать игрока

ROOM_KICK_PLAYER (0x0209) C → S

```
{
  "room_id": "660e8400-...",
  "user_id": "770e8400-..."
}
```

Ошибки:

1015 — не владелец комнаты
1041 — недостаточно прав

---

## 4. Игра (GAME)

### 4.1 Запуск игры

GAME_START_REQUEST (0x0301) C → S

```
{
  "room_id": "660e8400-..."
}
``` 
GAME_STARTED (0x0302) S → C (broadcast)

```
{
  "game_id": "880e8400-e29b-41d4-a716-446655440000",
  "players": ["550e8400-...", "660e8400-..."],
  "turn_order": ["550e8400-...", "660e8400-..."],
  "first_player_id": "660e8400-..."
}
```

Ошибки:

1015 — не владелец комнаты
Недостаточно игроков (минимум 2)

### 4.2 Синхронизация состояния

STATE_SYNC (0x0505) S → C

Автоматически отправляется после:
Подключения к игре
Переподключения
По запросу клиента

```
{
  "game_id": "880e8400-...",
  "state": "active",
  "turn_number": 5,
  "current_player_id": "550e8400-...",
  "players": {
    "550e8400-...": {
      "username": "player1",
      "money": 1200,
      "position": {"cell_id": 15, "laps_completed": 1},
      "properties": ["sivka_burka", "railroad_1"],
      "in_jail": false,
      "bankrupt": false,
      "is_online": true,
      "color": "#e74c3c"
    }
  },
  "properties": {
    "sivka_burka": {
      "owner_id": "550e8400-...",
      "houses": 2,
      "has_hotel": false,
      "mortgaged": false
    }
  },
  "free_parking_money": 0,
  "turn_order": ["550e8400-...", "660e8400-..."],
  "current_turn_index": 0
}
```

### 4.3 Бросок кубиков

ROLL_DICE_REQUEST (0x0303) C → S

```
{}
```

ROLL_DICE_RESULT (0x0304) S → C (broadcast)

```
{
  "player_id": "550e8400-...",
  "die1": 3,
  "die2": 5,
  "total": 8,
  "is_double": false,
  "from_cell": 15,
  "to_cell": 23,
  "passed_start": false,
  "cell_type": "property",
  "cell_name": "Буратино",
  "property_id": "buratino",
  "can_buy": true
}
```

Ошибки:

1022 — не ваш ход

### 4.4 Покупка собственности

BUY_PROPERTY_REQUEST (0x0305) C → S

```
{
  "property_id": "buratino"
}
```

BUY_PROPERTY_RESPONSE (0x0306) S → C

```
{
  "property_id": "buratino",
  "price": 220,
  "new_balance": 980,
  "owner_id": "550e8400-..."
}
```

Ошибки:

1022 — не ваш ход
1023 — недостаточно средств
1024 — собственность уже занята

### 4.5 Отказ от покупки / запуск аукциона

DECLINE_PROPERTY (0x0307) C → S

```
{
  "property_id": "buratino"
}
```

Если аукционы включены, сервер автоматически запускает аукцион и отправляет всем:

AUCTION_RESULT (0x030A) S → C (broadcast) — начало аукциона

```
{
  "status": "active",
  "property_id": "buratino",
  "property_name": "Буратино",
  "start_price": 110,
  "current_bid": 0,
  "highest_bidder_id": null,
  "timeout_seconds": 180
}
```

### 4.6 Ставка на аукционе

AUCTION_BID_REQUEST (0x0308) C → S

```
{
  "property_id": "buratino",
  "amount": 150
}
```

AUCTION_BID_RESPONSE (0x0309) S → C

```
{
  "property_id": "buratino",
  "amount": 150,
  "bidder_id": "660e8400-...",
  "is_highest": true
}
```

Ошибки:

1023 — недостаточно средств
1041 — не можете участвовать в аукционе

### 4.7 Завершение аукциона

AUCTION_RESULT (0x030A) S → C (broadcast) — результат

```
{
  "status": "finished",
  "property_id": "buratino",
  "property_name": "Буратино",
  "winner_id": "660e8400-...",
  "winning_bid": 150,
  "no_bids": false
}
```

Или если никто не купил:

```
{
  "status": "no_bids",
  "property_id": "buratino",
  "property_name": "Буратино",
  "no_bids": true
}
```

### 4.8 Строительство

BUILD_HOUSE_REQUEST (0x030B) C → S

```
{
  "property_id": "sivka_burka"
}
```

BUILD_HOUSE_RESPONSE (0x030C) S → C

```
{
  "property_id": "sivka_burka",
  "new_houses": 3,
  "cost": 10,
  "new_balance": 970
}
```

BUILD_HOTEL_REQUEST (0x030D) C → S

```
{
  "property_id": "sivka_burka"
}
```

BUILD_HOTEL_RESPONSE (0x030E) S → C

```
{
  "property_id": "sivka_burka",
  "has_hotel": true,
  "cost": 50,
  "new_balance": 920
}
```

Ошибки:

1025 — не владеете собственностью
1026 — невозможно построить (не улица, максимум домов, в залоге)
1023 — недостаточно средств

### 4.9 Залог и выкуп

MORTGAGE_REQUEST (0x030F) C → S

```
{
  "property_id": "sivka_burka"
}
```

MORTGAGE_RESPONSE (0x0310) S → C

```
{
  "property_id": "sivka_burka",
  "mortgage_value": 30,
  "new_balance": 1000
}
```

UNMORTGAGE_REQUEST (0x0311) C → S

```
{
  "property_id": "sivka_burka"
}
```

UNMORTGAGE_RESPONSE (0x0312) S → C

```
{
  "property_id": "sivka_burka",
  "unmortgage_cost": 33,
  "new_balance": 967
}
```

Ошибки:

1027 — невозможно заложить (есть постройки, уже в залоге)

### 4.10 Торговля

TRADE_OFFER_REQUEST (0x0313) C → S

```
{
  "to_player_id": "660e8400-...",
  "offer": {
    "properties": ["sivka_burka"],
    "cards": [],
    "money": 0,
    "loan": {"amount": 0, "percent": null}
  },
  "request": {
    "properties": ["railroad_1"],
    "cards": [],
    "money": 0
  },
  "message": "Меняю Сивку-бурку на станцию"
}
```

TRADE_OFFER_RESPONSE (0x0314) S → C

```
{
  "trade_id": "990e8400-...",
  "from_player_id": "550e8400-...",
  "to_player_id": "660e8400-...",
  "status": "pending",
  "expires_at": "2024-01-15T10:32:00Z"
}
```

TRADE_RESULT (0x0317) S → C — при принятии сделки

```
{
  "trade_id": "990e8400-...",
  "status": "accepted",
  "transferred_to_initiator": {
    "properties": ["railroad_1"],
    "cards": []
  },
  "transferred_to_recipient": {
    "properties": ["sivka_burka"],
    "cards": []
  }
}
```

Ошибки:

1028 — некорректная сделка

### 4.11 Завершение хода

END_TURN_REQUEST (0x0318) C → S

```
{}
```

TURN_CHANGED (0x0319) S → C (broadcast)

```
{
  "previous_player_id": "550e8400-...",
  "current_player_id": "660e8400-...",
  "turn_number": 6
}
```

TURN_TIMEOUT_NOTIFY (0x031A) S → C

```
{
  "player_id": "550e8400-...",
  "reason": "timeout"
}
```

### 4.12 Карточки

DRAW_CARD_RESULT (0x031C) S → C

```
{
  "player_id": "550e8400-...",
  "card": {
    "card_id": "chance_06",
    "card_type": "chance",
    "title": "Наследство",
    "description": "Вы получили наследство. Получите 100$.",
    "action_type": "receive_money"
  },
  "result": {
    "money_change": 100,
    "new_balance": 1100,
    "message": "Вы получили наследство. Получите 100$."
  }
}
```

### 4.13 Тюрьма

JAIL_ACTION_REQUEST (0x031D) C → S

```
{
  "action": "pay_fine"
}
```

Доступные действия: pay_fine, use_card.
JAIL_ACTION_RESPONSE (0x031E) S → C

```
{
  "action": "pay_fine",
  "success": true,
  "new_balance": 1050,
  "message": "Вы заплатили 50$ и вышли из тюрьмы."
}
```

### 4.14 Веранда

VERANDA_ACTION_REQUEST (0x031F) C → S

```
{
  "action": "pay_exit"
}
```

Доступные действия: pay_exit, use_card.

VERANDA_ACTION_RESPONSE (0x0320) S → C

```
{
  "action": "pay_exit",
  "success": true,
  "new_balance": 1000,
  "new_position": 15,
  "message": "Вы заплатили 50$ и покинули Веранду."
}
```

### 4.15 Банкротство

PLAYER_BANKRUPT_NOTIFY (0x0321) S → C (broadcast)

```
{
  "player_id": "550e8400-...",
  "username": "player1",
  "reason": "cannot_pay_rent",
  "debt_amount": 200,
  "creditor_id": "660e8400-...",
  "properties_lost": ["sivka_burka", "railroad_1"]
}
```

### 4.16 Завершение игры

GAME_OVER (0x0322) S → C (broadcast)

```
{
  "game_id": "880e8400-...",
  "trigger": "player_bankrupt",
  "results": [
    {
      "player_id": "660e8400-...",
      "username": "player2",
      "final_money": 2500,
      "properties_value": 800,
      "total_wealth": 3300,
      "rank": 1,
      "is_winner": true
    },
    {
      "player_id": "550e8400-...",
      "username": "player1",
      "final_money": 0,
      "properties_value": 0,
      "total_wealth": 0,
      "rank": 2,
      "is_bankrupt": true
    }
  ],
  "total_turns": 25,
  "duration_seconds": 1800
}
```

---

## 5. Чат (CHAT)

### 5.1 Отправка сообщения

CHAT_MESSAGE (0x0401) C → S

```
{
  "room_id": "660e8400-...",
  "content": "Привет всем!"
}
```

CHAT_MESSAGE (0x0401) S → C (broadcast)

```
{
  "message_id": 12345,
  "room_id": "660e8400-...",
  "user_id": "550e8400-...",
  "username": "player1",
  "content": "Привет всем!",
  "message_type": "player",
  "created_at": "2024-01-15T10:30:30Z"
}
```

### 5.2 История чата

CHAT_HISTORY_REQUEST (0x0402) C → S

```
{
  "room_id": "660e8400-...",
  "limit": 50,
  "before_id": 12300
}
```

CHAT_HISTORY_RESPONSE (0x0403) S → C

```
{
  "messages": [
    {
      "message_id": 12344,
      "user_id": "660e8400-...",
      "username": "player2",
      "content": "Как дела?",
      "message_type": "player",
      "created_at": "2024-01-15T10:30:25Z"
    }
  ],
  "has_more": true
}
```

### 5.4 Системное сообщение

SYSTEM_MESSAGE (0x0404) S → C

```
{
  "message_type": "game_event",
  "content": "Игрок player1 купил Сивка-бурка за 60$",
  "data": {
    "event": "property_bought",
    "player_id": "550e8400-...",
    "property_id": "sivka_burka"
  }
}
```

---

## 6. Системные (SYSTEM)

### 6.1 Heartbeat

HEARTBEAT_REQUEST (0x0501) S → C

```
{
  "server_time": "2024-01-15T10:30:35Z"
}
```

HEARTBEAT_RESPONSE (0x0502) C → S

```
{
  "client_time": "2024-01-15T10:30:35Z"
}
```

### 6.2 Ping

PING (0x0503) C → S

```
{
  "sent_at": 1705312235000
}
```

PONG (0x0504) S → C

```
{
  "sent_at": 1705312235000,
  "received_at": 1705312235050,
  "server_time": 1705312235050
}
```

### 6.3 Переподключение

RECONNECT_REQUEST (0x0508) C → S

```
{
  "refresh_token": "dGhpcyBpcyBhIHJlZnJl...",
  "game_id": "880e8400-..."
}
```

RECONNECT_RESPONSE (0x0509) S → C

```
{
  "success": true,
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "game_state": "active",
  "player_state": { "...": "..." }
}
```

Ошибки:

1006 — токен недействителен
1020 — игра не найдена

### 6.4 Ошибка

ERROR (0x0507) S → C

```
{
  "error_code": 1023,
  "message": "Недостаточно средств: требуется 200$, доступно 150$",
  "details": {
    "required": 200,
    "available": 150,
    "property_id": "emelya"
  }
}
```

### 6.5 Частичное обновление

STATE_UPDATE (0x0506) S → C

```
{
  "updates": [
    {
      "type": "player_money",
      "player_id": "550e8400-...",
      "data": {"money": 1200}
    },
    {
      "type": "property_state",
      "property_id": "sivka_burka",
      "data": {"houses": 3, "has_hotel": false}
    }
  ]
}
```

---

## 7. Административные (ADMIN)

### 7.1 Изменение денег

ADMIN_SET_MONEY (0x0603) C → S

```
{
  "player_id": "550e8400-...",
  "amount": 5000
}
```

ADMIN_RESPONSE (0x0602) S → C

```
{
  "command": "set_money",
  "success": true,
  "message": "Баланс игрока player1 установлен на 5000$"
}
```

### 7.2 Изменение собственности

ADMIN_SET_PROPERTY (0x0604) C → S

```
{
  "property_id": "emelya",
  "owner_id": "550e8400-...",
  "houses": 4,
  "has_hotel": true
}
```

### 7.3 Телепортация

ADMIN_TELEPORT (0x0605) C → S

```
{
  "player_id": "550e8400-...",
  "cell_id": 20
}
```

### 7.4 Изменение роли

ADMIN_CHANGE_ROLE (0x0606) C → S

```
{
  "user_id": "660e8400-...",
  "new_role": "creator"
}
```

### 7.5 Просмотр логов

ADMIN_VIEW_LOGS (0x0607) C → S

```
{
  "log_type": "game",
  "game_id": "880e8400-...",
  "limit": 100,
  "offset": 0
}
```

### 7.6 Отмена действия

ADMIN_UNDO_ACTION (0x0608) C → S

```
{
  "game_id": "880e8400-...",
  "steps_back": 1
}
```

### 7.7 Объявление

ADMIN_BROADCAST (0x060A) C → S

```
{
  "message": "Сервер будет перезагружен через 5 минут!",
  "message_type": "warning"
}
```

### 7.8 Серверная команда

ADMIN_SERVER_COMMAND (0x0609) C → S

```
{
  "command": "shutdown",
  "parameters": {
    "delay_seconds": 60,
    "reason": "Плановое обслуживание"
  }
}
```

Доступные команды: shutdown, restart, backup, restore, reload_config, clear_logs.

8. Коды ошибок

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
1014	В комнате уже идёт игра
1015	Не владелец комнаты
1020	Игра не найдена
1021	Игра не активна
1022	Не ваш ход
1023	Недостаточно средств
1024	Собственность уже занята
1025	Не владеете собственностью
1026	Невозможно построить
1027	Невозможно заложить
1028	Некорректная сделка
1029	Не в тюрьме
1030	Не на Веранде
1031	Действие не разрешено
1040	Слишком много запросов
1041	Недостаточно прав
1050	Внутренняя ошибка сервера
1060	Клиент устарел
1061	Несовместимость протокола