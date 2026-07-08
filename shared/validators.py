"""
shared/validators.py

Модуль валидации данных для проекта "Миллиардер".

Содержит функции для проверки корректности:
- Пользовательского ввода (имена, пароли, сообщения)
- Игровых действий (покупка, строительство, торговля)
- Конфигураций комнат и игр
- Сетевых данных

Все проверки возвращают Optional[str] — сообщение об ошибке
или None, если данные корректны.

Python: 3.13+
"""

from __future__ import annotations

import re
from typing import Any, Optional
from uuid import UUID

from shared.constants import (
    MIN_USERNAME_LENGTH,
    MAX_USERNAME_LENGTH,
    MIN_PASSWORD_LENGTH,
    MAX_PASSWORD_LENGTH,
    MAX_CHAT_MESSAGE_LENGTH,
    MAX_ROOM_NAME_LENGTH,
    MAX_ROOM_PASSWORD_LENGTH,
    MIN_PLAYERS,
    MAX_PLAYERS,
    MIN_TURN_TIMEOUT,
    MAX_TURN_TIMEOUT,
    MIN_LOAN_PERCENT,
    MAX_LOAN_PERCENT,
    DEFAULT_START_MONEY,
    BOARD_CELLS_COUNT,
)


# ============================================================================
# ВАЛИДАЦИЯ ПОЛЬЗОВАТЕЛЬСКОГО ВВОДА
# ============================================================================

def validate_username(username: str) -> Optional[str]:
    """
    Проверить имя пользователя.

    Требования:
    - Длина от MIN_USERNAME_LENGTH до MAX_USERNAME_LENGTH символов
    - Только буквы, цифры, подчёркивание и дефис
    - Начинается с буквы

    Args:
        username: Имя пользователя.

    Returns:
        Сообщение об ошибке или None.
    """
    if not username:
        return "Имя пользователя не может быть пустым"

    if len(username) < MIN_USERNAME_LENGTH:
        return (
            f"Имя пользователя должно быть не менее "
            f"{MIN_USERNAME_LENGTH} символов"
        )

    if len(username) > MAX_USERNAME_LENGTH:
        return (
            f"Имя пользователя должно быть не более "
            f"{MAX_USERNAME_LENGTH} символов"
        )

    if not re.match(r"^[a-zA-Zа-яА-ЯёЁ][a-zA-Zа-яА-ЯёЁ0-9_-]*$", username):
        return (
            "Имя пользователя должно начинаться с буквы и содержать "
            "только буквы, цифры, подчёркивание и дефис"
        )

    # Запрещённые имена
    forbidden = {"admin", "root", "system", "server", "moderator", "moder"}
    if username.lower() in forbidden:
        return "Это имя пользователя зарезервировано"

    return None


def validate_password(password: str) -> Optional[str]:
    """
    Проверить пароль.

    Требования:
    - Длина от MIN_PASSWORD_LENGTH до MAX_PASSWORD_LENGTH символов
    - Минимум одна цифра
    - Минимум одна заглавная буква
    - Минимум одна строчная буква

    Args:
        password: Пароль.

    Returns:
        Сообщение об ошибке или None.
    """
    if not password:
        return "Пароль не может быть пустым"

    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Пароль должен быть не менее {MIN_PASSWORD_LENGTH} символов"

    if len(password) > MAX_PASSWORD_LENGTH:
        return f"Пароль должен быть не более {MAX_PASSWORD_LENGTH} символов"

    if not re.search(r"[0-9]", password):
        return "Пароль должен содержать хотя бы одну цифру"

    if not re.search(r"[A-ZА-ЯЁ]", password):
        return "Пароль должен содержать хотя бы одну заглавную букву"

    if not re.search(r"[a-zа-яё]", password):
        return "Пароль должен содержать хотя бы одну строчную букву"

    return None


