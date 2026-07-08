"""
shared/property_utils.py

Утилиты для работы с собственностью в игре "Миллиардер".

Содержит функции для:
- Расчёта арендной платы
- Проверки возможности строительства
- Расчёта стоимости строительства и залога
- Валидации операций с собственностью

Вся бизнес-логика вынесена из моделей в этот модуль.

Python: 3.13+
"""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from shared.constants import (
    MAX_HOUSES_PER_PROPERTY,
    HOTEL_REQUIRES_HOUSES,
    MORTGAGE_UNMORTGAGE_RATIO,
    AUCTION_START_PRICE_RATIO,
)
from shared.models.property import Property, PropertyState, PropertyGroup


# ============================================================================
# РАСЧЁТ АРЕНДНОЙ ПЛАТЫ
# ============================================================================

def calculate_rent(
    property_def: Property,
    property_state: PropertyState,
    dice_total: int = 0,
    railroads_owned: int = 0,
    utilities_owned: int = 0,
) -> int:
    """
    Рассчитать арендную плату для собственности.

    Учитывает:
    - Уровень застройки (дома/отель) для улиц
    - Количество станций для railroads
    - Сумму кубиков и количество utilities для коммунальных предприятий

    Args:
        property_def: Описание собственности (статическое).
        property_state: Состояние собственности в игре.
        dice_total: Сумма значений кубиков (для utilities).
        railroads_owned: Количество станций у владельца.
        utilities_owned: Количество utilities у владельца.

    Returns:
        Размер арендной платы. 0 если собственность в залоге.

    Raises:
        ValueError: Если тип собственности не поддерживается.
    """
    # Заложенная собственность не приносит аренду
    if property_state.mortgaged:
        return 0

    if property_def.is_street:
        return property_def.get_rent(
            houses=property_state.houses,
            has_hotel=property_state.has_hotel,
        )

    if property_def.is_railroad:
        return property_def.get_railroad_rent(railroads_owned)

    if property_def.is_utility:
        return property_def.get_utility_rent(dice_total, utilities_owned)

    raise ValueError(f"Неизвестный тип собственности: {property_def.type}")


def calculate_rent_for_player(
    property_def: Property,
    property_state: PropertyState,
    player_properties: list[PropertyState],
    property_defs: dict[str, Property],
    dice_total: int = 0,
) -> int:
    """
    Рассчитать арендную плату с учётом другой собственности игрока.

    Автоматически определяет количество railroads и utilities
    у владельца для правильного расчёта аренды.

    Args:
        property_def: Описание собственности.
        property_state: Состояние собственности.
        player_properties: Вся собственность владельца.
        property_defs: Словарь {property_id: Property} всех собственностей.
        dice_total: Сумма кубиков (для utilities).

    Returns:
        Размер арендной платы.
    """
    if property_def.is_railroad:
        railroads_owned = sum(
            1 for ps in player_properties
            if property_defs[ps.property_id].is_railroad
        )
        return calculate_rent(
            property_def, property_state,
            railroads_owned=railroads_owned,
        )

    if property_def.is_utility:
        utilities_owned = sum(
            1 for ps in player_properties
            if property_defs[ps.property_id].is_utility
        )
        return calculate_rent(
            property_def, property_state,
            dice_total=dice_total,
            utilities_owned=utilities_owned,
        )

    return calculate_rent(property_def, property_state)


# ============================================================================
# ПРОВЕРКИ ВОЗМОЖНОСТИ СТРОИТЕЛЬСТВА
# ============================================================================

