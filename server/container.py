"""
server/container.py

Dependency Injection контейнер сервера.

Создаёт и связывает все компоненты сервера:
- База данных и репозитории
- Аутентификация и токены
- Сетевой слой и middleware
- Игровой движок и менеджеры
- Планировщик и бэкапы

Обеспечивает централизованное управление зависимостями
и порядком инициализации компонентов.

Python: 3.13+
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from shared.env_config import EnvConfig, load_env_config
from shared.logger_config import setup_all_loggers, LogManager
from shared.models.property import Property
from shared.models.card import Card

from database.connection import DatabaseConnection
from database.repositories.postgresql.user_repository import UserRepository
from database.repositories.postgresql.room_repository import RoomRepository
from database.repositories.postgresql.game_repository import GameRepository
from database.repositories.postgresql.chat_repository import ChatRepository
from database.repositories.postgresql.event_repository import EventRepository

from server.auth.token_manager import TokenManager
from server.auth.auth_manager import AuthManager

from server.middleware.packet_validator import PacketValidator
from server.middleware.rate_limiter import RateLimiter
from server.middleware.security_middleware import SecurityMiddleware

from server.event.event_bus import EventBus
from server.event.event_logger import EventLogger
from server.event.replay_manager import ReplayManager

from server.scheduler.scheduler import Scheduler

from server.network.ssl_context import SSLContextFactory
from server.network.session_manager import SessionManager
from server.network.message_dispatcher import MessageDispatcher
from server.network.tcp_server import TCPServer

from server.room.observer_manager import ObserverManager
from server.room.room_manager import RoomManager

from server.chat.chat_manager import ChatManager

from server.game.auction_manager import AuctionManager
from server.game.trade_manager import TradeManager
from server.game.jail_manager import JailManager
from server.game.veranda_manager import VerandaManager
from server.game.bankruptcy_manager import BankruptcyManager
from server.game.undo_stack import UndoStack
from server.game.game_engine import GameEngine
from server.game.turn_manager import TurnManager
from server.game.game_loop import GameLoop
from server.game.game_manager import GameManager

from server.admin.admin_commands import AdminCommands

from server.backup.autosave import AutosaveManager
from server.backup.backup_manager import BackupManager
from server.backup.crash_recovery import CrashRecovery

from server.config.config_manager import ConfigManager
from server.config.hot_reloader import HotReloader

logger = logging.getLogger("billionaire.server")


# ============================================================================
# DI-КОНТЕЙНЕР
# ============================================================================

@dataclass(slots=True)
class ServerContainer:
    """
    Контейнер зависимостей сервера.

    Создаёт и хранит все компоненты сервера в правильном порядке.
    Компоненты создаются лениво при первом обращении.

    Usage:
        container = ServerContainer()
        await container.init()
        await container.tcp_server.start()
    """

    # Конфигурация
    env_config: EnvConfig = field(default_factory=load_env_config)
    config_manager: Optional[ConfigManager] = None

    # База данных
    db_connection: Optional[DatabaseConnection] = None
    user_repo: Optional[UserRepository] = None
    room_repo: Optional[RoomRepository] = None
    game_repo: Optional[GameRepository] = None
    chat_repo: Optional[ChatRepository] = None
    event_repo: Optional[EventRepository] = None

    # Аутентификация
    token_manager: Optional[TokenManager] = None
    auth_manager: Optional[AuthManager] = None

    # Middleware
    packet_validator: Optional[PacketValidator] = None
    rate_limiter: Optional[RateLimiter] = None
    security_middleware: Optional[SecurityMiddleware] = None

    # События
    event_bus: Optional[EventBus] = None
    event_logger: Optional[EventLogger] = None
    replay_manager: Optional[ReplayManager] = None

    # Планировщик
    scheduler: Optional[Scheduler] = None

    # Сеть
    ssl_context: Optional[object] = None
    session_manager: Optional[SessionManager] = None
    message_dispatcher: Optional[MessageDispatcher] = None
    tcp_server: Optional[TCPServer] = None

    # Комнаты
    observer_manager: Optional[ObserverManager] = None
    room_manager: Optional[RoomManager] = None

    # Чат
    chat_manager: Optional[ChatManager] = None

    # Игра
    auction_manager: Optional[AuctionManager] = None
    trade_manager: Optional[TradeManager] = None
    jail_manager: Optional[JailManager] = None
    veranda_manager: Optional[VerandaManager] = None
    bankruptcy_manager: Optional[BankruptcyManager] = None
    undo_stack: Optional[UndoStack] = None
    game_engine: Optional[GameEngine] = None
    turn_manager: Optional[TurnManager] = None
    game_manager: Optional[GameManager] = None

    # Админ
    admin_commands: Optional[AdminCommands] = None

    # Бэкапы
    autosave_manager: Optional[AutosaveManager] = None
    backup_manager: Optional[BackupManager] = None
    crash_recovery: Optional[CrashRecovery] = None

    # Игровые данные
    property_defs: dict[str, Property] = field(default_factory=dict)
    chance_cards: list[Card] = field(default_factory=list)
    fund_cards: list[Card] = field(default_factory=list)

    # Статус
    _initialized: bool = False

    # ========================================================================
    # ИНИЦИАЛИЗАЦИЯ
    # ========================================================================

    async def init(self) -> None:
        """
        Инициализировать все компоненты сервера.

        Порядок инициализации важен:
        1. Логирование
        2. Конфигурация
        3. База данных
        4. Базовые сервисы (токены, события, планировщик)
        5. Middleware и сеть
        6. Игровые компоненты
        7. Админ и бэкапы
        """
        if self._initialized:
            logger.warning("Контейнер уже инициализирован")
            return

        logger.info("Инициализация серверных компонентов...")

        # 1. Логирование
        setup_all_loggers(
            log_dir=self.env_config.LOG_DIR,
            log_level=self.env_config.LOG_LEVEL,
            console_output=self.env_config.DEBUG,
        )

        # 2. Конфигурация
        await self._init_config()

        # 3. База данных
        await self._init_database()

        # 4. Базовые сервисы
        self._init_auth()
        self._init_events()
        self._init_scheduler()

        # 5. Middleware и сеть
        self._init_middleware()
        self._init_network()

        # 6. Игровые данные и компоненты
        await self._init_game_data()
        self._init_game_components()

        # 7. Админ и бэкапы
        self._init_admin()
        self._init_backup()

        self._initialized = True
        logger.info("Все компоненты сервера инициализированы")

    async def shutdown(self) -> None:
        """
        Корректно завершить работу всех компонентов.
        """
        logger.info("Завершение работы серверных компонентов...")

        # Останавливаем TCP-сервер
        if self.tcp_server:
            await self.tcp_server.stop()

        # Останавливаем планировщик
        if self.scheduler:
            await self.scheduler.stop()

        # Останавливаем EventBus
        if self.event_bus:
            await self.event_bus.stop()

        # Сохраняем игры
        if self.game_manager:
            await self.game_manager.save_all_active_games()

        # Закрываем БД
        if self.db_connection:
            await self.db_connection.disconnect()

        # Завершаем логирование
        LogManager.shutdown()

        self._initialized = False
        logger.info("Сервер остановлен")

    # ========================================================================
    # ПРИВАТНЫЕ МЕТОДЫ ИНИЦИАЛИЗАЦИИ
    # ========================================================================

    async def _init_config(self) -> None:
        """Инициализация конфигурации."""
        self.config_manager = ConfigManager(self.env_config.CONFIGS_DIR)
        await self.config_manager.load_all()

    async def _init_database(self) -> None:
        """Инициализация базы данных и репозиториев."""
        self.db_connection = DatabaseConnection(
            database_url=self.env_config.DATABASE_URL,
            pool_size=self.env_config.DB_POOL_SIZE,
            max_overflow=self.env_config.DB_MAX_OVERFLOW,
        )
        await self.db_connection.connect()

        # Создаём репозитории с одной сессией
        async with self.db_connection.session() as session:
            self.user_repo = UserRepository(session)
            self.room_repo = RoomRepository(session)
            self.game_repo = GameRepository(session)
            self.chat_repo = ChatRepository(session)
            self.event_repo = EventRepository(session)

    def _init_auth(self) -> None:
        """Инициализация аутентификации."""
        self.token_manager = TokenManager(
            access_token_expire=self.env_config.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            refresh_token_expire=self.env_config.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        )
        self.auth_manager = AuthManager(self.user_repo, self.token_manager)

    def _init_events(self) -> None:
        """Инициализация шины событий и логгеров."""
        self.event_bus = EventBus()
        self.event_logger = EventLogger(self.event_repo)
        self.replay_manager = ReplayManager(self.event_repo)

        # Подписываем логгеры на события
        self.event_bus.subscribe("*", self.event_logger.handle_event)  # type: ignore[arg-type]
        self.event_bus.subscribe("*", self.replay_manager.handle_event)  # type: ignore[arg-type]

    def _init_scheduler(self) -> None:
        """Инициализация планировщика."""
        self.scheduler = Scheduler()

    def _init_middleware(self) -> None:
        """Инициализация middleware."""
        self.packet_validator = PacketValidator()
        self.rate_limiter = RateLimiter()
        self.security_middleware = SecurityMiddleware(
            self.token_manager,
            self.auth_manager,
        )

    def _init_network(self) -> None:
        """Инициализация сетевого слоя."""
        # SSL
        ssl_ctx = None
        if self.env_config.SSL_ENABLED:
            ssl_ctx = SSLContextFactory.create_server_context(
                cert_path=self.env_config.SSL_CERT_PATH,
                key_path=self.env_config.SSL_KEY_PATH,
            )

        self.ssl_context = ssl_ctx
        self.session_manager = SessionManager()
        self.message_dispatcher = MessageDispatcher()

        self.tcp_server = TCPServer(
            host=self.env_config.SERVER_HOST,
            port=self.env_config.SERVER_PORT,
            ssl_context=ssl_ctx,
            session_manager=self.session_manager,
            security_middleware=self.security_middleware,
            message_dispatcher=self.message_dispatcher,
            token_manager=self.token_manager,
            auth_manager=self.auth_manager,
        )

    async def _init_game_data(self) -> None:
        """Загрузка игровых данных из конфигурации."""
        self.property_defs = await self.config_manager.get_properties()
        self.chance_cards = await self.config_manager.get_chance_cards()
        self.fund_cards = await self.config_manager.get_fund_cards()

    def _init_game_components(self) -> None:
        """Инициализация игровых компонентов."""
        # Базовые менеджеры
        self.jail_manager = JailManager(self.event_bus)
        self.veranda_manager = VerandaManager(self.event_bus)
        self.bankruptcy_manager = BankruptcyManager(self.event_bus)
        self.auction_manager = AuctionManager(self.event_bus)
        self.trade_manager = TradeManager(self.event_bus)
        self.undo_stack = UndoStack(max_size=100)

        # Игровой движок
        self.game_engine = GameEngine(
            event_bus=self.event_bus,
            auction_manager=self.auction_manager,
            trade_manager=self.trade_manager,
            jail_manager=self.jail_manager,
            veranda_manager=self.veranda_manager,
            bankruptcy_manager=self.bankruptcy_manager,
            undo_stack=self.undo_stack,
        )

        # Менеджер ходов
        self.turn_manager = TurnManager(
            event_bus=self.event_bus,
            scheduler=self.scheduler,
        )

        # Менеджер комнат
        self.observer_manager = ObserverManager()
        self.room_manager = RoomManager(
            room_repository=self.room_repo,
            observer_manager=self.observer_manager,
        )

        # Менеджер чата
        self.chat_manager = ChatManager(self.chat_repo)

        # Менеджер игр
        self.game_manager = GameManager(
            game_repository=self.game_repo,
            room_repository=self.room_repo,
            event_bus=self.event_bus,
            engine=self.game_engine,
            turn_manager=self.turn_manager,
            jail_manager=self.jail_manager,
            veranda_manager=self.veranda_manager,
            bankruptcy_manager=self.bankruptcy_manager,
            auction_manager=self.auction_manager,
            trade_manager=self.trade_manager,
            undo_stack=self.undo_stack,
            property_defs=self.property_defs,
            chance_cards=self.chance_cards,
            fund_cards=self.fund_cards,
        )

    def _init_admin(self) -> None:
        """Инициализация админ-команд."""
        self.admin_commands = AdminCommands(
            game_manager=self.game_manager,
            undo_stack=self.undo_stack,
            event_bus=self.event_bus,
            jail_manager=self.jail_manager,
            veranda_manager=self.veranda_manager,
        )

    def _init_backup(self) -> None:
        """Инициализация бэкапов."""
        self.autosave_manager = AutosaveManager(self.game_repo)
        self.backup_manager = BackupManager(
            env_config=self.env_config,
            backup_dir=self.env_config.BACKUP_DIR,
            retention_days=self.env_config.BACKUP_RETENTION_DAYS,
        )
        self.crash_recovery = CrashRecovery(
            game_repository=self.game_repo,
            room_repository=self.room_repo,
            game_manager=self.game_manager,
        )