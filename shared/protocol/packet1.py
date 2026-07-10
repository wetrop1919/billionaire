"""
shared/protocol/packet.py

Сборка и разборка сетевых пакетов для проекта "Миллиардер".

Формат пакета:
    [Magic: 4] [Version: 6] [Type: 2] [Flags: 2] [PayloadLen: 4]
    [Sequence: 8] [Timestamp: 8]
    [Payload: N]
    [HMAC: 32]

Пакет поддерживает:
- Версионирование протокола
- Сжатие полезной нагрузки (zlib)
- HMAC-подпись для проверки целостности
- Порядковые номера для защиты от replay-атак
- Временные метки для предотвращения просроченных пакетов

Python: 3.13+
"""

from __future__ import annotations

import struct
import time
from dataclasses import dataclass
from typing import Any, Optional, Self

from shared.constants import (
    MAGIC_NUMBER,
    PACKET_HEADER_SIZE,
    HMAC_SIZE,
    MAX_PACKET_SIZE,
    MAX_PAYLOAD_SIZE,
    PACKET_TIMESTAMP_TOLERANCE,
    PROTOCOL_VERSION_MAJOR,
    PROTOCOL_VERSION_MINOR,
    PROTOCOL_VERSION_PATCH,
)
from shared.enums import PacketType, PacketFlags
from shared.protocol.compression import Compressor
from shared.protocol.crypto import HMACManager
from shared.protocol.serializer import JSONSerializer
from shared.protocol.version import ProtocolVersion


# ============================================================================
# ИСКЛЮЧЕНИЯ ПАКЕТА
# ============================================================================

class PacketError(Exception):
    """Ошибка при обработке пакета."""

    def __init__(self, message: str) -> None:
        super().__init__(f"Ошибка пакета: {message}")


class PacketBuildError(PacketError):
    """Ошибка при сборке пакета."""

    def __init__(self, message: str) -> None:
        super().__init__(f"Ошибка сборки: {message}")


class PacketParseError(PacketError):
    """Ошибка при разборе пакета."""

    def __init__(self, message: str) -> None:
        super().__init__(f"Ошибка разбора: {message}")


# ============================================================================
# ЗАГОЛОВОК ПАКЕТА
# ============================================================================

@dataclass(slots=True)
class PacketHeader:
    """
    Заголовок сетевого пакета.

    Содержит метаданные для маршрутизации, проверки целостности
    и защиты от повторной отправки.

    Attributes:
        magic: Магическое число (0x4247484D).
        version: Версия протокола.
        packet_type: Тип пакета (PacketType).
        flags: Битовые флаги (сжатие, шифрование).
        payload_length: Длина полезной нагрузки в байтах.
        sequence: Порядковый номер пакета.
        timestamp: Время отправки (Unix timestamp в миллисекундах).
    """

    magic: int
    version: ProtocolVersion
    packet_type: PacketType
    flags: PacketFlags
    payload_length: int
    sequence: int
    timestamp: int

    @property
    def is_compressed(self) -> bool:
        """Сжат ли пакет."""
        return bool(self.flags & PacketFlags.COMPRESSED)

    @property
    def is_encrypted(self) -> bool:
        """Зашифрован ли пакет."""
        return bool(self.flags & PacketFlags.ENCRYPTED)

    @property
    def is_urgent(self) -> bool:
        """Приоритетный ли пакет."""
        return bool(self.flags & PacketFlags.URGENT)

    def to_bytes(self) -> bytes:
        """
        Сериализовать заголовок в байты.

        Returns:
            26 байт заголовка.
        """
        # Упаковка версии: 2 байта major, 2 байта minor, 2 байта patch
        version_bytes = struct.pack(
            ">HHH",
            self.version.major,
            self.version.minor,
            self.version.patch,
        )

        header = struct.pack(
            ">IHHIIQ",
            self.magic,                # 4 байта
            self.packet_type.value,    # 2 байта
            self.flags.value,          # 2 байта
            self.payload_length,       # 4 байта
            self.sequence,             # 8 байт
            self.timestamp,            # 8 байт
        )

        return header[:4] + version_bytes + header[4:]

    @classmethod
    def from_bytes(cls, data: bytes) -> PacketHeader:
        """
        Десериализовать заголовок из байтов.

        Args:
            data: Ровно 26 байт заголовка.

        Returns:
            PacketHeader.

        Raises:
            PacketParseError: Если длина данных некорректна.
        """
        if len(data) < PACKET_HEADER_SIZE:
            raise PacketParseError(
                f"Недостаточно данных для заголовка: "
                f"{len(data)} < {PACKET_HEADER_SIZE}"
            )

        magic = struct.unpack(">I", data[0:4])[0]

        # Распаковка версии из байтов 4-9
        ver_major, ver_minor, ver_patch = struct.unpack(">HHH", data[4:10])
        version = ProtocolVersion(major=ver_major, minor=ver_minor, patch=ver_patch)

        # Остальные поля из байтов 10-26
        packet_type_val, flags_val, payload_length, sequence, timestamp = struct.unpack(
            ">HHIIQ",
            data[10:26],
        )

        return cls(
            magic=magic,
            version=version,
            packet_type=PacketType(packet_type_val),
            flags=PacketFlags(flags_val),
            payload_length=payload_length,
            sequence=sequence,
            timestamp=timestamp,
        )