def can_build_house(
    property_def: Property,
    property_state: PropertyState,
    player_money: int,
) -> tuple[bool, Optional[str]]:
    """
    Проверить, можно ли построить дом.

    Args:
        property_def: Описание собственности.
        property_state: Состояние собственности.
        player_money: Деньги игрока.

    Returns:
        Кортеж (можно_ли, причина_отказа).
    """
    if not property_def.can_build_houses:
        return False, "Нельзя строить дома на этом типе собственности"

    if property_state.mortgaged:
        return False, "Собственность в залоге"

    if property_state.has_hotel:
        return False, "Отель уже построен"

    if property_state.houses >= MAX_HOUSES_PER_PROPERTY:
        return False, f"Достигнут максимум домов ({MAX_HOUSES_PER_PROPERTY})"

    if player_money < property_def.house_cost:
        return False, (
            f"Недостаточно средств: нужно {property_def.house_cost}$, "
            f"доступно {player_money}$"
        )

    return True, None


def can_build_hotel(
    property_def: Property,
    property_state: PropertyState,
    player_money: int,
) -> tuple[bool, Optional[str]]:
    """
    Проверить, можно ли построить отель.

    Args:
        property_def: Описание собственности.
        property_state: Состояние собственности.
        player_money: Деньги игрока.

    Returns:
        Кортеж (можно_ли, причина_отказа).
    """
    if not property_def.can_build_houses:
        return False, "Нельзя строить отели на этом типе собственности"

    if property_state.mortgaged:
        return False, "Собственность в залоге"

    if property_state.has_hotel:
        return False, "Отель уже построен"

    if property_state.houses < HOTEL_REQUIRES_HOUSES:
        return False, (
            f"Нужно {HOTEL_REQUIRES_HOUSES} дома для постройки отеля "
            f"(сейчас {property_state.houses})"
        )

    if player_money < property_def.hotel_cost:
        return False, (
            f"Недостаточно средств: нужно {property_def.hotel_cost}$, "
            f"доступно {player_money}$"
        )

    return True, None


def can_sell_building(
    property_state: PropertyState,
) -> tuple[bool, Optional[str]]:
    """
    Проверить, можно ли продать постройку.

    Args:
        property_state: Состояние собственности.

    Returns:
        Кортеж (можно_ли, причина_отказа).
    """
    if property_state.mortgaged:
        return False, "Собственность в залоге"

    if property_state.houses == 0 and not property_state.has_hotel:
        return False, "Нет построек для продажи"

    return True, None


# ============================================================================
# РАСЧЁТ СТОИМОСТИ
# ============================================================================

def calculate_total_building_cost(
    property_def: Property,
    target_houses: int,
    build_hotel: bool = False,
) -> int:
    """
    Рассчитать общую стоимость строительства до целевого уровня.

    Args:
        property_def: Описание собственности.
        target_houses: Целевое количество домов (0-4).
        build_hotel: Нужно ли построить отель.

    Returns:
        Общая стоимость.

    Raises:
        ValueError: Если target_houses вне диапазона 0-4.
    """
    if not (0 <= target_houses <= MAX_HOUSES_PER_PROPERTY):
        raise ValueError(
            f"target_houses должен быть 0-{MAX_HOUSES_PER_PROPERTY}: {target_houses}"
        )

    total = target_houses * property_def.house_cost
    if build_hotel:
        total += property_def.hotel_cost

    return total


def calculate_sell_building_value(
    property_def: Property,
    property_state: PropertyState,
) -> int:
    """
    Рассчитать стоимость продажи построек (половина от цены строительства).

    Args:
        property_def: Описание собственности.
        property_state: Состояние собственности.

    Returns:
        Сумма, которую получит игрок при продаже всех построек.
    """
    total = 0

    # Продажа домов (полцены)
    if property_state.houses > 0:
        total += (property_state.houses * property_def.house_cost) // 2

    # Продажа отеля (полцены)
    if property_state.has_hotel:
        hotel_total = (MAX_HOUSES_PER_PROPERTY * property_def.house_cost
                       + property_def.hotel_cost) // 2
        total += hotel_total

    return total


def calculate_mortgage_value(property_price: int) -> int:
    """
    Рассчитать залоговую стоимость (половина цены).

    Args:
        property_price: Полная цена собственности.

    Returns:
        Залоговая стоимость.
    """
    return property_price // 2


