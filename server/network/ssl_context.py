"""
server/network/ssl_context.py

Фабрика SSL-контекстов для сервера.

Обеспечивает:
- Создание серверного SSL-контекста
- Загрузку сертификатов из файлов
- Настройку параметров безопасности (минимальная версия TLS, наборы шифров)
- Создание клиентского SSL-контекста (для тестов)

Python: 3.13+
"""

from __future__ import annotations

import logging
import ssl
from pathlib import Path
from typing import Optional

logger = logging.getLogger("billionaire.server")


# ============================================================================
# ИСКЛЮЧЕНИЯ SSL
# ============================================================================

class SSLError(Exception):
    """Ошибка создания SSL-контекста."""

    def __init__(self, message: str) -> None:
        super().__init__(f"Ошибка SSL: {message}")


class CertificateError(SSLError):
    """Ошибка загрузки сертификата."""

    def __init__(self, file_path: str, reason: str = "") -> None:
        msg = f"Не удалось загрузить сертификат '{file_path}'"
        if reason:
            msg += f": {reason}"
        super().__init__(msg)
        self.file_path = file_path


# ============================================================================
# ФАБРИКА SSL-КОНТЕКСТОВ
# ============================================================================

class SSLContextFactory:
    """
    Фабрика для создания настроенных SSL-контекстов.

    Поддерживает:
    - Загрузку сертификата и ключа из PEM-файлов
    - Самоподписанные сертификаты
    - Let's Encrypt сертификаты (с CA-цепочкой)
    - Настройку минимальной версии TLS (1.2+)
    - Настройку наборов шифров

    Usage:
        factory = SSLContextFactory()
        server_ctx = factory.create_server_context(
            cert_path="certs/server.crt",
            key_path="certs/server.key",
        )
    """

    # Минимальная версия TLS
    MINIMUM_TLS_VERSION: int = ssl.TLSVersion.TLSv1_2

    # Рекомендованные наборы шифров (Modern compatibility)
    CIPHERS: str = (
        "ECDHE+AESGCM:ECDHE+CHACHA20:DHE+AESGCM:DHE+CHACHA20:"
        "ECDHE+AES256:!aNULL:!MD5:!DSS"
    )

    @classmethod
    def create_server_context(
        cls,
        cert_path: str,
        key_path: str,
        ca_path: Optional[str] = None,
        verify_client: bool = False,
    ) -> ssl.SSLContext:
        """
        Создать серверный SSL-контекст.

        Args:
            cert_path: Путь к файлу сертификата (PEM).
            key_path: Путь к файлу приватного ключа (PEM).
            ca_path: Путь к CA-сертификату (для проверки клиентов).
            verify_client: Требовать ли клиентский сертификат.

        Returns:
            Настроенный ssl.SSLContext.

        Raises:
            CertificateError: Если сертификат или ключ не найдены.
            SSLError: При ошибке создания контекста.
        """
        # Проверка существования файлов
        if not Path(cert_path).exists():
            raise CertificateError(cert_path, "Файл не найден")
        if not Path(key_path).exists():
            raise CertificateError(key_path, "Файл не найден")

        try:
            # Создаём контекст
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)

            # Минимальная версия TLS
            context.minimum_version = cls.MINIMUM_TLS_VERSION

            # Наборы шифров
            context.set_ciphers(cls.CIPHERS)

            # Загружаем сертификат и ключ
            context.load_cert_chain(
                certfile=cert_path,
                keyfile=key_path,
            )

            # Настройки безопасности
            context.options |= (
                ssl.OP_NO_SSLv2
                | ssl.OP_NO_SSLv3
                | ssl.OP_NO_TLSv1
                | ssl.OP_NO_TLSv1_1
                | ssl.OP_NO_COMPRESSION  # Защита от CRIME
                | ssl.OP_CIPHER_SERVER_PREFERENCE  # Сервер выбирает шифр
            )

            # Предпочтение серверных наборов шифров
            context.options |= ssl.OP_SINGLE_DH_USE
            context.options |= ssl.OP_SINGLE_ECDH_USE

            # Проверка клиентского сертификата (опционально)
            if verify_client:
                context.verify_mode = ssl.CERT_REQUIRED
                if ca_path:
                    context.load_verify_locations(cafile=ca_path)
            else:
                context.verify_mode = ssl.CERT_NONE

            # Включаем поддержку session tickets (для быстрого переподключения)
            context.options |= ssl.OP_NO_TICKET

            logger.info(
                "Создан серверный SSL-контекст (сертификат: %s, TLS >= 1.2)",
                cert_path,
            )

            return context

        except ssl.SSLError as e:
            raise SSLError(f"Ошибка создания SSL-контекста: {e}") from e
        except OSError as e:
            raise CertificateError(cert_path, str(e)) from e

    @classmethod
    def create_client_context(
        cls,
        ca_path: Optional[str] = None,
        verify_server: bool = True,
    ) -> ssl.SSLContext:
        """
        Создать клиентский SSL-контекст (для тестов и внутренних нужд).

        Args:
            ca_path: Путь к CA-сертификату.
            verify_server: Проверять ли серверный сертификат.

        Returns:
            Настроенный ssl.SSLContext.
        """
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)

        context.minimum_version = cls.MINIMUM_TLS_VERSION
        context.set_ciphers(cls.CIPHERS)

        if verify_server:
            context.check_hostname = True
            context.verify_mode = ssl.CERT_REQUIRED

            if ca_path:
                context.load_verify_locations(cafile=ca_path)
            else:
                # Используем системные CA-сертификаты
                context.load_default_certs()
        else:
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE

        return context

    @classmethod
    def create_self_signed_context(
        cls,
        cert_path: str,
        key_path: str,
    ) -> ssl.SSLContext:
        """
        Создать контекст с самоподписанным сертификатом.

        Для разработки и тестирования.

        Args:
            cert_path: Путь для сохранения сертификата.
            key_path: Путь для сохранения ключа.

        Returns:
            Серверный SSL-контекст.
        """
        import datetime
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa

        # Генерируем ключ
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )

        # Создаём сертификат
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, "RU"),
            x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "Moscow"),
            x509.NameAttribute(NameOID.LOCALITY_NAME, "Moscow"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Billionaire Game"),
            x509.NameAttribute(NameOID.COMMON_NAME, "localhost"),
        ])

        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(private_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.datetime.now(datetime.timezone.utc))
            .not_valid_after(
                datetime.datetime.now(datetime.timezone.utc)
                + datetime.timedelta(days=365)
            )
            .add_extension(
                x509.SubjectAlternativeName([
                    x509.DNSName("localhost"),
                    x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
                ]),
                critical=False,
            )
            .sign(private_key, hashes.SHA256())
        )

        # Сохраняем ключ
        key_path_obj = Path(key_path)
        key_path_obj.parent.mkdir(parents=True, exist_ok=True)
        with open(key_path, "wb") as f:
            f.write(
                private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption(),
                )
            )

        # Сохраняем сертификат
        cert_path_obj = Path(cert_path)
        cert_path_obj.parent.mkdir(parents=True, exist_ok=True)
        with open(cert_path, "wb") as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))

        logger.info(
            "Создан самоподписанный сертификат: %s (ключ: %s)",
            cert_path,
            key_path,
        )

        # Создаём контекст
        return cls.create_server_context(cert_path, key_path)

    @classmethod
    def get_default_context(cls) -> Optional[ssl.SSLContext]:
        """
        Попытаться создать контекст со стандартными путями.

        Ищет сертификаты в стандартных расположениях:
        - certs/server.crt
        - certs/server.key

        Returns:
            SSL-контекст или None, если сертификаты не найдены.
        """
        default_cert = "certs/server.crt"
        default_key = "certs/server.key"

        if Path(default_cert).exists() and Path(default_key).exists():
            try:
                return cls.create_server_context(default_cert, default_key)
            except SSLError as e:
                logger.warning("Не удалось загрузить стандартные сертификаты: %s", e)

        return None