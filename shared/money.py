"""
shared/money.py

Модуль для работы с денежными операциями в игре "Миллиардер".

Обеспечивает:
- Типобезопасные денежные операции (сложение, вычитание, умножение)
- Валидацию денежных сумм (защита от отрицательных значений, переполнения)
- Форматирование денежных сумм для отображения
- Транзакционный перевод средств между игроками
- Проверку достаточности средств

Все операции выполняются с проверкой граничных условий.
Деньги хранятся в целочисленном формате (копейки не используются).

Использование:
    from shared.money import Money, MoneyTransaction

    player_money = Money(1500)
    player_money -= Money(200)  # Вычитание с проверкой
    formatted = Money.format_amount(1500)  # "1 500 $"

Python: 3.13+
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Self

from shared.constants import (
    DEFAULT_START_MONEY,
    DEFAULT_START_BONUS,
    JAIL_FINE,
    VERANDA_EXIT_COST,
)
from shared.exceptions import InsufficientFundsError


# ============================================================================
# ДЕНЕЖНАЯ СУММА (Value Object)
# ============================================================================

@dataclass(slots=True, frozen=True, order=True)
class Money:
    """
    Денежная сумма (Value Object).

    Неизменяемый объект, представляющий сумму денег.
    Поддерживает арифметические операции с автоматической валидацией.

    Деньги не могут быть отрицательными. Любая операция, приводящая
    к отрицательному значению, выбрасывает InsufficientFundsError.

    Attributes:
        amount: Сумма в долларах (целое неотрицательное число).

    Example:
        balance = Money(1500)
        rent = Money(25)
        new_balance = balance - rent  # Money(1475)
    """

    amount: int

    def __post_init__(self) -> None:
        """Валидация суммы после инициализации."""
        if self.amount < 0:
            raise ValueError(
                f"Денежная сумма не может быть отрицательной: {self.amount}"
            )

    # === ЗНАЧЕНИЯ ПО УМОЛЧАНИЮ ===

    @classmethod
    def zero(cls) -> Money:
        """Нулевая сумма."""
        return cls(0)

    @classmethod
    def start_capital(cls) -> Money:
        """Стартовый капитал игрока."""
        return cls(DEFAULT_START_MONEY)

    @classmethod
    def start_bonus(cls) -> Money:
        """Бонус за прохождение клетки Старт."""
        return cls(DEFAULT_START_BONUS)

    @classmethod
    def jail_fine(cls) -> Money:
        """Штраф за выход из тюрьмы."""
        return cls(JAIL_FINE)

    @classmethod
    def veranda_exit_cost(cls) -> Money:
        """Плата за выход с Веранды."""
        return cls(VERANDA_EXIT_COST)

    # === АРИФМЕТИЧЕСКИЕ ОПЕРАЦИИ ===

    def __add__(self, other: Money) -> Money:
        """
        Сложение двух денежных сумм.

        Args:
            other: Прибавляемая сумма.

        Returns:
            Новая сумма.

        Raises:
            OverflowError: Если результат превышает максимально допустимую сумму.
        """
        result = self.amount + other.amount
        if result > Money._max_amount():
            raise OverflowError(
                f"Сумма слишком велика: {self.amount} + {other.amount} = {result}"
            )
        return Money(result)

    def __sub__(self, other: Money) -> Money:
        """
        Вычитание денежных сумм.

        Args:
            other: Вычитаемая сумма.

        Returns:
            Новая сумма.

        Raises:
            InsufficientFundsError: Если результат становится отрицательным.
        """
        result = self.amount - other.amount
        if result < 0:
            raise InsufficientFundsError(
                player_id=None,  # type: ignore[arg-type]
                required=other.amount,
                available=self.amount,
            )
        return Money(result)

    def __mul__(self, multiplier: int) -> Money:
        """
        Умножение на целое число.

        Args:
            multiplier: Множитель (неотрицательное целое).

        Returns:
            Новая сумма.

        Raises:
            ValueError: Если множитель отрицательный.
            OverflowError: Если результат превышает максимум.
        """
        if multiplier < 0:
            raise ValueError(f"Множитель не может быть отрицательным: {multiplier}")
        result = self.amount * multiplier
        if result > Money._max_amount():
            raise OverflowError(
                f"Сумма слишком велика: {self.amount} * {multiplier} = {result}"
            )
        return Money(result)

    def __floordiv__(self, divisor: int) -> Money:
        """
        Целочисленное деление.

        Args:
            divisor: Делитель (положительное целое).

        Returns:
            Новая сумма (округление вниз).

        Raises:
            ValueError: Если делитель неположительный.
        """
        if divisor <= 0:
            raise ValueError(f"Делитель должен быть положительным: {divisor}")
        return Money(self.amount // divisor)

    def __mod__(self, divisor: int) -> Money:
        """
        Остаток от деления.

        Args:
            divisor: Делитель.

        Returns:
            Остаток.
        """
        if divisor <= 0:
            raise ValueError(f"Делитель должен быть положительным: {divisor}")
        return Money(self.amount % divisor)

    # === ОПЕРАЦИИ С ЦЕЛЫМИ ЧИСЛАМИ ===

    def add_int(self, amount: int) -> Money:
        """Добавить целое число (долларов)."""
        return self + Money(amount)

    def subtract_int(self, amount: int) -> Money:
        """Вычесть целое число (долларов)."""
        return self - Money(amount)

    # === СРАВНЕНИЯ ===

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Money):
            return NotImplemented
        return self.amount == other.amount

    def __lt__(self, other: Money) -> bool:
        return self.amount < other.amount

    def __le__(self, other: Money) -> bool:
        return self.amount <= other.amount

    def __gt__(self, other: Money) -> bool:
        return self.amount > other.amount

    def __ge__(self, other: Money) -> bool:
        return self.amount >= other.amount

    def __bool__(self) -> bool:
        """True, если сумма больше нуля."""
        return self.amount > 0

    # === ПРОВЕРКИ ===

    def is_zero(self) -> bool:
        """Проверка на нулевую сумму."""
        return self.amount == 0

    def can_afford(self, cost: Money) -> bool:
        """
        Проверить, достаточно ли средств для оплаты.

        Args:
            cost: Стоимость.

        Returns:
            True, если текущая сумма >= cost.
        """
        return self.amount >= cost.amount

    def percentage(self, percent: int) -> Money:
        """
        Вычислить процент от суммы.

        Args:
            percent: Процент (0-100).

        Returns:
            Сумма, равная указанному проценту (округление вниз).

        Raises:
            ValueError: Если процент вне диапазона [0, 100].
        """
        if not (0 <= percent <= 100):
            raise ValueError(f"Процент должен быть от 0 до 100: {percent}")
        return Money((self.amount * percent) // 100)

    # === ФОРМАТИРОВАНИЕ ===

    def format(self) -> str:
        """
        Форматированный вывод суммы.

        Returns:
            Строка вида "1 500 $".
        """
        return Money.format_amount(self.amount)

    # === СЕРИАЛИЗАЦИЯ ===

    def to_dict(self) -> dict[str, int]:
        """
        Сериализация в словарь.

        Returns:
            Словарь с ключом 'amount'.
        """
        return {"amount": self.amount}

    @classmethod
    def from_dict(cls, data: dict[str, int]) -> Money:
        """
        Создание из словаря.

        Args:
            data: Словарь с ключом 'amount'.

        Returns:
            Новый экземпляр Money.
        """
        return cls(data["amount"])

    def __repr__(self) -> str:
        return f"Money({self.amount})"

    def __str__(self) -> str:
        return self.format()

    def __int__(self) -> int:
        return self.amount

    def __hash__(self) -> int:
        return hash(self.amount)

    # === ПРИВАТНЫЕ МЕТОДЫ ===

    @staticmethod
    def _max_amount() -> int:
        """
        Максимально допустимая сумма денег.

        Ограничена для предотвращения целочисленного переполнения.
        2_147_483_647 — максимальное значение 32-битного signed int.

        Returns:
            Максимальная сумма.
        """
        return 2_147_483_647

    # === СТАТИЧЕСКИЕ УТИЛИТЫ ===

    @staticmethod
    def format_amount(amount: int) -> str:
        """
        Форматирование целочисленной суммы в читаемый вид.

        Args:
            amount: Сумма в долларах.

        Returns:
            Строка вида "1 500 $" или "0 $" для нуля.

        Example:
            Money.format_amount(1500)   -> "1 500 $"
            Money.format_amount(0)      -> "0 $"
            Money.format_amount(100000) -> "100 000 $"
        """
        if amount == 0:
            return "0 $"
        # Форматирование с разделением тысяч пробелами
        formatted = f"{amount:_}".replace("_", " ")
        return f"{formatted} $"

    @staticmethod
    def format_short(amount: int) -> str:
        """
        Краткое форматирование для больших сумм.

        Args:
            amount: Сумма в долларах.

        Returns:
            Краткая строка: "1.5K $" для 1500, "1M $" для 1_000_000.

        Example:
            Money.format_short(1500)     -> "1.5K $"
            Money.format_short(1000000)  -> "1M $"
            Money.format_short(500)      -> "500 $"
        """
        if amount < 1000:
            return f"{amount} $"
        elif amount < 1_000_000:
            k_value = amount / 1000
            if k_value == int(k_value):
                return f"{int(k_value)}K $"
            return f"{k_value:.1f}K $"
        else:
            m_value = amount / 1_000_000
            if m_value == int(m_value):
                return f"{int(m_value)}M $"
            return f"{m_value:.1f}M $"

    @staticmethod
    def from_float(amount: float) -> Money:
        """
        Создать Money из числа с плавающей точкой (с округлением).

        Args:
            amount: Сумма (будет округлена до целого).

        Returns:
            Новый экземпляр Money.
        """
        return Money(round(amount))


# ============================================================================
# ДЕНЕЖНАЯ ТРАНЗАКЦИЯ (Money Transaction)
# ============================================================================

@dataclass(slots=True)
class MoneyTransaction:
    """
    Денежная транзакция между двумя участниками.

    Обеспечивает атомарный перевод средств с проверкой
    достаточности баланса отправителя.

    Attributes:
        from_player_id: ID отправителя.
        to_player_id: ID получателя.
        amount: Сумма перевода.
        reason: Причина перевода (для логирования).
    """

    from_player_id: str
    to_player_id: str
    amount: Money
    reason: str

    def execute(
        self,
        from_balance: Money,
        to_balance: Money,
    ) -> tuple[Money, Money]:
        """
        Выполнить транзакцию.

        Args:
            from_balance: Текущий баланс отправителя.
            to_balance: Текущий баланс получателя.

        Returns:
            Кортеж (новый_баланс_отправителя, новый_баланс_получателя).

        Raises:
            InsufficientFundsError: Если у отправителя недостаточно средств.
        """
        if not from_balance.can_afford(self.amount):
            raise InsufficientFundsError(
                player_id=None,  # type: ignore[arg-type]
                required=self.amount.amount,
                available=from_balance.amount,
            )

        new_from = from_balance - self.amount
        new_to = to_balance + self.amount
        return new_from, new_to

    def to_dict(self) -> dict:
        """
        Сериализация транзакции в словарь.

        Returns:
            Словарь с данными транзакции.
        """
        return {
            "from_player_id": self.from_player_id,
            "to_player_id": self.to_player_id,
            "amount": self.amount.to_dict(),
            "reason": self.reason,
        }

    def __str__(self) -> str:
        return (
            f"Перевод {self.amount.format()} "
            f"от {self.from_player_id} -> {self.to_player_id} "
            f"({self.reason})"
        )


# ============================================================================
# ДЕНЕЖНЫЙ БАЛАНС ИГРОКА (Player Balance)
# ============================================================================

@dataclass(slots=True)
class PlayerBalance:
    """
    Баланс игрока с историей операций.

    Отслеживает текущий баланс и ведёт учёт доходов и расходов.

    Attributes:
        player_id: ID игрока.
        balance: Текущий баланс.
        total_earned: Всего заработано за игру.
        total_spent: Всего потрачено за игру.
    """

    player_id: str
    balance: Money
    total_earned: Money
    total_spent: Money

    def __init__(
        self,
        player_id: str,
        initial_balance: Money | None = None,
    ) -> None:
        """
        Инициализация баланса игрока.

        Args:
            player_id: ID игрока.
            initial_balance: Начальный баланс (по умолчанию — стартовый капитал).
        """
        self.player_id = player_id
        self.balance = initial_balance if initial_balance is not None else Money.start_capital()
        self.total_earned = Money.zero()
        self.total_spent = Money.zero()

    def receive(self, amount: Money, reason: str = "") -> None:
        """
        Получить деньги.

        Args:
            amount: Получаемая сумма.
            reason: Причина получения (для логов).
        """
        self.balance += amount
        self.total_earned += amount

    def pay(self, amount: Money, reason: str = "") -> None:
        """
        Заплатить деньги.

        Args:
            amount: Выплачиваемая сумма.
            reason: Причина платежа (для логов).

        Raises:
            InsufficientFundsError: Если недостаточно средств.
        """
        self.balance -= amount
        self.total_spent += amount

    @property
    def net_worth(self) -> Money:
        """
        Чистый капитал (разница доходов и расходов).

        Returns:
            Разница total_earned - total_spent.
        """
        if self.total_earned.amount >= self.total_spent.amount:
            return Money(self.total_earned.amount - self.total_spent.amount)
        return Money.zero()

    def can_afford(self, amount: Money) -> bool:
        """
        Проверить, может ли игрок позволить себе трату.

        Args:
            amount: Сумма.

        Returns:
            True, если баланс >= amount.
        """
        return self.balance.can_afford(amount)

    def to_dict(self) -> dict:
        """
        Сериализация баланса в словарь.

        Returns:
            Словарь с данными баланса.
        """
        return {
            "player_id": self.player_id,
            "balance": self.balance.to_dict(),
            "total_earned": self.total_earned.to_dict(),
            "total_spent": self.total_spent.to_dict(),
        }

    def __str__(self) -> str:
        return (
            f"Баланс игрока {self.player_id}: {self.balance.format()} "
            f"(заработано: {self.total_earned.format()}, "
            f"потрачено: {self.total_spent.format()})"
        )


# ============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================================

def calculate_rent_with_multiplier(
    base_rent: Money,
    multiplier: int,
) -> Money:
    """
    Вычислить арендную плату с множителем.

    Args:
        base_rent: Базовая арендная плата.
        multiplier: Множитель (целое положительное число).

    Returns:
        Итоговая арендная плата.
    """
    return base_rent * multiplier


def calculate_loan_interest(
    principal: Money,
    percent: int,
) -> Money:
    """
    Вычислить проценты по займу.

    Args:
        principal: Основная сумма займа.
        percent: Процентная ставка (0-50).

    Returns:
        Сумма процентов.

    Raises:
        ValueError: Если процент вне допустимого диапазона.
    """
    from shared.constants import MIN_LOAN_PERCENT, MAX_LOAN_PERCENT

    if not (MIN_LOAN_PERCENT <= percent <= MAX_LOAN_PERCENT):
        raise ValueError(
            f"Процент должен быть от {MIN_LOAN_PERCENT} до {MAX_LOAN_PERCENT}: {percent}"
        )
    return principal.percentage(percent)


def calculate_total_with_interest(
    principal: Money,
    percent: int,
) -> Money:
    """
    Вычислить общую сумму долга с процентами.

    Args:
        principal: Основная сумма.
        percent: Процентная ставка.

    Returns:
        Основная сумма + проценты.
    """
    interest = calculate_loan_interest(principal, percent)
    return principal + interest


def calculate_mortgage_value(property_price: Money) -> Money:
    """
    Вычислить залоговую стоимость собственности (половина цены).

    Args:
        property_price: Полная стоимость собственности.

    Returns:
        Залоговая стоимость (50% от цены).
    """
    return property_price // 2


def calculate_unmortgage_cost(mortgage_value: Money) -> Money:
    """
    Вычислить стоимость выкупа из залога (залог + 10%).

    Args:
        mortgage_value: Залоговая стоимость.

    Returns:
        Стоимость выкупа (110% от залоговой стоимости).
    """
    from shared.constants import MORTGAGE_UNMORTGAGE_RATIO

    # Вычисляем 110%
    extra = mortgage_value.percentage(10)
    return mortgage_value + extra


def calculate_auction_start_price(property_price: Money) -> Money:
    """
    Вычислить стартовую цену аукциона (50% от стоимости).

    Args:
        property_price: Полная стоимость собственности.

    Returns:
        Стартовая цена аукциона.
    """
    from shared.constants import AUCTION_START_PRICE_RATIO

    # 50% от стоимости с округлением вверх
    half_amount = int(property_price.amount * AUCTION_START_PRICE_RATIO)
    return Money(half_amount)