"""
server/game/auction_manager.py

Менеджер аукционов собственности.

Управляет процессом аукциона:
- Запуск при отказе игрока от покупки
- Приём ставок от участников
- Определение победителя
- Таймаут аукциона

Аукцион запускается, когда игрок отказывается покупать
свободную собственность. Участвовать могут все игроки.
Стартовая цена — 50% от стоимости собственности.

Python: 3.13+
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional
from uuid import UUID, uuid4

from shared.constants import (
    AUCTION_TIMEOUT,
    AUCTION_START_PRICE_RATIO,
    AUCTION_MIN_BID_INCREMENT,
)
from shared.enums import AuctionState, EventType
from shared.models.property import Property
from server.event.event_bus import EventBus

logger = logging.getLogger("billionaire.game")


# ============================================================================
# ДАННЫЕ АУКЦИОНА
# ============================================================================

@dataclass(slots=True)
class Auction:
    """
    Состояние одного аукциона.

    Attributes:
        auction_id: Уникальный идентификатор аукциона.
        game_id: ID игры.
        property_id: ID продаваемой собственности.
        property_name: Название собственности.
        start_price: Начальная цена.
        current_bid: Текущая максимальная ставка.
        highest_bidder_id: ID текущего лидера.
        state: Состояние аукциона.
        participants: Множество ID участников.
        started_at: Время начала.
        deadline: Время завершения.
        bid_history: История ставок [{player_id, amount, timestamp}].
    """

    auction_id: UUID
    game_id: UUID
    property_id: str
    property_name: str
    start_price: int
    current_bid: int = 0
    highest_bidder_id: Optional[UUID] = None
    state: AuctionState = AuctionState.WAITING
    participants: set[UUID] = field(default_factory=set)
    started_at: float = 0.0
    deadline: float = 0.0
    bid_history: list[dict[str, Any]] = field(default_factory=list)


# ============================================================================
# МЕНЕДЖЕР АУКЦИОНОВ
# ============================================================================

class AuctionManager:
    """
    Менеджер аукционов.

    Управляет жизненным циклом аукционов: создание,
    приём ставок, определение победителя, таймаут.

    Usage:
        manager = AuctionManager(event_bus)
        auction = await manager.start_auction(game_id, property_def)
        await manager.place_bid(auction_id, player_id, amount)
    """

    def __init__(self, event_bus: EventBus) -> None:
        """
        Инициализация менеджера аукционов.

        Args:
            event_bus: Шина событий.
        """
        self._event_bus = event_bus

        # Активные аукционы {auction_id: Auction}
        self._active_auctions: dict[UUID, Auction] = {}

        # Аукционы по играм {game_id: auction_id}
        self._game_auctions: dict[UUID, UUID] = {}

    # ========================================================================
    # УПРАВЛЕНИЕ АУКЦИОНОМ
    # ========================================================================

    async def start_auction(
        self,
        game_id: UUID,
        property_def: Property,
        players: list[UUID],
    ) -> Auction:
        """
        Запустить аукцион для собственности.

        Args:
            game_id: ID игры.
            property_def: Описание собственности.
            players: Список ID игроков, которые могут участвовать.

        Returns:
            Созданный аукцион.

        Raises:
            ValueError: Если аукцион для этой игры уже идёт.
        """
        # Проверяем, нет ли уже активного аукциона
        if game_id in self._game_auctions:
            existing_id = self._game_auctions[game_id]
            existing = self._active_auctions.get(existing_id)
            if existing and existing.state == AuctionState.ACTIVE:
                raise ValueError("В этой игре уже идёт аукцион")

        # Вычисляем стартовую цену
        start_price = max(1, int(property_def.price * AUCTION_START_PRICE_RATIO))

        now = time.time()
        auction = Auction(
            auction_id=uuid4(),
            game_id=game_id,
            property_id=property_def.property_id,
            property_name=property_def.name,
            start_price=start_price,
            started_at=now,
            deadline=now + AUCTION_TIMEOUT,
            state=AuctionState.ACTIVE,
        )

        self._active_auctions[auction.auction_id] = auction
        self._game_auctions[game_id] = auction.auction_id

        # Публикуем событие
        await self._event_bus.publish(
            EventType.PROPERTY_AUCTIONED,
            {
                "game_id": game_id,
                "property_id": property_def.property_id,
                "property_name": property_def.name,
                "start_price": start_price,
                "auction_id": str(auction.auction_id),
                "status": "started",
                "deadline": auction.deadline,
            },
        )

        logger.info(
            "Аукцион запущен: %s (старт: %d$, игра: %s)",
            property_def.name,
            start_price,
            str(game_id)[:8],
        )

        # Запускаем таймер
        asyncio.create_task(self._auction_timeout(auction.auction_id))

        return auction

    async def place_bid(
        self,
        auction_id: UUID,
        player_id: UUID,
        amount: int,
        player_name: str = "",
    ) -> tuple[bool, Optional[str]]:
        """
        Сделать ставку на аукционе.

        Args:
            auction_id: ID аукциона.
            player_id: ID игрока.
            amount: Сумма ставки.
            player_name: Имя игрока (для логов).

        Returns:
            Кортеж (успех, сообщение_об_ошибке).
        """
        auction = self._active_auctions.get(auction_id)
        if auction is None:
            return False, "Аукцион не найден"

        if auction.state != AuctionState.ACTIVE:
            return False, "Аукцион не активен"

        # Проверка минимальной ставки
        min_bid = max(
            auction.start_price,
            auction.current_bid + AUCTION_MIN_BID_INCREMENT,
        )

        if amount < min_bid:
            return False, f"Минимальная ставка: {min_bid}$"

        # Обновляем ставку
        old_bid = auction.current_bid
        old_bidder = auction.highest_bidder_id

        auction.current_bid = amount
        auction.highest_bidder_id = player_id
        auction.participants.add(player_id)
        auction.bid_history.append({
            "player_id": str(player_id),
            "amount": amount,
            "timestamp": time.time(),
        })

        # Публикуем событие
        await self._event_bus.publish(
            EventType.PROPERTY_AUCTIONED,
            {
                "game_id": auction.game_id,
                "property_id": auction.property_id,
                "auction_id": str(auction_id),
                "status": "bid_placed",
                "player_id": str(player_id),
                "amount": amount,
                "previous_bid": old_bid,
            },
        )

        logger.info(
            "Ставка на аукционе: %s ставит %d$ за %s",
            player_name or str(player_id)[:8],
            amount,
            auction.property_name,
        )

        return True, None

    async def pass_bid(
        self,
        auction_id: UUID,
        player_id: UUID,
    ) -> None:
        """
        Игрок пасует (пропускает ставку).

        Args:
            auction_id: ID аукциона.
            player_id: ID игрока.
        """
        auction = self._active_auctions.get(auction_id)
        if auction is None:
            return

        auction.participants.add(player_id)

    async def end_auction(self, auction_id: UUID) -> Optional[dict[str, Any]]:
        """
        Завершить аукцион и определить победителя.

        Args:
            auction_id: ID аукциона.

        Returns:
            Результат аукциона или None.
        """
        auction = self._active_auctions.get(auction_id)
        if auction is None:
            return None

        if auction.state != AuctionState.ACTIVE:
            return None

        auction.state = AuctionState.FINISHED

        result: dict[str, Any] = {
            "auction_id": str(auction_id),
            "property_id": auction.property_id,
            "property_name": auction.property_name,
            "winner_id": str(auction.highest_bidder_id) if auction.highest_bidder_id else None,
            "winning_bid": auction.current_bid,
            "no_bids": auction.current_bid == 0,
        }

        # Очищаем
        self._active_auctions.pop(auction_id, None)
        self._game_auctions.pop(auction.game_id, None)

        # Публикуем событие
        await self._event_bus.publish(
            EventType.PROPERTY_AUCTIONED,
            {
                "game_id": auction.game_id,
                "property_id": auction.property_id,
                "auction_id": str(auction_id),
                "status": "finished",
                "winner_id": str(auction.highest_bidder_id) if auction.highest_bidder_id else None,
                "winning_bid": auction.current_bid,
                "no_bids": auction.current_bid == 0,
            },
        )

        logger.info(
            "Аукцион завершён: %s, победитель: %s, ставка: %d$",
            auction.property_name,
            str(auction.highest_bidder_id)[:8] if auction.highest_bidder_id else "нет",
            auction.current_bid,
        )

        return result

    async def cancel_auction(self, auction_id: UUID) -> bool:
        """
        Отменить аукцион.

        Args:
            auction_id: ID аукциона.

        Returns:
            True, если отменён.
        """
        auction = self._active_auctions.get(auction_id)
        if auction is None:
            return False

        auction.state = AuctionState.CANCELLED

        self._active_auctions.pop(auction_id, None)
        self._game_auctions.pop(auction.game_id, None)

        logger.info("Аукцион отменён: %s", auction.property_name)
        return True

    # ========================================================================
    # ТАЙМЕР
    # ========================================================================

    async def _auction_timeout(self, auction_id: UUID) -> None:
        """
        Таймер завершения аукциона.

        Args:
            auction_id: ID аукциона.
        """
        auction = self._active_auctions.get(auction_id)
        if auction is None:
            return

        remaining = auction.deadline - time.time()
        if remaining > 0:
            await asyncio.sleep(remaining)

        # Проверяем, не завершён ли уже аукцион
        current = self._active_auctions.get(auction_id)
        if current and current.state == AuctionState.ACTIVE:
            await self.end_auction(auction_id)

    # ========================================================================
    # ИНФОРМАЦИЯ
    # ========================================================================

    def get_auction(self, auction_id: UUID) -> Optional[Auction]:
        """
        Получить данные аукциона.

        Args:
            auction_id: ID аукциона.

        Returns:
            Аукцион или None.
        """
        return self._active_auctions.get(auction_id)

    def get_active_auction_for_game(self, game_id: UUID) -> Optional[Auction]:
        """
        Получить активный аукцион для игры.

        Args:
            game_id: ID игры.

        Returns:
            Аукцион или None.
        """
        auction_id = self._game_auctions.get(game_id)
        if auction_id:
            return self._active_auctions.get(auction_id)
        return None

    def get_auction_state(self, auction_id: UUID) -> Optional[dict[str, Any]]:
        """
        Получить состояние аукциона для отправки клиенту.

        Args:
            auction_id: ID аукциона.

        Returns:
            Словарь с данными или None.
        """
        auction = self._active_auctions.get(auction_id)
        if auction is None:
            return None

        return {
            "auction_id": str(auction.auction_id),
            "property_id": auction.property_id,
            "property_name": auction.property_name,
            "start_price": auction.start_price,
            "current_bid": auction.current_bid,
            "highest_bidder_id": str(auction.highest_bidder_id) if auction.highest_bidder_id else None,
            "state": auction.state.value,
            "time_remaining": max(0.0, auction.deadline - time.time()),
            "participants_count": len(auction.participants),
        }

    def get_stats(self) -> dict:
        """
        Получить статистику менеджера аукционов.

        Returns:
            Словарь с метриками.
        """
        return {
            "active_auctions": len(self._active_auctions),
            "games_with_auctions": len(self._game_auctions),
        }