def validate_chat_message(message: str) -> Optional[str]:
    """
    Проверить сообщение чата.

    Args:
        message: Текст сообщения.

    Returns:
        Сообщение об ошибке или None.
    """
    if not message or not message.strip():
        return "Сообщение не может быть пустым"

    if len(message) > MAX_CHAT_MESSAGE_LENGTH:
        return (
            f"Сообщение слишком длинное: максимум "
            f"{MAX_CHAT_MESSAGE_LENGTH} символов"
        )

    # Проверка на непечатные символы
    if not message.isprintable():
        return "Сообщение содержит недопустимые символы"

    return None


def validate_room_name(name: str) -> Optional[str]:
    """
    Проверить название комнаты.

    Args:
        name: Название комнаты.

    Returns:
        Сообщение об ошибке или None.
    """
    if not name or not name.strip():
        return "Название комнаты не может быть пустым"

    if len(name) > MAX_ROOM_NAME_LENGTH:
        return (
            f"Название комнаты должно быть не более "
            f"{MAX_ROOM_NAME_LENGTH} символов"
        )

    if not name.isprintable():
        return "Название комнаты содержит недопустимые символы"

    # Запрет на HTML/скрипты
    dangerous = {"<", ">", "&", "\"", "'", "`"}
    if any(char in name for char in dangerous):
        return "Название комнаты содержит недопустимые символы"

    return None


def validate_room_password(password: str) -> Optional[str]:
    """
    Проверить пароль комнаты.

    Args:
        password: Пароль комнаты.

    Returns:
        Сообщение об ошибке или None.
    """
    if not password:
        return "Пароль комнаты не может быть пустым"

    if len(password) > MAX_ROOM_PASSWORD_LENGTH:
        return (
            f"Пароль комнаты должен быть не более "
            f"{MAX_ROOM_PASSWORD_LENGTH} символов"
        )

    if not password.isprintable():
        return "Пароль комнаты содержит недопустимые символы"

    return None


# ============================================================================
# ВАЛИДАЦИЯ КОНФИГУРАЦИИ КОМНАТЫ
# ============================================================================

def validate_max_players(max_players: int) -> Optional[str]:
    """
    Проверить максимальное количество игроков.

    Args:
        max_players: Количество игроков.

    Returns:
        Сообщение об ошибке или None.
    """
    if not isinstance(max_players, int):
        return "Количество игроков должно быть целым числом"

    if not (MIN_PLAYERS <= max_players <= MAX_PLAYERS):
        return (
            f"Количество игроков должно быть от {MIN_PLAYERS} "
            f"до {MAX_PLAYERS}"
        )

    return None


def validate_turn_timeout(timeout: int) -> Optional[str]:
    """
    Проверить таймаут хода.

    Args:
        timeout: Таймаут в секундах.

    Returns:
        Сообщение об ошибке или None.
    """
    if not isinstance(timeout, int):
        return "Таймаут должен быть целым числом"

    if not (MIN_TURN_TIMEOUT <= timeout <= MAX_TURN_TIMEOUT):
        return (
            f"Таймаут должен быть от {MIN_TURN_TIMEOUT} "
            f"до {MAX_TURN_TIMEOUT} секунд"
        )

    return None


def validate_start_money(money: int) -> Optional[str]:
    """
    Проверить стартовый капитал.

    Args:
        money: Сумма денег.

    Returns:
        Сообщение об ошибке или None.
    """
    if not isinstance(money, int):
        return "Стартовый капитал должен быть целым числом"

    if money < 0:
        return "Стартовый капитал не может быть отрицательным"

    if money > 100_000:
        return "Стартовый капитал не может превышать 100 000$"

    return None


def validate_start_bonus(bonus: int) -> Optional[str]:
    """
    Проверить бонус за прохождение Старта.

    Args:
        bonus: Сумма бонуса.

    Returns:
        Сообщение об ошибке или None.
    """
    if not isinstance(bonus, int):
        return "Бонус должен быть целым числом"

    if bonus < 0:
        return "Бонус не может быть отрицательным"

    if bonus > 10_000:
        return "Бонус не может превышать 10 000$"

    return None


# ============================================================================
# ВАЛИДАЦИЯ ИГРОВЫХ ДЕЙСТВИЙ
# ============================================================================

