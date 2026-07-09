"""
server/config/config_manager.py

Менеджер конфигурации сервера.

Обеспечивает:
- Загрузку JSON-конфигураций с проверкой схемы
- Кеширование загруженных конфигураций
- Доступ к игровым данным (поле, карточки, свойства, правила)
- Горячую перезагрузку конфигураций

Python: 3.13+
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

from shared.constants import (
    DEFAULT_SERVER_HOST,
    DEFAULT_SERVER_PORT,
    DEFAULT_START_MONEY,
    DEFAULT_START_BONUS,
    DEFAULT_TURN_TIMEOUT,
)
from shared.models.card import Card
from shared.models.position import Board, CellPosition
from shared.models.property import Property
from shared.game_rules import GameRules
from server.config.schema_validator import SchemaValidator

logger = logging.getLogger("billionaire.server")


# ============================================================================
# ИСКЛЮЧЕНИЯ КОНФИГУРАЦИИ
# ============================================================================

class ConfigError(Exception):
    """Ошибка конфигурации."""

    def __init__(self, message: str) -> None:
        super().__init__(f"Ошибка конфигурации: {message}")


class ConfigLoadError(ConfigError):
    """Ошибка загрузки конфигурации."""

    def __init__(self, file_path: str, reason: str = "") -> None:
        msg = f"Не удалось загрузить '{file_path}'"
        if reason:
            msg += f": {reason}"
        super().__init__(msg)
        self.file_path = file_path


class ConfigValidationError(ConfigError):
    """Ошибка валидации конфигурации."""

    def __init__(self, file_path: str, errors: list[str]) -> None:
        self.errors = errors
        error_list = "\n  - ".join(errors)
        super().__init__(
            f"Ошибки валидации '{file_path}':\n  - {error_list}"
        )


# ============================================================================
# МЕНЕДЖЕР КОНФИГУРАЦИИ
# ============================================================================

class ConfigManager:
    """
    Менеджер конфигурационных файлов.

    Загружает, кеширует и предоставляет доступ ко всем
    конфигурациям сервера и игровым данным.

    Attributes:
        configs_dir: Путь к директории с конфигурациями.
        _cache: Кеш загруженных конфигураций.
    """

    def __init__(self, configs_dir: str = "configs") -> None:
        """
        Инициализация менеджера.

        Args:
            configs_dir: Путь к директории configs/.
        """
        self.configs_dir: Path = Path(configs_dir)
        self._cache: dict[str, Any] = {}

    # ========================================================================
    # ЗАГРУЗКА КОНФИГУРАЦИЙ
    # ========================================================================

    async def load_all(self) -> None:
        """
        Загрузить все конфигурации.

        Вызывается при старте сервера для предварительной
        загрузки и валидации всех конфигурационных файлов.
        """
        logger.info("Загрузка конфигураций из %s...", self.configs_dir.absolute())

        try:
            await self.get_server_config()
            await self.get_network_config()
            await self.get_security_config()
            await self.get_game_board()
            await self.get_properties()
            await self.get_chance_cards()
            await self.get_fund_cards()
            await self.get_game_rules()
            logger.info("Все конфигурации загружены успешно")
        except ConfigError as e:
            logger.error("Ошибка загрузки конфигураций: %s", e)
            raise

    async def reload(self) -> None:
        """
        Перезагрузить все конфигурации.

        Очищает кеш и загружает заново. Используется
        при горячей перезагрузке.
        """
        logger.info("Перезагрузка конфигураций...")
        self._cache.clear()
        await self.load_all()

    # ========================================================================
    # СЕРВЕРНЫЕ КОНФИГУРАЦИИ
    # ========================================================================

    async def get_server_config(self) -> dict[str, Any]:
        """
        Получить конфигурацию сервера.

        Returns:
            Словарь с настройками сервера.
        """
        return await self._load_json(
            key="server",
            path="server/server.json",
            validator=SchemaValidator.validate_server_config,
            defaults={
                "host": DEFAULT_SERVER_HOST,
                "port": DEFAULT_SERVER_PORT,
                "log_level": "INFO",
                "log_dir": "logs",
                "backup_dir": "backups",
                "backup_retention_days": 30,
                "max_rooms_per_user": 5,
                "room_cleanup_timeout_seconds": 600,
                "debug": False,
                "environment": "production",
            },
        )

    async def get_network_config(self) -> dict[str, Any]:
        """
        Получить конфигурацию сети.

        Returns:
            Словарь с сетевыми настройками.
        """
        return await self._load_json(
            key="network",
            path="server/network.json",
            validator=SchemaValidator.validate_network_config,
            defaults={
                "ssl": {"enabled": True},
                "connection": {"max_connections": 1000},
                "heartbeat": {"interval_seconds": 15.0},
                "rate_limiting": {"max_packets_per_second": 50},
            },
        )

    async def get_security_config(self) -> dict[str, Any]:
        """
        Получить конфигурацию безопасности.

        Returns:
            Словарь с настройками безопасности.
        """
        return await self._load_json(
            key="security",
            path="server/security.json",
            validator=SchemaValidator.validate_security_config,
            defaults={
                "hmac": {"key_size": 32},
                "passwords": {"algorithm": "argon2id"},
                "tokens": {"access_token_expire_seconds": 3600},
            },
        )

    # ========================================================================
    # ИГРОВЫЕ КОНФИГУРАЦИИ
    # ========================================================================

    async def get_game_board(self) -> Board:
        """
        Получить игровое поле.

        Returns:
            Объект Board с клетками и специальными клетками.
        """
        cache_key = "game_board"
        if cache_key in self._cache:
            return self._cache[cache_key]

        data = await self._load_json(
            key=None,
            path="game/board.json",
            validator=SchemaValidator.validate_game_board,
        )

        board = Board.from_dict(data)
        self._cache[cache_key] = board
        return board

    async def get_properties(self) -> dict[str, Property]:
        """
        Получить все объекты собственности.

        Загружает улицы, станции и коммунальные предприятия
        и объединяет в один словарь.

        Returns:
            Словарь {property_id: Property}.
        """
        cache_key = "properties"
        if cache_key in self._cache:
            return self._cache[cache_key]

        properties: dict[str, Property] = {}

        # Загружаем улицы
        streets = await self._load_json(
            key=None,
            path="game/properties/properties.json",
        )
        for prop_data in streets.values():
            prop = Property.from_dict(prop_data)
            properties[prop.property_id] = prop

        # Загружаем станции
        stations = await self._load_json(
            key=None,
            path="game/properties/stations.json",
        )
        for prop_data in stations.values():
            prop = Property.from_dict(prop_data)
            properties[prop.property_id] = prop

        # Загружаем коммунальные предприятия
        utilities = await self._load_json(
            key=None,
            path="game/properties/utilities.json",
        )
        for prop_data in utilities.values():
            prop = Property.from_dict(prop_data)
            properties[prop.property_id] = prop

        self._cache[cache_key] = properties
        logger.info(
            "Загружено %d объектов собственности", len(properties)
        )
        return properties

    async def get_chance_cards(self) -> list[Card]:
        """
        Получить карточки «Шанс».

        Returns:
            Список карточек.
        """
        cache_key = "chance_cards"
        if cache_key in self._cache:
            return self._cache[cache_key]

        data = await self._load_json(
            key=None,
            path="game/cards/chance.json",
        )

        cards: list[Card] = []
        if isinstance(data, list):
            for card_data in data:
                cards.append(Card.from_dict(card_data))

        self._cache[cache_key] = cards
        logger.info("Загружено %d карточек «Шанс»", len(cards))
        return cards

    async def get_fund_cards(self) -> list[Card]:
        """
        Получить карточки «Фонд».

        Returns:
            Список карточек.
        """
        cache_key = "fund_cards"
        if cache_key in self._cache:
            return self._cache[cache_key]

        data = await self._load_json(
            key=None,
            path="game/cards/fund.json",
        )

        cards: list[Card] = []
        if isinstance(data, list):
            for card_data in data:
                cards.append(Card.from_dict(card_data))

        self._cache[cache_key] = cards
        logger.info("Загружено %d карточек «Фонд»", len(cards))
        return cards

    async def get_game_rules(self) -> GameRules:
        """
        Получить правила игры.

        Returns:
            Объект GameRules со значениями по умолчанию.
        """
        cache_key = "game_rules"
        if cache_key in self._cache:
            return self._cache[cache_key]

        data = await self._load_json(
            key=None,
            path="game/rules.json",
            validator=SchemaValidator.validate_game_rules,
        )

        rules = GameRules.from_dict(data)
        self._cache[cache_key] = rules
        return rules

    async def get_game_config(self) -> dict[str, Any]:
        """
        Получить игровую конфигурацию (свойства + карточки + поле + правила).

        Returns:
            Словарь со всеми игровыми данными.
        """
        return {
            "board": await self.get_game_board(),
            "properties": await self.get_properties(),
            "chance_cards": await self.get_chance_cards(),
            "fund_cards": await self.get_fund_cards(),
            "game_rules": await self.get_game_rules(),
        }

    # ========================================================================
    # ВНУТРЕННИЕ МЕТОДЫ
    # ========================================================================

    async def _load_json(
        self,
        key: Optional[str],
        path: str,
        validator: Optional[callable] = None,
        defaults: Optional[dict[str, Any]] = None,
    ) -> Any:
        """
        Загрузить JSON-файл конфигурации.

        Args:
            key: Ключ для кеширования (None — не кешировать).
            path: Относительный путь к файлу.
            validator: Функция валидации (принимает dict, возвращает list ошибок).
            defaults: Значения по умолчанию.

        Returns:
            Данные из файла (словарь, список или объект).

        Raises:
            ConfigLoadError: Если файл не найден.
            ConfigValidationError: Если валидация не пройдена.
        """
        # Проверяем кеш
        if key and key in self._cache:
            return self._cache[key]

        file_path = self.configs_dir / path

        if not file_path.exists():
            if defaults is not None:
                logger.warning(
                    "Файл конфигурации не найден: %s. Используются значения по умолчанию.",
                    file_path,
                )
                if key:
                    self._cache[key] = defaults
                return defaults
            raise ConfigLoadError(
                str(file_path), "Файл не найден"
            )

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise ConfigLoadError(
                str(file_path), f"Некорректный JSON: {e}"
            ) from e
        except OSError as e:
            raise ConfigLoadError(
                str(file_path), str(e)
            ) from e

        # Извлекаем данные из обёртки {version, data}
        if isinstance(data, dict) and "data" in data:
            config_data = data["data"]
        else:
            config_data = data

        # Валидация
        if validator is not None:
            errors = validator(data)
            if errors:
                raise ConfigValidationError(str(file_path), errors)

        # Кеширование
        if key:
            self._cache[key] = config_data

        logger.debug("Загружена конфигурация: %s", file_path)
        return config_data

    def clear_cache(self) -> None:
        """Очистить кеш конфигураций."""
        self._cache.clear()
        logger.debug("Кеш конфигураций очищен")

    def get_cache_info(self) -> dict[str, bool]:
        """
        Получить информацию о загруженных конфигурациях.

        Returns:
            Словарь {имя_конфигурации: загружена}.
        """
        return {
            "server": "server" in self._cache,
            "network": "network" in self._cache,
            "security": "security" in self._cache,
            "game_board": "game_board" in self._cache,
            "properties": "properties" in self._cache,
            "chance_cards": "chance_cards" in self._cache,
            "fund_cards": "fund_cards" in self._cache,
            "game_rules": "game_rules" in self._cache,
        }