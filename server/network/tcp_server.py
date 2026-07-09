"""
server/network/tcp_server.py

Асинхронный TCP-сервер с SSL/TLS.

Обеспечивает:
- Приём входящих TCP-соединений
- SSL/TLS handshake
- Чтение и запись данных через asyncio Streams
- Передачу пакетов в SecurityMiddleware и MessageDispatcher
- Отправку ответов клиентам
- Обработку отключений

Использует asyncio.start_server (asyncio Streams API).

Python: 3.13+
"""

from __future__ import annotations

import asyncio
import logging
import ssl
import time
from typing import Optional
from uuid import UUID

from shared.constants import (
    DEFAULT_SERVER_HOST,
    DEFAULT_SERVER_PORT,
    BUFFER_SIZE,
    MAX_PACKET_SIZE,
    CONNECTION_TIMEOUT,
    HEARTBEAT_INTERVAL,
    HEARTBEAT_TIMEOUT,
    MAX_MISSED_HEARTBEATS,
)
from shared.enums import PacketType
from shared.protocol.packet import Packet, PacketParser, PacketBuilder, PacketParseError
from shared.protocol.crypto import HMACManager
from server.auth.auth_manager import AuthManager
from server.auth.token_manager import TokenManager
from server.middleware.security_middleware import SecurityMiddleware
from server.network.session_manager import Session, SessionManager
from server.network.message_dispatcher import MessageDispatcher

logger = logging.getLogger("billionaire.network")


# ============================================================================
# TCP СЕРВЕР
# ============================================================================

