"""
server/auth/auth_manager.py

Менеджер аутентификации пользователей.

Обеспечивает:
- Регистрацию новых пользователей
- Вход (login) с проверкой пароля
- Выход (logout) с отзывом токенов
- Смену пароля
- Блокировку/разблокировку пользователей

Пароли хешируются через Argon2id. Токены управляются TokenManager.

Python: 3.13+
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from database.repositories.postgresql.user_repository import UserRepository
from shared.enums import UserRole
from shared.models.user import User
from shared.protocol.crypto import PasswordHasher
from shared.validators import validate_username, validate_password
from server.auth.token_manager import TokenManager

logger = logging.getLogger("billionaire.server")


# ============================================================================
# ИСКЛЮЧЕНИЯ АУТЕНТИФИКАЦИИ
# ============================================================================

class AuthError(Exception):
    """Ошибка аутентификации."""

    def __init__(self, message: str, error_code: int = 0) -> None:
        self.error_code = error_code
        super().__init__(message)


class InvalidCredentialsError(AuthError):
    """Неверные учётные данные."""

    def __init__(self) -> None:
        super().__init__("Неверное имя пользователя или пароль", 1002)


class UsernameTakenError(AuthError):
    """Имя пользователя занято."""

    def __init__(self, username: str) -> None:
        super().__init__(f"Имя пользователя '{username}' уже занято", 1003)


class UserBannedError(AuthError):
    """Пользователь заблокирован."""

    def __init__(self) -> None:
        super().__init__("Ваш аккаунт заблокирован", 1004)


class TokenExpiredError(AuthError):
    """Токен истёк."""

    def __init__(self) -> None:
        super().__init__("Токен истёк, выполните вход заново", 1005)


class TokenInvalidError(AuthError):
    """Токен недействителен."""

    def __init__(self) -> None:
        super().__init__("Токен недействителен", 1006)


class ValidationError(AuthError):
    """Ошибка валидации ввода."""

    def __init__(self, message: str) -> None:
        super().__init__(message, 0)


# ============================================================================
# МЕНЕДЖЕР АУТЕНТИФИКАЦИИ
# ============================================================================

class AuthManager:
    """
    Менеджер аутентификации пользователей.

    Обрабатывает регистрацию, вход, выход и управление учётными записями.

    Usage:
        manager = AuthManager(user_repo, token_manager)
        tokens = await manager.login("player1", "password123")
        await manager.logout(access_token)
    """

    # Максимальное количество попыток входа (защита от brute-force)
    MAX_LOGIN_ATTEMPTS: int = 5

    # Время блокировки после превышения попыток (секунд)
    LOGIN_BLOCK_TIME: int = 300

    def __init__(
        self,
        user_repository: UserRepository,
        token_manager: TokenManager,
    ) -> None:
        """
        Инициализация менеджера аутентификации.

        Args:
            user_repository: Репозиторий пользователей.
            token_manager: Менеджер токенов.
        """
        self._user_repo = user_repository
        self._token_manager = token_manager

        # Отслеживание попыток входа (в памяти)
        self._login_attempts: dict[str, tuple[int, float]] = {}

    # ========================================================================
    # РЕГИСТРАЦИЯ
    # ========================================================================

    async def register(
        self,
        username: str,
        password: str,
        role: str = "player",
    ) -> User:
        """
        Зарегистрировать нового пользователя.

        Args:
            username: Имя пользователя.
            password: Пароль (открытый текст).
            role: Роль (player, observer).

        Returns:
            Созданный пользователь.

        Raises:
            ValidationError: Если данные не прошли валидацию.
            UsernameTakenError: Если имя занято.
        """
        # Валидация имени
        error = validate_username(username)
        if error:
            raise ValidationError(error)

        # Валидация пароля
        error = validate_password(password)
        if error:
            raise ValidationError(error)

        # Проверка занятости имени
        if await self._user_repo.username_exists(username):
            raise UsernameTakenError(username)

        # Хеширование пароля
        password_hash = await PasswordHasher.hash_password(password)

        # Создание пользователя
        user = User.create(
            username=username,
            password_hash=password_hash,
            role=UserRole(role),
        )

        # Сохранение в БД
        saved_user = await self._user_repo.save(user)

        logger.info(
            "Зарегистрирован новый пользователь: %s (роль: %s)",
            username,
            role,
        )

        return saved_user

    # ========================================================================
    # ВХОД
    # ========================================================================

    async def login(
        self,
        username: str,
        password: str,
    ) -> tuple[str, str, int, User]:
        """
        Выполнить вход пользователя.

        Args:
            username: Имя пользователя.
            password: Пароль (открытый текст).

        Returns:
            Кортеж (access_token, refresh_token, expires_in, user).

        Raises:
            InvalidCredentialsError: Неверные учётные данные.
            UserBannedError: Пользователь заблокирован.
            ValidationError: Слишком много попыток.
        """
        # Проверка на brute-force
        self._check_login_attempts(username)

        # Поиск пользователя
        user = await self._user_repo.get_by_username(username)
        if user is None:
            self._record_failed_attempt(username)
            raise InvalidCredentialsError()

        # Проверка блокировки
        if user.is_banned:
            raise UserBannedError()

        # Проверка пароля
        password_valid = await PasswordHasher.verify_password(
            password, user.password_hash
        )

        if not password_valid:
            self._record_failed_attempt(username)
            logger.warning("Неверный пароль для пользователя %s", username)
            raise InvalidCredentialsError()

        # Сброс счётчика попыток
        self._login_attempts.pop(username, None)

        # Создание токенов
        access_token, refresh_token, expires_in = self._token_manager.create_tokens(
            user_id=user.user_id,
            role=user.role.value,
        )

        # Обновление времени входа
        await self._user_repo.update_last_login(user.user_id)

        logger.info("Пользователь %s вошёл в систему", username)

        return access_token, refresh_token, expires_in, user

    # ========================================================================
    # ВЫХОД
    # ========================================================================

    async def logout(self, access_token: str) -> bool:
        """
        Выполнить выход пользователя.

        Args:
            access_token: Токен доступа.

        Returns:
            True, если выход выполнен.
        """
        token_data = self._token_manager.validate_access_token(access_token)
        if token_data is None:
            return False

        # Отзываем токен
        self._token_manager.revoke_access_token(access_token)

        # Отмечаем пользователя офлайн (если есть сессия)
        user = await self._user_repo.get_by_id(token_data.user_id)
        if user:
            user.set_offline()
            await self._user_repo.save(user)

        logger.info("Пользователь %s вышел из системы", token_data.user_id)
        return True

    # ========================================================================
    # ОБНОВЛЕНИЕ ТОКЕНА
    # ========================================================================

    async def refresh_token(
        self,
        refresh_token: str,
    ) -> Optional[tuple[str, str, int, User]]:
        """
        Обновить access-токен по refresh-токену.

        Args:
            refresh_token: Токен обновления.

        Returns:
            Кортеж (new_access_token, new_refresh_token, expires_in, user) или None.

        Raises:
            TokenExpiredError: Токен истёк.
            TokenInvalidError: Токен недействителен.
            UserBannedError: Пользователь заблокирован.
        """
        # Проверяем refresh-токен
        refresh_data = self._token_manager.validate_refresh_token(refresh_token)
        if refresh_data is None:
            raise TokenInvalidError()

        # Проверяем, не истёк ли
        from time import time
        if time() > refresh_data.expires_at:
            raise TokenExpiredError()

        # Получаем пользователя
        user = await self._user_repo.get_by_id(refresh_data.user_id)
        if user is None:
            raise TokenInvalidError()

        if user.is_banned:
            raise UserBannedError()

        # Отзываем старый access-токен
        self._token_manager.revoke_access_token(refresh_data.access_token)

        # Создаём новые токены
        access_token, new_refresh_token, expires_in = self._token_manager.create_tokens(
            user_id=user.user_id,
            role=user.role.value,
        )

        logger.info("Токены обновлены для пользователя %s", user.user_id)

        return access_token, new_refresh_token, expires_in, user

    # ========================================================================
    # ВАЛИДАЦИЯ СЕССИИ
    # ========================================================================

    async def validate_session(self, access_token: str) -> Optional[User]:
        """
        Проверить сессию по access-токену.

        Args:
            access_token: Токен доступа.

        Returns:
            Пользователь или None.
        """
        token_data = self._token_manager.validate_access_token(access_token)
        if token_data is None:
            return None

        user = await self._user_repo.get_by_id(token_data.user_id)
        if user is None or user.is_banned:
            return None

        return user

    # ========================================================================
    # УПРАВЛЕНИЕ ПАРОЛЯМИ
    # ========================================================================

    async def change_password(
        self,
        user_id: UUID,
        old_password: str,
        new_password: str,
    ) -> bool:
        """
        Сменить пароль пользователя.

        Args:
            user_id: ID пользователя.
            old_password: Старый пароль.
            new_password: Новый пароль.

        Returns:
            True, если пароль изменён.

        Raises:
            InvalidCredentialsError: Неверный старый пароль.
            ValidationError: Новый пароль не прошёл валидацию.
        """
        # Валидация нового пароля
        error = validate_password(new_password)
        if error:
            raise ValidationError(error)

        user = await self._user_repo.get_by_id(user_id)
        if user is None:
            raise InvalidCredentialsError()

        # Проверка старого пароля
        password_valid = await PasswordHasher.verify_password(
            old_password, user.password_hash
        )
        if not password_valid:
            raise InvalidCredentialsError()

        # Хеширование нового пароля
        new_hash = await PasswordHasher.hash_password(new_password)

        # Обновление
        await self._user_repo.update_password(user_id, new_hash)

        # Отзыв всех токенов
        self._token_manager.revoke_all_user_tokens(user_id)

        logger.info("Пароль изменён для пользователя %s", user_id)
        return True

    # ========================================================================
    # УПРАВЛЕНИЕ БЛОКИРОВКОЙ
    # ========================================================================

    async def ban_user(self, admin_id: UUID, user_id: UUID) -> bool:
        """
        Заблокировать пользователя.

        Args:
            admin_id: ID администратора.
            user_id: ID блокируемого пользователя.

        Returns:
            True, если блокировка выполнена.
        """
        result = await self._user_repo.ban_user(user_id)
        if result:
            # Отзыв всех токенов
            self._token_manager.revoke_all_user_tokens(user_id)
            logger.info(
                "Пользователь %s заблокирован администратором %s",
                user_id,
                admin_id,
            )
        return result

    async def unban_user(self, admin_id: UUID, user_id: UUID) -> bool:
        """
        Разблокировать пользователя.

        Args:
            admin_id: ID администратора.
            user_id: ID разблокируемого пользователя.

        Returns:
            True, если разблокировка выполнена.
        """
        result = await self._user_repo.unban_user(user_id)
        if result:
            logger.info(
                "Пользователь %s разблокирован администратором %s",
                user_id,
                admin_id,
            )
        return result

    # ========================================================================
    # ЗАЩИТА ОТ BRUTE-FORCE
    # ========================================================================

    def _check_login_attempts(self, username: str) -> None:
        """
        Проверить количество попыток входа.

        Args:
            username: Имя пользователя.

        Raises:
            ValidationError: Превышен лимит попыток.
        """
        if username not in self._login_attempts:
            return

        attempts, first_attempt_time = self._login_attempts[username]

        from time import time
        if attempts >= self.MAX_LOGIN_ATTEMPTS:
            elapsed = time() - first_attempt_time
            if elapsed < self.LOGIN_BLOCK_TIME:
                remaining = int(self.LOGIN_BLOCK_TIME - elapsed)
                raise ValidationError(
                    f"Слишком много попыток входа. "
                    f"Попробуйте через {remaining} секунд."
                )
            else:
                # Блокировка истекла — сбрасываем
                self._login_attempts.pop(username, None)

    def _record_failed_attempt(self, username: str) -> None:
        """
        Записать неудачную попытку входа.

        Args:
            username: Имя пользователя.
        """
        from time import time
        now = time()

        if username in self._login_attempts:
            attempts, _ = self._login_attempts[username]
            self._login_attempts[username] = (attempts + 1, now)
        else:
            self._login_attempts[username] = (1, now)

        logger.warning(
            "Неудачная попытка входа: %s (попытка %d)",
            username,
            self._login_attempts[username][0],
        )

    def clear_login_attempts(self, username: str) -> None:
        """
        Сбросить счётчик попыток входа.

        Args:
            username: Имя пользователя.
        """
        self._login_attempts.pop(username, None)

    # ========================================================================
    # ИНФОРМАЦИЯ
    # ========================================================================

    async def get_user_info(self, user_id: UUID) -> Optional[dict]:
        """
        Получить информацию о пользователе.

        Args:
            user_id: ID пользователя.

        Returns:
            Словарь с данными пользователя или None.
        """
        user = await self._user_repo.get_by_id(user_id)
        if user is None:
            return None
        return user.to_dict()

    async def get_user_profile(self, user_id: UUID) -> Optional[dict]:
        """
        Получить профиль игрока со статистикой.

        Args:
            user_id: ID пользователя.

        Returns:
            Словарь с профилем или None.
        """
        profile = await self._user_repo.get_player_profile(user_id)
        if profile is None:
            return None
        return profile.to_dict()