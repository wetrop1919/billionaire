"""
shared/enums.py

Централизованное хранилище всех перечислений (Enum) проекта "Миллиардер".

Все Enum-классы определены исключительно здесь и используются как
единый источник истины для типов состояний, ролей, категорий и пр.

Использование:
    from shared.enums import PlayerRole, GameState, CellType, ...

Python: 3.13+
"""

from __future__ import annotations

from enum import StrEnum, IntEnum, IntFlag, auto


# ============================================================================
# РОЛИ ПОЛЬЗОВАТЕЛЕЙ (User Roles)
# ============================================================================

class UserRole(StrEnum):
    """
    Глобальная роль пользователя в системе.

    Определяет базовый уровень доступа к функциям сервера.
    Конкретные права определяются через Permission (см. shared/permissions.py).
    """

    CREATOR = "creator"        # Создатель/администратор — полный доступ
    PLAYER = "player"          # Обычный игрок
    OBSERVER = "observer"      # Наблюдатель


# ============================================================================
# СОСТОЯНИЯ КОМНАТЫ (Room States)
# ============================================================================

class RoomState(StrEnum):
    """
    Состояние игровой комнаты.
    """

    WAITING = "waiting"        # Ожидание игроков, игра не началась
    IN_GAME = "in_game"        # Игра активна
    FINISHED = "finished"      # Игра завершена


# ============================================================================
# СОСТОЯНИЯ ИГРЫ (Game States)
# ============================================================================

class GameState(StrEnum):
    """
    Состояние игровой сессии.
    """

    WAITING_FOR_PLAYERS = "waiting_for_players"  # Ожидание минимального числа игроков
    STARTING = "starting"                          # Инициализация игры
    ACTIVE = "active"                              # Игра идёт
    PAUSED = "paused"                              # Игра на паузе
    FINISHING = "finishing"                        # Подсчёт результатов
    FINISHED = "finished"                          # Игра завершена
    CLOSED = "closed"                              # Игра закрыта


# ============================================================================
# СОСТОЯНИЯ ХОДА (Turn States) — для игрового конечного автомата
# ============================================================================

class TurnState(StrEnum):
    """
    Состояния конечного автомата хода игрока.
    """

    AWAITING_DICE = "awaiting_dice"           # Ожидание броска кубиков
    DICE_ROLLED = "dice_rolled"               # Кубики брошены, начинается движение
    MOVING = "moving"                         # Фишка перемещается
    TOKEN_ARRIVED = "token_arrived"           # Фишка достигла клетки
    AWAITING_CELL_ACTION = "awaiting_cell_action"  # Ожидание действия на клетке
    AUCTION_ACTIVE = "auction_active"         # Идёт аукцион
    TRADE_NEGOTIATION = "trade_negotiation"   # Идут торги
    BUILDING_PHASE = "building_phase"         # Фаза строительства
    AWAITING_EXTRA_ACTIONS = "awaiting_extra_actions"  # Дополнительные действия
    TURN_COMPLETING = "turn_completing"       # Завершение хода
    TURN_COMPLETED = "turn_completed"         # Ход завершён


# ============================================================================
# ТРИГГЕРЫ КОНЕЧНОГО АВТОМАТА (State Machine Triggers)
# ============================================================================