class TCPServer:
    """
    Асинхронный TCP-сервер с SSL/TLS.

    Принимает входящие соединения, управляет сессиями,
    обрабатывает входящие пакеты и отправляет ответы.

    Usage:
        server = TCPServer(
            host="0.0.0.0",
            port=8443,
            ssl_context=ssl_ctx,
            session_manager=session_mgr,
            security_middleware=security_mw,
            message_dispatcher=dispatcher,
            token_manager=token_mgr,
            auth_manager=auth_mgr,
        )
        await server.start()
    """

    def __init__(
        self,
        host: str,
        port: int,
        ssl_context: Optional[ssl.SSLContext],
        session_manager: SessionManager,
        security_middleware: SecurityMiddleware,
        message_dispatcher: MessageDispatcher,
        token_manager: TokenManager,
        auth_manager: AuthManager,
    ) -> None:
        """
        Инициализация TCP-сервера.

        Args:
            host: Адрес для прослушивания.
            port: Порт.
            ssl_context: SSL-контекст (None — без шифрования).
            session_manager: Менеджер сессий.
            security_middleware: Middleware безопасности.
            message_dispatcher: Диспетчер сообщений.
            token_manager: Менеджер токенов.
            auth_manager: Менеджер аутентификации.
        """
        self._host: str = host
        self._port: int = port
        self._ssl_context: Optional[ssl.SSLContext] = ssl_context
        self._session_manager: SessionManager = session_manager
        self._security_middleware: SecurityMiddleware = security_middleware
        self._message_dispatcher: MessageDispatcher = message_dispatcher
        self._token_manager: TokenManager = token_manager
        self._auth_manager: AuthManager = auth_manager

        self._server: Optional[asyncio.Server] = None
        self._running: bool = False

        # Парсер пакетов
        self._packet_parser = PacketParser()

        # Сборщик пакетов (переиспользуемый)
        self._packet_builder = PacketBuilder()

        # Задача heartbeat
        self._heartbeat_task: Optional[asyncio.Task] = None

    # ========================================================================
    # ЖИЗНЕННЫЙ ЦИКЛ
    # ========================================================================

    async def start(self) -> None:
        """
        Запустить сервер.

        Начинает прослушивание входящих соединений.
        """
        if self._running:
            logger.warning("Сервер уже запущен")
            return

        try:
            self._server = await asyncio.start_server(
                self._handle_client,
                host=self._host,
                port=self._port,
                ssl=self._ssl_context,
            )

            self._running = True

            # Запускаем heartbeat
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

            addr = self._server.sockets[0].getsockname() if self._server.sockets else (self._host, self._port)
            logger.info(
                "TCP-сервер запущен на %s:%d (SSL: %s)",
                addr[0],
                addr[1],
                "включён" if self._ssl_context else "выключен",
            )

            # Держим сервер запущенным
            async with self._server:
                await self._server.serve_forever()

        except asyncio.CancelledError:
            logger.info("Сервер остановлен")
        except Exception as e:
            logger.error("Ошибка запуска сервера: %s", e)
            raise
        finally:
            await self.stop()

    async def stop(self) -> None:
        """
        Остановить сервер.

        Закрывает все активные соединения и останавливает прослушивание.
        """
        if not self._running:
            return

        logger.info("Остановка TCP-сервера...")
        self._running = False

        # Останавливаем heartbeat
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None

        # Закрываем сервер
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

        # Закрываем все сессии
        for session_id in list(self._session_manager._sessions.keys()):
            self._session_manager.disconnect_session(session_id)

        logger.info("TCP-сервер остановлен")

    # ========================================================================
    # ОБРАБОТКА КЛИЕНТОВ
    # ========================================================================

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """
        Обработать новое клиентское подключение.

        Args:
            reader: StreamReader для чтения.
            writer: StreamWriter для записи.
        """
        # Получаем адрес клиента
        peer = writer.get_extra_info("peername")
        ip_address = peer[0] if peer else "unknown"

        # Создаём сессию
        session = self._session_manager.create_session(writer, reader, ip_address)

        logger.info(
            "Клиент подключился: %s (сессия: %s)",
            ip_address,
            str(session.session_id)[:8],
        )

        try:
            # Основной цикл чтения
            while self._running and session.is_online:
                try:
                    # Читаем данные с таймаутом
                    data = await asyncio.wait_for(
                        reader.read(BUFFER_SIZE),
                        timeout=CONNECTION_TIMEOUT,
                    )

                    if not data:
                        # Клиент закрыл соединение
                        logger.info(
                            "Клиент отключился: %s (сессия: %s)",
                            ip_address,
                            str(session.session_id)[:8],
                        )
                        break

                    # Обрабатываем входящий пакет
                    await self._process_incoming_data(session, data)

                except asyncio.TimeoutError:
                    # Таймаут чтения — проверяем, не пора ли отключить
                    if session.is_idle:
                        logger.info(
                            "Отключение неактивного клиента: %s",
                            str(session.session_id)[:8],
                        )
                        break
                    continue

                except asyncio.CancelledError:
                    break

        except Exception as e:
            logger.error(
                "Ошибка обработки клиента %s: %s",
                str(session.session_id)[:8],
                e,
            )
        finally:
            # Закрываем соединение
            await self._handle_disconnect(session)

    async def _process_incoming_data(
        self,
        session: Session,
        data: bytes,
    ) -> None:
        """
        Обработать входящие данные от клиента.

        Args:
            session: Сессия клиента.
            data: Полученные байты.
        """
        try:
            # Парсим пакет
            packet = self._packet_parser.parse(data, session.hmac_key)

            # Обновляем активность
            session.touch()

            # Проверяем через SecurityMiddleware
            user, error = await self._security_middleware.process(
                str(session.session_id),
                packet,
                session.hmac_key,
            )

            if error:
                # Отправляем ошибку клиенту
                await self._send_error(
                    session,
                    packet.sequence,
                    error,
                    1041,
                )
                return

            # Если пакет аутентификации и ещё не аутентифицирован
            if packet.packet_type in (
                PacketType.LOGIN_REQUEST,
                PacketType.REGISTER_REQUEST,
            ):
                response, error = await self._message_dispatcher.dispatch(
                    session.session_id,
                    packet,
                    user,
                )
                if response:
                    # Извлекаем токены для аутентификации сессии
                    await self._handle_auth_response(session, response)
                    await self._send_response(session, packet, response)

            elif user is None:
                # Не аутентифицирован — требуем вход
                await self._send_error(
                    session,
                    packet.sequence,
                    "Требуется аутентификация",
                    1041,
                )

            else:
                # Диспетчеризация к обработчику
                response, error = await self._message_dispatcher.dispatch(
                    session.session_id,
                    packet,
                    user,
                )

                if error:
                    await self._send_error(
                        session,
                        packet.sequence,
                        error,
                        1050,
                    )
                elif response:
                    await self._send_response(session, packet, response)

        except PacketParseError as e:
            logger.warning(
                "Ошибка парсинга пакета от сессии %s: %s",
                str(session.session_id)[:8],
                e,
            )
            await self._send_error(
                session,
                0,
                str(e),
                1001,
            )

    async def _handle_auth_response(
        self,
        session: Session,
        response: dict,
    ) -> None:
        """
        Обработать ответ аутентификации.

        Извлекает токены и аутентифицирует сессию.

        Args:
            session: Сессия.
            response: Ответ от AuthManager.
        """
        access_token = response.get("access_token")
        user_id = response.get("user_id")
        username = response.get("username")
        role = response.get("role")

        if access_token and user_id and username:
            self._session_manager.authenticate_session(
                session.session_id,
                UUID(user_id) if isinstance(user_id, str) else user_id,
                username,
                role or "player",
                access_token,
            )

    async def _handle_disconnect(self, session: Session) -> None:
        """
        Обработать отключение клиента.

        Args:
            session: Отключаемая сессия.
        """
        session_id = session.session_id

        # Закрываем writer
        if session.writer:
            try:
                session.writer.close()
                await session.writer.wait_closed()
            except Exception:
                pass

        # Удаляем сессию
        self._session_manager.remove_session(session_id)

        # Очищаем middleware
        self._security_middleware.remove_session(str(session_id))

        logger.info(
            "Клиент отключён: сессия %s (пользователь: %s)",
            str(session_id)[:8],
            session.username or "не аутентифицирован",
        )

    # ========================================================================
    # ОТПРАВКА ДАННЫХ
    # ========================================================================

    async def _send_response(
        self,
        session: Session,
        request_packet: Packet,
        response: dict,
    ) -> None:
        """
        Отправить ответ клиенту.

        Args:
            session: Сессия.
            request_packet: Исходный пакет-запрос.
            response: Данные ответа.
        """
        try:
            packet_bytes = self._packet_builder.reset() \
                .set_type(PacketType(request_packet.packet_type.value + 1)) \
                .set_payload(response) \
                .set_sequence(session.get_next_sequence()) \
                .build(session.hmac_key)

            await self._session_manager.send_to_session(
                session.session_id,
                packet_bytes,
            )

        except Exception as e:
            logger.error(
                "Ошибка отправки ответа сессии %s: %s",
                str(session.session_id)[:8],
                e,
            )

    async def _send_error(
        self,
        session: Session,
        sequence: int,
        message: str,
        error_code: int,
    ) -> None:
        """
        Отправить сообщение об ошибке клиенту.

        Args:
            session: Сессия.
            sequence: Порядковый номер исходного пакета.
            message: Сообщение об ошибке.
            error_code: Код ошибки.
        """
        try:
            error_payload = {
                "error_code": error_code,
                "message": message,
            }

            packet_bytes = self._packet_builder.reset() \
                .set_type(PacketType.ERROR) \
                .set_payload(error_payload) \
                .set_sequence(session.get_next_sequence()) \
                .build(session.hmac_key)

            await self._session_manager.send_to_session(
                session.session_id,
                packet_bytes,
            )

        except Exception as e:
            logger.error(
                "Ошибка отправки ошибки сессии %s: %s",
                str(session.session_id)[:8],
                e,
            )

    # ========================================================================
    # HEARTBEAT
    # ========================================================================

    async def _heartbeat_loop(self) -> None:
        """
        Цикл проверки heartbeat.

        Периодически отправляет HEARTBEAT_REQUEST всем сессиям
        и отключает не ответившие.
        """
        logger.debug("Heartbeat-цикл запущен (интервал: %.1f сек)", HEARTBEAT_INTERVAL)

        # Счётчики пропущенных ответов {session_id: count}
        missed_heartbeats: dict[UUID, int] = {}

        while self._running:
            try:
                await asyncio.sleep(HEARTBEAT_INTERVAL)

                now = time.time()

                for session in list(self._session_manager._sessions.values()):
                    if not session.is_online or not session.writer:
                        continue

                    # Отправляем heartbeat
                    try:
                        packet_bytes = self._packet_builder.reset() \
                            .set_type(PacketType.HEARTBEAT_REQUEST) \
                            .set_payload({"server_time": now}) \
                            .set_sequence(session.get_next_sequence()) \
                            .build(session.hmac_key)

                        session.writer.write(packet_bytes)
                        await session.writer.drain()

                        # Сбрасываем счётчик пропусков
                        missed_heartbeats.pop(session.session_id, None)

                    except Exception:
                        # Увеличиваем счётчик
                        missed_heartbeats[session.session_id] = \
                            missed_heartbeats.get(session.session_id, 0) + 1

                        if missed_heartbeats[session.session_id] >= MAX_MISSED_HEARTBEATS:
                            logger.warning(
                                "Клиент не отвечает на heartbeat: сессия %s",
                                str(session.session_id)[:8],
                            )
                            self._session_manager.disconnect_session(session.session_id)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Ошибка в heartbeat-цикле: %s", e)

        logger.debug("Heartbeat-цикл завершён")

    # ========================================================================
    # ИНФОРМАЦИЯ
    # ========================================================================

    @property
    def is_running(self) -> bool:
        """Запущен ли сервер."""
        return self._running

    def get_stats(self) -> dict:
        """
        Получить статистику сервера.

        Returns:
            Словарь с метриками.
        """
        return {
            "running": self._running,
            "host": self._host,
            "port": self._port,
            "ssl_enabled": self._ssl_context is not None,
            "sessions": self._session_manager.get_stats(),
            "dispatcher": self._message_dispatcher.get_stats(),
        }