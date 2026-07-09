"""
client/viewmodels/game_viewmodel.py

ViewModel для игрового процесса.

Управляет игровыми действиями: бросок кубиков, покупка,
строительство, завершение хода. Связывает NetworkClient с GameModel.

Python: 3.13+
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional
from uuid import UUID

from PySide6.QtCore import QObject, Signal, Slot, Property

from client.network.network_client import NetworkClient
from client.models.game_model import GameModel
from client.models.player_model import PlayerModel

logger = logging.getLogger("billionaire.client")


# ============================================================================
# VIEWMODEL ИГРЫ
# ============================================================================

class GameViewModel(QObject):
    """
    ViewModel для игрового процесса.

    Предоставляет слоты для UI (бросок кубиков, покупка, строительство)
    и сигналы для обновления состояния игры.

    Сигналы:
        dice_rolled — кубики брошены
        property_bought — собственность куплена
        turn_ended — ход завершён
        action_result — результат действия
        error_occurred — ошибка
    """

    # Сигналы
    dice_rolled = Signal(dict)
    property_bought = Signal(dict)
    turn_ended = Signal(dict)
    auction_started = Signal(dict)
    action_result = Signal(str, dict)  # action_type, result
    error_occurred = Signal(str)
    game_over = Signal(dict)

    def __init__(
        self,
        network_client: NetworkClient,
        game_model: GameModel,
        player_model: PlayerModel,
        parent: Optional[QObject] = None,
    ) -> None:
        """
        Инициализация ViewModel.

        Args:
            network_client: Сетевой клиент.
            game_model: Модель игры.
            player_model: Модель игрока.
            parent: Родительский QObject.
        """
        super().__init__(parent)

        self._network = network_client
        self._game_model = game_model
        self._player_model = player_model

        # Состояние действий
        self._can_roll_dice: bool = False
        self._can_buy: bool = False
        self._can_end_turn: bool = False
        self._dice_rolled_this_turn: bool = False
        self._pending_property_id: Optional[str] = None

    # ========================================================================
    # Q_PROPERTY
    # ========================================================================

    def get_can_roll_dice(self) -> bool:
        return self._can_roll_dice

    def get_can_buy(self) -> bool:
        return self._can_buy

    def get_can_end_turn(self) -> bool:
        return self._can_end_turn

    def get_is_my_turn(self) -> bool:
        return self._game_model.is_my_turn()

    canRollDice = Property(bool, get_can_roll_dice, notify=action_result)
    canBuy = Property(bool, get_can_buy, notify=action_result)
    canEndTurn = Property(bool, get_can_end_turn, notify=action_result)
    isMyTurn = Property(bool, get_is_my_turn, notify=action_result)

    # ========================================================================
    # СЛОТЫ
    # ========================================================================

    @Slot()
    def roll_dice(self) -> None:
        """Бросить кубики."""
        if not self._can_roll_dice:
            return
        asyncio.ensure_future(self._do_roll_dice())

    @Slot()
    def buy_property(self) -> None:
        """Купить текущую собственность."""
        if not self._can_buy or not self._pending_property_id:
            return
        asyncio.ensure_future(self._do_buy_property(self._pending_property_id))

    @Slot()
    def decline_property(self) -> None:
        """Отказаться от покупки."""
        if not self._pending_property_id:
            return
        asyncio.ensure_future(self._do_decline_property(self._pending_property_id))

    @Slot(str)
    def build_house(self, property_id: str) -> None:
        """
        Построить дом.

        Args:
            property_id: ID собственности.
        """
        asyncio.ensure_future(self._do_build_house(property_id))

    @Slot(str)
    def build_hotel(self, property_id: str) -> None:
        """
        Построить отель.

        Args:
            property_id: ID собственности.
        """
        asyncio.ensure_future(self._do_build_hotel(property_id))

    @Slot(str)
    def mortgage_property(self, property_id: str) -> None:
        """
        Заложить собственность.

        Args:
            property_id: ID собственности.
        """
        asyncio.ensure_future(self._do_mortgage(property_id))

    @Slot(str)
    def unmortgage_property(self, property_id: str) -> None:
        """
        Выкупить из залога.

        Args:
            property_id: ID собственности.
        """
        asyncio.ensure_future(self._do_unmortgage(property_id))

    @Slot()
    def end_turn(self) -> None:
        """Завершить ход."""
        if not self._can_end_turn:
            return
        asyncio.ensure_future(self._do_end_turn())

    @Slot()
    def pay_jail_fine(self) -> None:
        """Заплатить штраф за выход из тюрьмы."""
        asyncio.ensure_future(self._do_jail_action("pay_fine"))

    @Slot()
    def use_jail_card(self) -> None:
        """Использовать карточку освобождения."""
        asyncio.ensure_future(self._do_jail_action("use_card"))

    @Slot()
    def pay_veranda_exit(self) -> None:
        """Заплатить за выход с Веранды."""
        asyncio.ensure_future(self._do_veranda_action("pay_exit"))

    @Slot(int)
    def place_auction_bid(self, amount: int) -> None:
        """
        Сделать ставку на аукционе.

        Args:
            amount: Сумма ставки.
        """
        asyncio.ensure_future(self._do_auction_bid(amount))

    @Slot()
    def pass_auction(self) -> None:
        """Пас на аукционе."""
        asyncio.ensure_future(self._do_auction_pass())

    # ========================================================================
    # АСИНХРОННЫЕ ОПЕРАЦИИ
    # ========================================================================

    async def _do_roll_dice(self) -> None:
        """Выполнить бросок кубиков."""
        try:
            from shared.enums import PacketType

            response = await self._network.send_request(
                PacketType.ROLL_DICE_REQUEST,
                {},
                timeout=15.0,
            )

            if response:
                self._dice_rolled_this_turn = True
                self._can_roll_dice = False

                # Проверяем, можно ли купить
                if response.get("can_buy"):
                    self._can_buy = True
                    self._pending_property_id = response.get("property_id")

                self._can_end_turn = True
                self._game_model.dice_rolled.emit(response)
                self.dice_rolled.emit(response)
            else:
                self.error_occurred.emit("Ошибка броска кубиков")

        except Exception as e:
            self.error_occurred.emit(str(e))

    async def _do_buy_property(self, property_id: str) -> None:
        """Купить собственность."""
        try:
            from shared.enums import PacketType

            response = await self._network.send_request(
                PacketType.BUY_PROPERTY_REQUEST,
                {"property_id": property_id},
            )

            if response and "property_id" in response:
                self._can_buy = False
                self._pending_property_id = None
                self._game_model.properties_updated.emit()
                self.property_bought.emit(response)
            else:
                self.error_occurred.emit(response.get("message", "Ошибка покупки"))

        except Exception as e:
            self.error_occurred.emit(str(e))

    async def _do_decline_property(self, property_id: str) -> None:
        """Отказаться от покупки."""
        try:
            from shared.enums import PacketType

            await self._network.send_packet(
                PacketType.DECLINE_PROPERTY,
                {"property_id": property_id},
            )

            self._can_buy = False
            self._pending_property_id = None

        except Exception as e:
            self.error_occurred.emit(str(e))

    async def _do_build_house(self, property_id: str) -> None:
        """Построить дом."""
        try:
            from shared.enums import PacketType

            response = await self._network.send_request(
                PacketType.BUILD_HOUSE_REQUEST,
                {"property_id": property_id},
            )

            if response:
                self._game_model.properties_updated.emit()
                self.action_result.emit("build_house", response)

        except Exception as e:
            self.error_occurred.emit(str(e))

    async def _do_build_hotel(self, property_id: str) -> None:
        """Построить отель."""
        try:
            from shared.enums import PacketType

            response = await self._network.send_request(
                PacketType.BUILD_HOTEL_REQUEST,
                {"property_id": property_id},
            )

            if response:
                self._game_model.properties_updated.emit()
                self.action_result.emit("build_hotel", response)

        except Exception as e:
            self.error_occurred.emit(str(e))

    async def _do_mortgage(self, property_id: str) -> None:
        """Заложить."""
        try:
            from shared.enums import PacketType

            response = await self._network.send_request(
                PacketType.MORTGAGE_REQUEST,
                {"property_id": property_id},
            )

            if response:
                self._game_model.properties_updated.emit()
                self.action_result.emit("mortgage", response)

        except Exception as e:
            self.error_occurred.emit(str(e))

    async def _do_unmortgage(self, property_id: str) -> None:
        """Выкупить из залога."""
        try:
            from shared.enums import PacketType

            response = await self._network.send_request(
                PacketType.UNMORTGAGE_REQUEST,
                {"property_id": property_id},
            )

            if response:
                self._game_model.properties_updated.emit()
                self.action_result.emit("unmortgage", response)

        except Exception as e:
            self.error_occurred.emit(str(e))

    async def _do_end_turn(self) -> None:
        """Завершить ход."""
        try:
            from shared.enums import PacketType

            response = await self._network.send_request(
                PacketType.END_TURN_REQUEST,
                {"was_double": False},
            )

            self._can_end_turn = False
            self._can_roll_dice = False
            self._can_buy = False
            self._dice_rolled_this_turn = False
            self._pending_property_id = None

            if response:
                self.turn_ended.emit(response)

                if response.get("game_over"):
                    self.game_over.emit(response)

        except Exception as e:
            self.error_occurred.emit(str(e))

    async def _do_jail_action(self, action: str) -> None:
        """Действие в тюрьме."""
        try:
            from shared.enums import PacketType

            response = await self._network.send_request(
                PacketType.JAIL_ACTION_REQUEST,
                {"action": action},
            )

            if response:
                self.action_result.emit(f"jail_{action}", response)

        except Exception as e:
            self.error_occurred.emit(str(e))

    async def _do_veranda_action(self, action: str) -> None:
        """Действие на Веранде."""
        try:
            from shared.enums import PacketType

            response = await self._network.send_request(
                PacketType.VERANDA_ACTION_REQUEST,
                {"action": action},
            )

            if response:
                self.action_result.emit(f"veranda_{action}", response)

        except Exception as e:
            self.error_occurred.emit(str(e))

    async def _do_auction_bid(self, amount: int) -> None:
        """Ставка на аукционе."""
        try:
            from shared.enums import PacketType

            await self._network.send_packet(
                PacketType.AUCTION_BID_REQUEST,
                {"amount": amount},
            )

        except Exception as e:
            self.error_occurred.emit(str(e))

    async def _do_auction_pass(self) -> None:
        """Пас на аукционе."""
        try:
            from shared.enums import PacketType

            await self._network.send_packet(
                PacketType.AUCTION_BID_REQUEST,
                {"pass": True},
            )

        except Exception as e:
            self.error_occurred.emit(str(e))

    # ========================================================================
    # ОБНОВЛЕНИЕ СОСТОЯНИЯ
    # ========================================================================

    def on_turn_started(self, player_id: str) -> None:
        """
        Обработчик начала хода.

        Args:
            player_id: ID игрока, чей ход.
        """
        my_id = self._player_model.user_id
        is_my = my_id and str(my_id) == player_id

        self._can_roll_dice = is_my
        self._can_buy = False
        self._can_end_turn = False
        self._dice_rolled_this_turn = False
        self._pending_property_id = None

        self.action_result.emit("turn_started", {"player_id": player_id, "is_my_turn": is_my})

    def on_game_over(self, results: dict) -> None:
        """
        Обработчик завершения игры.

        Args:
            results: Результаты игры.
        """
        self._can_roll_dice = False
        self._can_buy = False
        self._can_end_turn = False
        self.game_over.emit(results)

    def reset(self) -> None:
        """Сбросить состояние."""
        self._can_roll_dice = False
        self._can_buy = False
        self._can_end_turn = False
        self._dice_rolled_this_turn = False
        self._pending_property_id = None