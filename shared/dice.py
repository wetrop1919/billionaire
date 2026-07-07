"""
shared/dice.py

Модуль для работы с игровыми кубиками.

Предоставляет функциональность броска кубиков, определения дублей,
подсчёта суммы и форматирования результатов для отображения.

Все случайные значения генерируются криптографически безопасным
генератором secrets для предотвращения предсказуемости.

Использование:
    from shared.dice import Dice, DiceRoll

    dice = Dice()
    roll = dice.roll()  # DiceRoll(die1=3, die2=5, total=8, is_double=False)

Python: 3.13+
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Self

from shared.constants import DICE_MIN, DICE_MAX, DICE_COUNT, DOUBLES_FOR_JAIL


# ============================================================================
# РЕЗУЛЬТАТ БРОСКА КУБИКОВ
# ============================================================================

@dataclass(slots=True, frozen=True)
class DiceRoll:
    """
    Результат броска кубиков.

    Неизменяемый (frozen) объект, представляющий один бросок.
    Содержит значения каждого кубика, сумму и флаг дубля.

    Attributes:
        die1: Значение первого кубика (1-6).
        die2: Значение второго кубика (1-6).
        total: Сумма значений обоих кубиков.
        is_double: True, если выпал дубль (оба значения равны).
    """

    die1: int
    die2: int
    total: int
    is_double: bool

    @classmethod
    def from_values(cls, die1: int, die2: int) -> DiceRoll:
        """
        Создать результат броска из двух значений кубиков.

        Args:
            die1: Значение первого кубика.
            die2: Значение второго кубика.

        Returns:
            Новый экземпляр DiceRoll.

        Raises:
            ValueError: Если значения вне допустимого диапазона.
        """
        if not (DICE_MIN <= die1 <= DICE_MAX):
            raise ValueError(
                f"Значение первого кубика должно быть от {DICE_MIN} до {DICE_MAX}, "
                f"получено {die1}"
            )
        if not (DICE_MIN <= die2 <= DICE_MAX):
            raise ValueError(
                f"Значение второго кубика должно быть от {DICE_MIN} до {DICE_MAX}, "
                f"получено {die2}"
            )
        return cls(
            die1=die1,
            die2=die2,
            total=die1 + die2,
            is_double=(die1 == die2),
        )

    def to_dict(self) -> dict[str, int | bool]:
        """
        Сериализация результата броска в словарь.

        Returns:
            Словарь с ключами die1, die2, total, is_double.
        """
        return {
            "die1": self.die1,
            "die2": self.die2,
            "total": self.total,
            "is_double": self.is_double,
        }

    def __str__(self) -> str:
        """Человекочитаемое представление броска."""
        double_text = " (ДУБЛЬ!)" if self.is_double else ""
        return f"[{self.die1}] + [{self.die2}] = {self.total}{double_text}"


# ============================================================================
# ИСТОРИЯ БРОСКОВ
# ============================================================================

@dataclass(slots=True)
class DiceHistory:
    """
    История бросков кубиков для одного игрока в течение хода.

    Отслеживает последовательные дубли для определения
    необходимости отправки в тюрьму (3 дубля подряд).

    Attributes:
        rolls: Список результатов бросков.
        consecutive_doubles: Количество последовательных дублей.
    """

    rolls: list[DiceRoll]
    consecutive_doubles: int

    def __init__(self) -> None:
        """Инициализация пустой истории бросков."""
        self.rolls = []
        self.consecutive_doubles = 0

    def add_roll(self, roll: DiceRoll) -> None:
        """
        Добавить результат броска в историю.

        Автоматически обновляет счётчик последовательных дублей.

        Args:
            roll: Результат броска кубиков.
        """
        self.rolls.append(roll)
        if roll.is_double:
            self.consecutive_doubles += 1
        else:
            self.consecutive_doubles = 0

    @property
    def should_go_to_jail(self) -> bool:
        """
        Проверка, должен ли игрок отправиться в тюрьму.

        Игрок отправляется в тюрьму, если выбросил три дубля подряд.

        Returns:
            True, если игрок должен отправиться в тюрьму.
        """
        return self.consecutive_doubles >= DOUBLES_FOR_JAIL

    @property
    def has_rolled(self) -> bool:
        """Проверка, был ли совершён хотя бы один бросок."""
        return len(self.rolls) > 0

    @property
    def last_roll(self) -> DiceRoll | None:
        """
        Последний результат броска.

        Returns:
            Последний DiceRoll или None, если бросков не было.
        """
        return self.rolls[-1] if self.rolls else None

    @property
    def total_steps(self) -> int:
        """
        Общее количество шагов за все броски в истории.

        Returns:
            Сумма всех значений total в истории.
        """
        return sum(roll.total for roll in self.rolls)

    def clear(self) -> None:
        """Очистить историю бросков."""
        self.rolls.clear()
        self.consecutive_doubles = 0

    def to_dict(self) -> dict:
        """
        Сериализация истории бросков в словарь.

        Returns:
            Словарь с историей бросков.
        """
        return {
            "rolls": [roll.to_dict() for roll in self.rolls],
            "consecutive_doubles": self.consecutive_doubles,
            "should_go_to_jail": self.should_go_to_jail,
            "total_steps": self.total_steps,
        }


# ============================================================================
# КУБИКИ
# ============================================================================

class Dice:
    """
    Генератор бросков кубиков.

    Использует криптографически безопасный генератор случайных чисел
    (secrets) для предотвращения предсказуемости результатов.

    Usage:
        dice = Dice()
        roll = dice.roll()  # Случайный бросок двух кубиков
        roll = dice.roll_deterministic(3, 5)  # Для тестов
    """

    def __init__(self) -> None:
        """Инициализация генератора кубиков."""
        pass

    def _generate_die(self) -> int:
        """
        Сгенерировать значение одного кубика.

        Использует secrets.randbelow для криптографически безопасной
        генерации случайного числа в диапазоне [DICE_MIN, DICE_MAX].

        Returns:
            Случайное целое число от DICE_MIN до DICE_MAX включительно.
        """
        return DICE_MIN + secrets.randbelow(DICE_MAX - DICE_MIN + 1)

    def roll(self) -> DiceRoll:
        """
        Выполнить случайный бросок двух кубиков.

        Returns:
            Результат броска (DiceRoll).
        """
        die1 = self._generate_die()
        die2 = self._generate_die()
        return DiceRoll.from_values(die1, die2)

    def roll_deterministic(self, die1: int, die2: int) -> DiceRoll:
        """
        Создать бросок с заданными значениями (для тестирования).

        Args:
            die1: Значение первого кубика.
            die2: Значение второго кубика.

        Returns:
            Результат броска с указанными значениями.
        """
        return DiceRoll.from_values(die1, die2)

    @staticmethod
    def is_valid_die(value: int) -> bool:
        """
        Проверить, является ли значение допустимым для одного кубика.

        Args:
            value: Проверяемое значение.

        Returns:
            True, если значение в диапазоне [DICE_MIN, DICE_MAX].
        """
        return DICE_MIN <= value <= DICE_MAX

    @staticmethod
    def calculate_steps(die1: int, die2: int) -> int:
        """
        Вычислить количество шагов по значениям кубиков.

        Args:
            die1: Значение первого кубика.
            die2: Значение второго кубика.

        Returns:
            Сумма значений (количество шагов).
        """
        return die1 + die2

    @staticmethod
    def is_double(die1: int, die2: int) -> bool:
        """
        Проверить, является ли бросок дублем.

        Args:
            die1: Значение первого кубика.
            die2: Значение второго кубика.

        Returns:
            True, если значения равны.
        """
        return die1 == die2


# ============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================================

def roll_dice() -> DiceRoll:
    """
    Быстрый бросок двух кубиков (без создания экземпляра Dice).

    Удобная функция для однократного использования.

    Returns:
        Результат броска.
    """
    dice = Dice()
    return dice.roll()


def check_jail_after_roll(history: DiceHistory) -> bool:
    """
    Проверить, должен ли игрок отправиться в тюрьму после серии бросков.

    Args:
        history: История бросков игрока за текущий ход.

    Returns:
        True, если набрано 3 дубля подряд.
    """
    return history.should_go_to_jail