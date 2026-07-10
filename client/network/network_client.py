"""
client/network/network_client.py

Асинхронный сетевой клиент для взаимодействия с сервером.

Обеспечивает:
- Подключение к серверу по TCP/SSL
- Отправку и получение пакетов
- Аутентификацию и управление токенами
- Heartbeat (ping/pong)
- Обработку разрыва соединения

Использует asyncio Streams для асинхронного сетевого взаимодействия.

Python: 3.13+
"""

from __future__ import annotations

import asyncio
import logging
import ssl
import time
from typing import Any, Callable, Coroutine, Optional
from uuid import UUID

from shared.constants import (
    DEFAULT_SERVER_HOST,
    DEFAULT_SERVER_PORT,
    BUFFER_SIZE,
    CONNECTION_TIMEOUT,
    HEARTBEAT_INTERVAL,
    PING_INTERVAL,
    RECONNECTION_WINDOW,
)
from shared.enums import PacketType
from shared.protocol.packet import Packet, PacketParser, PacketBuilder, PacketParseError
from shared.protocol.crypto import HMACManager
from shared.protocol.compression import Compressor

logger = logging.getLogger("billionaire.client")

_USE_SSL = False

# ============================================================================
# ТИПЫ ОБРАТНЫХ ВЫЗОВОВ
# ============================================================================

# Обработчик входящего пакета
PacketCallback = Callable[[Packet], Coroutine[Any, Any, None]]

# Обработчик изменения состояния подключения
StateCallback = Callable[[bool], Coroutine[Any, Any, None]]


# ============================================================================
# СЕТЕВОЙ КЛИЕНТ
# ============================================================================

