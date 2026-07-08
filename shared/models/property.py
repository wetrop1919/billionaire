"""
shared/models/property.py

Модели собственности для проекта "Миллиардер".

Содержит:
- Property — описание объекта собственности (улица, станция, utility)
- PropertyState — состояние собственности в конкретной игре
- PropertyGroup — группа собственности одного цвета

Используется игровым движком, менеджером аукционов и торговли,
а также для отображения информации на клиенте.

Python: 3.13+
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Self
from uuid import UUID

from shared.enums import PropertyType, ColorGroup


# ============================================================================
# МОДЕЛЬ СОБСТВЕННОСТИ (Property)
# ============================================================================

@dataclass(slots=True)
class Property:
    """
    Описание объекта собственности.

    Содержит статические характеристики: название, тип, стоимость,
    арендную плату, стоимость строительства. Эти данные загружаются
    из JSON-конфигурации и не меняются в процессе игры.

    Attributes:
        property_id: Уникальный строковый идентификатор (например, "sivka_burka").
        name: Название собственности.
        type: Тип (STREET, RAILROAD, UTILITY).
        price: Цена покупки.
        rent: Список арендной платы [базовая, 1 дом, 2 дома, 3 дома, 4 дома, отель].
        house_cost: Стоимость постройки одного дома.
        hotel_cost: Стоимость постройки отеля (сверх 4 домов).
        mortgage_value: Залоговая стоимость.
        color_group: Цветовая группа (только для улиц).
        position: Позиция на игровом поле (0-39).
    """

    property_id: str
    name: str
    type: PropertyType
    price: int
    rent: list[int]  # [base, 1h, 2h, 3h, 4h, hotel]
    house_cost: int
    hotel_cost: int
    mortgage_value: int
    color_group: Optional[ColorGroup] = None
    position: int = -1

    def __post_init__(self) -> None:
        """Валидация данных после инициализации."""
        if self.price < 0:
            raise ValueError(f"Цена не может быть отрицательной: {self.price}")
        if self.house_cost < 0:
            raise ValueError(f"Стоимость дома не может быть отрицательной: {self.house_cost}")
        if self.hotel_cost < 0:
            raise ValueError(f"Стоимость отеля не может быть отрицательной: {self.hotel_cost}")
        if self.mortgage_value < 0:
            raise ValueError(f"Залоговая стоимость не может быть отрицательной: {self.mortgage_value}")
        if len(self.rent) != 6:
            raise ValueError(
                f"Список арендной платы должен содержать 6 значений (получено {len(self.rent)})"
            )
        for i, r in enumerate(self.rent):
            if r < 0:
                raise ValueError(f"Арендная плата [{i}] не может быть отрицательной: {r}")

    # === СВОЙСТВА ===

    @property
    def is_street(self) -> bool:
        """Является ли собственность улицей."""
        return self.type == PropertyType.STREET

    @property
    def is_railroad(self) -> bool:
        """Является ли собственность станцией."""
        return self.type == PropertyType.RAILROAD

    @property
    def is_utility(self) -> bool:
        """Является ли собственность коммунальным предприятием."""
        return self.type == PropertyType.UTILITY

    @property
    def can_build_houses(self) -> bool:
        """Можно ли строить дома на этой собственности."""
        return self.type == PropertyType.STREET

    @property
    def max_houses(self) -> int:
        """Максимальное количество домов (4) перед отелем."""
        return 4

    @property
    def total_building_cost(self) -> int:
        """
        Полная стоимость застройки (4 дома + отель).

        Returns:
            Сумма: 4 * house_cost + hotel_cost.
        """
        return (4 * self.house_cost) + self.hotel_cost

    # === АРЕНДНАЯ ПЛАТА ===

    def get_rent(self, houses: int = 0, has_hotel: bool = False) -> int:
        """
        Получить арендную плату в зависимости от уровня застройки.

        Args:
            houses: Количество домов (0-4).
            has_hotel: Есть ли отель.

        Returns:
            Размер арендной платы.

        Raises:
            ValueError: Если параметры застройки некорректны.
        """
        if has_hotel:
            return self.rent[5]  # Отель — индекс 5

        if not (0 <= houses <= 4):
            raise ValueError(f"Количество домов должно быть 0-4: {houses}")

        return self.rent[houses]

    def get_railroad_rent(self, railroads_owned: int) -> int:
        """
        Получить арендную плату для станции.

        Зависит от количества станций у владельца:
        1 станция = 25, 2 = 50, 3 = 100, 4 = 200.

        Args:
            railroads_owned: Количество станций у владельца.

        Returns:
            Размер арендной платы.

        Raises:
            ValueError: Если не является станцией.
        """
        if self.type != PropertyType.RAILROAD:
            raise ValueError(f"{self.name} не является станцией")

        multipliers = {1: 25, 2: 50, 3: 100, 4: 200}
        return multipliers.get(railroads_owned, 25)

    def get_utility_rent(self, dice_total: int, utilities_owned: int) -> int:
        """
        Получить арендную плату для коммунального предприятия.

        1 предприятие = 4x сумма кубиков
        2 предприятия = 10x сумма кубиков

        Args:
            dice_total: Сумма значений на кубиках.
            utilities_owned: Количество коммунальных предприятий у владельца.

        Returns:
            Размер арендной платы.

        Raises:
            ValueError: Если не является коммунальным предприятием.
        """
        if self.type != PropertyType.UTILITY:
            raise ValueError(f"{self.name} не является коммунальным предприятием")

        multiplier = 10 if utilities_owned >= 2 else 4
        return dice_total * multiplier

    # === СЕРИАЛИЗАЦИЯ ===

    def to_dict(self) -> dict:
        """
        Сериализация собственности в словарь.

        Returns:
            Словарь со всеми характеристиками собственности.
        """
        return {
            "property_id": self.property_id,
            "name": self.name,
            "type": self.type.value,
            "price": self.price,
            "rent": self.rent,
            "house_cost": self.house_cost,
            "hotel_cost": self.hotel_cost,
            "mortgage_value": self.mortgage_value,
            "color_group": self.color_group.value if self.color_group else None,
            "position": self.position,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Property:
        """
        Создать собственность из словаря (из JSON-конфигурации).

        Args:
            data: Словарь с данными собственности.

        Returns:
            Новый экземпляр Property.
        """
        color_group = None
        if data.get("color_group"):
            color_group = ColorGroup(data["color_group"])

        return cls(
            property_id=data["property_id"],
            name=data["name"],
            type=PropertyType(data["type"]),
            price=data["price"],
            rent=data["rent"],
            house_cost=data["house_cost"],
            hotel_cost=data["hotel_cost"],
            mortgage_value=data["mortgage_value"],
            color_group=color_group,
            position=data.get("position", -1),
        )

    def __repr__(self) -> str:
        return (
            f"Property(id='{self.property_id}', name='{self.name}', "
            f"type={self.type.value}, price={self.price}$)"
        )


# ============================================================================
# СОСТОЯНИЕ СОБСТВЕННОСТИ В ИГРЕ (PropertyState)
# ============================================================================

@dataclass(slots=True)
class PropertyState:
    """
    Состояние собственности в конкретной игре.

    Отслеживает владельца, уровень застройки и статус залога.
    Создаётся для каждого объекта собственности при старте игры.

    Attributes:
        property_id: Ссылка на идентификатор собственности.
        owner_id: ID игрока-владельца (None — ничья).
        houses: Количество построенных домов (0-4).
        has_hotel: Построен ли отель.
        mortgaged: Находится ли в залоге.
    """

    property_id: str
    owner_id: Optional[UUID] = None
    houses: int = 0
    has_hotel: bool = False
    mortgaged: bool = False

    def __post_init__(self) -> None:
        """Валидация после инициализации."""
        if self.houses < 0 or self.houses > 4:
            raise ValueError(f"Количество домов должно быть 0-4: {self.houses}")
        if self.has_hotel and self.houses < 4:
            raise ValueError("Отель не может быть построен без 4 домов")

    # === СВОЙСТВА ===

    @property
    def is_owned(self) -> bool:
        """Принадлежит ли собственность кому-либо."""
        return self.owner_id is not None

    @property
    def is_unowned(self) -> bool:
        """Свободна ли собственность."""
        return self.owner_id is None

    @property
    def can_collect_rent(self) -> bool:
        """Можно ли собирать арендную плату (не в залоге)."""
        return self.is_owned and not self.mortgaged

    @property
    def building_level(self) -> int:
        """
        Уровень застройки (0-5).

        Returns:
            0 = нет построек, 1-4 = дома, 5 = отель.
        """
        if self.has_hotel:
            return 5
        return self.houses

    @property
    def total_houses(self) -> int:
        """
        Общее количество единиц жилья (домов).

        Отель считается как 5 единиц (4 дома + отель).
        """
        if self.has_hotel:
            return 5
        return self.houses

    # === ДЕЙСТВИЯ ===

    def assign_owner(self, player_id: UUID) -> None:
        """
        Назначить владельца.

        Args:
            player_id: ID игрока-покупателя.

        Raises:
            ValueError: Если собственность уже имеет владельца.
        """
        if self.is_owned:
            raise ValueError(
                f"Собственность '{self.property_id}' уже принадлежит игроку {self.owner_id}"
            )
        self.owner_id = player_id

    def remove_owner(self) -> None:
        """Убрать владельца (возврат в банк при банкротстве)."""
        self.owner_id = None
        self.houses = 0
        self.has_hotel = False
        self.mortgaged = False

    def build_house(self) -> None:
        """
        Построить один дом.

        Raises:
            ValueError: Если уже есть отель или достигнут максимум домов.
        """
        if self.has_hotel:
            raise ValueError(f"На '{self.property_id}' уже построен отель")
        if self.houses >= 4:
            raise ValueError(f"На '{self.property_id}' уже 4 дома (максимум)")
        if self.mortgaged:
            raise ValueError(f"'{self.property_id}' в залоге — строительство невозможно")
        self.houses += 1

    def build_hotel(self) -> None:
        """
        Построить отель (заменяет 4 дома).

        Raises:
            ValueError: Если недостаточно домов или уже есть отель.
        """
        if self.has_hotel:
            raise ValueError(f"На '{self.property_id}' уже есть отель")
        if self.houses < 4:
            raise ValueError(
                f"Для постройки отеля на '{self.property_id}' нужно 4 дома (сейчас {self.houses})"
            )
        if self.mortgaged:
            raise ValueError(f"'{self.property_id}' в залоге — строительство невозможно")
        self.houses = 0
        self.has_hotel = True

    def mortgage(self) -> None:
        """
        Заложить собственность.

        Raises:
            ValueError: Если уже в залоге или есть постройки.
        """
        if self.mortgaged:
            raise ValueError(f"'{self.property_id}' уже в залоге")
        if self.houses > 0 or self.has_hotel:
            raise ValueError(
                f"Нельзя заложить '{self.property_id}': сначала продайте постройки"
            )
        self.mortgaged = True

    def unmortgage(self) -> None:
        """
        Выкупить из залога.

        Raises:
            ValueError: Если не в залоге.
        """
        if not self.mortgaged:
            raise ValueError(f"'{self.property_id}' не в залоге")
        self.mortgaged = False

    def sell_all_buildings(self) -> tuple[int, int]:
        """
        Продать все постройки (дома и отель) за полцены.

        Returns:
            Кортеж (количество проданных домов, был ли отель).
        """
        houses_sold = self.houses
        had_hotel = self.has_hotel
        self.houses = 0
        self.has_hotel = False
        return (houses_sold, had_hotel)

    # === СЕРИАЛИЗАЦИЯ ===

    def to_dict(self) -> dict:
        """
        Сериализация состояния в словарь.

        Returns:
            Словарь с состоянием собственности.
        """
        return {
            "property_id": self.property_id,
            "owner_id": str(self.owner_id) if self.owner_id else None,
            "houses": self.houses,
            "has_hotel": self.has_hotel,
            "mortgaged": self.mortgaged,
            "building_level": self.building_level,
        }

    @classmethod
    def from_dict(cls, data: dict) -> PropertyState:
        """
        Создать состояние из словаря.

        Args:
            data: Словарь с данными состояния.

        Returns:
            Новый экземпляр PropertyState.
        """
        owner_id = None
        if data.get("owner_id"):
            owner_id = UUID(data["owner_id"])

        return cls(
            property_id=data["property_id"],
            owner_id=owner_id,
            houses=data.get("houses", 0),
            has_hotel=data.get("has_hotel", False),
            mortgaged=data.get("mortgaged", False),
        )

    def __repr__(self) -> str:
        owner = str(self.owner_id)[:8] if self.owner_id else "bank"
        status = ""
        if self.mortgaged:
            status = " [ЗАЛОГ]"
        elif self.has_hotel:
            status = " [ОТЕЛЬ]"
        elif self.houses > 0:
            status = f" [{self.houses} дом(а)]"
        return (
            f"PropertyState('{self.property_id}', owner={owner}{status})"
        )


# ============================================================================
# ГРУППА СОБСТВЕННОСТИ (PropertyGroup)
# ============================================================================

@dataclass(slots=True)
class PropertyGroup:
    """
    Группа собственности одного цвета.

    Используется для проверки монополии (владение всей группой)
    и расчёта аренды для станций и коммунальных предприятий.

    Attributes:
        group_id: Идентификатор группы (цвет или "railroad"/"utility").
        property_ids: Список идентификаторов собственности в группе.
        owner_id: ID владельца всей группы (None — нет монополии).
    """

    group_id: str
    property_ids: list[str]
    owner_id: Optional[UUID] = None

    @property
    def size(self) -> int:
        """Количество собственности в группе."""
        return len(self.property_ids)

    def is_monopoly(self, owner_id: UUID) -> bool:
        """
        Проверить, владеет ли игрок всей группой (монополия).

        Args:
            owner_id: ID игрока.

        Returns:
            True, если игрок владеет всей группой.
        """
        return self.owner_id == owner_id

    def update_ownership(
        self,
        property_states: dict[str, PropertyState],
    ) -> None:
        """
        Обновить состояние монополии на основе состояний собственности.

        Если все объекты в группе принадлежат одному игроку,
        устанавливает его как владельца группы.

        Args:
            property_states: Словарь {property_id: PropertyState}.
        """
        owners: set[UUID] = set()
        for pid in self.property_ids:
            state = property_states.get(pid)
            if state and state.owner_id is not None:
                owners.add(state.owner_id)
            else:
                # Есть некупленная собственность — монополии нет
                self.owner_id = None
                return

        if len(owners) == 1:
            self.owner_id = owners.pop()
        else:
            self.owner_id = None

    def to_dict(self) -> dict:
        """
        Сериализация группы в словарь.

        Returns:
            Словарь с данными группы.
        """
        return {
            "group_id": self.group_id,
            "property_ids": self.property_ids,
            "owner_id": str(self.owner_id) if self.owner_id else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> PropertyGroup:
        """
        Создать группу из словаря.

        Args:
            data: Словарь с данными группы.

        Returns:
            Новый экземпляр PropertyGroup.
        """
        owner_id = None
        if data.get("owner_id"):
            owner_id = UUID(data["owner_id"])

        return cls(
            group_id=data["group_id"],
            property_ids=data["property_ids"],
            owner_id=owner_id,
        )

    def __repr__(self) -> str:
        owner = str(self.owner_id)[:8] if self.owner_id else "none"
        return f"PropertyGroup({self.group_id}, {self.size} properties, owner={owner})"