def validate_dice_values(die1: int, die2: int) -> Optional[str]:
    """
    Проверить значения кубиков.

    Args:
        die1: Первый кубик.
        die2: Второй кубик.

    Returns:
        Сообщение об ошибке или None.
    """
    if not (1 <= die1 <= 6):
        return f"Недопустимое значение первого кубика: {die1}"

    if not (1 <= die2 <= 6):
        return f"Недопустимое значение второго кубика: {die2}"

    return None


def validate_cell_id(cell_id: int) -> Optional[str]:
    """
    Проверить ID клетки.

    Args:
        cell_id: ID клетки.

    Returns:
        Сообщение об ошибке или None.
    """
    if not isinstance(cell_id, int):
        return "ID клетки должен быть целым числом"

    if not (0 <= cell_id < BOARD_CELLS_COUNT):
        return (
            f"ID клетки должен быть от 0 до {BOARD_CELLS_COUNT - 1}"
        )

    return None


def validate_property_id(property_id: str) -> Optional[str]:
    """
    Проверить ID собственности.

    Args:
        property_id: Идентификатор собственности.

    Returns:
        Сообщение об ошибке или None.
    """
    if not property_id or not property_id.strip():
        return "ID собственности не может быть пустым"

    if not re.match(r"^[a-zA-Z0-9_-]+$", property_id):
        return "ID собственности содержит недопустимые символы"

    return None


def validate_money_amount(amount: int) -> Optional[str]:
    """
    Проверить денежную сумму.

    Args:
        amount: Сумма денег.

    Returns:
        Сообщение об ошибке или None.
    """
    if not isinstance(amount, int):
        return "Сумма должна быть целым числом"

    if amount < 0:
        return "Сумма не может быть отрицательной"

    if amount > 10_000_000:
        return "Сумма не может превышать 10 000 000$"

    return None


def validate_bid_amount(bid: int, min_bid: int, player_money: int) -> Optional[str]:
    """
    Проверить ставку на аукционе.

    Args:
        bid: Предлагаемая ставка.
        min_bid: Минимальная допустимая ставка.
        player_money: Деньги игрока.

    Returns:
        Сообщение об ошибке или None.
    """
    if bid < min_bid:
        return f"Ставка должна быть не менее {min_bid}$"

    if bid > player_money:
        return (
            f"Недостаточно средств: ставка {bid}$, "
            f"доступно {player_money}$"
        )

    return None


def validate_build_action(
    property_id: str,
    player_properties: list[str],
    houses: int,
    has_hotel: bool,
    player_money: int,
    house_cost: int,
    hotel_cost: int,
    build_type: str = "house",
) -> Optional[str]:
    """
    Проверить действие строительства.

    Args:
        property_id: ID собственности.
        player_properties: Собственность игрока.
        houses: Текущее количество домов.
        has_hotel: Есть ли уже отель.
        player_money: Деньги игрока.
        house_cost: Стоимость дома.
        hotel_cost: Стоимость отеля.
        build_type: Тип стройки ("house" или "hotel").

    Returns:
        Сообщение об ошибке или None.
    """
    if property_id not in player_properties:
        return f"Вы не владеете собственностью '{property_id}'"

    if build_type == "house":
        if has_hotel:
            return "Отель уже построен"
        if houses >= 4:
            return "Достигнут максимум домов (4)"
        if player_money < house_cost:
            return (
                f"Недостаточно средств: нужно {house_cost}$, "
                f"доступно {player_money}$"
            )

    elif build_type == "hotel":
        if has_hotel:
            return "Отель уже построен"
        if houses < 4:
            return "Нужно 4 дома для постройки отеля"
        if player_money < hotel_cost:
            return (
                f"Недостаточно средств: нужно {hotel_cost}$, "
                f"доступно {player_money}$"
            )

    else:
        return f"Неизвестный тип строительства: {build_type}"

    return None


