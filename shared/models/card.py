"""
shared/models/card.py

Модели карточек "Шанс" и "Фонд" для проекта "Миллиардер".

Содержит:
- Card — описание карточки (загружается из JSON-конфигурации)
- PlayerCard — карточка, принадлежащая игроку (которые можно продавать)
- CardDeck — колода карточек определённого типа

Карточки могут требовать немедленного выполнения действия
или сохраняться у игрока для использования позже (например,
карточка освобождения из тюрьмы).

Python: 3.13+
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Optional, Self
from uuid import UUID, uuid4

from shared.enums import CardType, CardActionType


# ============================================================================
# МОДЕЛЬ КАРТОЧКИ (Card)
# ============================================================================

@dataclass(slots=True)
class Card:
    """
    Описание карточки "Шанс" или "Фонд".

    Содержит статические характеристики: тип, текст, действие.
    Загружается из JSON-конфигурации и не меняется в процессе игры.

    Attributes:
        card_id: Уникальный строковый идентификатор (например, "chance_01").
        card_type: Тип карточки (CHANCE или FUND).
        title: Краткое название карточки.
        description: Полный текст карточки.
        action_type: Тип действия, выполняемого карточкой.
        action_data: Параметры действия (сумма, клетка, шаги и т.д.).
        can_be_sold: Можно ли продавать/передавать эту карточку.
        keep_after_use: Остаётся ли карточка у игрока после использования.
    """

    card_id: str
    card_type: CardType
    title: str
    description: str
    action_type: CardActionType
    action_data: dict = field(default_factory=dict)
    can_be_sold: bool = False
    keep_after_use: bool = False

    # === СВОЙСТВА ===

    @property
    def is_chance(self) -> bool:
        """Является ли карточка Шанс."""
        return self.card_type == CardType.CHANCE

    @property
    def is_fund(self) -> bool:
        """Является ли карточка Фонд."""
        return self.card_type == CardType.FUND

    @property
    def is_get_out_of_jail(self) -> bool:
        """Является ли карточкой освобождения из тюрьмы."""
        return self.action_type == CardActionType.GET_OUT_OF_JAIL

    @property
    def is_money_action(self) -> bool:
        """Связано ли действие с получением или выплатой денег."""
        return self.action_type in (
            CardActionType.RECEIVE_MONEY,
            CardActionType.PAY_MONEY,
            CardActionType.COLLECT_FROM_PLAYERS,
            CardActionType.PAY_TO_PLAYERS,
            CardActionType.BIRTHDAY,
        )

    @property
    def is_movement_action(self) -> bool:
        """Связано ли действие с перемещением."""
        return self.action_type in (
            CardActionType.MOVE_TO,
            CardActionType.MOVE_STEPS,
            CardActionType.GO_TO_JAIL,
            CardActionType.GO_TO_VERANDA,
        )

    @property
    def is_property_action(self) -> bool:
        """Связано ли действие с ремонтом/строительством."""
        return self.action_type == CardActionType.REPAIR_PROPERTY

    # === ПОЛУЧЕНИЕ ПАРАМЕТРОВ ДЕЙСТВИЯ ===

    def get_money_amount(self) -> int:
        """
        Получить денежную сумму из данных действия.

        Returns:
            Сумма денег (положительная для получения, отрицательная для выплаты).

        Raises:
            ValueError: Если действие не связано с деньгами.
        """
        if not self.is_money_action:
            raise ValueError(f"Карточка '{self.card_id}' не связана с денежным действием")
        return self.action_data.get("amount", 0)

    def get_target_cell(self) -> int | None:
        """
        Получить ID целевой клетки для перемещения.

        Returns:
            ID клетки или None.
        """
        return self.action_data.get("cell_id")

    def get_steps(self) -> int | None:
        """
        Получить количество шагов для перемещения.

        Returns:
            Количество шагов (может быть отрицательным для движения назад).
        """
        return self.action_data.get("steps")

    def get_repair_cost_per_house(self) -> int | None:
        """
        Получить стоимость ремонта за один дом.

        Returns:
            Стоимость ремонта за дом.
        """
        return self.action_data.get("cost_per_house")

    def get_repair_cost_per_hotel(self) -> int | None:
        """
        Получить стоимость ремонта за отель.

        Returns:
            Стоимость ремонта за отель.
        """
        return self.action_data.get("cost_per_hotel")

    def get_collect_amount_per_player(self) -> int | None:
        """
        Получить сумму, собираемую с каждого игрока.

        Returns:
            Сумма сбора с одного игрока.
        """
        return self.action_data.get("amount_per_player")

    # === СЕРИАЛИЗАЦИЯ ===

    def to_dict(self) -> dict:
        """
        Сериализация карточки в словарь.

        Returns:
            Словарь с данными карточки.
        """
        return {
            "card_id": self.card_id,
            "card_type": self.card_type.value,
            "title": self.title,
            "description": self.description,
            "action_type": self.action_type.value,
            "action_data": self.action_data,
            "can_be_sold": self.can_be_sold,
            "keep_after_use": self.keep_after_use,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Card:
        """
        Создать карточку из словаря (из JSON-конфигурации).

        Args:
            data: Словарь с данными карточки.

        Returns:
            Новый экземпляр Card.
        """
        return cls(
            card_id=data["card_id"],
            card_type=CardType(data["card_type"]),
            title=data["title"],
            description=data["description"],
            action_type=CardActionType(data["action_type"]),
            action_data=data.get("action_data", {}),
            can_be_sold=data.get("can_be_sold", False),
            keep_after_use=data.get("keep_after_use", False),
        )

    def __repr__(self) -> str:
        return (
            f"Card(id='{self.card_id}', type={self.card_type.value}, "
            f"title='{self.title}', action={self.action_type.value})"
        )


# ============================================================================
# КАРТОЧКА ИГРОКА (PlayerCard)
# ============================================================================

@dataclass(slots=True)
class PlayerCard:
    """
    Карточка, принадлежащая игроку.

    Некоторые карточки могут быть сохранены для последующего использования
    (например, освобождение из тюрьмы) и могут быть проданы другим игрокам.

    Attributes:
        instance_id: Уникальный идентификатор экземпляра карточки у игрока.
        card_id: Ссылка на оригинальную карточку.
        card_type: Тип карточки.
        owner_id: ID игрока-владельца.
        is_used: Была ли использована карточка.
    """

    instance_id: UUID
    card_id: str
    card_type: CardType
    owner_id: UUID
    is_used: bool = False

    @classmethod
    def create_from_card(cls, card: Card, owner_id: UUID) -> PlayerCard:
        """
        Создать экземпляр карточки игрока из описания Card.

        Args:
            card: Оригинальная карточка.
            owner_id: ID игрока-владельца.

        Returns:
            Новый экземпляр PlayerCard.
        """
        return cls(
            instance_id=uuid4(),
            card_id=card.card_id,
            card_type=card.card_type,
            owner_id=owner_id,
            is_used=False,
        )

    @property
    def is_active(self) -> bool:
        """Можно ли ещё использовать карточку."""
        return not self.is_used

    def mark_used(self) -> None:
        """Отметить карточку как использованную."""
        self.is_used = True

    def transfer_to(self, new_owner_id: UUID) -> None:
        """
        Передать карточку другому игроку.

        Args:
            new_owner_id: ID нового владельца.
        """
        self.owner_id = new_owner_id

    def to_dict(self) -> dict:
        """
        Сериализация карточки игрока в словарь.

        Returns:
            Словарь с данными карточки.
        """
        return {
            "instance_id": str(self.instance_id),
            "card_id": self.card_id,
            "card_type": self.card_type.value,
            "owner_id": str(self.owner_id),
            "is_used": self.is_used,
        }

    @classmethod
    def from_dict(cls, data: dict) -> PlayerCard:
        """
        Создать карточку игрока из словаря.

        Args:
            data: Словарь с данными.

        Returns:
            Новый экземпляр PlayerCard.
        """
        return cls(
            instance_id=UUID(data["instance_id"]),
            card_id=data["card_id"],
            card_type=CardType(data["card_type"]),
            owner_id=UUID(data["owner_id"]),
            is_used=data.get("is_used", False),
        )

    def __repr__(self) -> str:
        status = "used" if self.is_used else "active"
        return (
            f"PlayerCard(id={self.instance_id}, card='{self.card_id}', "
            f"owner={self.owner_id}, {status})"
        )


# ============================================================================
# КОЛОДА КАРТОЧЕК (CardDeck)
# ============================================================================

@dataclass(slots=True)
class CardDeck:
    """
    Колода карточек одного типа (Шанс или Фонд).

    Управляет перемешиванием, выдачей и возвратом карточек.
    При инициализации карточки автоматически перемешиваются.

    Attributes:
        deck_id: Уникальный идентификатор колоды.
        card_type: Тип карточек в колоде.
        cards: Список карточек в колоде.
        discard_pile: Стопка сброса (использованные карточки).
    """

    deck_id: UUID
    card_type: CardType
    cards: list[Card] = field(default_factory=list)
    discard_pile: list[Card] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Перемешивание колоды после создания."""
        if self.cards:
            self.shuffle()

    # === СВОЙСТВА ===

    @property
    def cards_remaining(self) -> int:
        """Количество оставшихся карточек в колоде."""
        return len(self.cards)

    @property
    def cards_discarded(self) -> int:
        """Количество карточек в сбросе."""
        return len(self.discard_pile)

    @property
    def total_cards(self) -> int:
        """Общее количество карточек (в колоде + в сбросе)."""
        return self.cards_remaining + self.cards_discarded

    @property
    def is_empty(self) -> bool:
        """Пуста ли колода."""
        return len(self.cards) == 0

    # === ДЕЙСТВИЯ С КОЛОДОЙ ===

    def shuffle(self) -> None:
        """Перемешать колоду."""
        random.shuffle(self.cards)

    def draw(self) -> Card | None:
        """
        Взять верхнюю карточку из колоды.

        Если колода пуста, автоматически замешивает карты из сброса
        (если они есть) и берёт из обновлённой колоды.

        Returns:
            Карточку или None, если колода и сброс пусты.
        """
        if self.is_empty:
            if self.discard_pile:
                self.reshuffle_discard()
            else:
                return None

        return self.cards.pop(0)

    def discard(self, card: Card) -> None:
        """
        Сбросить карточку.

        Args:
            card: Карточка для сброса.
        """
        self.discard_pile.append(card)

    def return_to_deck(self, card: Card, shuffle: bool = True) -> None:
        """
        Вернуть карточку в колоду (например, "keep_after_use").

        Args:
            card: Возвращаемая карточка.
            shuffle: Перемешать ли колоду после возврата.
        """
        self.cards.append(card)
        if shuffle:
            self.shuffle()

    def reshuffle_discard(self) -> None:
        """Замешать сброшенные карточки обратно в колоду."""
        if not self.discard_pile:
            return
        self.cards.extend(self.discard_pile)
        self.discard_pile.clear()
        self.shuffle()

    def peek_top(self) -> Card | None:
        """
        Посмотреть верхнюю карточку, не извлекая её.

        Returns:
            Верхнюю карточку или None.
        """
        return self.cards[0] if self.cards else None

    def add_cards(self, new_cards: list[Card], shuffle: bool = True) -> None:
        """
        Добавить новые карточки в колоду.

        Args:
            new_cards: Список новых карточек.
            shuffle: Перемешать ли после добавления.
        """
        self.cards.extend(new_cards)
        if shuffle:
            self.shuffle()

    # === СЕРИАЛИЗАЦИЯ ===

    def to_dict(self) -> dict:
        """
        Сериализация колоды в словарь.

        Returns:
            Словарь с состоянием колоды.
        """
        return {
            "deck_id": str(self.deck_id),
            "card_type": self.card_type.value,
            "cards_remaining": self.cards_remaining,
            "cards_discarded": self.cards_discarded,
            "total_cards": self.total_cards,
            "cards": [card.to_dict() for card in self.cards],
            "discard_pile": [card.to_dict() for card in self.discard_pile],
        }

    @classmethod
    def from_dict(cls, data: dict) -> CardDeck:
        """
        Создать колоду из словаря.

        Args:
            data: Словарь с данными колоды.

        Returns:
            Новый экземпляр CardDeck.
        """
        cards = [Card.from_dict(c) for c in data.get("cards", [])]
        discard = [Card.from_dict(c) for c in data.get("discard_pile", [])]

        return cls(
            deck_id=UUID(data["deck_id"]),
            card_type=CardType(data["card_type"]),
            cards=cards,
            discard_pile=discard,
        )

    @classmethod
    def create_from_list(
        cls,
        card_type: CardType,
        cards_data: list[dict],
    ) -> CardDeck:
        """
        Создать колоду из списка словарей (из JSON-конфигурации).

        Args:
            card_type: Тип карточек.
            cards_data: Список словарей с данными карточек.

        Returns:
            Новая перемешанная колода.
        """
        cards = [Card.from_dict(data) for data in cards_data]
        return cls(
            deck_id=uuid4(),
            card_type=card_type,
            cards=cards,
        )

    def __repr__(self) -> str:
        return (
            f"CardDeck(id={self.deck_id}, type={self.card_type.value}, "
            f"cards={self.cards_remaining}, discarded={self.cards_discarded})"
        )