# ============================================================================
# ПАКЕТ
# ============================================================================

@dataclass(slots=True)
class Packet:
    """
    Полный сетевой пакет.

    Объединяет заголовок, полезную нагрузку и HMAC-подпись.

    Attributes:
        header: Заголовок пакета.
        payload: Полезная нагрузка (словарь с данными).
        hmac: HMAC-подпись для проверки целостности.
    """

    header: PacketHeader
    payload: dict[str, Any]
    hmac: bytes

    @property
    def packet_type(self) -> PacketType:
        """Тип пакета (из заголовка)."""
        return self.header.packet_type

    @property
    def sequence(self) -> int:
        """Порядковый номер (из заголовка)."""
        return self.header.sequence

    def get_payload_field(self, key: str, default: Any = None) -> Any:
        """
        Безопасно получить поле из полезной нагрузки.

        Args:
            key: Ключ поля.
            default: Значение по умолчанию.

        Returns:
            Значение поля или default.
        """
        return self.payload.get(key, default)

    def to_dict(self) -> dict[str, Any]:
        """
        Сериализовать пакет в словарь для логирования.

        Returns:
            Словарь с метаданными пакета (без полной нагрузки).
        """
        return {
            "type": self.packet_type.name,
            "sequence": self.sequence,
            "flags": self.header.flags.name,
            "payload_size": self.header.payload_length,
            "timestamp": self.header.timestamp,
        }


# ============================================================================
# СБОРЩИК ПАКЕТОВ (PacketBuilder)
# ============================================================================

