"""
translations/translation_manager.py

Менеджер локализации для проекта "Миллиардер".

Обеспечивает:
- Загрузку переводов из JSON-файлов
- Получение строк по иерархическим ключам (app.title, game.roll_dice)
- Подстановку параметров в строки (format с **kwargs)
- Переключение языка во время выполнения
- Кеширование загруженных переводов
- Определение системного языка по умолчанию

Использование:
    from translations.translation_manager import TranslationManager

    tm = TranslationManager("translations")
    await tm.load_language("ru")
    text = tm.get("game.dice_result", die1=3, die2=5, total=8)

Python: 3.13+
"""

from __future__ import annotations

import json
import locale
from pathlib import Path
from typing import Any, Optional


# ============================================================================
# ИСКЛЮЧЕНИЯ ПЕРЕВОДОВ
# ============================================================================

class TranslationError(Exception):
    """Ошибка при работе с переводами."""

    def __init__(self, message: str) -> None:
        super().__init__(f"Ошибка перевода: {message}")


class TranslationLoadError(TranslationError):
    """Ошибка загрузки файла перевода."""

    def __init__(self, language: str, file_path: str, reason: str = "") -> None:
        msg = f"Не удалось загрузить перевод '{language}' из '{file_path}'"
        if reason:
            msg += f": {reason}"
        super().__init__(msg)
        self.language = language
        self.file_path = file_path


class TranslationKeyError(TranslationError):
    """Ошибка: ключ перевода не найден."""

    def __init__(self, key: str, language: str) -> None:
        super().__init__(
            f"Ключ '{key}' не найден в переводах для языка '{language}'"
        )
        self.key = key
        self.language = language


# ============================================================================
# МЕНЕДЖЕР ПЕРЕВОДОВ
# ============================================================================

