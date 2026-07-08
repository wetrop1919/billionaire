"""
shared/card_actions.py

Модуль обработки действий карточек "Шанс" и "Фонд".

Содержит функции для выполнения действий, указанных на карточках:
- Денежные операции (получить/заплатить)
- Перемещение (на клетку, на N шагов, в тюрьму, на Веранду)
- Освобождение из тюрьмы
- Сбор/выплата денег с каждого игрока
- Ремонт собственности

Вся бизнес-логика вынесена из моделей в этот модуль.
Не содержит прямых зависимостей от GameEngine.

Python: 3.13+
"""

from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from shared.constants import (
    JAIL_CELL_ID,
    BOARD_CELLS_COUNT,
    JAIL_FINE,
    VERANDA_EXIT_COST,
)
from shared.enums import CardActionType, CardType
from shared.models.card import Card
from shared.models.property import PropertyState
from shared.models.position import BoardPosition


# ============================================================================
# РЕЗУЛЬТАТ ДЕЙСТВИЯ КАРТОЧКИ
# ============================================================================

class CardActionResult:
    """
    Результат выполнения действия карточки.

    Содержит все изменения, которые должны быть применены
    к состоянию игры после выполнения карточки.

    Attributes:
        money_change: Изменение денег игрока (положительное = доход).
        move_to_cell: Переместить на указанную клетку.
        move_steps: Переместить на N шагов.
        go_to_jail: Отправить в тюрьму.
        go_to_veranda: Отправить на Веранду.
        leave_veranda: Покинуть Веранду бесплатно.
        get_out_of_jail: Освободить из тюрьмы.
        collect_from_each: Собрать сумму с каждого игрока.
        pay_to_each: Заплатить сумму каждому игроку.
        repair_cost_per_house: Стоимость ремонта за дом.
        repair_cost_per_hotel: Стоимость ремонта за отель.
        message: Сообщение для игрока.
        keep_card: Оставить ли карточку у игрока.
    """

    __slots__ = (
        "money_change",
        "move_to_cell",
        "move_steps",
        "go_to_jail",
        "go_to_veranda",
        "leave_veranda",
        "get_out_of_jail",
        "collect_from_each",
        "pay_to_each",
        "repair_cost_per_house",
        "repair_cost_per_hotel",
        "message",
        "keep_card",
    )

    def __init__(self, message: str = "") -> None:
        self.money_change: int = 0
        self.move_to_cell: Optional[int] = None
        self.move_steps: Optional[int] = None
        self.go_to_jail: bool = False
        self.go_to_veranda: bool = False
        self.leave_veranda: bool = False
        self.get_out_of_jail: bool = False
        self.collect_from_each: Optional[int] = None
        self.pay_to_each: Optional[int] = None
        self.repair_cost_per_house: Optional[int] = None
        self.repair_cost_per_hotel: Optional[int] = None
        self.message: str = message
        self.keep_card: bool = False

    @property
    def has_money_change(self) -> bool:
        """Есть ли изменение денег."""
        return self.money_change != 0

    @property
    def has_movement(self) -> bool:
        """Требуется ли перемещение."""
        return (
            self.move_to_cell is not None
            or self.move_steps is not None
            or self.go_to_jail
            or self.go_to_veranda
        )

    @property
    def has_collection(self) -> bool:
        """Требуется ли сбор с других игроков."""
        return self.collect_from_each is not None

    @property
    def has_payment_to_players(self) -> bool:
        """Требуется ли выплата другим игрокам."""
        return self.pay_to_each is not None

    @property
    def has_repair(self) -> bool:
        """Требуется ли ремонт."""
        return (
            self.repair_cost_per_house is not None
            and self.repair_cost_per_hotel is not None
        )

    @property
    def is_get_out_of_jail_card(self) -> bool:
        """Является ли карточкой освобождения из тюрьмы."""
        return self.get_out_of_jail and self.keep_card

    def to_dict(self) -> dict[str, Any]:
        """Сериализация результата в словарь."""
        return {
            "money_change": self.money_change,
            "move_to_cell": self.move_to_cell,
            "move_steps": self.move_steps,
            "go_to_jail": self.go_to_jail,
            "go_to_veranda": self.go_to_veranda,
            "leave_veranda": self.leave_veranda,
            "get_out_of_jail": self.get_out_of_jail,
            "collect_from_each": self.collect_from_each,
            "pay_to_each": self.pay_to_each,
            "repair_cost_per_house": self.repair_cost_per_house,
            "repair_cost_per_hotel": self.repair_cost_per_hotel,
            "message": self.message,
            "keep_card": self.keep_card,
        }

    def __repr__(self) -> str:
        parts = []
        if self.has_money_change:
            parts.append(f"money={self.money_change:+d}$")
        if self.has_movement:
            parts.append("move")
        if self.go_to_jail:
            parts.append("jail")
        if self.get_out_of_jail:
            parts.append("free")
        return f"CardActionResult({' | '.join(parts) if parts else 'none'})"


