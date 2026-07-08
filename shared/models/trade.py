"""
shared/models/trade.py

Модели торговых операций для проекта "Миллиардер".

Содержит:
- TradeOffer — торговое предложение между двумя игроками
- TradeResult — результат завершённой сделки

Торговля позволяет игрокам обмениваться собственностью,
карточками и давать деньги в долг под проценты.

Python: 3.13+
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Self
from uuid import UUID, uuid4

from shared.enums import TradeStatus


# ============================================================================
# ТОРГОВОЕ ПРЕДЛОЖЕНИЕ (TradeOffer)
# ============================================================================

@dataclass(slots=True)
class TradeOffer:
    """
    Торговое предложение между двумя игроками.

    Инициатор (from_player) предлагает обмен получателю (to_player).
    Предложение может включать:
    - Собственность (property_ids) для обмена
    - Карточки (card_ids) для обмена
    - Деньги в долг с процентами (loan_amount + loan_percent)

    Attributes:
        trade_id: Уникальный идентификатор предложения.
        game_id: ID игры.
        from_player_id: ID инициатора предложения.
        to_player_id: ID получателя предложения.
        offer_properties: Собственность, предлагаемая инициатором.
        offer_cards: Карточки, предлагаемые инициатором.
        request_properties: Собственность, запрашиваемая у получателя.
        request_cards: Карточки, запрашиваемые у получателя.
        request_money: Деньги, запрашиваемые у получателя.
        loan_amount: Сумма денежного долга получателю.
        loan_percent: Процент по долгу (0-50).
        status: Статус предложения.
        created_at: Время создания.
        expires_at: Время истечения (если не принято).
        message: Сообщение к предложению.
    """

    trade_id: UUID
    game_id: UUID
    from_player_id: UUID
    to_player_id: UUID
    offer_properties: list[str] = field(default_factory=list)
    offer_cards: list[str] = field(default_factory=list)
    request_properties: list[str] = field(default_factory=list)
    request_cards: list[str] = field(default_factory=list)
    request_money: int = 0
    loan_amount: int = 0
    loan_percent: Optional[int] = None
    status: TradeStatus = TradeStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime | None = None
    message: str = ""

    def __post_init__(self) -> None:
        """Валидация предложения после инициализации."""
        # Проверка, что предложение не пустое
        if (
            not self.offer_properties
            and not self.offer_cards
            and self.loan_amount == 0
            and not self.request_properties
            and not self.request_cards
            and self.request_money == 0
        ):
            raise ValueError("Торговое предложение не может быть пустым")

        # Проверка процента по долгу
        if self.loan_percent is not None:
            if self.loan_percent < 0 or self.loan_percent > 50:
                raise ValueError(
                    f"Процент по долгу должен быть 0-50: {self.loan_percent}"
                )
            if self.loan_amount <= 0:
                raise ValueError(
                    "Сумма долга должна быть положительной при указании процента"
                )

        # Проверка статуса
        if self.status != TradeStatus.PENDING and self.expires_at is None:
            self.expires_at = datetime.now(timezone.utc)

    # === СВОЙСТВА ===

    @property
    def is_pending(self) -> bool:
        """Ожидает ли предложение ответа."""
        return self.status == TradeStatus.PENDING

    @property
    def is_accepted(self) -> bool:
        """Принято ли предложение."""
        return self.status == TradeStatus.ACCEPTED

    @property
    def is_declined(self) -> bool:
        """Отклонено ли предложение."""
        return self.status == TradeStatus.DECLINED

    @property
    def is_expired(self) -> bool:
        """Истекло ли время предложения."""
        if self.status == TradeStatus.EXPIRED:
            return True
        if self.expires_at and datetime.now(timezone.utc) > self.expires_at:
            return True
        return False

    @property
    def is_cancelled(self) -> bool:
        """Отменено ли предложение."""
        return self.status == TradeStatus.CANCELLED

    @property
    def is_active(self) -> bool:
        """Активно ли предложение (можно принять/отклонить)."""
        return self.is_pending and not self.is_expired

    @property
    def has_money_offer(self) -> bool:
        """Включает ли предложение денежный долг."""
        return self.loan_amount > 0

    @property
    def has_property_exchange(self) -> bool:
        """Включает ли предложение обмен собственностью."""
        return bool(self.offer_properties or self.request_properties)

    @property
    def has_card_exchange(self) -> bool:
        """Включает ли предложение обмен карточками."""
        return bool(self.offer_cards or self.request_cards)

    @property
    def summary(self) -> str:
        """
        Краткое описание предложения для отображения.

        Returns:
            Человекочитаемая строка с сутью предложения.
        """
        parts: list[str] = []

        if self.offer_properties:
            parts.append(f"Отдаёт: {len(self.offer_properties)} собств.")
        if self.request_properties:
            parts.append(f"Просит: {len(self.request_properties)} собств.")
        if self.offer_cards:
            parts.append(f"Отдаёт: {len(self.offer_cards)} карт.")
        if self.request_cards:
            parts.append(f"Просит: {len(self.request_cards)} карт.")
        if self.loan_amount > 0:
            percent_str = f" под {self.loan_percent}%" if self.loan_percent else ""
            parts.append(f"Даёт в долг: {self.loan_amount}${percent_str}")
        if self.request_money > 0:
            parts.append(f"Просит денег: {self.request_money}$")

        return "; ".join(parts) if parts else "Пустое предложение"

    # === ДЕЙСТВИЯ ===

    def accept(self) -> None:
        """
        Принять предложение.

        Raises:
            ValueError: Если предложение не в статусе PENDING или истекло.
        """
        if not self.is_active:
            raise ValueError(
                f"Невозможно принять предложение в статусе {self.status.value}"
            )
        self.status = TradeStatus.ACCEPTED
        self.expires_at = datetime.now(timezone.utc)

    def decline(self) -> None:
        """
        Отклонить предложение.

        Raises:
            ValueError: Если предложение не в статусе PENDING.
        """
        if not self.is_pending:
            raise ValueError(
                f"Невозможно отклонить предложение в статусе {self.status.value}"
            )
        self.status = TradeStatus.DECLINED
        self.expires_at = datetime.now(timezone.utc)

    def cancel(self) -> None:
        """
        Отменить предложение (только инициатором).

        Raises:
            ValueError: Если предложение не в статусе PENDING.
        """
        if not self.is_pending:
            raise ValueError(
                f"Невозможно отменить предложение в статусе {self.status.value}"
            )
        self.status = TradeStatus.CANCELLED
        self.expires_at = datetime.now(timezone.utc)

    def mark_expired(self) -> None:
        """Отметить предложение как истекшее."""
        if self.is_pending:
            self.status = TradeStatus.EXPIRED
            self.expires_at = datetime.now(timezone.utc)

    def involves_player(self, player_id: UUID) -> bool:
        """
        Проверить, участвует ли игрок в предложении.

        Args:
            player_id: ID игрока.

        Returns:
            True, если игрок — инициатор или получатель.
        """
        return player_id in (self.from_player_id, self.to_player_id)

    def is_initiator(self, player_id: UUID) -> bool:
        """
        Проверить, является ли игрок инициатором.

        Args:
            player_id: ID игрока.

        Returns:
            True, если игрок создал предложение.
        """
        return player_id == self.from_player_id

    def is_recipient(self, player_id: UUID) -> bool:
        """
        Проверить, является ли игрок получателем.

        Args:
            player_id: ID игрока.

        Returns:
            True, если игрок — получатель предложения.
        """
        return player_id == self.to_player_id

    # === СЕРИАЛИЗАЦИЯ ===

    def to_dict(self) -> dict:
        """
        Сериализация предложения в словарь.

        Returns:
            Словарь с данными предложения.
        """
        return {
            "trade_id": str(self.trade_id),
            "game_id": str(self.game_id),
            "from_player_id": str(self.from_player_id),
            "to_player_id": str(self.to_player_id),
            "offer_properties": self.offer_properties,
            "offer_cards": self.offer_cards,
            "request_properties": self.request_properties,
            "request_cards": self.request_cards,
            "request_money": self.request_money,
            "loan_amount": self.loan_amount,
            "loan_percent": self.loan_percent,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "message": self.message,
            "summary": self.summary,
        }

    @classmethod
    def from_dict(cls, data: dict) -> TradeOffer:
        """
        Создать предложение из словаря.

        Args:
            data: Словарь с данными предложения.

        Returns:
            Новый экземпляр TradeOffer.
        """
        return cls(
            trade_id=UUID(data["trade_id"]),
            game_id=UUID(data["game_id"]),
            from_player_id=UUID(data["from_player_id"]),
            to_player_id=UUID(data["to_player_id"]),
            offer_properties=data.get("offer_properties", []),
            offer_cards=data.get("offer_cards", []),
            request_properties=data.get("request_properties", []),
            request_cards=data.get("request_cards", []),
            request_money=data.get("request_money", 0),
            loan_amount=data.get("loan_amount", 0),
            loan_percent=data.get("loan_percent"),
            status=TradeStatus(data.get("status", "pending")),
            created_at=datetime.fromisoformat(data["created_at"])
                if data.get("created_at")
                else datetime.now(timezone.utc),
            expires_at=datetime.fromisoformat(data["expires_at"])
                if data.get("expires_at")
                else None,
            message=data.get("message", ""),
        )

    @classmethod
    def create(
        cls,
        game_id: UUID,
        from_player_id: UUID,
        to_player_id: UUID,
        offer_properties: list[str] | None = None,
        offer_cards: list[str] | None = None,
        request_properties: list[str] | None = None,
        request_cards: list[str] | None = None,
        request_money: int = 0,
        loan_amount: int = 0,
        loan_percent: int | None = None,
        message: str = "",
        timeout_seconds: int = 120,
    ) -> TradeOffer:
        """
        Создать новое торговое предложение.

        Args:
            game_id: ID игры.
            from_player_id: ID инициатора.
            to_player_id: ID получателя.
            offer_properties: Предлагаемая собственность.
            offer_cards: Предлагаемые карточки.
            request_properties: Запрашиваемая собственность.
            request_cards: Запрашиваемые карточки.
            request_money: Запрашиваемые деньги.
            loan_amount: Сумма долга.
            loan_percent: Процент по долгу.
            message: Сообщение.
            timeout_seconds: Таймаут предложения в секундах.

        Returns:
            Новый экземпляр TradeOffer.
        """
        now = datetime.now(timezone.utc)
        expires = datetime.fromtimestamp(
            now.timestamp() + timeout_seconds,
            tz=timezone.utc,
        )

        return cls(
            trade_id=uuid4(),
            game_id=game_id,
            from_player_id=from_player_id,
            to_player_id=to_player_id,
            offer_properties=offer_properties or [],
            offer_cards=offer_cards or [],
            request_properties=request_properties or [],
            request_cards=request_cards or [],
            request_money=request_money,
            loan_amount=loan_amount,
            loan_percent=loan_percent,
            status=TradeStatus.PENDING,
            created_at=now,
            expires_at=expires,
            message=message,
        )

    def __repr__(self) -> str:
        return (
            f"TradeOffer(id={self.trade_id}, "
            f"from={self.from_player_id}, to={self.to_player_id}, "
            f"status={self.status.value})"
        )


# ============================================================================
# РЕЗУЛЬТАТ СДЕЛКИ (TradeResult)
# ============================================================================

@dataclass(slots=True)
class TradeResult:
    """
    Результат завершённой торговой сделки.

    Содержит информацию о том, что было передано между игроками
    в результате принятия торгового предложения.

    Attributes:
        trade_id: ID исходного предложения.
        from_player_id: ID инициатора.
        to_player_id: ID получателя.
        properties_transferred_to_initiator: Собственность, полученная инициатором.
        properties_transferred_to_recipient: Собственность, полученная получателем.
        cards_transferred_to_initiator: Карточки, полученные инициатором.
        cards_transferred_to_recipient: Карточки, полученные получателем.
        money_paid_by_recipient: Деньги, выплаченные получателем инициатору.
        loan_principal: Основная сумма долга.
        loan_percent: Процент по долгу.
        completed_at: Время завершения сделки.
    """

    trade_id: UUID
    from_player_id: UUID
    to_player_id: UUID
    properties_transferred_to_initiator: list[str] = field(default_factory=list)
    properties_transferred_to_recipient: list[str] = field(default_factory=list)
    cards_transferred_to_initiator: list[str] = field(default_factory=list)
    cards_transferred_to_recipient: list[str] = field(default_factory=list)
    money_paid_by_recipient: int = 0
    loan_principal: int = 0
    loan_percent: Optional[int] = None
    completed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @classmethod
    def from_offer(cls, offer: TradeOffer) -> TradeResult:
        """
        Создать результат на основе принятого предложения.

        Args:
            offer: Принятое торговое предложение.

        Returns:
            Новый экземпляр TradeResult.

        Raises:
            ValueError: Если предложение не в статусе ACCEPTED.
        """
        if not offer.is_accepted:
            raise ValueError(
                f"Нельзя создать результат для предложения в статусе {offer.status.value}"
            )

        return cls(
            trade_id=offer.trade_id,
            from_player_id=offer.from_player_id,
            to_player_id=offer.to_player_id,
            properties_transferred_to_initiator=list(offer.request_properties),
            properties_transferred_to_recipient=list(offer.offer_properties),
            cards_transferred_to_initiator=list(offer.request_cards),
            cards_transferred_to_recipient=list(offer.offer_cards),
            money_paid_by_recipient=offer.request_money,
            loan_principal=offer.loan_amount,
            loan_percent=offer.loan_percent,
            completed_at=datetime.now(timezone.utc),
        )

    @property
    def total_loan_repayment(self) -> int:
        """
        Общая сумма к возврату по долгу (основная сумма + проценты).

        Returns:
            Сумма долга с процентами.
        """
        if self.loan_principal <= 0 or self.loan_percent is None:
            return 0
        interest = (self.loan_principal * self.loan_percent) // 100
        return self.loan_principal + interest

    def to_dict(self) -> dict:
        """
        Сериализация результата в словарь.

        Returns:
            Словарь с данными результата.
        """
        return {
            "trade_id": str(self.trade_id),
            "from_player_id": str(self.from_player_id),
            "to_player_id": str(self.to_player_id),
            "properties_transferred_to_initiator": self.properties_transferred_to_initiator,
            "properties_transferred_to_recipient": self.properties_transferred_to_recipient,
            "cards_transferred_to_initiator": self.cards_transferred_to_initiator,
            "cards_transferred_to_recipient": self.cards_transferred_to_recipient,
            "money_paid_by_recipient": self.money_paid_by_recipient,
            "loan_principal": self.loan_principal,
            "loan_percent": self.loan_percent,
            "total_loan_repayment": self.total_loan_repayment,
            "completed_at": self.completed_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> TradeResult:
        """
        Создать результат из словаря.

        Args:
            data: Словарь с данными.

        Returns:
            Новый экземпляр TradeResult.
        """
        return cls(
            trade_id=UUID(data["trade_id"]),
            from_player_id=UUID(data["from_player_id"]),
            to_player_id=UUID(data["to_player_id"]),
            properties_transferred_to_initiator=data.get(
                "properties_transferred_to_initiator", []
            ),
            properties_transferred_to_recipient=data.get(
                "properties_transferred_to_recipient", []
            ),
            cards_transferred_to_initiator=data.get(
                "cards_transferred_to_initiator", []
            ),
            cards_transferred_to_recipient=data.get(
                "cards_transferred_to_recipient", []
            ),
            money_paid_by_recipient=data.get("money_paid_by_recipient", 0),
            loan_principal=data.get("loan_principal", 0),
            loan_percent=data.get("loan_percent"),
            completed_at=datetime.fromisoformat(data["completed_at"])
                if data.get("completed_at")
                else datetime.now(timezone.utc),
        )

    def __repr__(self) -> str:
        return (
            f"TradeResult(trade={self.trade_id}, "
            f"props_to_initiator={len(self.properties_transferred_to_initiator)}, "
            f"props_to_recipient={len(self.properties_transferred_to_recipient)})"
        )