class TranslationManager:
    """
    Менеджер локализации.

    Загружает переводы из JSON-файлов, предоставляет доступ
    к строкам по иерархическим ключам с поддержкой параметров.

    Attributes:
        translations_dir: Путь к директории с файлами переводов.
        current_language: Текущий язык.
        _translations: Кеш загруженных переводов {language: data}.
        _supported_languages: Список поддерживаемых языков.
    """

    # Язык по умолчанию (используется, если системный не поддерживается)
    DEFAULT_LANGUAGE: str = "ru"

    # Поддерживаемые языки
    SUPPORTED_LANGUAGES: tuple[str, ...] = ("ru", "en")

    # Названия языков (для отображения в настройках)
    LANGUAGE_NAMES: dict[str, dict[str, str]] = {
        "ru": {"ru": "Русский", "en": "Russian"},
        "en": {"ru": "English", "en": "English"},
    }

    def __init__(self, translations_dir: str = "translations") -> None:
        """
        Инициализация менеджера переводов.

        Args:
            translations_dir: Путь к директории с JSON-файлами переводов.
        """
        self.translations_dir: Path = Path(translations_dir)
        self.current_language: str = self._detect_system_language()
        self._translations: dict[str, dict[str, Any]] = {}

    # ========================================================================
    # ЗАГРУЗКА ПЕРЕВОДОВ
    # ========================================================================

    async def load_language(self, language: str) -> None:
        """
        Загрузить переводы для указанного языка.

        Args:
            language: Код языка (ru, en).

        Raises:
            TranslationLoadError: Если файл перевода не найден или повреждён.
            ValueError: Если язык не поддерживается.
        """
        if language not in self.SUPPORTED_LANGUAGES:
            raise ValueError(
                f"Язык '{language}' не поддерживается. "
                f"Доступные: {', '.join(self.SUPPORTED_LANGUAGES)}"
            )

        # Используем кеш, если переводы уже загружены
        if language in self._translations:
            self.current_language = language
            return

        file_path = self.translations_dir / f"{language}.json"

        if not file_path.exists():
            raise TranslationLoadError(
                language=language,
                file_path=str(file_path),
                reason="Файл не найден",
            )

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = json.load(f)
        except json.JSONDecodeError as e:
            raise TranslationLoadError(
                language=language,
                file_path=str(file_path),
                reason=f"Некорректный JSON: {e}",
            ) from e
        except OSError as e:
            raise TranslationLoadError(
                language=language,
                file_path=str(file_path),
                reason=str(e),
            ) from e

        # Проверяем версию файла переводов
        version = content.get("version", 0)
        if version < 1:
            raise TranslationLoadError(
                language=language,
                file_path=str(file_path),
                reason="Устаревшая версия файла переводов",
            )

        # Извлекаем данные (поддерживаем формат с обёрткой "data")
        translations = content.get("data", content)
        if "data" not in content:
            # Старый формат без обёртки — используем как есть
            translations = content

        self._translations[language] = translations
        self.current_language = language

    async def load_all_languages(self) -> None:
        """
        Загрузить все поддерживаемые языки.

        Полезно при старте сервера для предварительной загрузки.
        """
        for language in self.SUPPORTED_LANGUAGES:
            try:
                await self.load_language(language)
            except TranslationLoadError:
                # Игнорируем отсутствующие файлы при массовой загрузке
                pass

    # ========================================================================
    # ПОЛУЧЕНИЕ ПЕРЕВОДОВ
    # ========================================================================

    def get(self, key: str, default: str = "", **kwargs: Any) -> str:
        """
        Получить переведённую строку по иерархическому ключу.

        Поддерживает подстановку параметров через format():
            tm.get("game.dice_result", die1=3, die2=5, total=8)
            -> "Выпало: 3 + 5 = 8"

        Args:
            key: Иерархический ключ (например, "game.dice_result").
            default: Значение по умолчанию, если ключ не найден.
            **kwargs: Параметры для подстановки в строку.

        Returns:
            Переведённая строка с подставленными параметрами.

        Raises:
            TranslationKeyError: Если ключ не найден и default не указан.
        """
        translations = self._translations.get(self.current_language)

        if translations is None:
            if default:
                return self._format_string(default, **kwargs)
            raise TranslationKeyError(key, self.current_language)

        # Навигация по иерархическому ключу (разделитель — точка)
        value: Any = translations
        for part in key.split("."):
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                if default:
                    return self._format_string(default, **kwargs)
                raise TranslationKeyError(key, self.current_language)

        if not isinstance(value, str):
            # Если значение — не строка (например, вложенный словарь)
            if default:
                return self._format_string(default, **kwargs)
            raise TranslationKeyError(key, self.current_language)

        return self._format_string(value, **kwargs)

    def get_optional(self, key: str, **kwargs: Any) -> Optional[str]:
        """
        Получить перевод без выброса исключения.

        Args:
            key: Иерархический ключ.
            **kwargs: Параметры для подстановки.

        Returns:
            Переведённую строку или None, если ключ не найден.
        """
        try:
            return self.get(key, **kwargs)
        except TranslationKeyError:
            return None

    def get_all(self, prefix: str) -> dict[str, str]:
        """
        Получить все переводы с указанным префиксом.

        Полезно для получения всех строк категории (например, всех ошибок).

        Args:
            prefix: Префикс ключа (например, "errors").

        Returns:
            Словарь {полный_ключ: перевод}.
        """
        translations = self._translations.get(self.current_language, {})
        result: dict[str, str] = {}

        # Находим корневой объект по префиксу
        root: Any = translations
        for part in prefix.split("."):
            if isinstance(root, dict) and part in root:
                root = root[part]
            else:
                return result

        if not isinstance(root, dict):
            return result

        # Собираем все строки рекурсивно
        self._collect_strings(root, prefix, result)
        return result

    def _collect_strings(
        self,
        data: dict[str, Any],
        prefix: str,
        result: dict[str, str],
    ) -> None:
        """
        Рекурсивно собрать все строки из вложенного словаря.

        Args:
            data: Словарь с данными.
            prefix: Текущий префикс ключа.
            result: Результирующий словарь.
        """
        for key, value in data.items():
            full_key = f"{prefix}.{key}"
            if isinstance(value, str):
                result[full_key] = value
            elif isinstance(value, dict):
                self._collect_strings(value, full_key, result)

    # ========================================================================
    # УПРАВЛЕНИЕ ЯЗЫКОМ
    # ========================================================================

    def set_language(self, language: str) -> None:
        """
        Установить текущий язык.

        Язык должен быть предварительно загружен через load_language().

        Args:
            language: Код языка.

        Raises:
            ValueError: Если язык не загружен.
        """
        if language not in self._translations:
            raise ValueError(
                f"Язык '{language}' не загружен. "
                f"Сначала вызовите load_language('{language}')"
            )
        self.current_language = language

    def get_current_language(self) -> str:
        """
        Получить текущий язык.

        Returns:
            Код текущего языка.
        """
        return self.current_language

    def get_current_language_name(self) -> str:
        """
        Получить название текущего языка на текущем языке.

        Returns:
            Название языка (например, "Русский").
        """
        return self.get_language_name(self.current_language)

    def get_language_name(self, language: str) -> str:
        """
        Получить название языка на указанном языке.

        Args:
            language: Код языка.

        Returns:
            Название языка на его родном языке.
        """
        names = self.LANGUAGE_NAMES.get(language, {})
        return names.get(language, language)

    def get_supported_languages(self) -> list[dict[str, str]]:
        """
        Получить список поддерживаемых языков с названиями.

        Returns:
            Список словарей {code, name}.
        """
        current = self.current_language
        return [
            {
                "code": lang,
                "name": self.LANGUAGE_NAMES.get(lang, {}).get(current, lang),
            }
            for lang in self.SUPPORTED_LANGUAGES
        ]

    # ========================================================================
    # ПРОВЕРКИ
    # ========================================================================

    def has_key(self, key: str, language: Optional[str] = None) -> bool:
        """
        Проверить существование ключа в переводах.

        Args:
            key: Иерархический ключ.
            language: Язык (по умолчанию — текущий).

        Returns:
            True, если ключ существует.
        """
        lang = language or self.current_language
        translations = self._translations.get(lang)

        if translations is None:
            return False

        value: Any = translations
        for part in key.split("."):
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                return False

        return isinstance(value, str)

    def is_loaded(self, language: str) -> bool:
        """
        Проверить, загружены ли переводы для языка.

        Args:
            language: Код языка.

        Returns:
            True, если переводы загружены.
        """
        return language in self._translations

    def get_missing_keys(self, reference_language: str = "en") -> dict[str, list[str]]:
        """
        Найти ключи, отсутствующие в переводах относительно эталонного языка.

        Args:
            reference_language: Эталонный язык для сравнения.

        Returns:
            Словарь {language: [missing_keys]}.
        """
        reference = self._translations.get(reference_language)
        if reference is None:
            return {}

        reference_keys = set()
        self._collect_keys(reference, "", reference_keys)

        missing: dict[str, list[str]] = {}
        for lang, translations in self._translations.items():
            if lang == reference_language:
                continue

            lang_keys: set[str] = set()
            self._collect_keys(translations, "", lang_keys)

            diff = sorted(reference_keys - lang_keys)
            if diff:
                missing[lang] = diff

        return missing

    def _collect_keys(
        self,
        data: dict[str, Any],
        prefix: str,
        keys: set[str],
    ) -> None:
        """
        Рекурсивно собрать все ключи из словаря переводов.

        Args:
            data: Словарь с данными.
            prefix: Текущий префикс.
            keys: Множество для сбора ключей.
        """
        for key, value in data.items():
            full_key = f"{prefix}.{key}" if prefix else key
            if isinstance(value, str):
                keys.add(full_key)
            elif isinstance(value, dict):
                self._collect_keys(value, full_key, keys)

    # ========================================================================
    # ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ
    # ========================================================================

    @staticmethod
    def _format_string(template: str, **kwargs: Any) -> str:
        """
        Форматировать строку с подстановкой параметров.

        Если параметр не указан, оставляет плейсхолдер как есть.

        Args:
            template: Шаблон строки.
            **kwargs: Параметры.

        Returns:
            Отформатированная строка.
        """
        if not kwargs:
            return template
        try:
            return template.format(**kwargs)
        except KeyError:
            # Оставляем неподставленные плейсхолдеры
            return template

    def _detect_system_language(self) -> str:
        """
        Определить системный язык.

        Пытается определить язык ОС и сопоставить с поддерживаемыми.
        Если системный язык не поддерживается, возвращает DEFAULT_LANGUAGE.

        Returns:
            Код поддерживаемого языка.
        """
        try:
            system_lang = locale.getdefaultlocale()[0]
            if system_lang:
                # Извлекаем основной код языка (ru_RU -> ru)
                lang_code = system_lang.split("_")[0].lower()
                if lang_code in self.SUPPORTED_LANGUAGES:
                    return lang_code
        except (locale.Error, ValueError):
            pass

        return self.DEFAULT_LANGUAGE

    def clear_cache(self) -> None:
        """Очистить кеш загруженных переводов."""
        self._translations.clear()

    def reload(self) -> None:
        """
        Перезагрузить переводы для текущего языка.

        Полезно при обновлении файлов переводов без перезапуска.
        """
        current = self.current_language
        self.clear_cache()
        # Загрузка будет выполнена при следующем вызове load_language
        self.current_language = current


