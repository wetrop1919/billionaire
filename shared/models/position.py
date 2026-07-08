"""
shared/models/position.py

Модели позиционирования на игровом поле для проекта "Миллиардер".

Содержит:
- CellPosition — описание одной клетки игрового поля
- BoardPosition — позиция игрока на поле с отслеживанием прохождения Старта
- Board — полное игровое поле со всеми клетками

Используется игровым движком для перемещения игроков,
определения типа клетки и расчёта позиции.

Python: 3.13+
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Self

from shared.enums import CellType


# ============================================================================
# ПОЗИЦИЯ НА КЛЕТКЕ (CellPosition)
# ============================================================================

@dataclass(slots=True)
class CellPosition:
    """
    Описание одной клетки игрового поля.

    Представляет статическую информацию о клетке: её тип,
    название, связанную собственность (если есть) и действие.

    Attributes:
        cell_id: Номер клетки на поле (0-39 для основных, особые для спецклеток).
        name: Название клетки.
        type: Тип клетки (START, PROPERTY, CHANCE, FUND, JAIL, и т.д.).
        property_id: ID связанной собственности (если type == PROPERTY).
        action: Дополнительное действие клетки (налог, перемещение).
        action_data: Параметры действия.
        position_x: X-координата для отрисовки (0-10).
        position_y: Y-координата для отрисовки (0-10).
        side: Сторона поля (0-3: низ, лево, верх, право).
    """

    cell_id: int
    name: str
    type: CellType
    property_id: Optional[str] = None
    action: Optional[str] = None
    action_data: dict = field(default_factory=dict)
    position_x: int = 0
    position_y: int = 0
    side: int = 0

    # === СВОЙСТВА ===

    @property
    def is_property(self) -> bool:
        """Является ли клетка собственностью."""
        return self.type == CellType.PROPERTY

    @property
    def is_chance(self) -> bool:
        """Является ли клетка Шанс."""
        return self.type == CellType.CHANCE

    @property
    def is_fund(self) -> bool:
        """Является ли клетка Фонд."""
        return self.type == CellType.FUND

    @property
    def is_start(self) -> bool:
        """Является ли клетка Старт."""
        return self.type == CellType.START

    @property
    def is_jail(self) -> bool:
        """Является ли клетка Тюрьма."""
        return self.type == CellType.JAIL

    @property
    def is_jail_visit(self) -> bool:
        """Является ли клетка посещения тюрьмы."""
        return self.type == CellType.JAIL_VISIT

    @property
    def is_go_to_jail(self) -> bool:
        """Отправляет ли клетка в тюрьму."""
        return self.type == CellType.GO_TO_JAIL

    @property
    def is_free_parking(self) -> bool:
        """Является ли клетка Бесплатная парковка."""
        return self.type == CellType.FREE_PARKING

    @property
    def is_tax(self) -> bool:
        """Является ли клетка налогом."""
        return self.type == CellType.TAX

    @property
    def is_veranda(self) -> bool:
        """Является ли клетка Верандой."""
        return self.type == CellType.VERANDA

    @property
    def requires_action(self) -> bool:
        """Требует ли клетка немедленного действия от игрока."""
        return self.type in (
            CellType.CHANCE,
            CellType.FUND,
            CellType.TAX,
            CellType.GO_TO_JAIL,
        )

    @property
    def can_be_purchased(self) -> bool:
        """Можно ли купить эту клетку."""
        return self.type == CellType.PROPERTY and self.property_id is not None

    def get_tax_amount(self) -> int | None:
        """
        Получить сумму налога для клетки TAX.

        Returns:
            Сумма налога или None, если клетка не налоговая.
        """
        if self.type != CellType.TAX:
            return None
        return self.action_data.get("amount", 0)

    def get_tax_is_percentage(self) -> bool:
        """
        Проверить, является ли налог процентным (от суммы денег игрока).

        Returns:
            True, если налог вычисляется как процент.
        """
        return self.action_data.get("is_percentage", False)

    # === СЕРИАЛИЗАЦИЯ ===

    def to_dict(self) -> dict:
        """
        Сериализация клетки в словарь.

        Returns:
            Словарь с данными клетки.
        """
        return {
            "cell_id": self.cell_id,
            "name": self.name,
            "type": self.type.value,
            "property_id": self.property_id,
            "action": self.action,
            "action_data": self.action_data,
            "position_x": self.position_x,
            "position_y": self.position_y,
            "side": self.side,
        }

    @classmethod
    def from_dict(cls, data: dict) -> CellPosition:
        """
        Создать клетку из словаря (из JSON-конфигурации).

        Args:
            data: Словарь с данными клетки.

        Returns:
            Новый экземпляр CellPosition.
        """
        return cls(
            cell_id=data["cell_id"],
            name=data["name"],
            type=CellType(data["type"]),
            property_id=data.get("property_id"),
            action=data.get("action"),
            action_data=data.get("action_data", {}),
            position_x=data.get("position_x", 0),
            position_y=data.get("position_y", 0),
            side=data.get("side", 0),
        )

    def __repr__(self) -> str:
        return (
            f"Cell({self.cell_id}: '{self.name}', "
            f"type={self.type.value})"
        )


# ============================================================================
# ПОЗИЦИЯ НА ДОСКЕ (BoardPosition)
# ============================================================================

@dataclass(slots=True)
class BoardPosition:
    """
    Текущая позиция игрока на игровом поле.

    Отслеживает номер клетки, количество прохождений Старта
    и общее количество пройденных клеток за игру.

    Attributes:
        cell_id: Текущий номер клетки (0-39).
        laps_completed: Количество полных кругов (прохождений Старта).
        total_cells_traveled: Общее количество пройденных клеток за игру.
    """

    cell_id: int = 0
    laps_completed: int = 0
    total_cells_traveled: int = 0

    def __post_init__(self) -> None:
        """Валидация позиции."""
        if self.cell_id < 0:
            raise ValueError(f"ID клетки не может быть отрицательным: {self.cell_id}")

    # === ПЕРЕМЕЩЕНИЕ ===

    def move(self, steps: int, board_size: int = 40) -> bool:
        """
        Переместиться на указанное количество шагов вперёд.

        Автоматически отслеживает прохождение Старта и обновляет
        счётчики кругов и пройденных клеток.

        Args:
            steps: Количество шагов вперёд (должно быть >= 0).
            board_size: Размер игрового поля (по умолчанию 40).

        Returns:
            True, если игрок прошёл через Старт (и получит бонус).

        Raises:
            ValueError: Если steps отрицательный.
        """
        if steps < 0:
            raise ValueError(f"Количество шагов не может быть отрицательным: {steps}")

        old_cell = self.cell_id
        new_position = old_cell + steps
        passed_start = False

        if new_position >= board_size:
            # Прошли через Старт
            passed_start = True
            self.laps_completed += 1
            new_position = new_position % board_size

        self.cell_id = new_position
        self.total_cells_traveled += steps
        return passed_start

    def move_to(self, target_cell: int, board_size: int = 40) -> bool:
        """
        Переместиться на указанную клетку.

        Вычисляет кратчайший путь вперёд до цели. Если цель "позади"
        текущей позиции, игрок проходит через Старт.

        Args:
            target_cell: Целевая клетка (0 до board_size-1).
            board_size: Размер поля.

        Returns:
            True, если игрок прошёл через Старт.

        Raises:
            ValueError: Если target_cell вне допустимого диапазона.
        """
        if not (0 <= target_cell < board_size):
            raise ValueError(
                f"Целевая клетка должна быть от 0 до {board_size - 1}: {target_cell}"
            )

        if target_cell == self.cell_id:
            return False

        if target_cell > self.cell_id:
            steps = target_cell - self.cell_id
        else:
            # Цель "позади" — идём через Старт
            steps = (board_size - self.cell_id) + target_cell

        return self.move(steps, board_size)

    def move_backward(self, steps: int, board_size: int = 40) -> None:
        """
        Переместиться назад на указанное количество шагов.

        Не может пройти меньше клетки 0 (останавливается на 0).

        Args:
            steps: Количество шагов назад (должно быть >= 0).
            board_size: Размер поля.

        Raises:
            ValueError: Если steps отрицательный.
        """
        if steps < 0:
            raise ValueError(f"Количество шагов не может быть отрицательным: {steps}")

        new_position = self.cell_id - steps
        if new_position < 0:
            new_position = 0
        self.cell_id = new_position
        self.total_cells_traveled += steps

    def teleport(self, target_cell: int) -> None:
        """
        Телепортироваться на указанную клетку без прохождения Старта.

        Args:
            target_cell: Целевая клетка.

        Raises:
            ValueError: Если target_cell < 0.
        """
        if target_cell < 0:
            raise ValueError(f"Целевая клетка не может быть отрицательной: {target_cell}")
        self.cell_id = target_cell

    # === ПРОВЕРКИ ===

    def is_on_cell(self, cell_id: int) -> bool:
        """
        Проверить, находится ли игрок на указанной клетке.

        Args:
            cell_id: ID клетки.

        Returns:
            True, если игрок на этой клетке.
        """
        return self.cell_id == cell_id

    @property
    def is_on_start(self) -> bool:
        """Находится ли игрок на клетке Старт (0)."""
        return self.cell_id == 0

    # === СЕРИАЛИЗАЦИЯ ===

    def to_dict(self) -> dict:
        """
        Сериализация позиции в словарь.

        Returns:
            Словарь с данными позиции.
        """
        return {
            "cell_id": self.cell_id,
            "laps_completed": self.laps_completed,
            "total_cells_traveled": self.total_cells_traveled,
        }

    @classmethod
    def from_dict(cls, data: dict) -> BoardPosition:
        """
        Создать позицию из словаря.

        Args:
            data: Словарь с данными позиции.

        Returns:
            Новый экземпляр BoardPosition.
        """
        return cls(
            cell_id=data.get("cell_id", 0),
            laps_completed=data.get("laps_completed", 0),
            total_cells_traveled=data.get("total_cells_traveled", 0),
        )

    def __repr__(self) -> str:
        return (
            f"BoardPosition(cell={self.cell_id}, "
            f"laps={self.laps_completed}, total={self.total_cells_traveled})"
        )


# ============================================================================
# ИГРОВОЕ ПОЛЕ (Board)
# ============================================================================

@dataclass(slots=True)
class Board:
    """
    Полное игровое поле со всеми клетками.

    Содержит массив из 40+ основных клеток и специальные клетки
    (например, Веранда). Загружается из JSON-конфигурации.

    Attributes:
        cells: Список всех клеток на поле (индекс = cell_id).
        special_cells: Особые клетки вне основного поля (Веранда).
        board_size: Размер основного поля (обычно 40).
    """

    cells: list[CellPosition] = field(default_factory=list)
    special_cells: dict[str, CellPosition] = field(default_factory=dict)
    board_size: int = 40

    def __post_init__(self) -> None:
        """Сортировка клеток по cell_id после инициализации."""
        if self.cells:
            self.cells.sort(key=lambda c: c.cell_id)
            self.board_size = len(self.cells)

    # === ДОСТУП К КЛЕТКАМ ===

    def get_cell(self, cell_id: int) -> CellPosition | None:
        """
        Получить клетку по ID.

        Args:
            cell_id: ID клетки.

        Returns:
            Клетку или None, если не найдена.
        """
        if 0 <= cell_id < len(self.cells):
            return self.cells[cell_id]
        return None

    def get_special_cell(self, cell_name: str) -> CellPosition | None:
        """
        Получить специальную клетку по имени.

        Args:
            cell_name: Имя клетки (например, "veranda").

        Returns:
            Специальную клетку или None.
        """
        return self.special_cells.get(cell_name)

    def get_cell_by_name(self, name: str) -> CellPosition | None:
        """
        Найти клетку по названию.

        Args:
            name: Название клетки.

        Returns:
            Клетку или None.
        """
        for cell in self.cells:
            if cell.name.lower() == name.lower():
                return cell
        for cell in self.special_cells.values():
            if cell.name.lower() == name.lower():
                return cell
        return None

    def get_property_cells(self) -> list[CellPosition]:
        """
        Получить все клетки, являющиеся собственностью.

        Returns:
            Список клеток с типом PROPERTY.
        """
        return [cell for cell in self.cells if cell.is_property]

    def get_cells_by_type(self, cell_type: CellType) -> list[CellPosition]:
        """
        Получить все клетки заданного типа.

        Args:
            cell_type: Тип клетки.

        Returns:
            Список клеток указанного типа.
        """
        return [cell for cell in self.cells if cell.type == cell_type]

    def get_start_cell(self) -> CellPosition | None:
        """Получить клетку Старт."""
        for cell in self.cells:
            if cell.is_start:
                return cell
        return None

    def get_jail_cell(self) -> CellPosition | None:
        """Получить клетку Тюрьма."""
        for cell in self.cells:
            if cell.is_jail:
                return cell
        return None

    def get_go_to_jail_cell(self) -> CellPosition | None:
        """Получить клетку, отправляющую в тюрьму."""
        for cell in self.cells:
            if cell.is_go_to_jail:
                return cell
        return None

    def get_veranda_cell(self) -> CellPosition | None:
        """Получить клетку Веранда (специальная)."""
        return self.special_cells.get("veranda")

    # === ПРОВЕРКИ ===

    def is_valid_cell(self, cell_id: int) -> bool:
        """
        Проверить, существует ли клетка с указанным ID.

        Args:
            cell_id: ID клетки.

        Returns:
            True, если клетка существует.
        """
        return 0 <= cell_id < len(self.cells)

    # === СЕРИАЛИЗАЦИЯ ===

    def to_dict(self) -> dict:
        """
        Сериализация поля в словарь.

        Returns:
            Словарь с данными поля.
        """
        return {
            "cells": [cell.to_dict() for cell in self.cells],
            "special_cells": {
                name: cell.to_dict()
                for name, cell in self.special_cells.items()
            },
            "board_size": self.board_size,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Board:
        """
        Создать поле из словаря (из JSON-конфигурации).

        Args:
            data: Словарь с данными поля.

        Returns:
            Новый экземпляр Board.
        """
        cells = [CellPosition.from_dict(c) for c in data.get("cells", [])]
        special = {
            name: CellPosition.from_dict(cell_data)
            for name, cell_data in data.get("special_cells", {}).items()
        }
        return cls(
            cells=cells,
            special_cells=special,
            board_size=data.get("board_size", 40),
        )

    def __repr__(self) -> str:
        return (
            f"Board(size={self.board_size}, "
            f"cells={len(self.cells)}, special={len(self.special_cells)})"
        )