"""
client/main.py

Точка входа клиента «Миллиардер».

Запускает PySide6 приложение, инициализирует компоненты
через DI-контейнер и отображает главное окно.

Python: 3.13+
"""
import sys
from pathlib import Path

# Добавляем корень проекта в PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent.parent))


import asyncio
import logging
import signal
import sys as _sys
from typing import Optional

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer

from client.container import ClientContainer
from shared.logger_config import setup_all_loggers

logger = logging.getLogger("billionaire.client")


# ============================================================================
# ГЛОБАЛЬНЫЙ КОНТЕЙНЕР
# ============================================================================

container: ClientContainer = ClientContainer()


# ============================================================================
# ИНТЕГРАЦИЯ ASYNCIO С QT
# ============================================================================

class AsyncHelper:
    """
    Помощник для интеграции asyncio event loop с Qt event loop.

    Позволяет запускать асинхронные задачи из Qt приложения
    без блокировки главного потока.
    """

    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        """
        Инициализация помощника.

        Args:
            loop: Asyncio event loop.
        """
        self._loop = loop
        self._timer = QTimer()
        self._timer.timeout.connect(self._process_events)
        self._timer.setInterval(10)  # 10 мс

    def start(self) -> None:
        """Запустить обработку asyncio событий."""
        self._timer.start()

    def stop(self) -> None:
        """Остановить обработку."""
        self._timer.stop()

    def _process_events(self) -> None:
        """Обработать накопившиеся asyncio события."""
        self._loop.call_soon(lambda: None)
        self._loop.stop()
        self._loop.run_forever()


# ============================================================================
# ЗАПУСК ПРИЛОЖЕНИЯ
# ============================================================================

def setup_logging() -> None:
    """Настроить логирование клиента."""
    setup_all_loggers(
        log_dir="logs",
        log_level="INFO",
        console_output=True,
    )


def setup_signal_handlers(app: QApplication) -> None:
    """
    Настроить обработчики сигналов ОС.

    Args:
        app: Экземпляр QApplication.
    """
    def handle_interrupt():
        logger.info("Получен сигнал прерывания, завершение...")
        app.quit()

    signal.signal(signal.SIGINT, lambda s, f: handle_interrupt())
    signal.signal(signal.SIGTERM, lambda s, f: handle_interrupt())


def main() -> int:
    """
    Главная функция клиента.

    Returns:
        Код возврата (0 = успех).
    """
    # Настройка логирования
    setup_logging()

    logger.info("=" * 60)
    logger.info("  Клиент «Миллиардер» v1.0.0")
    logger.info("  Python 3.13+ | PySide6 | asyncio")
    logger.info("=" * 60)

    # Создаём Qt приложение
    app = QApplication(sys.argv)
    app.setApplicationName("Миллиардер")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("Billionaire Game")

    # Настройка сигналов
    setup_signal_handlers(app)

    # Создаём asyncio event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # Интеграция asyncio с Qt
    async_helper = AsyncHelper(loop)
    async_helper.start()

    try:
        # Инициализируем компоненты
        container.init()

        # Создаём и показываем главное окно
        main_window = container.create_main_window()
        main_window.show()

        logger.info("Главное окно отображено")

        # Загружаем ресурсы
        container.asset_manager.preload_common()

        # Запускаем главный цикл Qt
        exit_code = app.exec()

        # Корректное завершение
        async_helper.stop()
        container.shutdown()

        logger.info("Клиент завершил работу (код %d)", exit_code)
        return exit_code

    except KeyboardInterrupt:
        logger.info("Прерывание пользователем")
        return 0

    except Exception as e:
        logger.critical("Критическая ошибка клиента: %s", e, exc_info=True)
        return 1

    finally:
        loop.close()


# ============================================================================
# ТОЧКА ВХОДА
# ============================================================================

if __name__ == "__main__":
    sys.exit(main())
