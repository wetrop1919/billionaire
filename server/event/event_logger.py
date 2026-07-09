"""
server/event/event_logger.py

Логгер игровых событий.

Подписывается на EventBus и записывает все игровые события
в базу данных через EventRepository и в файловые логи.

Обеспечивает:
- Запись всех игровых событий в БД
- Дублирование в game.log
- Фильтрацию по важности
- Пакетную запись для производительности

Python: 3.13+
"""

from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

from shared.enums import EventType
from shared.logger_config import get_game_logger
from database.repositories.postgresql.event_repository import EventRepository

logger = get_game_logger()


# ============================================================================
# ЛОГГЕР СОБЫТИЙ
# ============================================================================

class EventLogger:
    """
    Логгер игровых событий.

    Подписывается на EventBus и сохраняет все события
    в базу данных и файловый лог.

    Usage:
        event_logger = EventLogger(event_repo)
        event_bus.subscribe("*", event_logger.handle_event)
    """

    # События, которые всегда пишутся в лог
    IMPORTANT_EVENTS: set[EventType] = {
        EventType.GAME_STARTED,
        EventType.GAME_FINISHED,
        EventType.PLAYER_BANKRUPT,
        EventType.PLAYER_JOINED,
        EventType.PLAYER_LEFT,
        EventType.PROPERTY_BOUGHT,
        EventType.HOUSE_BUILT,
        EventType.HOTEL_BUILT,
        EventType.TRADE_ACCEPTED,
        EventType.PLAYER_JAILED,
        EventType.ADMIN_ACTION,
    }

    def __init__(self, event_repository: EventRepository) -> None:
        """
        Инициализация логгера событий.

        Args:
            event_repository: Репозиторий для записи в БД.
        """
        self._event_repo = event_repository
        self._batch: list[dict[str, Any]] = []
        self._batch_size: int = 50

    # ========================================================================
    # ОБРАБОТКА СОБЫТИЙ
    # ========================================================================

    async def handle_event(
        self,
        event_type: EventType,
        data: dict[str, Any],
    ) -> None:
        """
        Обработать событие из EventBus.

        Записывает в БД и логирует важные события.

        Args:
            event_type: Тип события.
            data: Данные события.
        """
        # Логирование важных событий
        if event_type in self.IMPORTANT_EVENTS:
            self._log_event(event_type, data)

        # Запись в БД
        await self._record_to_database(event_type, data)

    async def handle_event_batch(
        self,
        events: list[tuple[EventType, dict[str, Any]]],
    ) -> None:
        """
        Обработать пакет событий.

        Args:
            events: Список кортежей (event_type, data).
        """
        for event_type, data in events:
            await self.handle_event(event_type, data)

    # ========================================================================
    # ВНУТРЕННИЕ МЕТОДЫ
    # ========================================================================

    def _log_event(
        self,
        event_type: EventType,
        data: dict[str, Any],
    ) -> None:
        """
        Записать событие в файловый лог.

        Args:
            event_type: Тип события.
            data: Данные события.
        """
        # Формируем читаемое сообщение
        game_id = data.get("game_id", "?")
        user_id = data.get("user_id", "system")
        description = self._get_description(event_type, data)

        logger.info(
            "[Игра %s] [Игрок %s] %s",
            str(game_id)[:8] if isinstance(game_id, UUID) else game_id,
            str(user_id)[:8] if isinstance(user_id, UUID) else user_id,
            description,
        )

    async def _record_to_database(
        self,
        event_type: EventType,
        data: dict[str, Any],
    ) -> None:
        """
        Записать событие в базу данных.

        Args:
            event_type: Тип события.
            data: Данные события.
        """
        game_id = data.get("game_id")
        if game_id is None:
            return

        if isinstance(game_id, str):
            game_id = UUID(game_id)

        user_id = data.get("user_id")
        if isinstance(user_id, str):
            user_id = UUID(user_id)
        elif user_id is not None and not isinstance(user_id, UUID):
            user_id = None

        target_id = data.get("target_id")
        if isinstance(target_id, UUID):
            target_id = str(target_id)

        turn_number = data.get("turn_number", 0)
        sequence = data.get("sequence", 0)

        event_data = {
            "game_id": game_id,
            "event_type": event_type.value,
            "user_id": user_id,
            "target_id": target_id,
            "data": data,
            "turn_number": turn_number,
            "sequence": sequence,
        }

        self._batch.append(event_data)

        # Сбрасываем батч при достижении лимита
        if len(self._batch) >= self._batch_size:
            await self._flush_batch()

    async def _flush_batch(self) -> None:
        """Сохранить накопленные события в БД."""
        if not self._batch:
            return

        try:
            await self._event_repo.log_game_events_batch(self._batch)
            logger.debug("Сохранено %d событий в БД", len(self._batch))
        except Exception as e:
            logger.error("Ошибка сохранения событий в БД: %s", e)
        finally:
            self._batch.clear()

    def _get_description(
        self,
        event_type: EventType,
        data: dict[str, Any],
    ) -> str:
        """
        Получить читаемое описание события.

        Args:
            event_type: Тип события.
            data: Данные.

        Returns:
            Строка описания.
        """
        descriptions = {
            EventType.GAME_STARTED: "Игра началась",
            EventType.GAME_FINISHED: "Игра завершена",
            EventType.GAME_PAUSED: "Игра на паузе",
            EventType.GAME_RESUMED: "Игра возобновлена",
            EventType.PLAYER_JOINED: "Игрок присоединился",
            EventType.PLAYER_LEFT: "Игрок покинул игру",
            EventType.PLAYER_RECONNECTED: "Игрок переподключился",
            EventType.PLAYER_DISCONNECTED: "Игрок отключился",
            EventType.TURN_STARTED: "Ход начался",
            EventType.TURN_ENDED: "Ход завершён",
            EventType.TURN_TIMEOUT: "Таймаут хода",
            EventType.DICE_ROLLED: f"Бросок кубиков: {data.get('die1', 0)} + {data.get('die2', 0)}",
            EventType.PLAYER_MOVED: f"Перемещение на клетку {data.get('to_cell', '?')}",
            EventType.PROPERTY_BOUGHT: f"Куплено: {data.get('property_name', '?')}",
            EventType.PROPERTY_DECLINED: f"Отказ от покупки: {data.get('property_name', '?')}",
            EventType.PROPERTY_AUCTIONED: f"Продано на аукционе: {data.get('property_name', '?')}",
            EventType.RENT_PAID: f"Аренда: {data.get('amount', 0)}$",
            EventType.HOUSE_BUILT: f"Дом построен на {data.get('property_name', '?')}",
            EventType.HOTEL_BUILT: f"Отель построен на {data.get('property_name', '?')}",
            EventType.PROPERTY_MORTGAGED: f"Заложено: {data.get('property_name', '?')}",
            EventType.PROPERTY_UNMORTGAGED: f"Выкуплено из залога: {data.get('property_name', '?')}",
            EventType.CARD_DRAWN: f"Карточка: {data.get('title', '?')}",
            EventType.CARD_ACTION_EXECUTED: f"Действие карточки выполнено",
            EventType.TRADE_OFFERED: "Предложена сделка",
            EventType.TRADE_ACCEPTED: "Сделка принята",
            EventType.TRADE_DECLINED: "Сделка отклонена",
            EventType.PLAYER_JAILED: "Игрок отправлен в тюрьму",
            EventType.PLAYER_FREED: "Игрок освобождён из тюрьмы",
            EventType.VERANDA_ENTERED: "Игрок попал на Веранду",
            EventType.VERANDA_EXITED: "Игрок покинул Веранду",
            EventType.PLAYER_BANKRUPT: "Игрок стал банкротом",
            EventType.ADMIN_ACTION: f"Действие администратора: {data.get('command', '?')}",
            EventType.SYSTEM_ERROR: f"Системная ошибка: {data.get('error', '?')}",
            EventType.NETWORK_ERROR: f"Сетевая ошибка: {data.get('error', '?')}",
        }

        return descriptions.get(
            event_type,
            f"Событие: {event_type.value}",
        )

    # ========================================================================
    # ЗАПРОСЫ К ИСТОРИИ
    # ========================================================================

    async def get_game_events(
        self,
        game_id: UUID,
        offset: int = 0,
        limit: int = 100,
        event_type: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """
        Получить события игры.

        Args:
            game_id: ID игры.
            offset: Смещение.
            limit: Лимит.
            event_type: Фильтр по типу.

        Returns:
            Список событий.
        """
        return await self._event_repo.get_game_events(
            game_id=game_id,
            offset=offset,
            limit=limit,
            event_type=event_type,
        )

    async def get_events_since(
        self,
        game_id: UUID,
        since_sequence: int,
    ) -> list[dict[str, Any]]:
        """
        Получить события начиная с указанного номера.

        Args:
            game_id: ID игры.
            since_sequence: Начальный порядковый номер.

        Returns:
            Список новых событий.
        """
        return await self._event_repo.get_game_events_since(
            game_id=game_id,
            since_sequence=since_sequence,
        )

    # ========================================================================
    # УПРАВЛЕНИЕ
    # ========================================================================

    async def flush(self) -> None:
        """Принудительно сохранить накопленные события."""
        await self._flush_batch()

    def set_batch_size(self, size: int) -> None:
        """
        Установить размер пакета для записи.

        Args:
            size: Количество событий для накопления.
        """
        if size < 1:
            raise ValueError("Размер пакета должен быть >= 1")
        self._batch_size = size

    def get_stats(self) -> dict:
        """
        Получить статистику логгера.

        Returns:
            Словарь с метриками.
        """
        return {
            "batch_size": self._batch_size,
            "pending_events": len(self._batch),
        }