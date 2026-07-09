"""
client/network/reconnection_manager.py

Менеджер автоматического переподключения.

Обеспечивает:
- Обнаружение разрыва соединения
- Автоматические попытки переподключения
- Экспоненциальную задержку между попытками
- Восстановление сессии после переподключения

Python: 3.13+
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Coroutine, Optional
from uuid import UUID

from shared.constants import (
    RECONNECTION_WINDOW,
    MAX_RECONNECTION_ATTEMPTS as DEFAULT_MAX_ATTEMPTS,
    RECONNECTION_DELAY as DEFAULT_DELAY,
    RECONNECTION_BACKOFF_MULTIPLIER as DEFAULT_BACKOFF,
    RECONNECTION_MAX_DELAY as DEFAULT_MAX_DELAY,
)

logger = logging.getLogger("billionaire.client")


# ============================================================================
# ТИПЫ ОБРАТНЫХ ВЫЗОВОВ
# ============================================================================

# Обработчик переподключения
ReconnectCallback = Callable[[], Coroutine[Any, Any, bool]]

# Обработчик восстановления сессии
SessionRestoreCallback = Callable[[], Coroutine[Any, Any, bool]]


# ============================================================================
# МЕНЕДЖЕР ПЕРЕПОДКЛЮЧЕНИЯ
# ============================================================================

class ReconnectionManager:
    """
    Менеджер автоматического переподключения.

    При обрыве соединения пытается восстановить его
    с возрастающими интервалами. Поддерживает восстановление
    игровой сессии после переподключения.

    Usage:
        manager = ReconnectionManager()
        manager.set_reconnect_callback(my_reconnect_func)
        manager.set_session_restore_callback(my_restore_func)
        await manager.on_disconnect()
    """

    def __init__(
        self,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        initial_delay: float = DEFAULT_DELAY,
        backoff_multiplier: float = DEFAULT_BACKOFF,
        max_delay: float = DEFAULT_MAX_DELAY,
    ) -> None:
        """
        Инициализация менеджера переподключения.

        Args:
            max_attempts: Максимальное количество попыток.
            initial_delay: Начальная задержка (секунд).
            backoff_multiplier: Множитель задержки.
            max_delay: Максимальная задержка (секунд).
        """
        self._max_attempts: int = max_attempts
        self._initial_delay: float = initial_delay
        self._backoff_multiplier: float = backoff_multiplier
        self._max_delay: float = max_delay

        # Колбэки
        self._reconnect_callback: Optional[ReconnectCallback] = None
        self._session_restore_callback: Optional[SessionRestoreCallback] = None
        self._state_callback: Optional[Callable[[str], Coroutine[Any, Any, None]]] = None

        # Состояние
        self._is_reconnecting: bool = False
        self._current_attempt: int = 0
        self._should_reconnect: bool = True

        # Задача переподключения
        self._reconnect_task: Optional[asyncio.Task] = None

    # ========================================================================
    # НАСТРОЙКА
    # ========================================================================

    def set_reconnect_callback(self, callback: ReconnectCallback) -> None:
        """
        Установить функцию для переподключения.

        Args:
            callback: Асинхронная функция, возвращающая True при успехе.
        """
        self._reconnect_callback = callback

    def set_session_restore_callback(self, callback: SessionRestoreCallback) -> None:
        """
        Установить функцию для восстановления сессии.

        Args:
            callback: Асинхронная функция, возвращающая True при успехе.
        """
        self._session_restore_callback = callback

    def set_state_callback(
        self,
        callback: Callable[[str], Coroutine[Any, Any, None]],
    ) -> None:
        """
        Установить функцию для уведомления об изменении состояния.

        Args:
            callback: Асинхронная функция, принимающая строку состояния.
        """
        self._state_callback = callback

    # ========================================================================
    # ЗАПУСК / ОСТАНОВКА
    # ========================================================================

    async def on_disconnect(self) -> None:
        """
        Вызвать при обнаружении разрыва соединения.

        Запускает процесс переподключения.
        """
        if self._is_reconnecting:
            logger.debug("Переподключение уже выполняется")
            return

        self._is_reconnecting = True
        self._current_attempt = 0
        self._should_reconnect = True

        await self._notify_state("reconnecting")

        # Запускаем асинхронно
        self._reconnect_task = asyncio.create_task(self._reconnect_loop())

    def cancel(self) -> None:
        """Отменить переподключение."""
        self._should_reconnect = False
        self._is_reconnecting = False

        if self._reconnect_task:
            self._reconnect_task.cancel()
            self._reconnect_task = None

        logger.info("Переподключение отменено")

    # ========================================================================
    # ЦИКЛ ПЕРЕПОДКЛЮЧЕНИЯ
    # ========================================================================

    async def _reconnect_loop(self) -> None:
        """
        Основной цикл переподключения.

        Выполняет попытки с возрастающей задержкой.
        """
        logger.info(
            "Запущен цикл переподключения (макс. попыток: %d)",
            self._max_attempts,
        )

        while (
            self._should_reconnect
            and self._current_attempt < self._max_attempts
        ):
            self._current_attempt += 1

            # Вычисляем задержку (экспоненциальная)
            delay = min(
                self._initial_delay * (self._backoff_multiplier ** (self._current_attempt - 1)),
                self._max_delay,
            )

            logger.info(
                "Попытка переподключения %d/%d (задержка: %.1f сек)",
                self._current_attempt,
                self._max_attempts,
                delay,
            )

            await self._notify_state(
                f"reconnecting_{self._current_attempt}_{self._max_attempts}"
            )

            # Ждём перед попыткой
            await asyncio.sleep(delay)

            if not self._should_reconnect:
                break

            try:
                # Пытаемся переподключиться
                success = await self._try_reconnect()

                if success:
                    # Восстанавливаем сессию
                    await self._try_restore_session()

                    self._is_reconnecting = False
                    await self._notify_state("connected")
                    logger.info("Переподключение успешно!")
                    return

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Ошибка переподключения: %s", e)

        # Все попытки исчерпаны
        self._is_reconnecting = False
        await self._notify_state("disconnected")
        logger.warning(
            "Не удалось переподключиться после %d попыток",
            self._max_attempts,
        )

    async def _try_reconnect(self) -> bool:
        """
        Выполнить одну попытку переподключения.

        Returns:
            True, если подключение восстановлено.
        """
        if self._reconnect_callback is None:
            logger.warning("Не установлен callback переподключения")
            return False

        try:
            return await self._reconnect_callback()
        except Exception as e:
            logger.error("Ошибка в callback переподключения: %s", e)
            return False

    async def _try_restore_session(self) -> None:
        """
        Попытаться восстановить игровую сессию.
        """
        if self._session_restore_callback is None:
            return

        try:
            success = await self._session_restore_callback()
            if success:
                logger.info("Сессия восстановлена")
            else:
                logger.warning("Не удалось восстановить сессию")
        except Exception as e:
            logger.error("Ошибка восстановления сессии: %s", e)

    # ========================================================================
    # УВЕДОМЛЕНИЯ
    # ========================================================================

    async def _notify_state(self, state: str) -> None:
        """
        Уведомить об изменении состояния.

        Args:
            state: Новое состояние.
        """
        if self._state_callback:
            try:
                await self._state_callback(state)
            except Exception as e:
                logger.error("Ошибка в callback состояния: %s", e)

    # ========================================================================
    # ИНФОРМАЦИЯ
    # ========================================================================

    @property
    def is_reconnecting(self) -> bool:
        """Выполняется ли переподключение."""
        return self._is_reconnecting

    @property
    def current_attempt(self) -> int:
        """Текущая попытка."""
        return self._current_attempt

    @property
    def attempts_remaining(self) -> int:
        """Оставшиеся попытки."""
        return max(0, self._max_attempts - self._current_attempt)

    def get_stats(self) -> dict[str, Any]:
        """
        Получить статистику переподключения.

        Returns:
            Словарь с метриками.
        """
        return {
            "is_reconnecting": self._is_reconnecting,
            "current_attempt": self._current_attempt,
            "max_attempts": self._max_attempts,
            "attempts_remaining": self.attempts_remaining,
            "initial_delay": self._initial_delay,
            "max_delay": self._max_delay,
        }