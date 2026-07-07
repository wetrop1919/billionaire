"""
shared/game_rules.py

Модуль игровых правил для проекта "Миллиардер".

Предоставляет централизованный доступ ко всем настраиваемым
параметрам игры. Правила загружаются из JSON-конфигурации
и могут быть изменены владельцем комнаты перед началом игры.

Все правила валидируются на соответствие допустимым диапазонам.
Модуль не содержит жёстко заданных значений — всё настраивается.

Использование:
    from shared.game_rules import GameRules, RuleSet

    rules = GameRules.from_config(config_dict)
    start_money = rules.get_start_money()
    is_auction_enabled = rules.is_enabled("auction_enabled")

Python: 3.13+
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Self

from shared.constants import (
    DEFAULT_START_MONEY,
    DEFAULT_START_BONUS,
    DEFAULT_TURN_TIMEOUT,
    MIN_TURN_TIMEOUT,
    MAX_TURN_TIMEOUT,
    MIN_PLAYERS,
    MAX_PLAYERS,
    DEFAULT_MAX_PLAYERS,
    AUCTION_TIMEOUT,
    TRADE_TIMEOUT,
    MIN_LOAN_PERCENT,
    MAX_LOAN_PERCENT,
    JAIL_FINE,
    JAIL_MAX_ROUNDS,
    VERANDA_EXIT_COST,
    DOUBLES_FOR_JAIL,
)


# ============================================================================
# НАБОР ПРАВИЛ (RuleSet)
# ============================================================================

@dataclass(slots=True)
class RuleSet:
    """
    Набор игровых правил с возможностью включения/отключения.

    Каждое правило имеет:
    - value: текущее значение
    - default: значение по умолчанию
    - min_value: минимально допустимое значение
    - max_value: максимально допустимое значение
    - enabled: включено ли правило
    """

    # === ЭКОНОМИКА ===
    start_money: int = DEFAULT_START_MONEY
    start_bonus: int = DEFAULT_START_BONUS
    max_players: int = DEFAULT_MAX_PLAYERS
    turn_timeout: int = DEFAULT_TURN_TIMEOUT

    # === ТЮРЬМА ===
    jail_fine: int = JAIL_FINE
    jail_max_rounds: int = JAIL_MAX_ROUNDS
    doubles_for_jail: int = DOUBLES_FOR_JAIL

    # === ВЕРАНДА ===
    veranda_exit_cost: int = VERANDA_EXIT_COST

    # === АУКЦИОН ===
    auction_timeout: int = AUCTION_TIMEOUT
    auction_enabled: bool = True

    # === ТОРГОВЛЯ ===
    trade_enabled: bool = True
    trade_timeout: int = TRADE_TIMEOUT
    min_loan_percent: int = MIN_LOAN_PERCENT
    max_loan_percent: int = MAX_LOAN_PERCENT

    # === СТРОИТЕЛЬСТВО ===
    building_enabled: bool = True
    even_build_required: bool = False  # Требуется ли равномерная застройка

    # === КАРТОЧКИ ===
    chance_cards_enabled: bool = True
    fund_cards_enabled: bool = True

    # === ПРОЧЕЕ ===
    free_parking_bonus: int = 0  # Бонус на бесплатной парковке (0 = нет)
    allow_spectators: bool = True
    spectator_chat: bool = True

    def validate(self) -> list[str]:
        """
        Валидация всех правил на соответствие допустимым диапазонам.

        Returns:
            Список сообщений об ошибках (пустой, если всё корректно).
        """
        errors: list[str] = []

        # Экономика
        if self.start_money < 0:
            errors.append(f"start_money не может быть отрицательным: {self.start_money}")
        if self.start_money > 100_000:
            errors.append(f"start_money слишком велик: {self.start_money}")

        if self.start_bonus < 0:
            errors.append(f"start_bonus не может быть отрицательным: {self.start_bonus}")
        if self.start_bonus > 10_000:
            errors.append(f"start_bonus слишком велик: {self.start_bonus}")

        if not (MIN_PLAYERS <= self.max_players <= MAX_PLAYERS):
            errors.append(
                f"max_players должен быть от {MIN_PLAYERS} до {MAX_PLAYERS}: "
                f"{self.max_players}"
            )

        if not (MIN_TURN_TIMEOUT <= self.turn_timeout <= MAX_TURN_TIMEOUT):
            errors.append(
                f"turn_timeout должен быть от {MIN_TURN_TIMEOUT} до "
                f"{MAX_TURN_TIMEOUT}: {self.turn_timeout}"
            )

        # Тюрьма
        if self.jail_fine < 0:
            errors.append(f"jail_fine не может быть отрицательным: {self.jail_fine}")

        if self.jail_max_rounds < 1:
            errors.append(
                f"jail_max_rounds должен быть >= 1: {self.jail_max_rounds}"
            )

        if self.doubles_for_jail < 1:
            errors.append(
                f"doubles_for_jail должен быть >= 1: {self.doubles_for_jail}"
            )

        # Веранда
        if self.veranda_exit_cost < 0:
            errors.append(
                f"veranda_exit_cost не может быть отрицательным: "
                f"{self.veranda_exit_cost}"
            )

        # Торговля
        if not (MIN_LOAN_PERCENT <= self.min_loan_percent <= MAX_LOAN_PERCENT):
            errors.append(
                f"min_loan_percent должен быть от {MIN_LOAN_PERCENT} до "
                f"{MAX_LOAN_PERCENT}: {self.min_loan_percent}"
            )

        if not (MIN_LOAN_PERCENT <= self.max_loan_percent <= MAX_LOAN_PERCENT):
            errors.append(
                f"max_loan_percent должен быть от {MIN_LOAN_PERCENT} до "
                f"{MAX_LOAN_PERCENT}: {self.max_loan_percent}"
            )

        if self.min_loan_percent > self.max_loan_percent:
            errors.append(
                f"min_loan_percent ({self.min_loan_percent}) не может быть больше "
                f"max_loan_percent ({self.max_loan_percent})"
            )

        # Аукцион
        if self.auction_timeout < 10:
            errors.append(
                f"auction_timeout должен быть >= 10 секунд: {self.auction_timeout}"
            )

        if self.trade_timeout < 10:
            errors.append(
                f"trade_timeout должен быть >= 10 секунд: {self.trade_timeout}"
            )

        return errors

    def to_dict(self) -> dict[str, Any]:
        """
        Сериализация правил в словарь.

        Returns:
            Словарь со всеми правилами.
        """
        return {
            "start_money": self.start_money,
            "start_bonus": self.start_bonus,
            "max_players": self.max_players,
            "turn_timeout": self.turn_timeout,
            "jail_fine": self.jail_fine,
            "jail_max_rounds": self.jail_max_rounds,
            "doubles_for_jail": self.doubles_for_jail,
            "veranda_exit_cost": self.veranda_exit_cost,
            "auction_enabled": self.auction_enabled,
            "auction_timeout": self.auction_timeout,
            "trade_enabled": self.trade_enabled,
            "trade_timeout": self.trade_timeout,
            "min_loan_percent": self.min_loan_percent,
            "max_loan_percent": self.max_loan_percent,
            "building_enabled": self.building_enabled,
            "even_build_required": self.even_build_required,
            "chance_cards_enabled": self.chance_cards_enabled,
            "fund_cards_enabled": self.fund_cards_enabled,
            "free_parking_bonus": self.free_parking_bonus,
            "allow_spectators": self.allow_spectators,
            "spectator_chat": self.spectator_chat,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RuleSet:
        """
        Создать набор правил из словаря.

        Args:
            data: Словарь с правилами.

        Returns:
            Новый экземпляр RuleSet с применёнными значениями.
        """
        defaults = cls()
        return cls(
            start_money=data.get("start_money", defaults.start_money),
            start_bonus=data.get("start_bonus", defaults.start_bonus),
            max_players=data.get("max_players", defaults.max_players),
            turn_timeout=data.get("turn_timeout", defaults.turn_timeout),
            jail_fine=data.get("jail_fine", defaults.jail_fine),
            jail_max_rounds=data.get("jail_max_rounds", defaults.jail_max_rounds),
            doubles_for_jail=data.get("doubles_for_jail", defaults.doubles_for_jail),
            veranda_exit_cost=data.get("veranda_exit_cost", defaults.veranda_exit_cost),
            auction_enabled=data.get("auction_enabled", defaults.auction_enabled),
            auction_timeout=data.get("auction_timeout", defaults.auction_timeout),
            trade_enabled=data.get("trade_enabled", defaults.trade_enabled),
            trade_timeout=data.get("trade_timeout", defaults.trade_timeout),
            min_loan_percent=data.get("min_loan_percent", defaults.min_loan_percent),
            max_loan_percent=data.get("max_loan_percent", defaults.max_loan_percent),
            building_enabled=data.get("building_enabled", defaults.building_enabled),
            even_build_required=data.get("even_build_required", defaults.even_build_required),
            chance_cards_enabled=data.get("chance_cards_enabled", defaults.chance_cards_enabled),
            fund_cards_enabled=data.get("fund_cards_enabled", defaults.fund_cards_enabled),
            free_parking_bonus=data.get("free_parking_bonus", defaults.free_parking_bonus),
            allow_spectators=data.get("allow_spectators", defaults.allow_spectators),
            spectator_chat=data.get("spectator_chat", defaults.spectator_chat),
        )

    @classmethod
    def defaults(cls) -> RuleSet:
        """
        Получить набор правил по умолчанию.

        Returns:
            RuleSet со значениями по умолчанию.
        """
        return cls()


# ============================================================================
# ИГРОВЫЕ ПРАВИЛА (GameRules)
# ============================================================================

@dataclass(slots=True)
class GameRules:
    """
    Управление игровыми правилами с поддержкой включения/отключения.

    Предоставляет методы для проверки, включено ли правило,
    и получения текущих значений параметров игры.

    Attributes:
        rules: Набор правил (RuleSet).
        enabled_rules: Множество названий включённых правил.
    """

    rules: RuleSet
    enabled_rules: set[str]

    def __init__(self, rules: RuleSet | None = None) -> None:
        """
        Инициализация игровых правил.

        Args:
            rules: Набор правил. Если None, используются значения по умолчанию.
        """
        self.rules = rules if rules is not None else RuleSet.defaults()
        self.enabled_rules = self._build_enabled_set()

    def _build_enabled_set(self) -> set[str]:
        """
        Построить множество названий включённых правил на основе RuleSet.

        Returns:
            Множество строк-идентификаторов включённых правил.
        """
        enabled: set[str] = set()

        # Булевы правила
        if self.rules.auction_enabled:
            enabled.add("auction_enabled")
        if self.rules.trade_enabled:
            enabled.add("trade_enabled")
        if self.rules.building_enabled:
            enabled.add("building_enabled")
        if self.rules.even_build_required:
            enabled.add("even_build_required")
        if self.rules.chance_cards_enabled:
            enabled.add("chance_cards_enabled")
        if self.rules.fund_cards_enabled:
            enabled.add("fund_cards_enabled")
        if self.rules.allow_spectators:
            enabled.add("allow_spectators")
        if self.rules.spectator_chat:
            enabled.add("spectator_chat")

        return enabled

    # === МЕТОДЫ ДОСТУПА К ПРАВИЛАМ ===

    def is_enabled(self, rule_name: str) -> bool:
        """
        Проверить, включено ли указанное правило.

        Args:
            rule_name: Название правила (например, "auction_enabled").

        Returns:
            True, если правило включено.
        """
        return rule_name in self.enabled_rules

    def enable(self, rule_name: str) -> None:
        """
        Включить правило.

        Args:
            rule_name: Название правила.
        """
        self.enabled_rules.add(rule_name)
        self._apply_enabled_state(rule_name, True)

    def disable(self, rule_name: str) -> None:
        """
        Отключить правило.

        Args:
            rule_name: Название правила.
        """
        self.enabled_rules.discard(rule_name)
        self._apply_enabled_state(rule_name, False)

    def toggle(self, rule_name: str) -> bool:
        """
        Переключить состояние правила.

        Args:
            rule_name: Название правила.

        Returns:
            Новое состояние (True = включено, False = выключено).
        """
        if self.is_enabled(rule_name):
            self.disable(rule_name)
            return False
        else:
            self.enable(rule_name)
            return True

    def _apply_enabled_state(self, rule_name: str, state: bool) -> None:
        """
        Применить состояние включения к соответствующему полю RuleSet.

        Args:
            rule_name: Название правила.
            state: Новое состояние.
        """
        mapping: dict[str, str] = {
            "auction_enabled": "auction_enabled",
            "trade_enabled": "trade_enabled",
            "building_enabled": "building_enabled",
            "even_build_required": "even_build_required",
            "chance_cards_enabled": "chance_cards_enabled",
            "fund_cards_enabled": "fund_cards_enabled",
            "allow_spectators": "allow_spectators",
            "spectator_chat": "spectator_chat",
        }

        if rule_name in mapping:
            setattr(self.rules, mapping[rule_name], state)

    # === ПОЛУЧЕНИЕ ЗНАЧЕНИЙ ===

    def get_start_money(self) -> int:
        """Получить стартовый капитал."""
        return self.rules.start_money

    def get_start_bonus(self) -> int:
        """Получить бонус за прохождение Старта."""
        return self.rules.start_bonus

    def get_max_players(self) -> int:
        """Получить максимальное количество игроков."""
        return self.rules.max_players

    def get_turn_timeout(self) -> int:
        """Получить таймаут хода в секундах."""
        return self.rules.turn_timeout

    def get_jail_fine(self) -> int:
        """Получить штраф за выход из тюрьмы."""
        return self.rules.jail_fine

    def get_jail_max_rounds(self) -> int:
        """Получить максимальное количество кругов в тюрьме."""
        return self.rules.jail_max_rounds

    def get_doubles_for_jail(self) -> int:
        """Получить количество дублей для отправки в тюрьму."""
        return self.rules.doubles_for_jail

    def get_veranda_exit_cost(self) -> int:
        """Получить стоимость выхода с Веранды."""
        return self.rules.veranda_exit_cost

    def get_auction_timeout(self) -> int:
        """Получить таймаут аукциона в секундах."""
        return self.rules.auction_timeout

    def get_trade_timeout(self) -> int:
        """Получить таймаут торговли в секундах."""
        return self.rules.trade_timeout

    def get_loan_percent_range(self) -> tuple[int, int]:
        """Получить допустимый диапазон процентов по займу."""
        return (self.rules.min_loan_percent, self.rules.max_loan_percent)

    def get_free_parking_bonus(self) -> int:
        """Получить бонус на бесплатной парковке."""
        return self.rules.free_parking_bonus

    # === ВАЛИДАЦИЯ И СЕРИАЛИЗАЦИЯ ===

    def validate(self) -> list[str]:
        """
        Валидировать все правила.

        Returns:
            Список сообщений об ошибках (пустой, если всё корректно).
        """
        return self.rules.validate()

    def to_dict(self) -> dict[str, Any]:
        """
        Сериализация правил в словарь.

        Returns:
            Полный словарь правил и состояний.
        """
        result = self.rules.to_dict()
        result["enabled_rules"] = sorted(self.enabled_rules)
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GameRules:
        """
        Создать правила из словаря (например, из JSON-конфига).

        Args:
            data: Словарь с правилами.

        Returns:
            Новый экземпляр GameRules.
        """
        rules = RuleSet.from_dict(data)
        game_rules = cls(rules)

        # Применяем список включённых правил, если он есть
        enabled_list = data.get("enabled_rules", [])
        if enabled_list:
            game_rules.enabled_rules = set(enabled_list)
            # Синхронизируем состояние с RuleSet
            for rule_name in enabled_list:
                game_rules._apply_enabled_state(rule_name, True)

        return game_rules

    @classmethod
    def defaults(cls) -> GameRules:
        """
        Получить правила по умолчанию.

        Returns:
            GameRules со значениями по умолчанию.
        """
        return cls(RuleSet.defaults())

    def clone(self) -> GameRules:
        """
        Создать глубокую копию правил.

        Returns:
            Новый экземпляр GameRules с теми же значениями.
        """
        return GameRules.from_dict(self.to_dict())

    def __str__(self) -> str:
        """Человекочитаемое представление правил."""
        lines = [
            "Игровые правила:",
            f"  Стартовый капитал: {self.rules.start_money} $",
            f"  Бонус за Старт: {self.rules.start_bonus} $",
            f"  Максимум игроков: {self.rules.max_players}",
            f"  Таймаут хода: {self.rules.turn_timeout} сек",
            f"  Штраф за выход из тюрьмы: {self.rules.jail_fine} $",
            f"  Стоимость выхода с Веранды: {self.rules.veranda_exit_cost} $",
            f"  Аукционы: {'Вкл' if self.is_enabled('auction_enabled') else 'Выкл'}",
            f"  Торговля: {'Вкл' if self.is_enabled('trade_enabled') else 'Выкл'}",
            f"  Строительство: {'Вкл' if self.is_enabled('building_enabled') else 'Выкл'}",
            f"  Карточки Шанс: {'Вкл' if self.is_enabled('chance_cards_enabled') else 'Выкл'}",
            f"  Карточки Фонд: {'Вкл' if self.is_enabled('fund_cards_enabled') else 'Выкл'}",
        ]
        return "\n".join(lines)


# ============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================================

def load_rules_from_config(config_path: str) -> GameRules:
    """
    Загрузить правила из JSON-файла конфигурации.

    Args:
        config_path: Путь к JSON-файлу с правилами.

    Returns:
        Экземпляр GameRules с загруженными значениями.

    Raises:
        FileNotFoundError: Если файл не найден.
        json.JSONDecodeError: Если файл содержит некорректный JSON.
    """
    import json
    from pathlib import Path

    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Файл конфигурации правил не найден: {config_path}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    rules = GameRules.from_dict(data)
    errors = rules.validate()
    if errors:
        error_list = "\n  - ".join(errors)
        raise ValueError(
            f"Ошибки валидации правил из {config_path}:\n  - {error_list}"
        )

    return rules


def create_custom_rules(
    start_money: int | None = None,
    start_bonus: int | None = None,
    max_players: int | None = None,
    turn_timeout: int | None = None,
    auction_enabled: bool | None = None,
    trade_enabled: bool | None = None,
    building_enabled: bool | None = None,
) -> GameRules:
    """
    Создать правила с пользовательскими значениями.

    Все неуказанные параметры берутся из значений по умолчанию.

    Args:
        start_money: Стартовый капитал.
        start_bonus: Бонус за Старт.
        max_players: Максимум игроков.
        turn_timeout: Таймаут хода.
        auction_enabled: Включены ли аукционы.
        trade_enabled: Включена ли торговля.
        building_enabled: Включено ли строительство.

    Returns:
        Новый экземпляр GameRules.
    """
    rules = RuleSet.defaults()

    if start_money is not None:
        rules.start_money = start_money
    if start_bonus is not None:
        rules.start_bonus = start_bonus
    if max_players is not None:
        rules.max_players = max_players
    if turn_timeout is not None:
        rules.turn_timeout = turn_timeout
    if auction_enabled is not None:
        rules.auction_enabled = auction_enabled
    if trade_enabled is not None:
        rules.trade_enabled = trade_enabled
    if building_enabled is not None:
        rules.building_enabled = building_enabled

    return GameRules(rules)


def get_available_rules() -> list[dict[str, str]]:
    """
    Получить список всех доступных правил с описаниями.

    Используется для отображения в GUI при настройке комнаты.

    Returns:
        Список словарей с ключами: name, description, type, category.
    """
    return [
        {
            "name": "auction_enabled",
            "description": "Аукционы при отказе от покупки",
            "type": "bool",
            "category": "Экономика",
        },
        {
            "name": "trade_enabled",
            "description": "Торговля между игроками",
            "type": "bool",
            "category": "Экономика",
        },
        {
            "name": "building_enabled",
            "description": "Строительство домов и отелей",
            "type": "bool",
            "category": "Строительство",
        },
        {
            "name": "even_build_required",
            "description": "Требовать равномерную застройку",
            "type": "bool",
            "category": "Строительство",
        },
        {
            "name": "chance_cards_enabled",
            "description": "Карточки Шанс",
            "type": "bool",
            "category": "Карточки",
        },
        {
            "name": "fund_cards_enabled",
            "description": "Карточки Фонд",
            "type": "bool",
            "category": "Карточки",
        },
        {
            "name": "allow_spectators",
            "description": "Разрешить наблюдателей",
            "type": "bool",
            "category": "Комната",
        },
        {
            "name": "spectator_chat",
            "description": "Чат для наблюдателей",
            "type": "bool",
            "category": "Комната",
        },
    ]