class GameTrigger(StrEnum):
    """
    Триггеры для переходов в игровом конечном автомате.
    """

    ALL_PLAYERS_READY = "all_players_ready"
    GAME_START = "game_start"
    ROLL_DICE = "roll_dice"
    DICE_ANIMATION_DONE = "dice_animation_done"
    MOVING_ANIMATION_DONE = "moving_animation_done"
    BUY_PROPERTY = "buy_property"
    DECLINE_PROPERTY = "decline_property"
    START_AUCTION = "start_auction"
    AUCTION_WON = "auction_won"
    AUCTION_NO_BIDS = "auction_no_bids"
    PAY_RENT = "pay_rent"
    RENT_PAID = "rent_paid"
    CANNOT_PAY = "cannot_pay"
    DRAW_CARD = "draw_card"
    CARD_ACTION_DONE = "card_action_done"
    PAY_TAX = "pay_tax"
    TAX_PAID = "tax_paid"
    GO_TO_JAIL = "go_to_jail"
    JAIL_ACTION = "jail_action"
    BUILD_HOUSE = "build_house"
    BUILD_HOTEL = "build_hotel"
    MORTGAGE = "mortgage"
    UNMORTGAGE = "unmortgage"
    INITIATE_TRADE = "initiate_trade"
    TRADE_COMPLETED = "trade_completed"
    TRADE_DECLINED = "trade_declined"
    END_TURN = "end_turn"
    TURN_TIMEOUT = "turn_timeout"
    PLAYER_BANKRUPT = "player_bankrupt"
    GAME_END_TRIGGERED = "game_end_triggered"
    PAUSE = "pause"
    RESUME = "resume"


# ============================================================================
# ТИПЫ КЛЕТОК ИГРОВОГО ПОЛЯ (Cell Types)
# ============================================================================

class CellType(StrEnum):
    """
    Тип клетки на игровом поле.
    """

    START = "start"                   # Стартовая клетка
    PROPERTY = "property"             # Собственность (улица, станция, коммунальное)
    CHANCE = "chance"                 # Шанс
    FUND = "fund"                     # Фонд (аналог "Общественная казна")
    JAIL = "jail"                     # Тюрьма (клетка, куда отправляют)
    JAIL_VISIT = "jail_visit"         # Простое посещение тюрьмы
    GO_TO_JAIL = "go_to_jail"         # Отправляйся в тюрьму
    FREE_PARKING = "free_parking"     # Бесплатная парковка
    TAX = "tax"                       # Налог
    VERANDA = "veranda"               # Веранда (специальная клетка вне поля)


# ============================================================================
# ТИПЫ СОБСТВЕННОСТИ (Property Types)
# ============================================================================

class PropertyType(StrEnum):
    """
    Тип объекта собственности.
    """

    STREET = "street"           # Улица (цветовая группа, строительство домов/отелей)
    RAILROAD = "railroad"       # Железнодорожная станция
    UTILITY = "utility"         # Коммунальное предприятие


# ============================================================================
# ЦВЕТОВЫЕ ГРУППЫ УЛИЦ (Color Groups)
# ============================================================================

class ColorGroup(StrEnum):
    """
    Цветовые группы улиц для определения возможности строительства.
    """

    BROWN = "brown"
    LIGHT_BLUE = "light_blue"
    PINK = "pink"
    ORANGE = "orange"
    RED = "red"
    YELLOW = "yellow"
    GREEN = "green"
    DARK_BLUE = "dark_blue"


# ============================================================================
# ТИПЫ КАРТОЧЕК (Card Types)
# ============================================================================

class CardType(StrEnum):
    """
    Тип карточки.
    """

    CHANCE = "chance"   # Шанс
    FUND = "fund"       # Фонд


# ============================================================================
# ДЕЙСТВИЯ КАРТОЧЕК (Card Actions)
# ============================================================================

class CardActionType(StrEnum):
    """
    Тип действия, выполняемого по карточке.
    """

    RECEIVE_MONEY = "receive_money"           # Получить деньги
    PAY_MONEY = "pay_money"                   # Заплатить деньги
    MOVE_TO = "move_to"                       # Переместиться на клетку
    MOVE_STEPS = "move_steps"                 # Переместиться на N шагов
    GO_TO_JAIL = "go_to_jail"                 # Отправиться в тюрьму
    GET_OUT_OF_JAIL = "get_out_of_jail"       # Освободиться из тюрьмы
    GO_TO_VERANDA = "go_to_veranda"           # Отправиться на Веранду
    LEAVE_VERANDA = "leave_veranda"           # Покинуть Веранду
    COLLECT_FROM_PLAYERS = "collect_from_players"  # Собрать с каждого игрока
    PAY_TO_PLAYERS = "pay_to_players"         # Заплатить каждому игроку
    REPAIR_PROPERTY = "repair_property"       # Ремонт собственности
    BIRTHDAY = "birthday"                     # День рождения (сбор с игроков)
    CUSTOM = "custom"                         # Особое действие (описано в тексте)


