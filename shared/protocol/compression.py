"""
shared/protocol/compression.py

Модуль сжатия и распаковки данных для сетевого протокола.

Обеспечивает:
- Сжатие данных через zlib (быстро, эффективно для JSON)
- Автоматическое определение необходимости сжатия по порогу размера
- Прозрачную обработку как сжатых, так и несжатых данных
- Защиту от zip-бомб (ограничение размера распакованных данных)

Использование:
    from shared.protocol.compression import Compressor

    compressed = Compressor.compress(data_bytes)
    original = Compressor.decompress(compressed)

Python: 3.13+
"""

from __future__ import annotations

import zlib
from typing import Optional


# ============================================================================
# ИСКЛЮЧЕНИЯ КОМПРЕССИИ
# ============================================================================

class CompressionError(Exception):
    """Ошибка при сжатии или распаковке данных."""

    def __init__(self, message: str, operation: str = "") -> None:
        self.operation = operation
        prefix = f"Ошибка {operation}: " if operation else ""
        super().__init__(f"{prefix}{message}")


class DecompressionError(CompressionError):
    """Ошибка при распаковке данных."""

    def __init__(self, message: str) -> None:
        super().__init__(message, operation="распаковки")


class CompressionSizeExceededError(CompressionError):
    """Превышен максимальный размер распакованных данных (защита от zip-бомб)."""

    def __init__(self, actual_size: int, max_size: int) -> None:
        self.actual_size = actual_size
        self.max_size = max_size
        super().__init__(
            f"Размер распакованных данных ({actual_size} байт) "
            f"превышает лимит ({max_size} байт)",
            operation="распаковки",
        )


# ============================================================================
# КОМПРЕССОР
# ============================================================================

