"""
server/scheduler/scheduler.py

Планировщик периодических задач для сервера.

Обеспечивает:
- Выполнение задач по расписанию (интервальные)
- Отложенное выполнение (однократные таймауты)
- Управление жизненным циклом задач
- Мониторинг выполнения

Использует asyncio для неблокирующего выполнения.
Все задачи выполняются в фоне, не блокируя основной поток.

Python: 3.13+
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Optional
from uuid import UUID, uuid4

logger = logging.getLogger("billionaire.server")


# ============================================================================
# ЗАДАЧА
# ============================================================================

@dataclass(slots=True)
class ScheduledTask:
    """
    Описание запланированной задачи.

    Attributes:
        task_id: Уникальный идентификатор задачи.
        name: Человекочитаемое имя.
        coroutine: Асинхронная функция для выполнения.
        interval: Интервал в секундах (None = однократная).
        next_run: Время следующего запуска (Unix timestamp).
        last_run: Время последнего запуска.
        run_count: Количество выполнений.
        is_running: Выполняется ли сейчас.
        enabled: Включена ли задача.
    """

    task_id: UUID
    name: str
    coroutine: Callable[[], Coroutine[Any, Any, None]]
    interval: Optional[float] = None
    next_run: float = 0.0
    last_run: Optional[float] = None
    run_count: int = 0
    is_running: bool = False
    enabled: bool = True


# ============================================================================
# ПЛАНИРОВЩИК
# ============================================================================

class Scheduler:
    """
    Планировщик периодических и отложенных задач.

    Управляет выполнением фоновых задач сервера:
    - Автосохранение игр
    - Резервное копирование БД
    - Heartbeat / Ping
    - Очистка истёкших токенов
    - Очистка старых логов
    - Таймеры ходов и аукционов

    Usage:
        scheduler = Scheduler()
        scheduler.add_interval_task("backup", backup_coro, interval=300)
        scheduler.add_timeout_task("turn_timer", timeout_coro, delay=60)
        await scheduler.start()
    """

    def __init__(self) -> None:
        """Инициализация планировщика."""
        self._tasks: dict[UUID, ScheduledTask] = {}
        self._running: bool = False
        self._worker_task: Optional[asyncio.Task] = None
        self._check_interval: float = 0.5  # Интервал проверки очереди (сек)

    # ========================================================================
    # ДОБАВЛЕНИЕ ЗАДАЧ
    # ========================================================================

    def add_interval_task(
        self,
        name: str,
        coroutine: Callable[[], Coroutine[Any, Any, None]],
        interval: float,
        start_immediately: bool = False,
    ) -> UUID:
        """
        Добавить периодическую задачу.

        Args:
            name: Имя задачи (для логирования).
            coroutine: Асинхронная функция без аргументов.
            interval: Интервал в секундах.
            start_immediately: Запустить ли немедленно при старте.

        Returns:
            UUID задачи.
        """
        task_id = uuid4()
        now = time.time()

        task = ScheduledTask(
            task_id=task_id,
            name=name,
            coroutine=coroutine,
            interval=interval,
            next_run=now if start_immediately else now + interval,
        )

        self._tasks[task_id] = task

        logger.info(
            "Добавлена периодическая задача '%s' (id=%s, интервал=%.1f сек)",
            name,
            str(task_id)[:8],
            interval,
        )

        return task_id

    def add_timeout_task(
        self,
        name: str,
        coroutine: Callable[[], Coroutine[Any, Any, None]],
        delay: float,
    ) -> UUID:
        """
        Добавить отложенную задачу (выполняется один раз).

        Args:
            name: Имя задачи.
            coroutine: Асинхронная функция.
            delay: Задержка в секундах.

        Returns:
            UUID задачи.
        """
        task_id = uuid4()
        now = time.time()

        task = ScheduledTask(
            task_id=task_id,
            name=name,
            coroutine=coroutine,
            interval=None,  # Однократная
            next_run=now + delay,
        )

        self._tasks[task_id] = task

        logger.debug(
            "Добавлена отложенная задача '%s' (id=%s, задержка=%.1f сек)",
            name,
            str(task_id)[:8],
            delay,
        )

        return task_id

    def add_task_at(
        self,
        name: str,
        coroutine: Callable[[], Coroutine[Any, Any, None]],
        run_at: float,
    ) -> UUID:
        """
        Добавить задачу на конкретное время.

        Args:
            name: Имя задачи.
            coroutine: Асинхронная функция.
            run_at: Unix timestamp запуска.

        Returns:
            UUID задачи.
        """
        task_id = uuid4()

        task = ScheduledTask(
            task_id=task_id,
            name=name,
            coroutine=coroutine,
            interval=None,
            next_run=run_at,
        )

        self._tasks[task_id] = task

        logger.debug(
            "Добавлена задача '%s' на время %.1f",
            name,
            run_at,
        )

        return task_id

    # ========================================================================
    # УПРАВЛЕНИЕ ЗАДАЧАМИ
    # ========================================================================

    def cancel_task(self, task_id: UUID) -> bool:
        """
        Отменить задачу.

        Args:
            task_id: ID задачи.

        Returns:
            True, если задача удалена.
        """
        task = self._tasks.pop(task_id, None)
        if task:
            logger.debug("Задача '%s' отменена", task.name)
            return True
        return False

    def disable_task(self, task_id: UUID) -> bool:
        """
        Временно отключить задачу (без удаления).

        Args:
            task_id: ID задачи.

        Returns:
            True, если задача отключена.
        """
        task = self._tasks.get(task_id)
        if task:
            task.enabled = False
            logger.debug("Задача '%s' отключена", task.name)
            return True
        return False

    def enable_task(self, task_id: UUID) -> bool:
        """
        Включить отключённую задачу.

        Args:
            task_id: ID задачи.

        Returns:
            True, если задача включена.
        """
        task = self._tasks.get(task_id)
        if task:
            task.enabled = True
            task.next_run = time.time()  # Запуск при следующей проверке
            logger.debug("Задача '%s' включена", task.name)
            return True
        return False

    def reschedule_task(
        self,
        task_id: UUID,
        new_interval: float,
    ) -> bool:
        """
        Изменить интервал периодической задачи.

        Args:
            task_id: ID задачи.
            new_interval: Новый интервал в секундах.

        Returns:
            True, если интервал изменён.
        """
        task = self._tasks.get(task_id)
        if task and task.interval is not None:
            task.interval = new_interval
            logger.debug(
                "Интервал задачи '%s' изменён на %.1f сек",
                task.name,
                new_interval,
            )
            return True
        return False

    # ========================================================================
    # ЖИЗНЕННЫЙ ЦИКЛ
    # ========================================================================

    async def start(self) -> None:
        """
        Запустить планировщик.

        Создаёт фоновый воркер для проверки и выполнения задач.
        """
        if self._running:
            logger.warning("Планировщик уже запущен")
            return

        self._running = True
        self._worker_task = asyncio.create_task(self._worker_loop())

        logger.info(
            "Планировщик запущен (задач: %d)",
            len(self._tasks),
        )

    async def stop(self) -> None:
        """
        Остановить планировщик.

        Дожидается завершения текущих задач и останавливает воркер.
        """
        if not self._running:
            return

        logger.info("Остановка планировщика...")
        self._running = False

        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
            self._worker_task = None

        logger.info("Планировщик остановлен")

    async def _worker_loop(self) -> None:
        """
        Основной цикл планировщика.

        Периодически проверяет очередь задач и выполняет те,
        время которых наступило.
        """
        logger.debug("Воркер планировщика запущен")

        while self._running:
            try:
                now = time.time()

                # Находим задачи, готовые к выполнению
                tasks_to_run: list[ScheduledTask] = []
                for task in list(self._tasks.values()):
                    if task.enabled and not task.is_running and now >= task.next_run:
                        tasks_to_run.append(task)

                # Запускаем задачи
                for task in tasks_to_run:
                    asyncio.create_task(self._execute_task(task))

                await asyncio.sleep(self._check_interval)

            except asyncio.CancelledError:
                logger.debug("Воркер планировщика прерван")
                break
            except Exception as e:
                logger.error("Ошибка в воркере планировщика: %s", e)
                await asyncio.sleep(self._check_interval)

        logger.debug("Воркер планировщика завершён")

    async def _execute_task(self, task: ScheduledTask) -> None:
        """
        Выполнить задачу.

        Args:
            task: Задача для выполнения.
        """
        task.is_running = True
        task.last_run = time.time()

        try:
            logger.debug("Выполнение задачи '%s'...", task.name)
            await task.coroutine()
            task.run_count += 1
            logger.debug(
                "Задача '%s' выполнена (запуск #%d)",
                task.name,
                task.run_count,
            )

        except Exception as e:
            logger.error(
                "Ошибка выполнения задачи '%s': %s",
                task.name,
                e,
            )

        finally:
            task.is_running = False

            # Планируем следующий запуск
            if task.interval is not None:
                task.next_run = time.time() + task.interval
            else:
                # Однократная задача — удаляем после выполнения
                self._tasks.pop(task.task_id, None)
                logger.debug(
                    "Однократная задача '%s' удалена после выполнения",
                    task.name,
                )

    # ========================================================================
    # ИНФОРМАЦИЯ
    # ========================================================================

    @property
    def is_running(self) -> bool:
        """Запущен ли планировщик."""
        return self._running

    @property
    def task_count(self) -> int:
        """Количество активных задач."""
        return len(self._tasks)

    def get_task(self, task_id: UUID) -> Optional[dict]:
        """
        Получить информацию о задаче.

        Args:
            task_id: ID задачи.

        Returns:
            Словарь с данными задачи или None.
        """
        task = self._tasks.get(task_id)
        if task is None:
            return None

        return {
            "task_id": str(task.task_id),
            "name": task.name,
            "interval": task.interval,
            "next_run": task.next_run,
            "last_run": task.last_run,
            "run_count": task.run_count,
            "is_running": task.is_running,
            "enabled": task.enabled,
        }

    def get_all_tasks(self) -> list[dict]:
        """
        Получить список всех задач.

        Returns:
            Список словарей с данными задач.
        """
        return [
            {
                "task_id": str(task.task_id),
                "name": task.name,
                "interval": task.interval,
                "next_run": task.next_run,
                "last_run": task.last_run,
                "run_count": task.run_count,
                "is_running": task.is_running,
                "enabled": task.enabled,
            }
            for task in self._tasks.values()
        ]

    def get_stats(self) -> dict:
        """
        Получить статистику планировщика.

        Returns:
            Словарь с метриками.
        """
        total_runs = sum(t.run_count for t in self._tasks.values())
        running_now = sum(1 for t in self._tasks.values() if t.is_running)

        return {
            "running": self._running,
            "total_tasks": len(self._tasks),
            "interval_tasks": sum(1 for t in self._tasks.values() if t.interval is not None),
            "timeout_tasks": sum(1 for t in self._tasks.values() if t.interval is None),
            "total_runs": total_runs,
            "running_now": running_now,
            "enabled_tasks": sum(1 for t in self._tasks.values() if t.enabled),
        }