# ============================================================================
# ОБРАБОТКА ДЕЙСТВИЙ КАРТОЧЕК
# ============================================================================

def process_card(card: Card) -> CardActionResult:
    """
    Обработать действие карточки и вернуть результат.

    Не изменяет состояние игры напрямую — возвращает
    CardActionResult, который должен быть применён игровым движком.

    Args:
        card: Карточка для обработки.

    Returns:
        Результат действия карточки.

    Raises:
        ValueError: Если тип действия не поддерживается.
    """
    result = CardActionResult(message=card.description)

    # Определяем, нужно ли оставить карточку у игрока
    result.keep_card = card.keep_after_use

    match card.action_type:
        case CardActionType.RECEIVE_MONEY:
            _handle_receive_money(card, result)

        case CardActionType.PAY_MONEY:
            _handle_pay_money(card, result)

        case CardActionType.MOVE_TO:
            _handle_move_to(card, result)

        case CardActionType.MOVE_STEPS:
            _handle_move_steps(card, result)

        case CardActionType.GO_TO_JAIL:
            _handle_go_to_jail(result)

        case CardActionType.GET_OUT_OF_JAIL:
            _handle_get_out_of_jail(result)

        case CardActionType.GO_TO_VERANDA:
            _handle_go_to_veranda(result)

        case CardActionType.LEAVE_VERANDA:
            _handle_leave_veranda(result)

        case CardActionType.COLLECT_FROM_PLAYERS:
            _handle_collect_from_players(card, result)

        case CardActionType.PAY_TO_PLAYERS:
            _handle_pay_to_players(card, result)

        case CardActionType.REPAIR_PROPERTY:
            _handle_repair_property(card, result)

        case CardActionType.BIRTHDAY:
            _handle_birthday(card, result)

        case CardActionType.CUSTOM:
            _handle_custom(card, result)

        case _:
            raise ValueError(
                f"Неизвестный тип действия карточки: {card.action_type}"
            )

    return result


# ============================================================================
# ОБРАБОТЧИКИ КОНКРЕТНЫХ ДЕЙСТВИЙ
# ============================================================================

def _handle_receive_money(card: Card, result: CardActionResult) -> None:
    """Обработка: получить деньги."""
    amount = card.action_data.get("amount", 0)
    result.money_change = amount
    result.message = f"Вы получили {amount}$: {card.description}"


def _handle_pay_money(card: Card, result: CardActionResult) -> None:
    """Обработка: заплатить деньги."""
    amount = card.action_data.get("amount", 0)
    result.money_change = -amount
    result.message = f"Вы заплатили {amount}$: {card.description}"