# ============================================================================
# ТИПЫ СЕТЕВЫХ ПАКЕТОВ (Packet Types)
# ============================================================================

class PacketType(IntEnum):
    """
    Типы сетевых пакетов для маршрутизации сообщений.
    Каждый тип имеет уникальный числовой код для эффективной передачи.
    """

    # === AUTH (аутентификация) ===
    LOGIN_REQUEST = 0x0101
    LOGIN_RESPONSE = 0x0102
    REGISTER_REQUEST = 0x0103
    REGISTER_RESPONSE = 0x0104
    LOGOUT = 0x0105
    REFRESH_TOKEN_REQUEST = 0x0106
    REFRESH_TOKEN_RESPONSE = 0x0107

    # === ROOM (комнаты) ===
    ROOM_LIST_REQUEST = 0x0201
    ROOM_LIST_RESPONSE = 0x0202
    ROOM_CREATE_REQUEST = 0x0203
    ROOM_CREATE_RESPONSE = 0x0204
    ROOM_JOIN_REQUEST = 0x0205
    ROOM_JOIN_RESPONSE = 0x0206
    ROOM_LEAVE = 0x0207
    ROOM_SETTINGS_UPDATE = 0x0208
    ROOM_KICK_PLAYER = 0x0209
    PLAYER_JOINED = 0x020A
    PLAYER_LEFT = 0x020B

    # === GAME (игровые действия) ===
    GAME_START_REQUEST = 0x0301
    GAME_STARTED = 0x0302
    ROLL_DICE_REQUEST = 0x0303
    ROLL_DICE_RESULT = 0x0304
    BUY_PROPERTY_REQUEST = 0x0305
    BUY_PROPERTY_RESPONSE = 0x0306
    DECLINE_PROPERTY = 0x0307
    AUCTION_BID_REQUEST = 0x0308
    AUCTION_BID_RESPONSE = 0x0309
    AUCTION_RESULT = 0x030A
    BUILD_HOUSE_REQUEST = 0x030B
    BUILD_HOUSE_RESPONSE = 0x030C
    BUILD_HOTEL_REQUEST = 0x030D
    BUILD_HOTEL_RESPONSE = 0x030E
    MORTGAGE_REQUEST = 0x030F
    MORTGAGE_RESPONSE = 0x0310
    UNMORTGAGE_REQUEST = 0x0311
    UNMORTGAGE_RESPONSE = 0x0312
    TRADE_OFFER_REQUEST = 0x0313
    TRADE_OFFER_RESPONSE = 0x0314
    TRADE_ACCEPT_REQUEST = 0x0315
    TRADE_DECLINE_REQUEST = 0x0316
    TRADE_RESULT = 0x0317
    END_TURN_REQUEST = 0x0318
    TURN_CHANGED = 0x0319
    TURN_TIMEOUT_NOTIFY = 0x031A
    PAY_RENT_NOTIFY = 0x031B
    DRAW_CARD_RESULT = 0x031C
    JAIL_ACTION_REQUEST = 0x031D
    JAIL_ACTION_RESPONSE = 0x031E
    VERANDA_ACTION_REQUEST = 0x031F
    VERANDA_ACTION_RESPONSE = 0x0320
    PLAYER_BANKRUPT_NOTIFY = 0x0321
    GAME_OVER = 0x0322

    # === CHAT (чат) ===
    CHAT_MESSAGE = 0x0401
    CHAT_HISTORY_REQUEST = 0x0402
    CHAT_HISTORY_RESPONSE = 0x0403
    SYSTEM_MESSAGE = 0x0404

    # === SYSTEM (системные) ===
    HEARTBEAT_REQUEST = 0x0501
    HEARTBEAT_RESPONSE = 0x0502
    PING = 0x0503
    PONG = 0x0504
    STATE_SYNC = 0x0505
    STATE_UPDATE = 0x0506
    ERROR = 0x0507
    RECONNECT_REQUEST = 0x0508
    RECONNECT_RESPONSE = 0x0509
    SERVER_SHUTDOWN = 0x050A

    # === ADMIN (административные) ===
    ADMIN_COMMAND = 0x0601
    ADMIN_RESPONSE = 0x0602
    ADMIN_SET_MONEY = 0x0603
    ADMIN_SET_PROPERTY = 0x0604
    ADMIN_TELEPORT = 0x0605
    ADMIN_CHANGE_ROLE = 0x0606
    ADMIN_VIEW_LOGS = 0x0607
    ADMIN_UNDO_ACTION = 0x0608
    ADMIN_SERVER_COMMAND = 0x0609
    ADMIN_BROADCAST = 0x060A