def calculate_unmortgage_cost(mortgage_value: int) -> int:
    """
    Рассчитать стоимость выкупа из залога (залог + 10%).

    Args:
        mortgage_value: Залоговая стоимость.

    Returns:
        Стоимость выкупа (округление вверх).
    """
    extra = int(mortgage_value * (MORTGAGE_UNMORTGAGE_RATIO - 1.0))
    return mortgage_value + extra


def calculate_auction_start_price(property_price: int) -> int:
    """
    Рассчитать стартовую цену аукциона.

    Args:
        property_price: Полная цена собственности.

    Returns:
        Стартовая цена (50% от стоимости, округление вверх).
    """
    return int(property_price * AUCTION_START_PRICE_RATIO)


# ============================================================================
# ПРОВЕРКИ ВЛАДЕНИЯ
# ============================================================================

def check_monopoly(
    property_def: Property,
    property_groups: list[PropertyGroup],
    player_id: UUID,
) -> bool:
    """
    Проверить, имеет ли игрок монополию на цветовую группу.

    Args:
        property_def: Описание собственности.
        property_groups: Список всех групп собственности.
        player_id: ID игрока.

    Returns:
        True, если игрок владеет всей группой.
    """
    if property_def.color_group is None:
        return False

    for group in property_groups:
        if group.group_id == property_def.color_group.value:
            return group.is_monopoly(player_id)

    return False


def get_owner_railroads_count(
    owner_id: UUID,
    property_states: dict[str, PropertyState],
    property_defs: dict[str, Property],
) -> int:
    """
    Подсчитать количество станций у владельца.

    Args:
        owner_id: ID владельца.
        property_states: Словарь состояний всей собственности.
        property_defs: Словарь описаний всей собственности.

    Returns:
        Количество станций во владении.
    """
    count = 0
    for prop_id, state in property_states.items():
        if state.owner_id == owner_id:
            prop_def = property_defs.get(prop_id)
            if prop_def and prop_def.is_railroad:
                count += 1
    return count


def get_owner_utilities_count(
    owner_id: UUID,
    property_states: dict[str, PropertyState],
    property_defs: dict[str, Property],
) -> int:
    """
    Подсчитать количество коммунальных предприятий у владельца.

    Args:
        owner_id: ID владельца.
        property_states: Словарь состояний всей собственности.
        property_defs: Словарь описаний всей собственности.

    Returns:
        Количество utilities во владении.
    """
    count = 0
    for prop_id, state in property_states.items():
        if state.owner_id == owner_id:
            prop_def = property_defs.get(prop_id)
            if prop_def and prop_def.is_utility:
                count += 1
    return count


# ============================================================================
# ПРОВЕРКИ ДЛЯ ЗАЛОГА
# ============================================================================

def can_mortgage(
    property_state: PropertyState,
) -> tuple[bool, Optional[str]]:
    """
    Проверить, можно ли заложить собственность.

    Args:
        property_state: Состояние собственности.

    Returns:
        Кортеж (можно_ли, причина_отказа).
    """
    if property_state.mortgaged:
        return False, "Уже в залоге"

    if not property_state.is_owned:
        return False, "Собственность не принадлежит игроку"

    if property_state.houses > 0 or property_state.has_hotel:
        return False, "Сначала продайте все постройки"

    return True, None


def can_unmortgage(
    property_state: PropertyState,
    property_def: Property,
    player_money: int,
) -> tuple[bool, Optional[str]]:
    """
    Проверить, можно ли выкупить из залога.

    Args:
        property_state: Состояние собственности.
        property_def: Описание собственности.
        player_money: Деньги игрока.

    Returns:
        Кортеж (можно_ли, причина_отказа).
    """
    if not property_state.mortgaged:
        return False, "Не в залоге"

    cost = calculate_unmortgage_cost(property_def.mortgage_value)

    if player_money < cost:
        return False, (
            f"Недостаточно средств: нужно {cost}$, "
            f"доступно {player_money}$"
        )

    return True, None