def validate_mortgage_action(
    property_id: str,
    player_properties: list[str],
    mortgaged: bool,
    houses: int,
    has_hotel: bool,
) -> Optional[str]:
    """
    Проверить действие залога.

    Args:
        property_id: ID собственности.
        player_properties: Собственность игрока.
        mortgaged: Уже в залоге.
        houses: Количество домов.
        has_hotel: Есть ли отель.

    Returns:
        Сообщение об ошибке или None.
    """
    if property_id not in player_properties:
        return f"Вы не владеете собственностью '{property_id}'"

    if mortgaged:
        return "Собственность уже в залоге"

    if houses > 0 or has_hotel:
        return "Сначала продайте все постройки"

    return None


def validate_unmortgage_action(
    property_id: str,
    player_properties: list[str],
    mortgaged: bool,
    player_money: int,
    unmortgage_cost: int,
) -> Optional[str]:
    """
    Проверить действие выкупа из залога.

    Args:
        property_id: ID собственности.
        player_properties: Собственность игрока.
        mortgaged: В залоге ли.
        player_money: Деньги игрока.
        unmortgage_cost: Стоимость выкупа.

    Returns:
        Сообщение об ошибке или None.
    """
    if property_id not in player_properties:
        return f"Вы не владеете собственностью '{property_id}'"

    if not mortgaged:
        return "Собственность не в залоге"

    if player_money < unmortgage_cost:
        return (
            f"Недостаточно средств: нужно {unmortgage_cost}$, "
            f"доступно {player_money}$"
        )

    return None


# ============================================================================
# ВАЛИДАЦИЯ ТОРГОВЛИ
# ============================================================================

def validate_trade_offer(
    from_player_id: UUID,
    to_player_id: UUID,
    offer_properties: list[str],
    request_properties: list[str],
    offer_cards: list[str],
    request_cards: list[str],
    request_money: int,
    loan_amount: int,
    loan_percent: Optional[int],
    from_properties: list[str],
    from_cards: list[str],
    from_money: int,
    to_properties: list[str],
    to_cards: list[str],
) -> Optional[str]:
    """
    Проверить торговое предложение.

    Args:
        from_player_id: ID инициатора.
        to_player_id: ID получателя.
        offer_properties: Предлагаемая инициатором собственность.
        request_properties: Запрашиваемая у получателя собственность.
        offer_cards: Предлагаемые инициатором карточки.
        request_cards: Запрашиваемые у получателя карточки.
        request_money: Запрашиваемые деньги.
        loan_amount: Сумма долга.
        loan_percent: Процент по долгу.
        from_properties: Собственность инициатора.
        from_cards: Карточки инициатора.
        from_money: Деньги инициатора.
        to_properties: Собственность получателя.
        to_cards: Карточки получателя.

    Returns:
        Сообщение об ошибке или None.
    """
    # Проверка на торговлю с самим собой
    if from_player_id == to_player_id:
        return "Нельзя торговать с самим собой"

    # Проверка, что предложение не пустое
    if (
        not offer_properties
        and not offer_cards
        and loan_amount == 0
        and not request_properties
        and not request_cards
        and request_money == 0
    ):
        return "Торговое предложение не может быть пустым"

    # Проверка владения предлагаемой собственностью
    for prop_id in offer_properties:
        if prop_id not in from_properties:
            return f"Вы не владеете собственностью '{prop_id}'"

    # Проверка владения предлагаемыми карточками
    for card_id in offer_cards:
        if card_id not in from_cards:
            return f"У вас нет карточки '{card_id}'"

    # Проверка существования запрашиваемой собственности
    for prop_id in request_properties:
        if prop_id not in to_properties:
            return f"Игрок не владеет собственностью '{prop_id}'"

    # Проверка существования запрашиваемых карточек
    for card_id in request_cards:
        if card_id not in to_cards:
            return f"У игрока нет карточки '{card_id}'"

    # Проверка долга
    if loan_amount > 0:
        if loan_amount > from_money:
            return (
                f"Недостаточно средств для займа: "
                f"нужно {loan_amount}$, доступно {from_money}$"
            )
        if loan_percent is not None:
            if not (MIN_LOAN_PERCENT <= loan_percent <= MAX_LOAN_PERCENT):
                return (
                    f"Процент по долгу должен быть от {MIN_LOAN_PERCENT} "
                    f"до {MAX_LOAN_PERCENT}"
                )

    # Проверка запрашиваемых денег
    if request_money > 0:
        if request_money > from_money:
            return (
                f"У игрока недостаточно средств: "
                f"запрошено {request_money}$, доступно {from_money}$"
            )

    return None