# ============================================================================
# ФЛАГИ ПАКЕТА (Packet Flags)
# ============================================================================

class PacketFlags(IntFlag):
    """
    Битовые флаги заголовка пакета.
    """

    NONE = 0
    COMPRESSED = 1 << 0    # Пакет сжат zlib
    ENCRYPTED = 1 << 1     # Пакет зашифрован (зарезервировано)
    URGENT = 1 << 2        # Приоритетный пакет
    RESERVED_3 = 1 << 3    # Зарезервировано
    RESERVED_4 = 1 << 4    # Зарезервировано


# ============================================================================
# ТИПЫ ИГРОВЫХ СОБЫТИЙ (Event Types)
# ============================================================================

class EventType(StrEnum):
    """
    Типы игровых событий для журнала и системы событий.
    """

    # Игроки
    PLAYER_JOINED = "player_joined"
    PLAYER_LEFT = "player_left"
    PLAYER_RECONNECTED = "player_reconnected"
    PLAYER_DISCONNECTED = "player_disconnected"

    # Ходы
    TURN_STARTED = "turn_started"
    TURN_ENDED = "turn_ended"
    TURN_TIMEOUT = "turn_timeout"
    DICE_ROLLED = "dice_rolled"
    PLAYER_MOVED = "player_moved"

    # Собственность
    PROPERTY_BOUGHT = "property_bought"
    PROPERTY_DECLINED = "property_declined"
    PROPERTY_AUCTIONED = "property_auctioned"
    RENT_PAID = "rent_paid"
    HOUSE_BUILT = "house_built"
    HOTEL_BUILT = "hotel_built"
    PROPERTY_MORTGAGED = "property_mortgaged"
    PROPERTY_UNMORTGAGED = "property_unmortgaged"

    # Карточки
    CARD_DRAWN = "card_drawn"
    CARD_ACTION_EXECUTED = "card_action_executed"

    # Торговля
    TRADE_OFFERED = "trade_offered"
    TRADE_ACCEPTED = "trade_accepted"
    TRADE_DECLINED = "trade_declined"

    # Тюрьма
    PLAYER_JAILED = "player_jailed"
    PLAYER_FREED = "player_freed"

    # Веранда
    VERANDA_ENTERED = "veranda_entered"
    VERANDA_EXITED = "veranda_exited"

    # Банкротство
    PLAYER_BANKRUPT = "player_bankrupt"

    # Игра
    GAME_STARTED = "game_started"
    GAME_FINISHED = "game_finished"
    GAME_PAUSED = "game_paused"
    GAME_RESUMED = "game_resumed"

    # Админ
    ADMIN_ACTION = "admin_action"

    # Система
    SYSTEM_ERROR = "system_error"
    NETWORK_ERROR = "network_error"


# ============================================================================
# СОСТОЯНИЯ АУКЦИОНА (Auction States)
# ============================================================================

class AuctionState(StrEnum):
    """
    Состояние аукциона.
    """

    WAITING = "waiting"        # Ожидание участников
    ACTIVE = "active"          # Аукцион идёт
    FINISHED = "finished"      # Аукцион завершён (продан)
    NO_BIDS = "no_bids"        # Нет ставок (никто не купил)
    CANCELLED = "cancelled"    # Аукцион отменён


