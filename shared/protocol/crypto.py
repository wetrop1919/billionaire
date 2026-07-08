"""
shared/protocol/crypto.py

Модуль криптографических функций для проекта "Миллиардер".

Обеспечивает:
- Хеширование и проверку паролей (Argon2id)
- HMAC-подпись и верификацию пакетов (SHA-256)
- Генерацию криптографически безопасных токенов
- Генерацию случайных идентификаторов и соли

Все криптографические операции используют современные алгоритмы
и библиотеки, соответствующие стандартам безопасности.

Использование:
    from shared.protocol.crypto import (
        PasswordHasher,
        HMACManager,
        TokenGenerator,
    )

    # Хеширование пароля
    hashed = await PasswordHasher.hash_password("user_password")

    # Проверка пароля
    is_valid = await PasswordHasher.verify_password("user_password", hashed)

    # HMAC-подпись
    signature = HMACManager.sign(data, secret_key)
    is_valid = HMACManager.verify(data, signature, secret_key)

    # Токены
    token = TokenGenerator.generate_session_token()
    refresh = TokenGenerator.generate_refresh_token()

Python: 3.13+
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from base64 import urlsafe_b64encode
from typing import Optional


# ============================================================================
# ИСКЛЮЧЕНИЯ КРИПТОГРАФИИ
# ============================================================================

class CryptoError(Exception):
    """Базовая ошибка криптографических операций."""

    def __init__(self, message: str) -> None:
        super().__init__(f"Криптографическая ошибка: {message}")


class PasswordHashError(CryptoError):
    """Ошибка при хешировании пароля."""

    def __init__(self, message: str) -> None:
        super().__init__(f"Ошибка хеширования пароля: {message}")


class PasswordVerificationError(CryptoError):
    """Ошибка при проверке пароля."""

    def __init__(self, message: str) -> None:
        super().__init__(f"Ошибка проверки пароля: {message}")


class HMACSigningError(CryptoError):
    """Ошибка при создании HMAC-подписи."""

    def __init__(self, message: str) -> None:
        super().__init__(f"Ошибка HMAC-подписи: {message}")


class HMACVerificationError(CryptoError):
    """Ошибка при проверке HMAC-подписи."""

    def __init__(self, message: str) -> None:
        super().__init__(f"Ошибка проверки HMAC: {message}")


class TokenGenerationError(CryptoError):
    """Ошибка при генерации токена."""

    def __init__(self, message: str) -> None:
        super().__init__(f"Ошибка генерации токена: {message}")


# ============================================================================
# ХЕШИРОВАНИЕ ПАРОЛЕЙ (Password Hasher)
# ============================================================================

class PasswordHasher:
    """
    Хеширование и проверка паролей с использованием Argon2id.

    Argon2id — победитель Password Hashing Competition (2015).
    Обеспечивает защиту от:
    - GPU-атак (memory-hard)
    - Side-channel атак (hybrid mode)
    - Time-memory trade-off атак

    Конфигурация по умолчанию (OWASP recommendations):
    - memory_cost: 65536 KB (64 MB)
    - time_cost: 3 итерации
    - parallelism: 4 потока

    Usage:
        hashed = await PasswordHasher.hash_password("password123")
        is_valid = await PasswordHasher.verify_password("password123", hashed)
    """

    # Параметры Argon2id по умолчанию
    DEFAULT_MEMORY_COST: int = 65536   # KB (64 MB)
    DEFAULT_TIME_COST: int = 3         # Итерации
    DEFAULT_PARALLELISM: int = 4       # Потоки
    DEFAULT_HASH_LENGTH: int = 32      # Байт
    DEFAULT_SALT_LENGTH: int = 16      # Байт

    @classmethod
    async def hash_password(
        cls,
        password: str,
        memory_cost: int | None = None,
        time_cost: int | None = None,
        parallelism: int | None = None,
    ) -> str:
        """
        Создать хеш пароля с использованием Argon2id.

        Args:
            password: Пароль в открытом виде.
            memory_cost: Затраты памяти в KB (по умолчанию 65536).
            time_cost: Количество итераций (по умолчанию 3).
            parallelism: Количество потоков (по умолчанию 4).

        Returns:
            Строка хеша в формате argon2 (содержит соль и параметры).

        Raises:
            PasswordHashError: При ошибке хеширования.
            ImportError: Если argon2-cffi не установлен.
        """
        try:
            from argon2 import PasswordHasher as Argon2Hasher
            from argon2.exceptions import HashingError
        except ImportError:
            raise ImportError(
                "argon2-cffi не установлен. "
                "Установите: pip install argon2-cffi"
            )

        if not password:
            raise PasswordHashError("Пароль не может быть пустым")

        mem = memory_cost or cls.DEFAULT_MEMORY_COST
        time = time_cost or cls.DEFAULT_TIME_COST
        par = parallelism or cls.DEFAULT_PARALLELISM

        try:
            hasher = Argon2Hasher(
                memory_cost=mem,
                time_cost=time,
                parallelism=par,
                hash_len=cls.DEFAULT_HASH_LENGTH,
                salt_len=cls.DEFAULT_SALT_LENGTH,
            )
            return hasher.hash(password)
        except HashingError as e:
            raise PasswordHashError(str(e)) from e

    @classmethod
    async def verify_password(cls, password: str, password_hash: str) -> bool:
        """
        Проверить пароль по хешу.

        Args:
            password: Пароль в открытом виде.
            password_hash: Хеш пароля (в формате argon2).

        Returns:
            True, если пароль совпадает с хешем.

        Raises:
            PasswordVerificationError: При ошибке проверки.
            ImportError: Если argon2-cffi не установлен.
        """
        try:
            from argon2 import PasswordHasher as Argon2Hasher
            from argon2.exceptions import VerificationError, InvalidHashError
        except ImportError:
            raise ImportError(
                "argon2-cffi не установлен. "
                "Установите: pip install argon2-cffi"
            )

        if not password or not password_hash:
            return False

        try:
            hasher = Argon2Hasher()
            hasher.verify(password_hash, password)
            return True
        except VerificationError:
            return False
        except InvalidHashError as e:
            raise PasswordVerificationError(
                f"Некорректный формат хеша: {e}"
            ) from e

    @classmethod
    async def needs_rehash(
        cls,
        password_hash: str,
        memory_cost: int | None = None,
        time_cost: int | None = None,
        parallelism: int | None = None,
    ) -> bool:
        """
        Проверить, нужно ли перехешировать пароль (изменились параметры).

        Args:
            password_hash: Существующий хеш пароля.
            memory_cost: Новые затраты памяти.
            time_cost: Новое количество итераций.
            parallelism: Новое количество потоков.

        Returns:
            True, если пароль следует перехешировать с новыми параметрами.
        """
        try:
            from argon2 import PasswordHasher as Argon2Hasher
        except ImportError:
            raise ImportError(
                "argon2-cffi не установлен. "
                "Установите: pip install argon2-cffi"
            )

        mem = memory_cost or cls.DEFAULT_MEMORY_COST
        time = time_cost or cls.DEFAULT_TIME_COST
        par = parallelism or cls.DEFAULT_PARALLELISM

        hasher = Argon2Hasher(
            memory_cost=mem,
            time_cost=time,
            parallelism=par,
        )
        return hasher.check_needs_rehash(password_hash)


# ============================================================================
# HMAC-ПОДПИСЬ (HMAC Manager)
# ============================================================================

class HMACManager:
    """
    Создание и проверка HMAC-подписей для защиты целостности пакетов.

    Использует HMAC-SHA256 для подписи данных.
    Ключ должен храниться в секрете (передаётся через .env).

    Usage:
        key = HMACManager.generate_key()
        signature = HMACManager.sign(data_bytes, key)
        is_valid = HMACManager.verify(data_bytes, signature, key)
    """

    # Алгоритм хеширования для HMAC
    HASH_ALGORITHM: str = "sha256"

    # Размер подписи в байтах (256 бит)
    SIGNATURE_SIZE: int = 32

    # Размер ключа по умолчанию в байтах (256 бит)
    DEFAULT_KEY_SIZE: int = 32

    @staticmethod
    def sign(data: bytes, secret_key: bytes) -> bytes:
        """
        Создать HMAC-подпись для данных.

        Args:
            data: Данные для подписи.
            secret_key: Секретный ключ (байты).

        Returns:
            HMAC-подпись (32 байта).

        Raises:
            HMACSigningError: При ошибке создания подписи.
        """
        if not data:
            raise HMACSigningError("Данные не могут быть пустыми")
        if not secret_key or len(secret_key) < 16:
            raise HMACSigningError(
                "Секретный ключ должен быть не менее 16 байт"
            )

        try:
            return hmac.digest(
                key=secret_key,
                msg=data,
                digest=HMACManager.HASH_ALGORITHM,
            )
        except Exception as e:
            raise HMACSigningError(str(e)) from e

    @staticmethod
    def verify(data: bytes, signature: bytes, secret_key: bytes) -> bool:
        """
        Проверить HMAC-подпись данных.

        Использует функцию сравнения, устойчивую к timing-атакам
        (hmac.compare_digest).

        Args:
            data: Данные.
            signature: Ожидаемая подпись (32 байта).
            secret_key: Секретный ключ.

        Returns:
            True, если подпись корректна.

        Raises:
            HMACVerificationError: При ошибке проверки.
        """
        if not data or not signature or not secret_key:
            return False

        if len(signature) != HMACManager.SIGNATURE_SIZE:
            return False

        try:
            expected_signature = HMACManager.sign(data, secret_key)
            return hmac.compare_digest(expected_signature, signature)
        except Exception as e:
            raise HMACVerificationError(str(e)) from e

    @staticmethod
    def generate_key(size: int | None = None) -> bytes:
        """
        Сгенерировать криптографически безопасный ключ для HMAC.

        Args:
            size: Размер ключа в байтах (по умолчанию 32 = 256 бит).

        Returns:
            Случайный ключ.
        """
        key_size = size or HMACManager.DEFAULT_KEY_SIZE
        return secrets.token_bytes(key_size)

    @staticmethod
    def key_from_string(key_string: str) -> bytes:
        """
        Преобразовать строковый ключ в байты.

        Args:
            key_string: Ключ в виде строки (hex или base64).

        Returns:
            Ключ в виде байтов.
        """
        # Пробуем интерпретировать как hex
        try:
            if len(key_string) == HMACManager.DEFAULT_KEY_SIZE * 2:
                return bytes.fromhex(key_string)
        except ValueError:
            pass

        # Используем SHA-256 для получения ключа нужной длины
        return hashlib.sha256(key_string.encode("utf-8")).digest()


# ============================================================================
# ГЕНЕРАЦИЯ ТОКЕНОВ (Token Generator)
# ============================================================================

class TokenGenerator:
    """
    Генерация криптографически безопасных токенов.

    Использует secrets.token_bytes для создания случайных токенов
    и base64url для кодирования в строковый формат.

    Usage:
        session_token = TokenGenerator.generate_session_token()
        refresh_token = TokenGenerator.generate_refresh_token()
        api_key = TokenGenerator.generate_api_key()
    """

    # Размеры токенов в байтах
    SESSION_TOKEN_SIZE: int = 32       # 256 бит
    REFRESH_TOKEN_SIZE: int = 48       # 384 бита
    API_KEY_SIZE: int = 64             # 512 бит

    @staticmethod
    def generate_session_token() -> str:
        """
        Сгенерировать сессионный токен (32 байта).

        Используется для идентификации сессии после аутентификации.

        Returns:
            Строка токена в base64url-кодировке.
        """
        token_bytes = secrets.token_bytes(TokenGenerator.SESSION_TOKEN_SIZE)
        return TokenGenerator._encode_token(token_bytes)

    @staticmethod
    def generate_refresh_token() -> str:
        """
        Сгенерировать refresh-токен (48 байт).

        Используется для обновления сессионного токена без повторного входа.

        Returns:
            Строка токена в base64url-кодировке.
        """
        token_bytes = secrets.token_bytes(TokenGenerator.REFRESH_TOKEN_SIZE)
        return TokenGenerator._encode_token(token_bytes)

    @staticmethod
    def generate_api_key() -> str:
        """
        Сгенерировать API-ключ (64 байта).

        Используется для долгосрочной аутентификации (если потребуется).

        Returns:
            Строка ключа в base64url-кодировке.
        """
        token_bytes = secrets.token_bytes(TokenGenerator.API_KEY_SIZE)
        return TokenGenerator._encode_token(token_bytes)

    @staticmethod
    def generate_custom_token(size: int = 32) -> str:
        """
        Сгенерировать токен произвольного размера.

        Args:
            size: Размер в байтах (минимум 16).

        Returns:
            Строка токена в base64url-кодировке.

        Raises:
            TokenGenerationError: Если размер меньше 16 байт.
        """
        if size < 16:
            raise TokenGenerationError(
                "Размер токена должен быть не менее 16 байт"
            )
        token_bytes = secrets.token_bytes(size)
        return TokenGenerator._encode_token(token_bytes)

    @staticmethod
    def _encode_token(token_bytes: bytes) -> str:
        """
        Кодировать токен в URL-безопасную base64 строку.

        Args:
            token_bytes: Байты токена.

        Returns:
            Строка без завершающих знаков '='.
        """
        return urlsafe_b64encode(token_bytes).rstrip(b"=").decode("ascii")

    @staticmethod
    def tokens_match(token1: str, token2: str) -> bool:
        """
        Сравнить два токена (устойчиво к timing-атакам).

        Args:
            token1: Первый токен.
            token2: Второй токен.

        Returns:
            True, если токены совпадают.
        """
        if not token1 or not token2:
            return False
        return hmac.compare_digest(
            token1.encode("ascii"),
            token2.encode("ascii"),
        )


# ============================================================================
# ГЕНЕРАЦИЯ СЛУЧАЙНЫХ ДАННЫХ
# ============================================================================

class RandomGenerator:
    """
    Генерация криптографически безопасных случайных данных.

    Использует модуль secrets (системный CSPRNG).
    """

    @staticmethod
    def generate_salt(size: int = 16) -> bytes:
        """
        Сгенерировать соль для хеширования паролей.

        Args:
            size: Размер соли в байтах (по умолчанию 16).

        Returns:
            Случайные байты.
        """
        return secrets.token_bytes(size)

    @staticmethod
    def generate_uuid_hex() -> str:
        """
        Сгенерировать случайный UUID в hex-формате.

        Returns:
            Строка из 32 шестнадцатеричных символов.
        """
        return secrets.token_hex(16)

    @staticmethod
    def generate_random_hex(size: int = 32) -> str:
        """
        Сгенерировать случайную hex-строку.

        Args:
            size: Количество байт случайных данных.

        Returns:
            Hex-строка (в 2 раза длиннее size).
        """
        return secrets.token_hex(size)

    @staticmethod
    def generate_random_int(min_value: int, max_value: int) -> int:
        """
        Сгенерировать случайное целое число в диапазоне.

        Args:
            min_value: Минимальное значение (включительно).
            max_value: Максимальное значение (включительно).

        Returns:
            Случайное целое число.

        Raises:
            ValueError: Если min_value > max_value.
        """
        if min_value > max_value:
            raise ValueError(
                f"min_value ({min_value}) не может быть больше max_value ({max_value})"
            )
        return min_value + secrets.randbelow(max_value - min_value + 1)


# ============================================================================
# ХЕШИРОВАНИЕ ОБЩЕГО НАЗНАЧЕНИЯ
# ============================================================================

class HashUtils:
    """
    Утилиты хеширования общего назначения.
    """

    @staticmethod
    def sha256(data: bytes | str) -> str:
        """
        Вычислить SHA-256 хеш данных.

        Args:
            data: Данные (байты или строка).

        Returns:
            Hex-строка хеша (64 символа).
        """
        if isinstance(data, str):
            data = data.encode("utf-8")
        return hashlib.sha256(data).hexdigest()

    @staticmethod
    def sha256_bytes(data: bytes | str) -> bytes:
        """
        Вычислить SHA-256 хеш данных в виде байтов.

        Args:
            data: Данные (байты или строка).

        Returns:
            32 байта хеша.
        """
        if isinstance(data, str):
            data = data.encode("utf-8")
        return hashlib.sha256(data).digest()

    @staticmethod
    def hash_dict(data: dict, encoding: str = "utf-8") -> str:
        """
        Вычислить детерминированный хеш словаря.

        Порядок ключей сортируется для обеспечения детерминированности.

        Args:
            data: Словарь для хеширования.
            encoding: Кодировка строк.

        Returns:
            Hex-строка SHA-256 хеша.
        """
        import json
        serialized = json.dumps(data, sort_keys=True, ensure_ascii=False)
        return HashUtils.sha256(serialized.encode(encoding))


# ============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================================

def generate_secure_password(length: int = 16) -> str:
    """
    Сгенерировать безопасный случайный пароль.

    Содержит буквы (верхний и нижний регистр), цифры и спецсимволы.

    Args:
        length: Длина пароля (минимум 8).

    Returns:
        Случайный пароль.

    Raises:
        ValueError: Если длина меньше 8.
    """
    if length < 8:
        raise ValueError("Длина пароля должна быть не менее 8 символов")

    alphabet = (
        "abcdefghijklmnopqrstuvwxyz"
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        "0123456789"
        "!@#$%^&*()-_=+[]{}|;:,.<>?"
    )

    # Гарантируем наличие хотя бы одного символа каждой категории
    password_chars: list[str] = [
        secrets.choice("abcdefghijklmnopqrstuvwxyz"),
        secrets.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ"),
        secrets.choice("0123456789"),
        secrets.choice("!@#$%^&*()-_=+[]{}|;:,.<>?"),
    ]

    # Заполняем остальное случайными символами
    for _ in range(length - len(password_chars)):
        password_chars.append(secrets.choice(alphabet))

    # Перемешиваем
    shuffled: list[str] = []
    indices = list(range(len(password_chars)))
    while indices:
        idx = secrets.choice(indices)
        indices.remove(idx)
        shuffled.append(password_chars[idx])

    return "".join(shuffled)