"""
server/game/trade_manager.py

Менеджер торговли между игроками.

Управляет процессом создания, принятия и отклонения
торговых предложений. Торговля позволяет игрокам обмениваться
собственностью, карточками и давать деньги в долг.

Торговать можно только в свой ход (инициатор).
Вторая сторона может отвечать в любой момент.

Python: 3.13+
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Optional
from uuid import UUID

from shared.constants import (
    TRADE_TIMEOUT,
    MIN_LOAN_PERCENT,
    MAX_LOAN_PERCENT,
)
from shared.enums import TradeStatus, EventType
from shared.models.trade import TradeOffer, TradeResult
from shared.validators import validate_trade_offer
from server.event.event_bus import EventBus

logger = logging.getLogger("billionaire.game")


# ============================================================================
# МЕНЕДЖЕР ТОРГОВЛИ
# ============================================================================

class TradeManager:
    """
    Менеджер торговых предложений.

    Управляет жизненным циклом сделок между игроками:
    создание, принятие, отклонение, таймаут.

    Usage:
        manager = TradeManager(event_bus)
        offer = await manager.create_offer(game_id, from_id, to_id, ...)
        await manager.accept_offer(offer.trade_id)
    """

    def __init__(self, event_bus: EventBus) -> None:
        """
        Инициализация менеджера торговли.

        Args:
            event_bus: Шина событий.
        """
        self._event_bus = event_bus

        # Активные предложения {trade_id: TradeOffer}
        self._active_offers: dict[UUID, TradeOffer] = {}

        # Предложения по играм {game_id: set[trade_id]}
        self._game_offers: dict[UUID, set[UUID]] = {}

    # ========================================================================
    # СОЗДАНИЕ ПРЕДЛОЖЕНИЯ
    # ========================================================================

    async def create_offer(
        self,
        game_id: UUID,
        from_player_id: UUID,
        to_player_id: UUID,
        offer_properties: list[str],
        request_properties: list[str],
        offer_cards: list[str],
        request_cards: list[str],
        request_money: int = 0,
        loan_amount: int = 0,
        loan_percent: Optional[int] = None,
        message: str = "",
        from_properties: Optional[list[str]] = None,
        from_cards: Optional[list[str]] = None,
        from_money: int = 0,
        to_properties: Optional[list[str]] = None,
        to_cards: Optional[list[str]] = None,
    ) -> TradeOffer:
        """
        Создать торговое предложение.

        Args:
            game_id: ID игры.
            from_player_id: ID инициатора.
            to_player_id: ID получателя.
            offer_properties: Предлагаемая инициатором собственность.
            request_properties: Запрашиваемая у получателя собственность.
            offer_cards: Предлагаемые карточки.
            request_cards: Запрашиваемые карточки.
            request_money: Запрашиваемые деньги.
            loan_amount: Сумма долга.
            loan_percent: Процент по долгу (0-50).
            message: Сообщение.
            from_properties: Вся собственность инициатора (для валидации).
            from_cards: Все карточки инициатора.
            from_money: Деньги инициатора.
            to_properties: Вся собственность получателя.
            to_cards: Все карточки получателя.

        Returns:
            Созданное предложение.

        Raises:
            ValueError: Если предложение некорректно.
        """
        # Валидация
        error = validate_trade_offer(
            from_player_id=from_player_id,
            to_player_id=to_player_id,
            offer_properties=offer_properties,
            request_properties=request_properties,
            offer_cards=offer_cards,
            request_cards=request_cards,
            request_money=request_money,
            loan_amount=loan_amount,
            loan_percent=loan_percent,
            from_properties=from_properties or [],
            from_cards=from_cards or [],
            from_money=from_money,
            to_properties=to_properties or [],
            to_cards=to_cards or [],
        )

        if error:
            raise ValueError(error)

        # Создаём предложение
        offer = TradeOffer.create(
            game_id=game_id,
            from_player_id=from_player_id,
            to_player_id=to_player_id,
            offer_properties=offer_properties,
            offer_cards=offer_cards,
            request_properties=request_properties,
            request_cards=request_cards,
            request_money=request_money,
            loan_amount=loan_amount,
            loan_percent=loan_percent,
            message=message,
            timeout_seconds=TRADE_TIMEOUT,
        )

        # Сохраняем
        self._active_offers[offer.trade_id] = offer

        if game_id not in self._game_offers:
            self._game_offers[game_id] = set()
        self._game_offers[game_id].add(offer.trade_id)

        # Публикуем событие
        await self._event_bus.publish(
            EventType.TRADE_OFFERED,
            {
                "game_id": game_id,
                "trade_id": str(offer.trade_id),
                "from_player_id": str(from_player_id),
                "to_player_id": str(to_player_id),
                "offer": {
                    "properties": offer_properties,
                    "cards": offer_cards,
                    "money": loan_amount,
                },
                "request": {
                    "properties": request_properties,
                    "cards": request_cards,
                    "money": request_money,
                },
            },
        )

        logger.info(
            "Торговое предложение создано: %s → %s (собств: %d↔%d, карт: %d↔%d)",
            str(from_player_id)[:8],
            str(to_player_id)[:8],
            len(offer_properties),
            len(request_properties),
            len(offer_cards),
            len(request_cards),
        )

        # Запускаем таймер
        asyncio.create_task(self._offer_timeout(offer.trade_id))

        return offer

    # ========================================================================
    # ОТВЕТ НА ПРЕДЛОЖЕНИЕ
    # ========================================================================

    async def accept_offer(
        self,
        trade_id: UUID,
        player_id: UUID,
    ) -> tuple[Optional[TradeResult], Optional[str]]:
        """
        Принять торговое предложение.

        Args:
            trade_id: ID предложения.
            player_id: ID игрока (должен быть получателем).

        Returns:
            Кортеж (результат, ошибка).

        Raises:
            ValueError: Если предложение не в статусе PENDING.
        """
        offer = self._active_offers.get(trade_id)
        if offer is None:
            return None, "Предложение не найдено"

        if not offer.is_active:
            return None, "Предложение уже не действительно"

        if offer.to_player_id != player_id:
            return None, "Только получатель может принять предложение"

        # Принимаем
        offer.accept()

        # Создаём результат
        result = TradeResult.from_offer(offer)

        # Очищаем
        self._remove_offer(trade_id)

        # Публикуем событие
        await self._event_bus.publish(
            EventType.TRADE_ACCEPTED,
            {
                "game_id": offer.game_id,
                "trade_id": str(trade_id),
                "from_player_id": str(offer.from_player_id),
                "to_player_id": str(offer.to_player_id),
                "result": result.to_dict(),
            },
        )

        logger.info(
            "Сделка принята: %s ↔ %s",
            str(offer.from_player_id)[:8],
            str(offer.to_player_id)[:8],
        )

        return result, None

    async def decline_offer(
        self,
        trade_id: UUID,
        player_id: UUID,
    ) -> bool:
        """
        Отклонить торговое предложение.

        Args:
            trade_id: ID предложения.
            player_id: ID игрока (должен быть получателем).

        Returns:
            True, если отклонено.
        """
        offer = self._active_offers.get(trade_id)
        if offer is None:
            return False

        if offer.to_player_id != player_id:
            return False

        offer.decline()
        self._remove_offer(trade_id)

        # Публикуем событие
        await self._event_bus.publish(
            EventType.TRADE_DECLINED,
            {
                "game_id": offer.game_id,
                "trade_id": str(trade_id),
                "from_player_id": str(offer.from_player_id),
                "to_player_id": str(offer.to_player_id),
            },
        )

        logger.info("Сделка отклонена: %s", str(trade_id)[:8])
        return True

    async def cancel_offer(
        self,
        trade_id: UUID,
        player_id: UUID,
    ) -> bool:
        """
        Отменить предложение (только инициатор).

        Args:
            trade_id: ID предложения.
            player_id: ID инициатора.

        Returns:
            True, если отменено.
        """
        offer = self._active_offers.get(trade_id)
        if offer is None:
            return False

        if offer.from_player_id != player_id:
            return False

        offer.cancel()
        self._remove_offer(trade_id)

        logger.info("Предложение отменено: %s", str(trade_id)[:8])
        return True

    # ========================================================================
    # ТАЙМЕР
    # ========================================================================

    async def _offer_timeout(self, trade_id: UUID) -> None:
        """
        Таймер истечения предложения.

        Args:
            trade_id: ID предложения.
        """
        offer = self._active_offers.get(trade_id)
        if offer is None or offer.expires_at is None:
            return

        remaining = (offer.expires_at - time.time())
        if remaining > 0:
            await asyncio.sleep(remaining)

        # Проверяем, не обработано ли уже
        current = self._active_offers.get(trade_id)
        if current and current.is_pending:
            current.mark_expired()
            self._remove_offer(trade_id)

            await self._event_bus.publish(
                EventType.TRADE_DECLINED,
                {
                    "game_id": current.game_id,
                    "trade_id": str(trade_id),
                    "reason": "expired",
                },
            )

            logger.debug("Предложение истекло: %s", str(trade_id)[:8])

    # ========================================================================
    # ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ
    # ========================================================================

    def _remove_offer(self, trade_id: UUID) -> None:
        """
        Удалить предложение из активных.

        Args:
            trade_id: ID предложения.
        """
        offer = self._active_offers.pop(trade_id, None)
        if offer and offer.game_id in self._game_offers:
            self._game_offers[offer.game_id].discard(trade_id)
            if not self._game_offers[offer.game_id]:
                del self._game_offers[offer.game_id]

    # ========================================================================
    # ИНФОРМАЦИЯ
    # ========================================================================

    def get_offer(self, trade_id: UUID) -> Optional[TradeOffer]:
        """
        Получить предложение.

        Args:
            trade_id: ID предложения.

        Returns:
            TradeOffer или None.
        """
        return self._active_offers.get(trade_id)

    def get_player_offers(self, player_id: UUID) -> list[TradeOffer]:
        """
        Получить все предложения, в которых участвует игрок.

        Args:
            player_id: ID игрока.

        Returns:
            Список предложений.
        """
        return [
            offer for offer in self._active_offers.values()
            if offer.involves_player(player_id)
        ]

    def get_offers_for_player(
        self,
        player_id: UUID,
    ) -> list[TradeOffer]:
        """
        Получить входящие предложения для игрока.

        Args:
            player_id: ID игрока.

        Returns:
            Список активных предложений, где игрок — получатель.
        """
        return [
            offer for offer in self._active_offers.values()
            if offer.to_player_id == player_id and offer.is_active
        ]

    def get_game_offers(self, game_id: UUID) -> list[TradeOffer]:
        """
        Получить все предложения в игре.

        Args:
            game_id: ID игры.

        Returns:
            Список предложений.
        """
        offer_ids = self._game_offers.get(game_id, set())
        return [
            self._active_offers[oid]
            for oid in offer_ids
            if oid in self._active_offers
        ]

    def get_offer_state(self, trade_id: UUID) -> Optional[dict[str, Any]]:
        """
        Получить состояние предложения для отправки клиенту.

        Args:
            trade_id: ID предложения.

        Returns:
            Словарь с данными или None.
        """
        offer = self._active_offers.get(trade_id)
        if offer is None:
            return None

        return {
            "trade_id": str(offer.trade_id),
            "from_player_id": str(offer.from_player_id),
            "to_player_id": str(offer.to_player_id),
            "status": offer.status.value,
            "summary": offer.summary,
            "message": offer.message,
            "time_remaining": (
                max(0.0, offer.expires_at - time.time())
                if offer.expires_at else 0.0
            ),
        }

    def get_stats(self) -> dict:
        """
        Получить статистику менеджера торговли.

        Returns:
            Словарь с метриками.
        """
        return {
            "active_offers": len(self._active_offers),
            "games_with_offers": len(self._game_offers),
        }