class PacketBuilder:
    """
    Сборка пакетов для отправки.

    Использует Builder Pattern для последовательного конструирования
    пакета с последующей сериализацией в байты.

    Usage:
        builder = PacketBuilder()
        packet_bytes = (
            builder
            .set_type(PacketType.LOGIN_REQUEST)
            .set_payload({"username": "test", "password_hash": "..."})
            .set_sequence(42)
            .build(hmac_key)
        )
    """

    def __init__(self) -> None:
        self._packet_type: PacketType = PacketType.HEARTBEAT_REQUEST
        self._payload: dict[str, Any] = {}
        self._sequence: int = 0
        self._compress: bool = True
        self._urgent: bool = False

    def set_type(self, packet_type: PacketType) -> Self:
        """
        Установить тип пакета.

        Args:
            packet_type: Тип пакета.

        Returns:
            Self для chaining.
        """
        self._packet_type = packet_type
        return self

    def set_payload(self, payload: dict[str, Any]) -> Self:
        """
        Установить полезную нагрузку.

        Args:
            payload: Словарь с данными.

        Returns:
            Self для chaining.
        """
        self._payload = payload
        return self

    def set_sequence(self, sequence: int) -> Self:
        """
        Установить порядковый номер.

        Args:
            sequence: Порядковый номер.

        Returns:
            Self для chaining.
        """
        self._sequence = sequence
        return self

    def set_compress(self, compress: bool) -> Self:
        """
        Включить/отключить сжатие.

        Args:
            compress: Сжимать ли пакет.

        Returns:
            Self для chaining.
        """
        self._compress = compress
        return self

    def set_urgent(self, urgent: bool) -> Self:
        """
        Пометить пакет как срочный.

        Args:
            urgent: Срочный ли пакет.

        Returns:
            Self для chaining.
        """
        self._urgent = urgent
        return self

    def build(self, hmac_key: bytes) -> bytes:
        """
        Собрать пакет в байты для отправки.

        Args:
            hmac_key: Ключ для HMAC-подписи.

        Returns:
            Готовые байты пакета.

        Raises:
            PacketBuildError: При ошибке сборки.
        """
        try:
            return _build_packet_bytes(
                packet_type=self._packet_type,
                payload=self._payload,
                sequence=self._sequence,
                hmac_key=hmac_key,
                compress=self._compress,
                urgent=self._urgent,
            )
        except Exception as e:
            raise PacketBuildError(str(e)) from e

    def reset(self) -> Self:
        """
        Сбросить все параметры строителя.

        Returns:
            Self для chaining.
        """
        self._packet_type = PacketType.HEARTBEAT_REQUEST
        self._payload = {}
        self._sequence = 0
        self._compress = True
        self._urgent = False
        return self


# ============================================================================
# ПАРСЕР ПАКЕТОВ (PacketParser)
# ============================================================================

class PacketParser:
    """
    Разбор входящих байтов в объект Packet.

    Выполняет:
    - Проверку магического числа
    - Проверку версии протокола
    - Проверку размера пакета
    - Распаковку сжатых данных
    - Проверку HMAC-подписи
    - Проверку временной метки

    Usage:
        parser = PacketParser()
        packet = parser.parse(data_bytes, hmac_key)
    """

    def __init__(self) -> None:
        pass

    def parse(self, data: bytes, hmac_key: bytes) -> Packet:
        """
        Разобрать входящие байты в пакет.

        Args:
            data: Байты пакета (заголовок + нагрузка + HMAC).
            hmac_key: Ключ для проверки HMAC.

        Returns:
            Объект Packet.

        Raises:
            PacketParseError: При любой ошибке разбора.
        """
        try:
            return _parse_packet_bytes(data, hmac_key)
        except PacketParseError:
            raise
        except Exception as e:
            raise PacketParseError(str(e)) from e


# ============================================================================
# ФУНКЦИИ СБОРКИ (НИЗКОУРОВНЕВЫЕ)
# ============================================================================

def _build_packet_bytes(
    packet_type: PacketType,
    payload: dict[str, Any],
    sequence: int,
    hmac_key: bytes,
    compress: bool = True,
    urgent: bool = False,
) -> bytes:
    """
    Собрать пакет в байты.

    Args:
        packet_type: Тип пакета.
        payload: Полезная нагрузка.
        sequence: Порядковый номер.
        hmac_key: Ключ HMAC.
        compress: Сжимать ли данные.
        urgent: Срочный ли пакет.

    Returns:
        Байты пакета.
    """
    # Сериализуем payload в JSON
    payload_json = JSONSerializer.serialize_to_json(payload)
    payload_bytes = payload_json.encode("utf-8")

    # Определяем флаги
    flags = PacketFlags.NONE
    if urgent:
        flags |= PacketFlags.URGENT

    # Сжатие (если включено и размер превышает порог)
    if compress:
        compressed = Compressor.compress(payload_bytes)
        if Compressor.is_compressed(compressed):
            flags |= PacketFlags.COMPRESSED
            payload_bytes = compressed

    # Проверка размера
    if len(payload_bytes) > MAX_PAYLOAD_SIZE:
        raise PacketBuildError(
            f"Размер нагрузки ({len(payload_bytes)} байт) "
            f"превышает лимит ({MAX_PAYLOAD_SIZE} байт)"
        )

    # Текущее время в миллисекундах
    timestamp_ms = int(time.time() * 1000)

    # Собираем заголовок
    header = PacketHeader(
        magic=MAGIC_NUMBER,
        version=ProtocolVersion(
            major=PROTOCOL_VERSION_MAJOR,
            minor=PROTOCOL_VERSION_MINOR,
            patch=PROTOCOL_VERSION_PATCH,
        ),
        packet_type=packet_type,
        flags=flags,
        payload_length=len(payload_bytes),
        sequence=sequence,
        timestamp=timestamp_ms,
    )

    header_bytes = header.to_bytes()

    # Вычисляем HMAC (заголовок + нагрузка)
    data_for_hmac = header_bytes + payload_bytes
    hmac_signature = HMACManager.sign(data_for_hmac, hmac_key)

    # Проверка общего размера
    total_size = len(header_bytes) + len(payload_bytes) + len(hmac_signature)
    if total_size > MAX_PACKET_SIZE:
        raise PacketBuildError(
            f"Размер пакета ({total_size} байт) "
            f"превышает лимит ({MAX_PACKET_SIZE} байт)"
        )

    return header_bytes + payload_bytes + hmac_signature