class Compressor:
    """
    Статический класс для сжатия и распаковки данных.

    Использует zlib (уровень сжатия 6 — хороший баланс скорость/размер).
    Автоматически определяет, нужно ли сжимать данные, на основе порога.

    Attributes:
        COMPRESSION_LEVEL: Уровень сжатия zlib (1-9, по умолчанию 6).
        COMPRESSION_THRESHOLD: Порог размера в байтах, после которого
                               применяется сжатие (по умолчанию 512).
        MAX_DECOMPRESSED_SIZE: Максимальный размер распакованных данных
                               (защита от zip-бомб, по умолчанию 10 МБ).
    """

    # Уровень сжатия zlib: 1 (быстро) - 9 (максимальное сжатие)
    # 6 — рекомендованный баланс скорости и эффективности
    COMPRESSION_LEVEL: int = 6

    # Порог сжатия: данные меньше этого размера не сжимаются
    COMPRESSION_THRESHOLD: int = 512

    # Максимальный размер распакованных данных (10 МБ)
    MAX_DECOMPRESSED_SIZE: int = 10_485_760

    # Магический байт для идентификации сжатых данных
    COMPRESSED_MARKER: bytes = b"\x1F\x9D"  # Нестандартный маркер (не gzip)

    # ========================================================================
    # ПУБЛИЧНЫЕ МЕТОДЫ
    # ========================================================================

    @classmethod
    def compress(cls, data: bytes) -> bytes:
        """
        Сжать данные с использованием zlib.

        Если размер данных меньше COMPRESSION_THRESHOLD,
        возвращает данные без сжатия (экономия CPU).

        Args:
            data: Исходные данные (байты).

        Returns:
            Сжатые данные с маркером сжатия в начале,
            либо исходные данные, если сжатие не требуется.

        Raises:
            CompressionError: При ошибке сжатия.
        """
        if not isinstance(data, bytes):
            raise CompressionError(
                f"Ожидались байты, получен {type(data).__name__}",
                operation="сжатия",
            )

        # Проверяем, нужно ли сжимать
        if not cls.should_compress(data):
            return data

        try:
            compressed = zlib.compress(data, level=cls.COMPRESSION_LEVEL)
            # Добавляем маркер для идентификации сжатых данных
            return cls.COMPRESSED_MARKER + compressed
        except zlib.error as e:
            raise CompressionError(
                f"Ошибка zlib при сжатии: {e}",
                operation="сжатия",
            ) from e

    @classmethod
    def decompress(cls, data: bytes) -> bytes:
        """
        Распаковать данные.

        Автоматически определяет, сжаты ли данные, по наличию маркера.
        Если данные не сжаты, возвращает их без изменений.

        Args:
            data: Сжатые или несжатые данные (байты).

        Returns:
            Распакованные данные.

        Raises:
            DecompressionError: При ошибке распаковки.
            CompressionSizeExceededError: Если размер распакованных данных
                                           превышает MAX_DECOMPRESSED_SIZE.
        """
        if not isinstance(data, bytes):
            raise DecompressionError(
                f"Ожидались байты, получен {type(data).__name__}"
            )

        # Проверяем, сжаты ли данные
        if not cls.is_compressed(data):
            return data

        # Извлекаем сжатые данные (без маркера)
        compressed_data = data[len(cls.COMPRESSED_MARKER):]

        try:
            # Используем декомпрессию с ограничением размера
            decompressor = zlib.decompressobj()

            # Поэтапная распаковка для контроля размера
            chunks: list[bytes] = []
            total_size = 0

            # Распаковываем данные
            chunk = decompressor.decompress(compressed_data)
            total_size += len(chunk)
            if total_size > cls.MAX_DECOMPRESSED_SIZE:
                raise CompressionSizeExceededError(
                    total_size, cls.MAX_DECOMPRESSED_SIZE
                )
            chunks.append(chunk)

            # Обрабатываем оставшиеся данные (flush)
            if decompressor.unconsumed_tail or not decompressor.eof:
                remaining = decompressor.flush()
                total_size += len(remaining)
                if total_size > cls.MAX_DECOMPRESSED_SIZE:
                    raise CompressionSizeExceededError(
                        total_size, cls.MAX_DECOMPRESSED_SIZE
                    )
                if remaining:
                    chunks.append(remaining)

            return b"".join(chunks)

        except CompressionSizeExceededError:
            raise
        except zlib.error as e:
            raise DecompressionError(
                f"Ошибка zlib при распаковке: {e}"
            ) from e

    @classmethod
    def compress_if_needed(cls, data: bytes) -> tuple[bytes, bool]:
        """
        Сжать данные и вернуть флаг сжатия.

        Args:
            data: Исходные данные.

        Returns:
            Кортеж (данные, флаг_сжатия).
            Флаг True, если данные были сжаты.
        """
        should_compress = cls.should_compress(data)
        if should_compress:
            return cls.compress(data), True
        return data, False

    @classmethod
    def should_compress(cls, data: bytes) -> bool:
        """
        Проверить, нужно ли сжимать данные.

        Данные сжимаются, если их размер превышает COMPRESSION_THRESHOLD.

        Args:
            data: Данные для проверки.

        Returns:
            True, если данные следует сжать.
        """
        return len(data) >= cls.COMPRESSION_THRESHOLD

    @classmethod
    def is_compressed(cls, data: bytes) -> bool:
        """
        Проверить, сжаты ли данные (по наличию маркера).

        Args:
            data: Данные для проверки.

        Returns:
            True, если данные начинаются с маркера сжатия.
        """
        return data.startswith(cls.COMPRESSED_MARKER)

    # ========================================================================
    # СТАТИСТИКА СЖАТИЯ
    # ========================================================================

    @classmethod
    def get_compression_ratio(cls, original: bytes, compressed: bytes) -> float:
        """
        Вычислить коэффициент сжатия.

        Args:
            original: Исходные данные.
            compressed: Сжатые данные.

        Returns:
            Коэффициент сжатия (отношение размеров, в процентах).
            Например, 40.0 означает, что сжатые данные занимают 40% от исходных.
        """
        if len(original) == 0:
            return 100.0
        return (len(compressed) / len(original)) * 100.0

    @classmethod
    def get_compression_stats(cls, data: bytes) -> dict[str, int | float]:
        """
        Получить статистику сжатия для отладки.

        Args:
            data: Исходные данные.

        Returns:
            Словарь с размерами и коэффициентом сжатия.
        """
        compressed = cls.compress(data)
        return {
            "original_size": len(data),
            "compressed_size": len(compressed),
            "compressed": cls.is_compressed(compressed),
            "ratio_percent": round(cls.get_compression_ratio(data, compressed), 2),
            "saved_bytes": len(data) - len(compressed),
        }


# ============================================================================
# УТИЛИТЫ ДЛЯ РАБОТЫ СО СТРОКАМИ
# ============================================================================

def compress_string(text: str, encoding: str = "utf-8") -> bytes:
    """
    Сжать строку.

    Args:
        text: Исходная строка.
        encoding: Кодировка (по умолчанию UTF-8).

    Returns:
        Сжатые байты.
    """
    return Compressor.compress(text.encode(encoding))


def decompress_string(data: bytes, encoding: str = "utf-8") -> str:
    """
    Распаковать строку.

    Args:
        data: Сжатые байты.
        encoding: Кодировка (по умолчанию UTF-8).

    Returns:
        Распакованная строка.
    """
    return Compressor.decompress(data).decode(encoding)


def compress_json(json_data: dict, encoding: str = "utf-8") -> bytes:
    """
    Сжать JSON-словарь.

    Args:
        json_data: Словарь с данными.
        encoding: Кодировка.

    Returns:
        Сжатые байты.
    """
    import json
    json_string = json.dumps(json_data, ensure_ascii=False, separators=(",", ":"))
    return Compressor.compress(json_string.encode(encoding))


def decompress_json(data: bytes, encoding: str = "utf-8") -> dict:
    """
    Распаковать JSON-словарь.

    Args:
        data: Сжатые байты.
        encoding: Кодировка.

    Returns:
        Распакованный словарь.
    """
    import json
    json_string = Compressor.decompress(data).decode(encoding)
    return json.loads(json_string)