"""
server/event/event_bus.py

Центральная шина событий (EventBus) для проекта «Миллиардер».

Обеспечивает:
- Публикацию событий (publish)
- Подписку на события (subscribe)
- Асинхронную доставку событий подписчикам
- Изоляцию отправителей от получателей

Никто не вызывает друг друга напрямую — все взаимодействия
проходят через EventBus. Это позволяет легко добавлять новых
подписчиков (логирование, статистика, достижения) без изменения
существующего кода.

Python: 3.13+
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Coroutine, Optional

from shared.enums import EventType

logger = logging.getLogger("billionaire.server")


# ============================================================================
# ТИПЫ ДЛЯ ОБРАБОТЧИКОВ
# ============================================================================

# Обработчик события — асинхронная функция, принимающая event_type и data
EventHandler = Callable[[EventType, dict[str, Any]], Coroutine[Any, Any, None]]

# Синхронный обработчик (для простых случаев)
SyncEventHandler = Callable[[EventType, dict[str, Any]], None]


# ============================================================================
# ШИНА СОБЫТИЙ
# ============================================================================

class EventBus:
    """
    Центральная шина событий.

    Реализует паттерн Publisher-Subscriber:
    - Издатели публикуют события через publish()
    - Подписчики регистрируются через subscribe()
    - Доставка происходит асинхронно

    Поддерживает:
    - Подписку на конкретный тип события
    - Подписку на все события (wildcard "*")
    - Приоритеты обработчиков
    - Асинхронные и синхронные обработчики

    Usage:
        bus = EventBus()
        bus.subscribe(EventType.DICE_ROLLED, my_handler)
        await bus.publish(EventType.DICE_ROLLED, {"player_id": "..."})
    """

    def __init__(self) -> None:
        """Инициализация шины событий."""
        # Словарь {event_type: list[(priority, handler)]}
        self._subscribers: dict[str, list[tuple[int, EventHandler]]] = {}

        # Словарь {event_type: list[sync_handler]}
        self._sync_subscribers: dict[str, list[SyncEventHandler]] = {}

        # Очередь для асинхронной доставки
        self._queue: asyncio.Queue[tuple[EventType, dict[str, Any]]] = asyncio.Queue(
            maxsize=10000
        )

        # Флаг работы
        self._running: bool = False

        # Задача-воркер
        self._worker_task: Optional[asyncio.Task] = None

    # ========================================================================
    # ПОДПИСКА
    # ========================================================================

    def subscribe(
        self,
        event_type: EventType | str,
        handler: EventHandler,
        priority: int = 0,
    ) -> None:
        """
        Подписаться на событие.

        Args:
            event_type: Тип события (EventType или "*" для всех).
            handler: Асинхронная функция-обработчик.
            priority: Приоритет (больше = раньше вызывается).
        """
        event_key = event_type.value if isinstance(event_type, EventType) else event_type

        if event_key not in self._subscribers:
            self._subscribers[event_key] = []

        self._subscribers[event_key].append((priority, handler))
        # Сортируем по приоритету (по убыванию)
        self._subscribers[event_key].sort(key=lambda x: x[0], reverse=True)

        logger.debug(
            "Подписка на событие '%s': %s (приоритет=%d)",
            event_key,
            handler.__name__ if hasattr(handler, "__name__") else str(handler),
            priority,
        )

    def subscribe_sync(
        self,
        event_type: EventType | str,
        handler: SyncEventHandler,
    ) -> None:
        """
        Подписаться на событие синхронно.

        Синхронные обработчики выполняются немедленно при publish(),
        до асинхронной доставки. Полезно для быстрых операций
        (например, обновление счётчика).

        Args:
            event_type: Тип события.
            handler: Синхронная функция.
        """
        event_key = event_type.value if isinstance(event_type, EventType) else event_type

        if event_key not in self._sync_subscribers:
            self._sync_subscribers[event_key] = []

        self._sync_subscribers[event_key].append(handler)

    def unsubscribe(
        self,
        event_type: EventType | str,
        handler: EventHandler,
    ) -> bool:
        """
        Отписаться от события.

        Args:
            event_type: Тип события.
            handler: Ранее зарегистрированный обработчик.

        Returns:
            True, если обработчик был удалён.
        """
        event_key = event_type.value if isinstance(event_type, EventType) else event_type

        subscribers = self._subscribers.get(event_key, [])
        for i, (_, h) in enumerate(subscribers):
            if h is handler:
                subscribers.pop(i)
                logger.debug("Отписка от события '%s'", event_key)
                return True

        return False

    # ========================================================================
    # ПУБЛИКАЦИЯ
    # ========================================================================

    async def publish(
        self,
        event_type: EventType,
        data: dict[str, Any] | None = None,
        immediate: bool = False,
    ) -> None:
        """
        Опубликовать событие.

        Args:
            event_type: Тип события.
            data: Данные события (словарь).
            immediate: Если True — обработать синхронно (не через очередь).
        """
        event_data = data or {}

        if immediate:
            # Синхронная обработка
            await self._deliver(event_type, event_data)
        else:
            # Асинхронная обработка через очередь
            try:
                self._queue.put_nowait((event_type, event_data))
            except asyncio.QueueFull:
                logger.warning(
                    "Очередь событий переполнена! Событие %s отброшено.",
                    event_type.value,
                )

    async def publish_many(
        self,
        events: list[tuple[EventType, dict[str, Any]]],
    ) -> None:
        """
        Опубликовать несколько событий.

        Args:
            events: Список кортежей (event_type, data).
        """
        for event_type, data in events:
            await self.publish(event_type, data)

    # ========================================================================
    # УПРАВЛЕНИЕ ЖИЗНЕННЫМ ЦИКЛОМ
    # ========================================================================

    async def start(self) -> None:
        """
        Запустить обработку событий.

        Создаёт фоновую задачу-воркер, которая разбирает очередь
        и доставляет события подписчикам.
        """
        if self._running:
            logger.warning("EventBus уже запущен")
            return

        self._running = True
        self._worker_task = asyncio.create_task(self._worker_loop())
        logger.info("EventBus запущен")

    async def stop(self) -> None:
        """
        Остановить обработку событий.

        Дожидается завершения текущих событий в очереди,
        затем останавливает воркер.
        """
        if not self._running:
            return

        logger.info("Остановка EventBus...")
        self._running = False

        # Даём сигнал воркеру завершиться
        try:
            self._queue.put_nowait((EventType.GAME_FINISHED, {"_shutdown": True}))
        except asyncio.QueueFull:
            pass

        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
            self._worker_task = None

        logger.info("EventBus остановлен")

    async def _worker_loop(self) -> None:
        """
        Основной цикл воркера.

        Извлекает события из очереди и доставляет подписчикам.
        """
        logger.debug("Воркер EventBus запущен")

        while self._running:
            try:
                # Ждём событие с таймаутом
                event_type, data = await asyncio.wait_for(
                    self._queue.get(), timeout=1.0
                )

                # Проверка на shutdown
                if data.get("_shutdown"):
                    continue

                # Доставляем событие
                await self._deliver(event_type, data)

            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                logger.debug("Воркер EventBus прерван")
                break
            except Exception as e:
                logger.error("Ошибка в воркере EventBus: %s", e)

        logger.debug("Воркер EventBus завершён")

    # ========================================================================
    # ДОСТАВКА СОБЫТИЙ
    # ========================================================================

    async def _deliver(
        self,
        event_type: EventType,
        data: dict[str, Any],
    ) -> None:
        """
        Доставить событие всем подписчикам.

        Args:
            event_type: Тип события.
            data: Данные события.
        """
        # Сначала синхронные обработчики
        self._deliver_sync(event_type, data)

        # Затем асинхронные
        await self._deliver_async(event_type, data)

    def _deliver_sync(
        self,
        event_type: EventType,
        data: dict[str, Any],
    ) -> None:
        """
        Доставить событие синхронным обработчикам.

        Args:
            event_type: Тип события.
            data: Данные.
        """
        handlers = self._sync_subscribers.get(event_type.value, [])
        # Добавляем wildcard-обработчики
        handlers.extend(self._sync_subscribers.get("*", []))

        for handler in handlers:
            try:
                handler(event_type, data)
            except Exception as e:
                logger.error(
                    "Ошибка в синхронном обработчике %s для события %s: %s",
                    handler.__name__ if hasattr(handler, "__name__") else str(handler),
                    event_type.value,
                    e,
                )

    async def _deliver_async(
        self,
        event_type: EventType,
        data: dict[str, Any],
    ) -> None:
        """
        Доставить событие асинхронным обработчикам.

        Args:
            event_type: Тип события.
            data: Данные.
        """
        handlers = self._subscribers.get(event_type.value, [])
        # Добавляем wildcard-обработчики
        handlers.extend(self._subscribers.get("*", []))

        # Сортируем по приоритету
        handlers.sort(key=lambda x: x[0], reverse=True)

        for _, handler in handlers:
            try:
                await handler(event_type, data)
            except Exception as e:
                logger.error(
                    "Ошибка в обработчике %s для события %s: %s",
                    handler.__name__ if hasattr(handler, "__name__") else str(handler),
                    event_type.value,
                    e,
                )

    # ========================================================================
    # ИНФОРМАЦИЯ
    # ========================================================================

    @property
    def is_running(self) -> bool:
        """Запущена ли шина."""
        return self._running

    @property
    def queue_size(self) -> int:
        """Размер очереди событий."""
        return self._queue.qsize()

    def get_subscriber_count(self, event_type: EventType | str | None = None) -> int:
        """
        Получить количество подписчиков.

        Args:
            event_type: Тип события (None = всего).

        Returns:
            Количество подписчиков.
        """
        if event_type is None:
            total = sum(len(h) for h in self._subscribers.values())
            total += sum(len(h) for h in self._sync_subscribers.values())
            return total

        event_key = event_type.value if isinstance(event_type, EventType) else event_type
        async_count = len(self._subscribers.get(event_key, []))
        sync_count = len(self._sync_subscribers.get(event_key, []))
        return async_count + sync_count

    def get_stats(self) -> dict:
        """
        Получить статистику шины.

        Returns:
            Словарь с метриками.
        """
        return {
            "running": self._running,
            "queue_size": self.queue_size,
            "total_subscribers": self.get_subscriber_count(),
            "event_types": len(self._subscribers),
        }