def validate_loan_percent(percent: int) -> Optional[str]:
    """
    Проверить процент по долгу.

    Args:
        percent: Процент (0-50).

    Returns:
        Сообщение об ошибке или None.
    """
    if not isinstance(percent, int):
        return "Процент должен быть целым числом"

    if not (MIN_LOAN_PERCENT <= percent <= MAX_LOAN_PERCENT):
        return (
            f"Процент должен быть от {MIN_LOAN_PERCENT} "
            f"до {MAX_LOAN_PERCENT}"
        )

    return None


# ============================================================================
# ВАЛИДАЦИЯ UUID
# ============================================================================

def validate_uuid(value: str) -> Optional[str]:
    """
    Проверить, является ли строка корректным UUID.

    Args:
        value: Проверяемая строка.

    Returns:
        Сообщение об ошибке или None.
    """
    if not value:
        return "UUID не может быть пустым"

    try:
        UUID(value)
    except ValueError:
        return f"Некорректный UUID: {value}"

    return None


# ============================================================================
# УНИВЕРСАЛЬНАЯ ВАЛИДАЦИЯ
# ============================================================================

def validate_required_field(value: Any, field_name: str) -> Optional[str]:
    """
    Проверить, что обязательное поле заполнено.

    Args:
        value: Значение поля.
        field_name: Название поля.

    Returns:
        Сообщение об ошибке или None.
    """
    if value is None:
        return f"Поле '{field_name}' обязательно"

    if isinstance(value, str) and not value.strip():
        return f"Поле '{field_name}' не может быть пустым"

    if isinstance(value, (list, dict)) and len(value) == 0:
        return f"Поле '{field_name}' не может быть пустым"

    return None


def validate_string_length(
    value: str,
    field_name: str,
    min_length: int = 1,
    max_length: int = 256,
) -> Optional[str]:
    """
    Проверить длину строки.

    Args:
        value: Строка.
        field_name: Название поля.
        min_length: Минимальная длина.
        max_length: Максимальная длина.

    Returns:
        Сообщение об ошибке или None.
    """
    if not isinstance(value, str):
        return f"Поле '{field_name}' должно быть строкой"

    if len(value) < min_length:
        return (
            f"Поле '{field_name}' должно быть не менее "
            f"{min_length} символов"
        )

    if len(value) > max_length:
        return (
            f"Поле '{field_name}' должно быть не более "
            f"{max_length} символов"
        )

    return None


def validate_integer_range(
    value: int,
    field_name: str,
    min_value: int,
    max_value: int,
) -> Optional[str]:
    """
    Проверить, что целое число входит в диапазон.

    Args:
        value: Число.
        field_name: Название поля.
        min_value: Минимальное значение.
        max_value: Максимальное значение.

    Returns:
        Сообщение об ошибке или None.
    """
    if not isinstance(value, int):
        return f"Поле '{field_name}' должно быть целым числом"

    if value < min_value:
        return (
            f"Поле '{field_name}' должно быть не менее {min_value}"
        )

    if value > max_value:
        return (
            f"Поле '{field_name}' должно быть не более {max_value}"
        )

    return None


def validate_enum_value(
    value: str,
    field_name: str,
    allowed_values: list[str],
) -> Optional[str]:
    """
    Проверить, что строковое значение входит в список допустимых.

    Args:
        value: Значение.
        field_name: Название поля.
        allowed_values: Список допустимых значений.

    Returns:
        Сообщение об ошибке или None.
    """
    if value not in allowed_values:
        return (
            f"Недопустимое значение '{value}' для поля '{field_name}'. "
            f"Допустимые: {', '.join(allowed_values)}"
        )

    return None