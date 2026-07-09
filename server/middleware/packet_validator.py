"""
server/middleware/packet_validator.py

Валидатор сетевых пакетов.

Проверяет:
- Целостность пакета (HMAC)
- Порядковый номер (защита от replay-атак)
- Временную метку (предотвращение просроченных пакетов)
- Размер пакета

Является частью цепочки middleware обработки входящих пакетов.

Python: 3.13+
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from shared.constants import (
    MAX_PACKET_SIZE,
    PACKET_TIMESTAMP_TOLERANCE,
)
from shared.protocol.packet import Packet, PacketHeader, PacketParseError
from shared.protocol.crypto import HMACManager

logger = logging.getLogger("billionaire.security")


# ============================================================================
# ВАЛИДАТОР ПАКЕТОВ
# ============================================================================

class PacketValidator:
    """
    Валидатор входящих сетевых пакетов.

    Выполняет многоуровневую проверку каждого пакета
    перед передачей его в обработку.

    Attributes:
        _sequences: Словарь {session_id: last_sequence} для отслеживания
                    порядковых номеров.
    """

    def __init__(self) -> None:
        """Инициализация валидатора."""
        self._sequences: dict[str, int] = {}

    # ========================================================================
    # ОСНОВНЫЕ ПРОВЕРКИ
    # ========================================================================

    def validate(
        self,
        packet: Packet,
        session_id: str,
        hmac_key: bytes,
    ) -> Optional[str]:
        """
        Выполнить полную валидацию пакета.

        Args:
            packet: Разобранный пакет.
            session_id: ID сессии.
            hmac_key: HMAC-ключ сессии.

        Returns:
            Сообщение об ошибке или None, если пакет валиден.
        """
        # Проверка целостности (HMAC)
        error = self._validate_hmac(packet, hmac_key)
        if error:
            return error

        # Проверка размера
        error = self._validate_size(packet)
        if error:
            return error

        # Проверка порядкового номера
        error = self._validate_sequence(packet, session_id)
        if error:
            return error

        # Проверка временной метки
        error = self._validate_timestamp(packet)
        if error:
            return error

        return None

    def validate_packet_only(self, packet: Packet) -> Optional[str]:
        """
        Базовая проверка пакета (без сессионных данных).

        Используется для пакетов аутентификации,
        когда сессия ещё не создана.

        Args:
            packet: Пакет.

        Returns:
            Сообщение об ошибке или None.
        """
        # Проверка размера
        error = self._validate_size(packet)
        if error:
            return error

        # Проверка временной метки
        error = self._validate_timestamp(packet)
        if error:
            return error

        return None

    # ========================================================================
    # ПРИВАТНЫЕ ПРОВЕРКИ
    # ========================================================================

    def _validate_hmac(
        self,
        packet: Packet,
        hmac_key: bytes,
    ) -> Optional[str]:
        """
        Проверить HMAC-подпись пакета.

        Args:
            packet: Пакет.
            hmac_key: Ключ HMAC.

        Returns:
            Сообщение об ошибке или None.
        """
        # HMAC проверяется на этапе парсинга в PacketParser
        # Здесь дополнительная проверка, если потребуется
        if not packet.hmac or len(packet.hmac) != 32:
            return "Отсутствует или некорректна HMAC-подпись"

        return None

    def _validate_size(self, packet: Packet) -> Optional[str]:
        """
        Проверить размер пакета.

        Args:
            packet: Пакет.

        Returns:
            Сообщение об ошибке или None.
        """
        if packet.header.payload_length > MAX_PACKET_SIZE:
            return (
                f"Размер пакета ({packet.header.payload_length} байт) "
                f"превышает лимит ({MAX_PACKET_SIZE} байт)"
            )

        return None

    def _validate_sequence(
        self,
        packet: Packet,
        session_id: str,
    ) -> Optional[str]:
        """
        Проверить порядковый номер пакета.

        Защита от replay-атак: sequence должен быть
        строго больше предыдущего для данной сессии.

        Args:
            packet: Пакет.
            session_id: ID сессии.

        Returns:
            Сообщение об ошибке или None.
        """
        current_sequence = packet.sequence
        last_sequence = self._sequences.get(session_id, -1)

        # Первый пакет сессии — всегда валиден
        if last_sequence == -1:
            self._sequences[session_id] = current_sequence
            return None

        # Проверка на replay
        if current_sequence <= last_sequence:
            logger.warning(
                "Обнаружена replay-атака: session=%s, "
                "ожидался seq > %d, получен seq=%d",
                session_id,
                last_sequence,
                current_sequence,
            )
            return (
                f"Нарушение последовательности: "
                f"ожидался > {last_sequence}, получен {current_sequence}"
            )

        # Проверка на слишком большой пропуск (> 1000)
        if current_sequence - last_sequence > 1000:
            logger.warning(
                "Большой пропуск последовательности: session=%s, "
                "последний=%d, текущий=%d (разница=%d)",
                session_id,
                last_sequence,
                current_sequence,
                current_sequence - last_sequence,
            )

        self._sequences[session_id] = current_sequence
        return None

    def _validate_timestamp(self, packet: Packet) -> Optional[str]:
        """
        Проверить временную метку пакета.

        Пакет не должен расходиться с серверным временем
        более чем на PACKET_TIMESTAMP_TOLERANCE секунд.

        Args:
            packet: Пакет.

        Returns:
            Сообщение об ошибке или None.
        """
        now_ms = int(time.time() * 1000)
        diff_ms = abs(now_ms - packet.header.timestamp)
        tolerance_ms = PACKET_TIMESTAMP_TOLERANCE * 1000

        if diff_ms > tolerance_ms:
            logger.warning(
                "Пакет вне допустимого временного окна: "
                "разница %.1f сек > %.1f сек",
                diff_ms / 1000,
                PACKET_TIMESTAMP_TOLERANCE,
            )
            return (
                f"Временная метка пакета вне допустимого диапазона "
                f"(разница {diff_ms / 1000:.1f} сек)"
            )

        return None

    # ========================================================================
    # УПРАВЛЕНИЕ ПОСЛЕДОВАТЕЛЬНОСТЯМИ
    # ========================================================================

    def get_last_sequence(self, session_id: str) -> int:
        """
        Получить последний порядковый номер для сессии.

        Args:
            session_id: ID сессии.

        Returns:
            Последний sequence или 0.
        """
        return self._sequences.get(session_id, 0)

    def reset_sequence(self, session_id: str) -> None:
        """
        Сбросить счётчик последовательности для сессии.

        Используется при переподключении.

        Args:
            session_id: ID сессии.
        """
        self._sequences.pop(session_id, None)
        logger.debug("Сброшен счётчик последовательности для сессии %s", session_id)

    def remove_session(self, session_id: str) -> None:
        """
        Удалить данные сессии.

        Args:
            session_id: ID сессии.
        """
        self._sequences.pop(session_id, None)

    def get_stats(self) -> dict:
        """
        Получить статистику валидатора.

        Returns:
            Словарь с метриками.
        """
        return {
            "active_sessions": len(self._sequences),
        }