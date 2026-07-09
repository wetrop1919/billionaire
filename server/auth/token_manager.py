"""
server/auth/token_manager.py

Менеджер токенов доступа и обновления.

Обеспечивает:
- Создание и валидацию access/refresh токенов
- Хранение активных токенов в памяти
- Отзыв токенов (logout)
- Автоматическую очистку истёкших токенов

Токены — криптографически безопасные случайные строки (не JWT),
хранятся на сервере и связываются с сессией пользователя.

Python: 3.13+
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Optional
from uuid import UUID

from shared.constants import (
    ACCESS_TOKEN_EXPIRE,
    REFRESH_TOKEN_EXPIRE,
    SESSION_TOKEN_SIZE,
)
from shared.protocol.crypto import TokenGenerator

logger = logging.getLogger("billionaire.server")


# ============================================================================
# ДАННЫЕ ТОКЕНА
# ============================================================================

@dataclass(slots=True)
class TokenData:
    """
    Данные, связанные с токеном доступа.

    Attributes:
        user_id: ID пользователя.
        role: Роль пользователя.
        issued_at: Время создания (Unix timestamp).
        expires_at: Время истечения (Unix timestamp).
        refresh_token: Связанный refresh-токен.
    """

    user_id: UUID
    role: str
    issued_at: float
    expires_at: float
    refresh_token: str


@dataclass(slots=True)
class RefreshTokenData:
    """
    Данные, связанные с refresh-токеном.

    Attributes:
        user_id: ID пользователя.
        issued_at: Время создания.
        expires_at: Время истечения.
        access_token: Текущий связанный access-токен.
    """

    user_id: UUID
    issued_at: float
    expires_at: float
    access_token: str


# ============================================================================
# МЕНЕДЖЕР ТОКЕНОВ
# ============================================================================

class TokenManager:
    """
    Управление токенами аутентификации.

    Хранит активные токены в словарях (в памяти).
    При перезапуске сервера все токены сбрасываются —
    пользователям нужно заново войти.

    Attributes:
        _access_tokens: Словарь {access_token: TokenData}.
        _refresh_tokens: Словарь {refresh_token: RefreshTokenData}.
        _user_tokens: Словарь {user_id: set[access_token]}.
        _access_token_expire: Время жизни access-токена в секундах.
        _refresh_token_expire: Время жизни refresh-токена в секундах.
    """

    def __init__(
        self,
        access_token_expire: int | None = None,
        refresh_token_expire: int | None = None,
    ) -> None:
        """
        Инициализация менеджера токенов.

        Args:
            access_token_expire: Время жизни access-токена (по умолчанию 1 час).
            refresh_token_expire: Время жизни refresh-токена (по умолчанию 30 дней).
        """
        self._access_tokens: dict[str, TokenData] = {}
        self._refresh_tokens: dict[str, RefreshTokenData] = {}
        self._user_tokens: dict[UUID, set[str]] = {}

        self._access_token_expire: int = access_token_expire or ACCESS_TOKEN_EXPIRE
        self._refresh_token_expire: int = refresh_token_expire or REFRESH_TOKEN_EXPIRE

    # ========================================================================
    # СОЗДАНИЕ ТОКЕНОВ
    # ========================================================================

    def create_tokens(self, user_id: UUID, role: str) -> tuple[str, str, int]:
        """
        Создать пару токенов (access + refresh) для пользователя.

        Отзывает все предыдущие токены пользователя.

        Args:
            user_id: ID пользователя.
            role: Роль пользователя.

        Returns:
            Кортеж (access_token, refresh_token, expires_in_seconds).
        """
        # Отзываем старые токены
        self.revoke_all_user_tokens(user_id)

        now = time.time()

        # Создаём refresh-токен
        refresh_token = TokenGenerator.generate_refresh_token()
        refresh_data = RefreshTokenData(
            user_id=user_id,
            issued_at=now,
            expires_at=now + self._refresh_token_expire,
            access_token="",  # Будет установлен после создания access
        )

        # Создаём access-токен
        access_token = TokenGenerator.generate_session_token()
        token_data = TokenData(
            user_id=user_id,
            role=role,
            issued_at=now,
            expires_at=now + self._access_token_expire,
            refresh_token=refresh_token,
        )

        # Связываем токены
        refresh_data.access_token = access_token

        # Сохраняем
        self._access_tokens[access_token] = token_data
        self._refresh_tokens[refresh_token] = refresh_data

        # Индексируем по пользователю
        if user_id not in self._user_tokens:
            self._user_tokens[user_id] = set()
        self._user_tokens[user_id].add(access_token)

        logger.info(
            "Созданы токены для user_id=%s, роль=%s",
            user_id,
            role,
        )

        return access_token, refresh_token, self._access_token_expire

    # ========================================================================
    # ВАЛИДАЦИЯ ТОКЕНОВ
    # ========================================================================

    def validate_access_token(self, access_token: str) -> Optional[TokenData]:
        """
        Проверить access-токен.

        Args:
            access_token: Токен доступа.

        Returns:
            TokenData если токен валиден, иначе None.
        """
        token_data = self._access_tokens.get(access_token)

        if token_data is None:
            return None

        # Проверка срока действия
        if time.time() > token_data.expires_at:
            self._revoke_access_token(access_token)
            return None

        return token_data

    def validate_refresh_token(self, refresh_token: str) -> Optional[RefreshTokenData]:
        """
        Проверить refresh-токен.

        Args:
            refresh_token: Токен обновления.

        Returns:
            RefreshTokenData если токен валиден, иначе None.
        """
        token_data = self._refresh_tokens.get(refresh_token)

        if token_data is None:
            return None

        # Проверка срока действия
        if time.time() > token_data.expires_at:
            self._revoke_refresh_token(refresh_token)
            return None

        return token_data

    def is_access_token_valid(self, access_token: str) -> bool:
        """
        Быстрая проверка валидности access-токена.

        Args:
            access_token: Токен.

        Returns:
            True если токен активен.
        """
        return self.validate_access_token(access_token) is not None

    # ========================================================================
    # ОБНОВЛЕНИЕ ТОКЕНОВ
    # ========================================================================

    def refresh_access_token(self, refresh_token: str) -> Optional[tuple[str, str, int]]:
        """
        Обновить access-токен по refresh-токену.

        Args:
            refresh_token: Действующий refresh-токен.

        Returns:
            Кортеж (new_access_token, new_refresh_token, expires_in) или None.
        """
        refresh_data = self.validate_refresh_token(refresh_token)
        if refresh_data is None:
            return None

        # Отзываем старый access-токен
        old_access = refresh_data.access_token
        if old_access:
            self._revoke_access_token(old_access, remove_refresh=False)

        # Создаём новые токены
        return self.create_tokens(
            user_id=refresh_data.user_id,
            role="",  # Роль будет получена из данных пользователя
        )

    # ========================================================================
    # ОТЗЫВ ТОКЕНОВ
    # ========================================================================

    def revoke_access_token(self, access_token: str) -> bool:
        """
        Отозвать access-токен (logout).

        Args:
            access_token: Токен для отзыва.

        Returns:
            True, если токен был отозван.
        """
        return self._revoke_access_token(access_token)

    def revoke_all_user_tokens(self, user_id: UUID) -> int:
        """
        Отозвать все токены пользователя.

        Используется при смене пароля, блокировке или повторном входе.

        Args:
            user_id: ID пользователя.

        Returns:
            Количество отозванных токенов.
        """
        count = 0

        access_tokens = self._user_tokens.pop(user_id, set())
        for token in list(access_tokens):
            if self._revoke_access_token(token):
                count += 1

        # Очищаем refresh-токены пользователя
        refresh_to_remove = [
            rt for rt, data in self._refresh_tokens.items()
            if data.user_id == user_id
        ]
        for rt in refresh_to_remove:
            self._revoke_refresh_token(rt)

        if count > 0:
            logger.info("Отозвано %d токенов пользователя %s", count, user_id)

        return count

    def _revoke_access_token(
        self,
        access_token: str,
        remove_refresh: bool = True,
    ) -> bool:
        """
        Внутренний метод отзыва access-токена.

        Args:
            access_token: Токен.
            remove_refresh: Удалить ли связанный refresh-токен.

        Returns:
            True, если токен существовал.
        """
        token_data = self._access_tokens.pop(access_token, None)
        if token_data is None:
            return False

        # Удаляем из индекса пользователя
        user_tokens = self._user_tokens.get(token_data.user_id)
        if user_tokens:
            user_tokens.discard(access_token)

        # Удаляем связанный refresh-токен
        if remove_refresh and token_data.refresh_token:
            self._revoke_refresh_token(token_data.refresh_token)

        return True

    def _revoke_refresh_token(self, refresh_token: str) -> bool:
        """
        Внутренний метод отзыва refresh-токена.

        Args:
            refresh_token: Токен.

        Returns:
            True, если токен существовал.
        """
        return self._refresh_tokens.pop(refresh_token, None) is not None

    # ========================================================================
    # ОЧИСТКА ИСТЁКШИХ ТОКЕНОВ
    # ========================================================================

    def cleanup_expired_tokens(self) -> tuple[int, int]:
        """
        Удалить все истёкшие токены.

        Вызывается периодически (например, раз в час) планировщиком.

        Returns:
            Кортеж (удалено_access, удалено_refresh).
        """
        now = time.time()

        # Очистка access-токенов
        expired_access = [
            token for token, data in self._access_tokens.items()
            if now > data.expires_at
        ]
        for token in expired_access:
            self._revoke_access_token(token)

        # Очистка refresh-токенов
        expired_refresh = [
            token for token, data in self._refresh_tokens.items()
            if now > data.expires_at
        ]
        for token in expired_refresh:
            self._revoke_refresh_token(token)

        if expired_access or expired_refresh:
            logger.debug(
                "Очищено токенов: access=%d, refresh=%d",
                len(expired_access),
                len(expired_refresh),
            )

        return len(expired_access), len(expired_refresh)

    # ========================================================================
    # ИНФОРМАЦИЯ
    # ========================================================================

    @property
    def active_access_tokens(self) -> int:
        """Количество активных access-токенов."""
        return len(self._access_tokens)

    @property
    def active_refresh_tokens(self) -> int:
        """Количество активных refresh-токенов."""
        return len(self._refresh_tokens)

    @property
    def active_users(self) -> int:
        """Количество пользователей с активными токенами."""
        return len(self._user_tokens)

    def get_user_active_tokens(self, user_id: UUID) -> int:
        """
        Получить количество активных токенов пользователя.

        Args:
            user_id: ID пользователя.

        Returns:
            Количество токенов.
        """
        return len(self._user_tokens.get(user_id, set()))

    def get_stats(self) -> dict:
        """
        Получить статистику токенов.

        Returns:
            Словарь с метриками.
        """
        return {
            "active_access_tokens": self.active_access_tokens,
            "active_refresh_tokens": self.active_refresh_tokens,
            "active_users": self.active_users,
            "access_token_expire_seconds": self._access_token_expire,
            "refresh_token_expire_seconds": self._refresh_token_expire,
        }