def _handle_move_to(card: Card, result: CardActionResult) -> None:
    """Обработка: переместиться на указанную клетку."""
    cell_id = card.action_data.get("cell_id")
    if cell_id is None:
        raise ValueError(f"Карточка '{card.card_id}': не указан cell_id")
    result.move_to_cell = cell_id
    result.message = f"Переместитесь на клетку {cell_id}: {card.description}"


def _handle_move_steps(card: Card, result: CardActionResult) -> None:
    """Обработка: переместиться на N шагов."""
    steps = card.action_data.get("steps", 0)
    result.move_steps = steps
    direction = "вперёд" if steps >= 0 else "назад"
    result.message = f"Переместитесь на {abs(steps)} шагов {direction}: {card.description}"


def _handle_go_to_jail(result: CardActionResult) -> None:
    """Обработка: отправиться в тюрьму."""
    result.go_to_jail = True
    result.move_to_cell = JAIL_CELL_ID
    result.message = "Отправляйтесь в тюрьму!"


def _handle_get_out_of_jail(result: CardActionResult) -> None:
    """Обработка: освободиться из тюрьмы."""
    result.get_out_of_jail = True
    result.keep_card = True  # Карточка остаётся у игрока
    result.message = "Карточка освобождения из тюрьмы. Можно использовать или продать."


def _handle_go_to_veranda(result: CardActionResult) -> None:
    """Обработка: отправиться на Веранду."""
    result.go_to_veranda = True
    result.message = f"Вы попали на Веранду! Для выхода нужно заплатить {VERANDA_EXIT_COST}$."


def _handle_leave_veranda(result: CardActionResult) -> None:
    """Обработка: покинуть Веранду бесплатно."""
    result.leave_veranda = True
    result.message = "Вы покидаете Веранду бесплатно!"


def _handle_collect_from_players(card: Card, result: CardActionResult) -> None:
    """Обработка: собрать деньги с каждого игрока."""
    amount = card.action_data.get("amount_per_player", 0)
    result.collect_from_each = amount
    result.message = f"Получите {amount}$ с каждого игрока: {card.description}"


def _handle_pay_to_players(card: Card, result: CardActionResult) -> None:
    """Обработка: заплатить каждому игроку."""
    amount = card.action_data.get("amount_per_player", 0)
    result.pay_to_each = amount
    result.message = f"Заплатите {amount}$ каждому игроку: {card.description}"


def _handle_repair_property(card: Card, result: CardActionResult) -> None:
    """Обработка: ремонт собственности."""
    cost_per_house = card.action_data.get("cost_per_house", 0)
    cost_per_hotel = card.action_data.get("cost_per_hotel", 0)
    result.repair_cost_per_house = cost_per_house
    result.repair_cost_per_hotel = cost_per_hotel
    result.message = (
        f"Ремонт: {cost_per_house}$ за дом, "
        f"{cost_per_hotel}$ за отель. {card.description}"
    )


def _handle_birthday(card: Card, result: CardActionResult) -> None:
    """Обработка: день рождения (собрать с каждого игроков)."""
    amount = card.action_data.get("amount_per_player", 10)
    result.collect_from_each = amount
    result.message = f"У вас день рождения! Получите {amount}$ с каждого игрока."


def _handle_custom(card: Card, result: CardActionResult) -> None:
    """
    Обработка: особое действие.

    Интерпретирует action_data как полный набор параметров
    для CardActionResult.
    """
    data = card.action_data

    if "money_change" in data:
        result.money_change = data["money_change"]
    if "move_to_cell" in data:
        result.move_to_cell = data["move_to_cell"]
    if "move_steps" in data:
        result.move_steps = data["move_steps"]
    if "go_to_jail" in data:
        result.go_to_jail = data["go_to_jail"]
    if "go_to_veranda" in data:
        result.go_to_veranda = data["go_to_veranda"]
    if "collect_from_each" in data:
        result.collect_from_each = data["collect_from_each"]
    if "pay_to_each" in data:
        result.pay_to_each = data["pay_to_each"]
    if "keep_card" in data:
        result.keep_card = data["keep_card"]

    result.message = card.description


