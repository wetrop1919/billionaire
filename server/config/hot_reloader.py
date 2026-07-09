"""
server/config/hot_reloader.py

Модуль горячей перезагрузки конфигураций.

Отслеживает изменения JSON-файлов конфигурации и автоматически
перезагружает их без остановки сервера. Использует asyncio
для периодической проверки файлов.

Python: 3.13+
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger("billionaire.server")


# ============================================================================
# ГОРЯЧАЯ ПЕРЕЗАГРУЗКА
# ============================================================================

class HotReloader:
    """
    Отслеживание изменений конфигурационных файлов.

    Периодически проверяет время модификации файлов и
    вызывает callback при обнаружении изменений.

    Attributes:
        configs_dir: Директория с конфигурациями.
        check_interval: Интервал проверки в секундах.
        _watched_files: Словарь {путь: время_модификации}.
        _callbacks: Список функций обратного вызова.
        _task: Асинхронная задача отслеживания.
        _running: Флаг работы.
    """

    def __init__(
        self,
        configs_dir: str = "configs",
        check_interval: float = 5.0,
    ) -> None:
        """
        Инициализация отслеживателя.

        Args:
            configs_dir: Путь к директории с конфигурациями.
            check_interval: Интервал проверки в секундах.
        """
        self.configs_dir: Path = Path(configs_dir)
        self.check_interval: float = check_interval
        self._watched_files: dict[str, float] = {}
        self._callbacks: list[Callable[[str], None]] = []
        self._task: Optional[asyncio.Task] = None
        self._running: bool = False

    # ========================================================================
    # УПРАВЛЕНИЕ ОТСЛЕЖИВАНИЕМ
    # ========================================================================

    async def start(self) -> None:
        """
        Запустить отслеживание изменений.

        Сканирует директорию конфигураций, запоминает время
        модификации всех JSON-файлов и запускает фоновую задачу.
        """
        if self._running:
            logger.warning("HotReloader уже запущен")
            return

        logger.info(
            "Запуск HotReloader (директория: %s, интервал: %.1f сек)",
            self.configs_dir.absolute(),
            self.check_interval,
        )

        # Сканируем файлы
        self._scan_files()

        # Запускаем задачу
        self._running = True
        self._task = asyncio.create_task(self._watch_loop())

    async def stop(self) -> None:
        """
        Остановить отслеживание изменений.
        """
        if not self._running:
            return

        logger.info("Остановка HotReloader")
        self._running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        self._watched_files.clear()

    def add_callback(self, callback: Callable[[str], None]) -> None:
        """
        Добавить функцию обратного вызова.

        Callback вызывается при обнаружении изменений в любом файле.
        Принимает один аргумент — путь к изменённому файлу.

        Args:
            callback: Асинхронная или синхронная функция.
        """
        if callback not in self._callbacks:
            self._callbacks.append(callback)
            logger.debug("Добавлен callback для HotReloader")

    def remove_callback(self, callback: Callable[[str], None]) -> None:
        """
        Удалить функцию обратного вызова.

        Args:
            callback: Ранее добавленная функция.
        """
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    # ========================================================================
    # ВНУТРЕННИЕ МЕТОДЫ
    # ========================================================================

    async def _watch_loop(self) -> None:
        """
        Основной цикл отслеживания.

        Периодически проверяет изменения файлов и вызывает callbacks.
        """
        logger.debug("Цикл HotReloader запущен")

        while self._running:
            try:
                changed_files = self._check_changes()

                if changed_files:
                    logger.info(
                        "Обнаружены изменения в %d файлах: %s",
                        len(changed_files),
                        ", ".join(changed_files),
                    )

                    for file_path in changed_files:
                        await self._notify_callbacks(file_path)

                await asyncio.sleep(self.check_interval)

            except asyncio.CancelledError:
                logger.debug("Цикл HotReloader прерван")
                break
            except Exception as e:
                logger.error("Ошибка в цикле HotReloader: %s", e)
                await asyncio.sleep(self.check_interval)

        logger.debug("Цикл HotReloader завершён")

    def _scan_files(self) -> None:
        """
        Сканировать директорию конфигураций и запомнить времена модификации.
        """
        self._watched_files.clear()

        if not self.configs_dir.exists():
            logger.warning("Директория конфигураций не найдена: %s", self.configs_dir)
            return

        json_files = list(self.configs_dir.rglob("*.json"))
        for file_path in json_files:
            try:
                mtime = os.path.getmtime(file_path)
                relative_path = str(file_path.relative_to(self.configs_dir))
                self._watched_files[relative_path] = mtime
            except OSError as e:
                logger.warning("Не удалось прочитать файл %s: %s", file_path, e)

        logger.debug(
            "Просканировано %d JSON-файлов", len(self._watched_files)
        )

    def _check_changes(self) -> list[str]:
        """
        Проверить изменения в отслеживаемых файлах.

        Returns:
            Список относительных путей к изменённым файлам.
        """
        changed: list[str] = []

        # Проверяем существующие файлы
        for relative_path, old_mtime in list(self._watched_files.items()):
            full_path = self.configs_dir / relative_path

            if not full_path.exists():
                # Файл удалён
                changed.append(relative_path)
                del self._watched_files[relative_path]
                continue

            try:
                new_mtime = os.path.getmtime(full_path)
                if new_mtime != old_mtime:
                    changed.append(relative_path)
                    self._watched_files[relative_path] = new_mtime
            except OSError:
                continue

        # Проверяем новые файлы
        json_files = list(self.configs_dir.rglob("*.json"))
        for file_path in json_files:
            relative_path = str(file_path.relative_to(self.configs_dir))
            if relative_path not in self._watched_files:
                try:
                    mtime = os.path.getmtime(file_path)
                    self._watched_files[relative_path] = mtime
                    changed.append(relative_path)
                except OSError:
                    pass

        return changed

    async def _notify_callbacks(self, file_path: str) -> None:
        """
        Вызвать все функции обратного вызова.

        Args:
            file_path: Путь к изменённому файлу.
        """
        for callback in self._callbacks:
            try:
                result = callback(file_path)
                # Поддерживаем как синхронные, так и асинхронные callbacks
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error(
                    "Ошибка в callback HotReloader для %s: %s",
                    file_path,
                    e,
                )

    # ========================================================================
    # ИНФОРМАЦИЯ
    # ========================================================================

    @property
    def is_running(self) -> bool:
        """Запущено ли отслеживание."""
        return self._running

    @property
    def watched_count(self) -> int:
        """Количество отслеживаемых файлов."""
        return len(self._watched_files)

    def get_watched_files(self) -> list[str]:
        """
        Получить список отслеживаемых файлов.

        Returns:
            Список относительных путей.
        """
        return sorted(self._watched_files.keys())

    def get_status(self) -> dict:
        """
        Получить статус HotReloader.

        Returns:
            Словарь с информацией о состоянии.
        """
        return {
            "running": self._running,
            "configs_dir": str(self.configs_dir.absolute()),
            "check_interval": self.check_interval,
            "watched_files": self.watched_count,
            "callbacks": len(self._callbacks),
        }