# ============================================================================
# ФУНКЦИИ РАЗБОРА (НИЗКОУРОВНЕВЫЕ)
# ============================================================================

def _parse_packet_bytes(data: bytes, hmac_key: bytes) -> Packet:
    """
    Разобрать байты в пакет с полной валидацией.

    Args:
        data: Входящие байты.
        hmac_key: Ключ HMAC.

    Returns:
        Объект Packet.

    Raises:
        PacketParseError: При ошибке разбора.
    """
    # Проверка минимального размера
    min_size = PACKET_HEADER_SIZE + HMAC_SIZE
    if len(data) < min_size:
        raise PacketParseError(
            f"Пакет слишком мал: {len(data)} байт < {min_size} байт"
        )

    # Проверка максимального размера
    if len(data) > MAX_PACKET_SIZE:
        raise PacketParseError(
            f"Пакет слишком велик: {len(data)} байт > {MAX_PACKET_SIZE} байт"
        )

    # Извлекаем заголовок
    header_bytes = data[:PACKET_HEADER_SIZE]
    header = PacketHeader.from_bytes(header_bytes)

    # Проверка магического числа
    if header.magic != MAGIC_NUMBER:
        raise PacketParseError(
            f"Неверное магическое число: 0x{header.magic:08X}, "
            f"ожидалось 0x{MAGIC_NUMBER:08X}"
        )

    # Проверка версии протокола
    _check_protocol_version(header.version)

    # Извлекаем нагрузку и HMAC
    payload_length = header.payload_length
    remaining = len(data) - PACKET_HEADER_SIZE

    if remaining < payload_length + HMAC_SIZE:
        raise PacketParseError(
            f"Недостаточно данных: нужно {payload_length + HMAC_SIZE} байт, "
            f"получено {remaining} байт"
        )

    payload_bytes = data[PACKET_HEADER_SIZE:PACKET_HEADER_SIZE + payload_length]
    hmac_received = data[PACKET_HEADER_SIZE + payload_length:
                         PACKET_HEADER_SIZE + payload_length + HMAC_SIZE]

    # Проверка HMAC
    data_for_hmac = header_bytes + payload_bytes
    if not HMACManager.verify(data_for_hmac, hmac_received, hmac_key):
        raise PacketParseError("HMAC-подпись не совпадает")

    # Проверка временной метки
    _check_timestamp(header.timestamp)

    # Распаковка сжатых данных
    if header.is_compressed:
        try:
            payload_bytes = Compressor.decompress(payload_bytes)
        except Exception as e:
            raise PacketParseError(f"Ошибка распаковки: {e}") from e

    # Десериализация JSON
    try:
        payload_json = payload_bytes.decode("utf-8")
        payload = JSONSerializer.deserialize_from_json(payload_json, dict)
    except Exception as e:
        raise PacketParseError(f"Ошибка десериализации JSON: {e}") from e

    return Packet(
        header=header,
        payload=payload,
        hmac=hmac_received,
    )