# ============================================================================
# РАСЧЁТ СТОИМОСТИ РЕМОНТА
# ============================================================================

def calculate_repair_cost(
    repair_cost_per_house: int,
    repair_cost_per_hotel: int,
    player_properties: list[PropertyState],
) -> int:
    """
    Рассчитать общую стоимость ремонта для игрока.

    Args:
        repair_cost_per_house: Стоимость ремонта за один дом.
        repair_cost_per_hotel: Стоимость ремонта за один отель.
        player_properties: Список состояний собственности игрока.

    Returns:
        Общая стоимость ремонта.
    """
    total = 0

    for prop_state in player_properties:
        if prop_state.mortgaged:
            continue
        total += prop_state.houses * repair_cost_per_house
        if prop_state.has_hotel:
            total += repair_cost_per_hotel

    return total


# ============================================================================
# ПРОВЕРКА ИСПОЛЬЗОВАНИЯ КАРТОЧКИ
# ============================================================================

def can_use_card(
    card: Card,
    is_in_jail: bool,
    is_on_veranda: bool,
    player_money: int,
    player_properties: Optional[list[PropertyState]] = None,
) -> tuple[bool, Optional[str]]:
    """
    Проверить, может ли игрок использовать карточку.

    Args:
        card: Карточка.
        is_in_jail: Находится ли игрок в тюрьме.
        is_on_veranda: Находится ли игрок на Веранде.
        player_money: Деньги игрока.
        player_properties: Собственность игрока (для ремонта).

    Returns:
        Кортеж (можно_ли, причина_отказа).
    """
    # Карточку освобождения можно использовать только в тюрьме
    if card.action_type == CardActionType.GET_OUT_OF_JAIL:
        if not is_in_jail:
            return False, "Вы не в тюрьме"
        return True, None

    # Карточку выхода с Веранды — только на Веранде
    if card.action_type == CardActionType.LEAVE_VERANDA:
        if not is_on_veranda:
            return False, "Вы не на Веранде"
        return True, None

    # Проверка платёжных карточек
    if card.action_type == CardActionType.PAY_MONEY:
        amount = card.action_data.get("amount", 0)
        if player_money < amount:
            return False, f"Недостаточно средств: нужно {amount}$, доступно {player_money}$"

    # Проверка ремонта
    if card.action_type == CardActionType.REPAIR_PROPERTY:
        if player_properties is None:
            return False, "Нет данных о собственности"
        cost_per_house = card.action_data.get("cost_per_house", 0)
        cost_per_hotel = card.action_data.get("cost_per_hotel", 0)
        total = calculate_repair_cost(cost_per_house, cost_per_hotel, player_properties)
        if player_money < total:
            return False, f"Недостаточно средств на ремонт: нужно {total}$, доступно {player_money}$"

    return True, None


# ============================================================================
# ПОЛУЧЕНИЕ КАРТОЧЕК ДЛЯ КОЛОДЫ
# ============================================================================

def filter_cards_by_type(
    cards: list[Card],
    card_type: CardType,
) -> list[Card]:
    """
    Отфильтровать карточки по типу.

    Args:
        cards: Список карточек.
        card_type: Тип для фильтрации.

    Returns:
        Отфильтрованный список.
    """
    return [card for card in cards if card.card_type == card_type]


def get_keepable_cards(cards: list[Card]) -> list[Card]:
    """
    Получить карточки, которые остаются у игрока после использования.

    Args:
        cards: Список всех карточек.

    Returns:
        Список карточек с keep_after_use=True.
    """
    return [card for card in cards if card.keep_after_use]


def get_sellable_cards(cards: list[Card]) -> list[Card]:
    """
    Получить карточки, которые можно продавать.

    Args:
        cards: Список всех карточек.

    Returns:
        Список карточек с can_be_sold=True.
    """
    return [card for card in cards if card.can_be_sold]