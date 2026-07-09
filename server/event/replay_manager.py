"""
server/event/replay_manager.py

Менеджер воспроизведения игр (Replay).

Обеспечивает:
- Запись всех событий игры для последующего воспроизведения
- Хранение реплеев в БД и/или файлах
- Экспорт реплеев в JSON
- Загрузку и воспроизведение с любой точки

Replay позволяет просмотреть полную историю игры:
все ходы, покупки, броски кубиков, сделки и банкротства.

Python: 3.13+
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import UUID, uuid4

from shared.enums import EventType
from database.repositories.postgresql.event_repository import EventRepository

logger = logging.getLogger("billionaire.server")


# ============================================================================
# МОДЕЛЬ РЕПЛЕЯ
# ============================================================================

@dataclass(slots=True)
class Replay:
    """
    Запись одной игры для воспроизведения.

    Attributes:
        replay_id: Уникальный идентификатор реплея.
        game_id: ID исходной игры.
        events: Список событий в хронологическом порядке.
        started_at: Время начала игры.
        finished_at: Время завершения.
        players: Список игроков.
        winner_id: ID победителя.
        total_turns: Общее количество ходов.
    """

    replay_id: UUID
    game_id: UUID
    events: list[dict[str, Any]] = field(default_factory=list)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    players: list[dict[str, Any]] = field(default_factory=list)
    winner_id: Optional[UUID] = None
    total_turns: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Сериализация реплея в словарь."""
        return {
            "replay_id": str(self.replay_id),
            "game_id": str(self.game_id),
            "events": self.events,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "players": self.players,
            "winner_id": str(self.winner_id) if self.winner_id else None,
            "total_turns": self.total_turns,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Replay:
        """Создать реплей из словаря."""
        return cls(
            replay_id=UUID(data["replay_id"]),
            game_id=UUID(data["game_id"]),
            events=data.get("events", []),
            started_at=datetime.fromisoformat(data["started_at"])
                if data.get("started_at") else None,
            finished_at=datetime.fromisoformat(data["finished_at"])
                if data.get("finished_at") else None,
            players=data.get("players", []),
            winner_id=UUID(data["winner_id"]) if data.get("winner_id") else None,
            total_turns=data.get("total_turns", 0),
        )


# ============================================================================
# МЕНЕДЖЕР РЕПЛЕЕВ
# ============================================================================

class ReplayManager:
    """
    Менеджер записи и воспроизведения игр.

    Подписывается на EventBus для автоматической записи
    всех событий игры в реплей.

    Usage:
        manager = ReplayManager(event_repo, replay_dir="replays")
        manager.start_recording(game_id)
        # ... игра идёт ...
        manager.stop_recording(game_id)
        replay = manager.get_replay(replay_id)
    """

    def __init__(
        self,
        event_repository: EventRepository,
        replay_dir: str = "replays",
    ) -> None:
        """
        Инициализация менеджера реплеев.

        Args:
            event_repository: Репозиторий для доступа к событиям.
            replay_dir: Директория для хранения экспортированных реплеев.
        """
        self._event_repo = event_repository
        self._replay_dir: Path = Path(replay_dir)

        # Активные записи {game_id: Replay}
        self._active_recordings: dict[UUID, Replay] = {}

        # Кеш загруженных реплеев
        self._cache: dict[UUID, Replay] = {}

    # ========================================================================
    # ЗАПИСЬ РЕПЛЕЯ
    # ========================================================================

    def start_recording(
        self,
        game_id: UUID,
        players: list[dict[str, Any]],
    ) -> Replay:
        """
        Начать запись реплея для игры.

        Args:
            game_id: ID игры.
            players: Список игроков [{user_id, username, color}].

        Returns:
            Новый объект Replay.
        """
        if game_id in self._active_recordings:
            logger.warning("Запись для игры %s уже ведётся", game_id)
            return self._active_recordings[game_id]

        replay = Replay(
            replay_id=uuid4(),
            game_id=game_id,
            started_at=datetime.now(timezone.utc),
            players=players,
        )

        self._active_recordings[game_id] = replay
        logger.info("Начата запись реплея для игры %s", game_id)

        return replay

    async def record_event(
        self,
        game_id: UUID,
        event_type: EventType,
        data: dict[str, Any],
    ) -> None:
        """
        Записать событие в активный реплей.

        Args:
            game_id: ID игры.
            event_type: Тип события.
            data: Данные события.
        """
        replay = self._active_recordings.get(game_id)
        if replay is None:
            return

        event = {
            "event_type": event_type.value,
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        replay.events.append(event)

    def stop_recording(
        self,
        game_id: UUID,
        winner_id: Optional[UUID] = None,
        total_turns: int = 0,
    ) -> Optional[Replay]:
        """
        Остановить запись реплея.

        Args:
            game_id: ID игры.
            winner_id: ID победителя.
            total_turns: Общее количество ходов.

        Returns:
            Завершённый реплей или None.
        """
        replay = self._active_recordings.pop(game_id, None)
        if replay is None:
            logger.warning("Нет активной записи для игры %s", game_id)
            return None

        replay.finished_at = datetime.now(timezone.utc)
        replay.winner_id = winner_id
        replay.total_turns = total_turns

        # Сохраняем в кеш
        self._cache[replay.replay_id] = replay

        logger.info(
            "Запись реплея завершена: игра=%s, событий=%d",
            game_id,
            len(replay.events),
        )

        return replay

    # ========================================================================
    # ОБРАБОТЧИК ДЛЯ EVENTBUS
    # ========================================================================

    async def handle_event(
        self,
        event_type: EventType,
        data: dict[str, Any],
    ) -> None:
        """
        Обработчик событий из EventBus.

        Автоматически записывает все события в активные реплеи.

        Args:
            event_type: Тип события.
            data: Данные события.
        """
        game_id = data.get("game_id")
        if game_id is None:
            return

        if isinstance(game_id, str):
            game_id = UUID(game_id)

        await self.record_event(game_id, event_type, data)

    # ========================================================================
    # ЗАГРУЗКА РЕПЛЕЯ
    # ========================================================================

    async def load_replay_from_db(self, game_id: UUID) -> Optional[Replay]:
        """
        Загрузить реплей из базы данных.

        Args:
            game_id: ID игры.

        Returns:
            Replay или None.
        """
        events = await self._event_repo.get_game_events(
            game_id=game_id,
            limit=10_000,  # Максимум событий для реплея
        )

        if not events:
            logger.warning("События для игры %s не найдены", game_id)
            return None

        replay = Replay(
            replay_id=uuid4(),
            game_id=game_id,
            events=events,
            total_turns=events[-1].get("turn_number", 0) if events else 0,
        )

        self._cache[replay.replay_id] = replay
        return replay

    def get_replay(self, replay_id: UUID) -> Optional[Replay]:
        """
        Получить реплей из кеша.

        Args:
            replay_id: ID реплея.

        Returns:
            Replay или None.
        """
        return self._cache.get(replay_id)

    def get_replay_by_game_id(self, game_id: UUID) -> Optional[Replay]:
        """
        Найти реплей по ID игры.

        Args:
            game_id: ID игры.

        Returns:
            Replay или None.
        """
        for replay in self._cache.values():
            if replay.game_id == game_id:
                return replay
        return None

    # ========================================================================
    # ЭКСПОРТ
    # ========================================================================

    async def export_replay(
        self,
        replay_id: UUID,
        output_path: Optional[str] = None,
    ) -> Optional[str]:
        """
        Экспортировать реплей в JSON-файл.

        Args:
            replay_id: ID реплея.
            output_path: Путь для сохранения (если None — авто).

        Returns:
            Путь к сохранённому файлу или None.
        """
        replay = self.get_replay(replay_id)
        if replay is None:
            logger.warning("Реплей %s не найден для экспорта", replay_id)
            return None

        # Создаём директорию
        self._replay_dir.mkdir(parents=True, exist_ok=True)

        # Формируем имя файла
        if output_path is None:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            filename = f"replay_{replay.game_id}_{timestamp}.json"
            output_path = str(self._replay_dir / filename)

        try:
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(replay.to_dict(), f, ensure_ascii=False, indent=2)

            logger.info(
                "Реплей экспортирован: %s (событий: %d)",
                output_path,
                len(replay.events),
            )
            return output_path

        except OSError as e:
            logger.error("Ошибка экспорта реплея: %s", e)
            return None

    async def export_replay_from_db(
        self,
        game_id: UUID,
        output_path: Optional[str] = None,
    ) -> Optional[str]:
        """
        Загрузить реплей из БД и экспортировать.

        Args:
            game_id: ID игры.
            output_path: Путь для сохранения.

        Returns:
            Путь к файлу или None.
        """
        replay = await self.load_replay_from_db(game_id)
        if replay is None:
            return None

        return await self.export_replay(replay.replay_id, output_path)

    # ========================================================================
    # ВОСПРОИЗВЕДЕНИЕ
    # ========================================================================

    def get_events_at_position(
        self,
        replay_id: UUID,
        position: int,
    ) -> Optional[dict[str, Any]]:
        """
        Получить событие по позиции в реплее.

        Args:
            replay_id: ID реплея.
            position: Индекс события (0 = первое).

        Returns:
            Событие или None.
        """
        replay = self.get_replay(replay_id)
        if replay is None:
            return None

        if 0 <= position < len(replay.events):
            return replay.events[position]

        return None

    def get_events_range(
        self,
        replay_id: UUID,
        start: int = 0,
        end: Optional[int] = None,
    ) -> list[dict[str, Any]]:
        """
        Получить диапазон событий из реплея.

        Args:
            replay_id: ID реплея.
            start: Начальный индекс.
            end: Конечный индекс (None = до конца).

        Returns:
            Список событий.
        """
        replay = self.get_replay(replay_id)
        if replay is None:
            return []

        if end is None:
            end = len(replay.events)

        return replay.events[start:end]

    def get_turn_events(
        self,
        replay_id: UUID,
        turn_number: int,
    ) -> list[dict[str, Any]]:
        """
        Получить все события за указанный ход.

        Args:
            replay_id: ID реплея.
            turn_number: Номер хода.

        Returns:
            Список событий хода.
        """
        replay = self.get_replay(replay_id)
        if replay is None:
            return []

        return [
            e for e in replay.events
            if e.get("data", {}).get("turn_number") == turn_number
        ]

    # ========================================================================
    # ОЧИСТКА
    # ========================================================================

    def clear_cache(self) -> int:
        """
        Очистить кеш реплеев.

        Returns:
            Количество удалённых из кеша реплеев.
        """
        count = len(self._cache)
        self._cache.clear()
        logger.debug("Кеш реплеев очищен (%d записей)", count)
        return count

    def remove_replay(self, replay_id: UUID) -> bool:
        """
        Удалить реплей из кеша.

        Args:
            replay_id: ID реплея.

        Returns:
            True, если удалён.
        """
        return self._cache.pop(replay_id, None) is not None

    # ========================================================================
    # ИНФОРМАЦИЯ
    # ========================================================================

    @property
    def active_recordings_count(self) -> int:
        """Количество активных записей."""
        return len(self._active_recordings)

    @property
    def cached_replays_count(self) -> int:
        """Количество закешированных реплеев."""
        return len(self._cache)

    def get_stats(self) -> dict:
        """
        Получить статистику менеджера реплеев.

        Returns:
            Словарь с метриками.
        """
        return {
            "active_recordings": self.active_recordings_count,
            "cached_replays": self.cached_replays_count,
            "replay_dir": str(self._replay_dir.absolute()),
        }