class NetworkClient:
    """
    Асинхронный сетевой клиент.

    Управляет TCP-соединением с сервером, отправкой и получением пакетов.
    Поддерживает SSL, аутентификацию и heartbeat.

    Usage:
        client = NetworkClient()
        await client.connect("localhost", 8443)
        await client.login("player1", "password")
        await client.send_packet(PacketType.ROLL_DICE_REQUEST, {})
        response = await client.receive_packet()
    """

    def __init__(self) -> None:
        """Инициализация сетевого клиента."""
        # Соединение
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._connected: bool = False

        # Аутентификация
        self._access_token: Optional[str] = None
        self._refresh_token: Optional[str] = None
        self._user_id: Optional[UUID] = None
        self._username: Optional[str] = None
        self._role: Optional[str] = None

        # Ключи
        self._hmac_key: bytes = HMACManager.generate_key()

        # Парсер и сборщик пакетов
        self._packet_parser = PacketParser()
        self._packet_builder = PacketBuilder()

        # Счётчик последовательности
        self._sequence: int = 0

        # Heartbeat
        self._last_pong: float = time.time()
        self._heartbeat_task: Optional[asyncio.Task] = None

        # Обработчики
        self._packet_handlers: dict[PacketType, list[PacketCallback]] = {}
        self._state_handlers: list[StateCallback] = []

        # Очередь ответов {sequence: asyncio.Future}
        self._pending_requests: dict[int, asyncio.Future] = {}

        # Блокировка отправки
        self._send_lock = asyncio.Lock()

    # ========================================================================
    # ПОДКЛЮЧЕНИЕ
    # ========================================================================

    async def connect(
        self,
        host: str = DEFAULT_SERVER_HOST,
        port: int = DEFAULT_SERVER_PORT,
        use_ssl: bool = False,
    ) -> bool:
        """
        Подключиться к серверу.

        Args:
            host: Адрес сервера.
            port: Порт.
            use_ssl: Использовать SSL.

        Returns:
            True, если подключение успешно.
        """
        if self._connected:
            logger.warning("Уже подключены к серверу")
            return True

        try:
            # SSL-контекст
            ssl_context = None
            if use_ssl:
                ssl_context = ssl.create_default_context()
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE  # Для самоподписанных

            # Подключаемся с таймаутом
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(
                    host=host,
                    port=port,
                    ssl=None,
                ),
                timeout=CONNECTION_TIMEOUT,
            )

            self._connected = True
            self._sequence = 0
            self._last_pong = time.time()

            # Запускаем heartbeat
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

            # Уведомляем обработчики
            await self._notify_state(True)

            logger.info(
                "Подключено к серверу %s:%d (SSL: %s)",
                host,
                port,
                "да" if use_ssl else "нет",
            )

            return True

        except asyncio.TimeoutError:
            logger.error("Таймаут подключения к %s:%d", host, port)
            return False
        except OSError as e:
            logger.error("Ошибка подключения: %s", e)
            return False
        except Exception as e:
            logger.error("Неожиданная ошибка подключения: %s", e)
            return False

    async def disconnect(self) -> None:
        """
        Отключиться от сервера.

        Корректно закрывает соединение и останавливает heartbeat.
        """
        if not self._connected:
            return

        self._connected = False

        # Останавливаем heartbeat
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None

        # Закрываем соединение
        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:
                pass
            self._writer = None

        self._reader = None

        # Очищаем pending запросы
        for future in self._pending_requests.values():
            if not future.done():
                future.set_exception(ConnectionError("Соединение закрыто"))
        self._pending_requests.clear()

        # Уведомляем обработчики
        await self._notify_state(False)

        logger.info("Отключено от сервера")

    # ========================================================================
    # АУТЕНТИФИКАЦИЯ
    # ========================================================================

    async def login(self, username: str, password_hash: str) -> dict[str, Any]:
        """
        Выполнить вход.

        Args:
            username: Имя пользователя.
            password_hash: Хеш пароля (Argon2id).

        Returns:
            Ответ сервера с токенами.

        Raises:
            ConnectionError: Нет подключения.
        """
        response = await self.send_request(
            PacketType.LOGIN_REQUEST,
            {
                "username": username,
                "password_hash": password_hash,
            },
        )

        # Сохраняем токены
        self._access_token = response.get("access_token")
        self._refresh_token = response.get("refresh_token")
        self._user_id = UUID(response["user_id"]) if response.get("user_id") else None
        self._username = response.get("username")
        self._role = response.get("role")

        return response

    async def register(self, username: str, password_hash: str) -> dict[str, Any]:
        """
        Зарегистрировать нового пользователя.

        Args:
            username: Имя пользователя.
            password_hash: Хеш пароля.

        Returns:
            Ответ сервера.
        """
        return await self.send_request(
            PacketType.REGISTER_REQUEST,
            {
                "username": username,
                "password_hash": password_hash,
            },
        )

    async def logout(self) -> None:
        """Выполнить выход."""
        if self._connected:
            try:
                await self.send_packet(PacketType.LOGOUT, {})
            except Exception:
                pass

        self._access_token = None
        self._refresh_token = None
        self._user_id = None
        self._username = None
        self._role = None

        await self.disconnect()

    async def refresh_token(self) -> bool:
        """
        Обновить access-токен по refresh-токену.

        Returns:
            True, если токен обновлён.
        """
        if not self._refresh_token:
            return False

        try:
            response = await self.send_request(
                PacketType.REFRESH_TOKEN_REQUEST,
                {"refresh_token": self._refresh_token},
            )

            self._access_token = response.get("access_token")
            self._refresh_token = response.get("refresh_token")

            return True
        except Exception:
            return False

    # ========================================================================
    # ОТПРАВКА ПАКЕТОВ
    # ========================================================================

    async def send_packet(
        self,
        packet_type: PacketType,
        payload: dict[str, Any],
    ) -> None:
        """
        Отправить пакет без ожидания ответа.

        Args:
            packet_type: Тип пакета.
            payload: Данные.

        Raises:
            ConnectionError: Нет подключения.
        """
        if not self._connected:
            raise ConnectionError("Нет подключения к серверу")

        # Добавляем токен
        if self._access_token:
            payload["access_token"] = self._access_token

        async with self._send_lock:
            try:
                self._sequence += 1

                packet_bytes = (
                    self._packet_builder
                    .reset()
                    .set_type(packet_type)
                    .set_payload(payload)
                    .set_sequence(self._sequence)
                    .build(self._hmac_key)
                )

                self._writer.write(packet_bytes)
                await self._writer.drain()

                logger.debug(
                    "Отправлен пакет %s (seq=%d, размер=%d)",
                    packet_type.name,
                    self._sequence,
                    len(packet_bytes),
                )

            except OSError as e:
                self._connected = False
                raise ConnectionError(f"Ошибка отправки: {e}") from e

    async def send_request(
        self,
        packet_type: PacketType,
        payload: dict[str, Any],
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        """
        Отправить запрос и дождаться ответа.

        Args:
            packet_type: Тип пакета.
            payload: Данные.
            timeout: Таймаут ожидания ответа.

        Returns:
            Ответ сервера.

        Raises:
            ConnectionError: Нет подключения.
            asyncio.TimeoutError: Таймаут ожидания.
        """
        if not self._connected:
            raise ConnectionError("Нет подключения к серверу")

        # Создаём Future для ответа
        future: asyncio.Future = asyncio.get_event_loop().create_future()
        seq = self._sequence + 1
        self._pending_requests[seq] = future

        try:
            await self.send_packet(packet_type, payload)

            # Ждём ответ с таймаутом
            response = await asyncio.wait_for(future, timeout=timeout)

            if isinstance(response, dict):
                return response

            return {}

        finally:
            self._pending_requests.pop(seq, None)

    # ========================================================================
    # ПОЛУЧЕНИЕ ПАКЕТОВ
    # ========================================================================

    async def receive_loop(self) -> None:
        """
        Основной цикл получения пакетов.

        Должен запускаться как фоновая задача.
        """
        if not self._connected:
            logger.warning("Нет подключения для цикла получения")
            return

        logger.debug("Запущен цикл получения пакетов")

        while self._connected and self._reader is not None:
            try:
                # Читаем данные
                data = await asyncio.wait_for(
                    self._reader.read(BUFFER_SIZE),
                    timeout=HEARTBEAT_INTERVAL * 2,
                )

                if not data:
                    # Сервер закрыл соединение
                    logger.warning("Сервер закрыл соединение")
                    break

                # Парсим пакет
                try:
                    packet = self._packet_parser.parse(data, self._hmac_key)
                    await self._handle_packet(packet)
                except PacketParseError as e:
                    logger.warning("Ошибка парсинга пакета: %s", e)

            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Ошибка в цикле получения: %s", e)
                break

        # Соединение потеряно
        if self._connected:
            logger.warning("Соединение с сервером потеряно")
            await self._handle_disconnect()

    async def _handle_packet(self, packet: Packet) -> None:
        """
        Обработать входящий пакет.

        Args:
            packet: Пакет.
        """
        packet_type = packet.packet_type

        # Проверяем pending requests
        if packet.sequence in self._pending_requests:
            future = self._pending_requests.pop(packet.sequence)
            if not future.done():
                future.set_result(packet.payload)
                return

        # Обработка heartbeat
        if packet_type == PacketType.HEARTBEAT_REQUEST:
            await self.send_packet(PacketType.HEARTBEAT_RESPONSE, {})
            return

        # Обработка pong
        if packet_type == PacketType.PONG:
            self._last_pong = time.time()
            return

        # Обработка ошибок
        if packet_type == PacketType.ERROR:
            error_msg = packet.get_payload_field("message", "Неизвестная ошибка")
            logger.warning("Ошибка от сервера: %s", error_msg)
            return

        # Вызываем зарегистрированные обработчики
        await self._notify_handlers(packet_type, packet)

    async def _handle_disconnect(self) -> None:
        """Обработать разрыв соединения."""
        self._connected = False

        # Останавливаем heartbeat
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            self._heartbeat_task = None

        # Уведомляем обработчики
        await self._notify_state(False)

    # ========================================================================
    # HEARTBEAT
    # ========================================================================

    async def _heartbeat_loop(self) -> None:
        """Цикл heartbeat."""
        logger.debug("Heartbeat-цикл запущен")

        while self._connected:
            try:
                await asyncio.sleep(PING_INTERVAL)

                if not self._connected:
                    break

                # Отправляем ping
                await self.send_packet(
                    PacketType.PING,
                    {"sent_at": int(time.time() * 1000)},
                )

            except asyncio.CancelledError:
                break
            except Exception:
                break

        logger.debug("Heartbeat-цикл завершён")

    # ========================================================================
    # ОБРАБОТЧИКИ
    # ========================================================================

    def on_packet(
        self,
        packet_type: PacketType,
        handler: PacketCallback,
    ) -> None:
        """
        Зарегистрировать обработчик типа пакета.

        Args:
            packet_type: Тип пакета.
            handler: Асинхронный обработчик.
        """
        if packet_type not in self._packet_handlers:
            self._packet_handlers[packet_type] = []
        self._packet_handlers[packet_type].append(handler)

    def on_state_change(self, handler: StateCallback) -> None:
        """
        Зарегистрировать обработчик изменения состояния подключения.

        Args:
            handler: Асинхронный обработчик (принимает bool: connected).
        """
        self._state_handlers.append(handler)

    async def _notify_handlers(
        self,
        packet_type: PacketType,
        packet: Packet,
    ) -> None:
        """
        Уведомить обработчики о пакете.

        Args:
            packet_type: Тип пакета.
            packet: Пакет.
        """
        handlers = self._packet_handlers.get(packet_type, [])
        for handler in handlers:
            try:
                await handler(packet)
            except Exception as e:
                logger.error("Ошибка в обработчике %s: %s", packet_type.name, e)

    async def _notify_state(self, connected: bool) -> None:
        """
        Уведомить обработчики о состоянии.

        Args:
            connected: Подключено ли.
        """
        for handler in self._state_handlers:
            try:
                await handler(connected)
            except Exception as e:
                logger.error("Ошибка в обработчике состояния: %s", e)

    # ========================================================================
    # ИНФОРМАЦИЯ
    # ========================================================================

    @property
    def is_connected(self) -> bool:
        """Подключены ли к серверу."""
        return self._connected

    @property
    def is_authenticated(self) -> bool:
        """Аутентифицированы ли."""
        return self._access_token is not None

    @property
    def user_id(self) -> Optional[UUID]:
        """ID пользователя."""
        return self._user_id

    @property
    def username(self) -> Optional[str]:
        """Имя пользователя."""
        return self._username

    @property
    def role(self) -> Optional[str]:
        """Роль пользователя."""
        return self._role

    def get_stats(self) -> dict[str, Any]:
        """
        Получить статистику сетевого клиента.

        Returns:
            Словарь с метриками.
        """
        return {
            "connected": self._connected,
            "authenticated": self.is_authenticated,
            "username": self._username,
            "sequence": self._sequence,
            "pending_requests": len(self._pending_requests),
            "handlers_count": sum(len(h) for h in self._packet_handlers.values()),
        }