def _check_protocol_version(client_version: ProtocolVersion) -> None:
    """
    Проверить совместимость версии протокола клиента.

    Args:
        client_version: Версия протокола клиента.

    Raises:
        PacketParseError: Если версии несовместимы.
    """
    # Major должен совпадать
    if client_version.major != PROTOCOL_VERSION_MAJOR:
        raise PacketParseError(
            f"Несовместимая версия протокола: "
            f"клиент={client_version}, сервер={PROTOCOL_VERSION_MAJOR}."
            f"{PROTOCOL_VERSION_MINOR}.{PROTOCOL_VERSION_PATCH}"
        )

    # Minor клиента не должен быть больше серверного
    if client_version.minor > PROTOCOL_VERSION_MINOR:
        raise PacketParseError(
            f"Клиент использует более новую версию протокола: "
            f"клиент={client_version}, сервер={PROTOCOL_VERSION_MAJOR}."
            f"{PROTOCOL_VERSION_MINOR}.{PROTOCOL_VERSION_PATCH}"
        )


def _check_timestamp(timestamp_ms: int) -> None:
    """
    Проверить временную метку пакета.

    Отклоняет пакеты, отклонившиеся более чем на
    PACKET_TIMESTAMP_TOLERANCE секунд от текущего времени.

    Args:
        timestamp_ms: Временная метка в миллисекундах.

    Raises:
        PacketParseError: Если метка слишком старая или из будущего.
    """
    now_ms = int(time.time() * 1000)
    diff_ms = abs(now_ms - timestamp_ms)
    tolerance_ms = PACKET_TIMESTAMP_TOLERANCE * 1000

    if diff_ms > tolerance_ms:
        raise PacketParseError(
            f"Временная метка пакета вне допустимого диапазона: "
            f"разница {diff_ms / 1000:.1f} сек > {PACKET_TIMESTAMP_TOLERANCE} сек"
        )


# ============================================================================
# УТИЛИТЫ
# ============================================================================

def create_response_packet(
    request_packet: Packet,
    payload: dict[str, Any],
    hmac_key: bytes,
    packet_type: PacketType | None = None,
) -> bytes:
    """
    Создать пакет-ответ на основе запроса.

    Сохраняет тот же sequence для связывания запрос-ответ.

    Args:
        request_packet: Исходный пакет-запрос.
        payload: Данные ответа.
        hmac_key: Ключ HMAC.
        packet_type: Тип ответа (если None — к типу запроса + 1).

    Returns:
        Байты пакета-ответа.
    """
    if packet_type is None:
        # Автоматически определяем тип ответа
        response_type = PacketType(request_packet.packet_type.value + 1)
    else:
        response_type = packet_type

    return _build_packet_bytes(
        packet_type=response_type,
        payload=payload,
        sequence=request_packet.sequence,
        hmac_key=hmac_key,
    )


def create_notification_packet(
    packet_type: PacketType,
    payload: dict[str, Any],
    sequence: int,
    hmac_key: bytes,
) -> bytes:
    """
    Создать уведомительный пакет (не ответ на запрос).

    Args:
        packet_type: Тип пакета.
        payload: Данные.
        sequence: Порядковый номер.
        hmac_key: Ключ HMAC.

    Returns:
        Байты пакета.
    """
    return _build_packet_bytes(
        packet_type=packet_type,
        payload=payload,
        sequence=sequence,
        hmac_key=hmac_key,
    )


def create_error_packet(
    error_code: int,
    error_message: str,
    sequence: int,
    hmac_key: bytes,
    details: dict[str, Any] | None = None,
) -> bytes:
    """
    Создать пакет с ошибкой.

    Args:
        error_code: Код ошибки.
        error_message: Сообщение об ошибке.
        sequence: Порядковый номер.
        hmac_key: Ключ HMAC.
        details: Дополнительные детали.

    Returns:
        Байты пакета ERROR.
    """
    payload: dict[str, Any] = {
        "error_code": error_code,
        "message": error_message,
    }
    if details:
        payload["details"] = details

    return _build_packet_bytes(
        packet_type=PacketType.ERROR,
        payload=payload,
        sequence=sequence,
        hmac_key=hmac_key,
    )