# ============================================================================
# СТАТУСЫ ТОРГОВОГО ПРЕДЛОЖЕНИЯ (Trade Statuses)
# ============================================================================

class TradeStatus(StrEnum):
    """
    Статус торгового предложения.
    """

    PENDING = "pending"        # Ожидает ответа
    ACCEPTED = "accepted"      # Принято
    DECLINED = "declined"      # Отклонено
    EXPIRED = "expired"        # Истекло время
    CANCELLED = "cancelled"    # Отменено инициатором


# ============================================================================
# СПОСОБЫ ВЫХОДА ИЗ ТЮРЬМЫ (Jail Exit Methods)
# ============================================================================

class JailExitMethod(StrEnum):
    """
    Способ выхода из тюрьмы.
    """

    FINE = "fine"          # Штраф 50$
    CARD = "card"          # Карточка освобождения
    TIMEOUT = "timeout"    # Принудительный выход после 2 кругов


# ============================================================================
# НАПРАВЛЕНИЯ ПЕРЕМЕЩЕНИЯ (Movement Directions)
# ============================================================================

class Direction(StrEnum):
    """
    Направление перемещения по полю.
    """

    FORWARD = "forward"    # Вперёд (по часовой стрелке)
    BACKWARD = "backward"  # Назад (против часовой стрелки)


# ============================================================================
# ТИПЫ СИСТЕМНЫХ СООБЩЕНИЙ (System Message Types)
# ============================================================================

class SystemMessageType(StrEnum):
    """
    Тип системного сообщения в чате.
    """

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    SUCCESS = "success"
    GAME_EVENT = "game_event"


# ============================================================================
# ТИПЫ ОШИБОК СЕРВЕРА (Error Codes)
# ============================================================================

class ErrorCode(IntEnum):
    """
    Коды ошибок для передачи клиенту.
    """

    UNKNOWN = 0
    INVALID_PACKET = 1001
    INVALID_CREDENTIALS = 1002
    USERNAME_TAKEN = 1003
    USER_BANNED = 1004
    TOKEN_EXPIRED = 1005
    TOKEN_INVALID = 1006
    SESSION_NOT_FOUND = 1007
    ROOM_NOT_FOUND = 1010
    ROOM_FULL = 1011
    ROOM_LOCKED = 1012
    ROOM_WRONG_PASSWORD = 1013
    ROOM_IN_GAME = 1014
    NOT_ROOM_OWNER = 1015
    GAME_NOT_FOUND = 1020
    GAME_NOT_ACTIVE = 1021
    NOT_YOUR_TURN = 1022
    INSUFFICIENT_FUNDS = 1023
    PROPERTY_OWNED = 1024
    PROPERTY_NOT_OWNED = 1025
    CANNOT_BUILD = 1026
    CANNOT_MORTGAGE = 1027
    INVALID_TRADE = 1028
    NOT_IN_JAIL = 1029
    NOT_ON_VERANDA = 1030
    ACTION_NOT_ALLOWED = 1031
    RATE_LIMITED = 1040
    PERMISSION_DENIED = 1041
    SERVER_ERROR = 1050
    CLIENT_OUTDATED = 1060
    PROTOCOL_MISMATCH = 1061


# ============================================================================
# РЕЗУЛЬТАТЫ ПРОВЕРКИ ВЕРСИЙ (Version Check Results)
# ============================================================================

class VersionCheckResult(StrEnum):
    """
    Результат проверки совместимости версий клиента и сервера.
    """

    OK = "ok"
    CLIENT_TOO_OLD = "client_too_old"
    CLIENT_TOO_NEW = "client_too_new"
    PROTOCOL_MISMATCH = "protocol_mismatch"


# ============================================================================
# ЯЗЫКИ (Languages)
# ============================================================================

class Language(StrEnum):
    """
    Поддерживаемые языки интерфейса.
    """

    RU = "ru"
    EN = "en"