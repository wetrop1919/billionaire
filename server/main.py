"""
server/main.py

Точка входа сервера «Миллиардер».

Запускает сервер, инициализирует все компоненты через DI-контейнер,
восстанавливает незавершённые игры после сбоев, настраивает
периодические задачи и обрабатывает graceful shutdown.

Python: 3.13+
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from pathlib import Path

from server.container import ServerContainer

logger = logging.getLogger("billionaire.server")


# ============================================================================
# ГЛОБАЛЬНЫЙ КОНТЕЙНЕР
# ============================================================================

container: ServerContainer = ServerContainer()


# ============================================================================
# ОБРАБОТЧИКИ СИГНАЛОВ
# ============================================================================

def handle_signal(signum: int) -> None:
    """
    Обработчик системных сигналов (SIGINT, SIGTERM).

    Args:
        signum: Номер сигнала.
    """
    signal_name = signal.Signals(signum).name
    logger.info("Получен сигнал %s, завершение работы...", signal_name)

    # Планируем остановку
    asyncio.create_task(shutdown_server())


async def shutdown_server() -> None:
    """Корректно завершить работу сервера."""
    logger.info("Начало процедуры завершения...")

    # Сохраняем активные игры
    if container.game_manager:
        count = await container.game_manager.save_all_active_games()
        if count > 0:
            logger.info("Сохранено %d активных игр", count)

    # Создаём финальный бэкап
    if container.backup_manager:
        await container.backup_manager.create_backup(backup_type="full")

    # Завершаем все компоненты
    await container.shutdown()

    logger.info("Сервер остановлен. До свидания!")


# ============================================================================
# НАСТРОЙКА ПЕРИОДИЧЕСКИХ ЗАДАЧ
# ============================================================================

def setup_scheduled_tasks() -> None:
    """
    Настроить периодические задачи в планировщике.

    - Автосохранение игр (каждые 30 секунд)
    - Резервное копирование БД (каждые 5 минут)
    - Очистка истёкших токенов (каждый час)
    - Очистка старых логов (каждые 24 часа)
    - Очистка пустых комнат (каждые 10 минут)
    - Heartbeat-проверка (каждые 15 секунд)
    """
    scheduler = container.scheduler

    # Автосохранение игр
    scheduler.add_interval_task(
        name="autosave_games",
        coroutine=lambda: container.game_manager.save_all_active_games(),
        interval=30,
        start_immediately=False,
    )

    # Очистка истёкших токенов
    scheduler.add_interval_task(
        name="cleanup_tokens",
        coroutine=lambda: container.token_manager.cleanup_expired_tokens() if container.token_manager else None,
        interval=3600,
        start_immediately=False,
    )

    # Очистка пустых комнат
    scheduler.add_interval_task(
        name="cleanup_rooms",
        coroutine=lambda: container.room_manager.cleanup_empty_rooms(60) if container.room_manager else None,
        interval=600,
        start_immediately=False,
    )

    # Очистка старых логов
    scheduler.add_interval_task(
        name="cleanup_logs",
        coroutine=lambda: container.event_repo.cleanup_all_old_logs() if container.event_repo else None,
        interval=86400,
        start_immediately=False,
    )

    # Отключение неактивных сессий
    scheduler.add_interval_task(
        name="cleanup_sessions",
        coroutine=lambda: container.session_manager.disconnect_idle_sessions() if container.session_manager else None,
        interval=300,
        start_immediately=False,
    )

    # Очистка rate limiter
    scheduler.add_interval_task(
        name="cleanup_rate_limits",
        coroutine=lambda: container.rate_limiter.cleanup_expired() if container.rate_limiter else None,
        interval=60,
        start_immediately=False,
    )

    logger.info("Периодические задачи настроены (6 задач)")


# ============================================================================
# ЗАГРУЗКА ИГРОВЫХ ДАННЫХ
# ============================================================================

async def load_game_data() -> None:
    """Загрузить игровые данные из конфигураций."""
    config_mgr = container.config_manager

    logger.info("Загрузка игровых данных...")

    # Загружаем всё через ConfigManager
    await config_mgr.load_all()

    # Обновляем данные в контейнере
    container.property_defs = await config_mgr.get_properties()
    container.chance_cards = await config_mgr.get_chance_cards()
    container.fund_cards = await config_mgr.get_fund_cards()
    game_rules = await config_mgr.get_game_rules()
    board = await config_mgr.get_game_board()

    logger.info(
        "Загружено: %d свойств, %d карточек Шанс, %d карточек Фонд, "
        "игровое поле (%d клеток)",
        len(container.property_defs),
        len(container.chance_cards),
        len(container.fund_cards),
        board.board_size,
    )


# ============================================================================
# ВОССТАНОВЛЕНИЕ ПОСЛЕ СБОЕВ
# ============================================================================

async def recover_from_crash() -> None:
    """Восстановить незавершённые игры после перезапуска сервера."""
    recovery = container.crash_recovery

    logger.info("Проверка необходимости восстановления после сбоя...")

    result = await recovery.recover_all()

    if result["recovered"] > 0:
        logger.info(
            "Восстановлено %d игр после сбоя",
            result["recovered"],
        )
    else:
        logger.info("Незавершённых игр не найдено")


# ============================================================================
# ТОЧКА ВХОДА
# ============================================================================

async def main() -> None:
    """
    Главная функция сервера.

    Порядок запуска:
    1. Инициализация DI-контейнера
    2. Загрузка игровых данных
    3. Восстановление после сбоев
    4. Настройка периодических задач
    5. Запуск TCP-сервера
    """
    logger.info("=" * 60)
    logger.info("  Сервер «Миллиардер» v1.0.0")
    logger.info("  Python 3.13+ | asyncio | PostgreSQL | SSL")
    logger.info("=" * 60)

    try:
        # 1. Инициализация компонентов
        logger.info("Инициализация компонентов сервера...")
        await container.init()

        # 2. Загрузка игровых данных
        await load_game_data()

        # 3. Восстановление после сбоев
        await recover_from_crash()

        # 4. Настройка периодических задач
        setup_scheduled_tasks()

        # 5. Запуск планировщика
        await container.scheduler.start()

        # 6. Запуск EventBus
        await container.event_bus.start()

        # 7. Запуск TCP-сервера (блокирующий вызов)
        logger.info(
            "Сервер готов к работе на %s:%d",
            container.env_config.SERVER_HOST,
            container.env_config.SERVER_PORT,
        )

        await container.tcp_server.start()

    except KeyboardInterrupt:
        logger.info("Получен сигнал прерывания (Ctrl+C)")
        await shutdown_server()

    except Exception as e:
        logger.critical("Критическая ошибка сервера: %s", e, exc_info=True)
        await shutdown_server()
        sys.exit(1)


# ============================================================================
# ЗАПУСК
# ============================================================================

if __name__ == "__main__":
    # Регистрируем обработчики сигналов
    signal.signal(signal.SIGINT, lambda s, f: handle_signal(s))
    signal.signal(signal.SIGTERM, lambda s, f: handle_signal(s))

    # Запускаем asyncio
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.critical("Необработанная ошибка: %s", e, exc_info=True)
        sys.exit(1)