# ============================================================================
# ГРУППИРОВКА СОБСТВЕННОСТИ
# ============================================================================

def group_properties_by_color(
    property_defs: dict[str, Property],
) -> list[PropertyGroup]:
    """
    Сгруппировать собственность по цветовым группам.

    Args:
        property_defs: Словарь {property_id: Property} всех собственностей.

    Returns:
        Список PropertyGroup.
    """
    groups: dict[str, list[str]] = {}

    for prop_id, prop_def in property_defs.items():
        if prop_def.color_group is not None:
            group_key = prop_def.color_group.value
            if group_key not in groups:
                groups[group_key] = []
            groups[group_key].append(prop_id)

    # Добавляем railroads
    railroad_ids = [
        pid for pid, pdef in property_defs.items()
        if pdef.is_railroad
    ]
    if railroad_ids:
        groups["railroad"] = railroad_ids

    # Добавляем utilities
    utility_ids = [
        pid for pid, pdef in property_defs.items()
        if pdef.is_utility
    ]
    if utility_ids:
        groups["utility"] = utility_ids

    return [
        PropertyGroup(group_id=key, property_ids=ids)
        for key, ids in groups.items()
    ]


def update_property_groups(
    groups: list[PropertyGroup],
    property_states: dict[str, PropertyState],
) -> None:
    """
    Обновить состояние монополии для всех групп.

    Args:
        groups: Список групп собственности.
        property_states: Словарь состояний всей собственности.
    """
    for group in groups:
        group.update_ownership(property_states)


# ============================================================================
# ВАЛИДАЦИЯ ДЕЙСТВИЙ
# ============================================================================

def validate_purchase(
    property_def: Property,
    property_state: PropertyState,
    player_money: int,
    player_id: UUID,
) -> Optional[str]:
    """
    Проверить, может ли игрок купить собственность.

    Args:
        property_def: Описание собственности.
        property_state: Состояние собственности.
        player_money: Деньги игрока.
        player_id: ID игрока.

    Returns:
        Сообщение об ошибке или None, если всё корректно.
    """
    if property_state.is_owned:
        return f"Собственность уже принадлежит игроку {property_state.owner_id}"

    if player_money < property_def.price:
        return (
            f"Недостаточно средств: нужно {property_def.price}$, "
            f"доступно {player_money}$"
        )

    return None


def validate_sell_building(
    property_def: Property,
    property_state: PropertyState,
    player_id: UUID,
) -> Optional[str]:
    """
    Проверить, может ли игрок продать постройки.

    Args:
        property_def: Описание собственности.
        property_state: Состояние собственности.
        player_id: ID игрока.

    Returns:
        Сообщение об ошибке или None, если всё корректно.
    """
    if property_state.owner_id != player_id:
        return "Вы не владеете этой собственностью"

    if property_state.mortgaged:
        return "Собственность в залоге"

    if property_state.houses == 0 and not property_state.has_hotel:
        return "Нет построек для продажи"

    return None


def validate_trade_property(
    property_id: str,
    from_player_id: UUID,
    to_player_id: UUID,
    property_states: dict[str, PropertyState],
) -> Optional[str]:
    """
    Проверить, можно ли передать собственность в сделке.

    Args:
        property_id: ID собственности.
        from_player_id: Текущий владелец.
        to_player_id: Новый владелец.
        property_states: Состояния всей собственности.

    Returns:
        Сообщение об ошибке или None.
    """
    state = property_states.get(property_id)
    if state is None:
        return f"Собственность '{property_id}' не существует"

    if state.owner_id != from_player_id:
        return f"Игрок {from_player_id} не владеет '{property_id}'"

    if state.mortgaged:
        return f"'{property_id}' в залоге — нельзя передать"

    return None