# ============================================================================
# ГЛОБАЛЬНЫЙ ЭКЗЕМПЛЯР (ОПЦИОНАЛЬНО)
# ============================================================================

# Создаётся при первом импорте. Для production рекомендуется DI-контейнер.
_translation_manager: Optional[TranslationManager] = None


def get_translation_manager(
    translations_dir: str = "translations",
) -> TranslationManager:
    """
    Получить глобальный экземпляр менеджера переводов.

    При первом вызове создаёт экземпляр. При последующих —
    возвращает существующий.

    Args:
        translations_dir: Путь к директории с переводами.

    Returns:
        Экземпляр TranslationManager.
    """
    global _translation_manager
    if _translation_manager is None:
        _translation_manager = TranslationManager(translations_dir)
    return _translation_manager


# ============================================================================
# УДОБНАЯ ФУНКЦИЯ ДЛЯ БЫСТРОГО ПЕРЕВОДА
# ============================================================================

def t(key: str, default: str = "", **kwargs: Any) -> str:
    """
    Быстрый перевод строки через глобальный менеджер.

    Usage:
        from translations.translation_manager import t

        text = t("game.roll_dice")
        text = t("game.dice_result", die1=3, die2=5, total=8)

    Args:
        key: Ключ перевода.
        default: Значение по умолчанию.
        **kwargs: Параметры для подстановки.

    Returns:
        Переведённая строка.
    """
    manager = get_translation_manager()
    try:
        return manager.get(key, default, **kwargs)
    except TranslationKeyError:
        return default or key