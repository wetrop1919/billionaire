"""
client/assets/asset_manager.py

Менеджер ресурсов клиента.

Управляет загрузкой, кешированием и выгрузкой ресурсов:
- Изображения (QIcon, QPixmap)
- Звуки (QSoundEffect)
- Стили (QSS)
- Шрифты (QFont)

Обеспечивает:
- Ленивую загрузку (по требованию)
- Кеширование для повторного использования
- Автоматическую очистку при нехватке памяти

Python: 3.13+
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("billionaire.client")


# ============================================================================
# ТИПЫ РЕСУРСОВ
# ============================================================================

class AssetCache:
    """
    Простой кеш для ресурсов.

    Хранит загруженные ресурсы в словаре с ограничением размера.
    При превышении лимита удаляет наименее используемые элементы.

    Attributes:
        _cache: Словарь {ключ: объект}.
        _max_size: Максимальный размер кеша.
        _access_count: Счётчик обращений для LRU.
    """

    def __init__(self, max_size: int = 200) -> None:
        """
        Инициализация кеша.

        Args:
            max_size: Максимальное количество элементов.
        """
        self._cache: dict[str, Any] = {}
        self._max_size: int = max_size
        self._access_count: dict[str, int] = {}

    def get(self, key: str) -> Optional[Any]:
        """
        Получить элемент из кеша.

        Args:
            key: Ключ элемента.

        Returns:
            Закешированный объект или None.
        """
        if key in self._cache:
            self._access_count[key] = self._access_count.get(key, 0) + 1
            return self._cache[key]
        return None

    def put(self, key: str, value: Any) -> None:
        """
        Добавить элемент в кеш.

        Args:
            key: Ключ.
            value: Объект.
        """
        # Если кеш заполнен — удаляем наименее используемый
        if len(self._cache) >= self._max_size:
            self._evict_lru()

        self._cache[key] = value
        self._access_count[key] = 1

    def remove(self, key: str) -> bool:
        """
        Удалить элемент из кеша.

        Args:
            key: Ключ.

        Returns:
            True, если элемент был удалён.
        """
        if key in self._cache:
            del self._cache[key]
            self._access_count.pop(key, None)
            return True
        return False

    def clear(self) -> None:
        """Очистить кеш."""
        self._cache.clear()
        self._access_count.clear()

    def _evict_lru(self) -> None:
        """Удалить наименее используемый элемент."""
        if not self._access_count:
            return

        lru_key = min(self._access_count, key=lambda k: self._access_count[k])
        self.remove(lru_key)

    @property
    def size(self) -> int:
        """Размер кеша."""
        return len(self._cache)


# ============================================================================
# МЕНЕДЖЕР РЕСУРСОВ
# ============================================================================

class AssetManager:
    """
    Менеджер ресурсов клиента.

    Управляет всеми игровыми ресурсами: изображениями, звуками,
    стилями и шрифтами. Использует ленивую загрузку и кеширование.

    Usage:
        manager = AssetManager("assets")
        icon = manager.get_icon("properties/sivka_burka")
        pixmap = manager.get_pixmap("board/board_bg", 700, 700)
        stylesheet = manager.load_stylesheet("styles/main_style.qss")
    """

    # Директории ресурсов
    IMAGES_DIR: str = "images"
    SOUNDS_DIR: str = "sounds"
    STYLES_DIR: str = "styles"
    FONTS_DIR: str = "fonts"

    # Поддерживаемые форматы изображений
    IMAGE_EXTENSIONS: tuple[str, ...] = (".png", ".jpg", ".jpeg", ".svg", ".ico")

    def __init__(self, assets_dir: str = "assets") -> None:
        """
        Инициализация менеджера ресурсов.

        Args:
            assets_dir: Путь к директории assets/.
        """
        self._assets_dir: Path = Path(assets_dir)

        # Кеши для разных типов ресурсов
        self._icon_cache = AssetCache(max_size=100)
        self._pixmap_cache = AssetCache(max_size=100)
        self._stylesheet_cache: dict[str, str] = {}

        # Убеждаемся, что директории существуют
        self._ensure_directories()

    def _ensure_directories(self) -> None:
        """Создать директории ресурсов, если их нет."""
        for subdir in [self.IMAGES_DIR, self.SOUNDS_DIR, self.STYLES_DIR, self.FONTS_DIR]:
            (self._assets_dir / subdir).mkdir(parents=True, exist_ok=True)

    # ========================================================================
    # ИЗОБРАЖЕНИЯ
    # ========================================================================

    def get_icon(self, name: str) -> Optional[Any]:
        """
        Получить иконку (QIcon).

        Args:
            name: Имя файла без расширения (например, "properties/sivka_burka").

        Returns:
            QIcon или None.
        """
        cache_key = f"icon:{name}"

        cached = self._icon_cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            from PySide6.QtGui import QIcon

            path = self._find_image(name)
            if path is None:
                logger.warning("Иконка не найдена: %s", name)
                return None

            icon = QIcon(str(path))
            self._icon_cache.put(cache_key, icon)
            logger.debug("Загружена иконка: %s", name)
            return icon

        except ImportError:
            logger.warning("PySide6 не установлен — иконки недоступны")
            return None

    def get_pixmap(
        self,
        name: str,
        width: int = 0,
        height: int = 0,
    ) -> Optional[Any]:
        """
        Получить изображение (QPixmap).

        Args:
            name: Имя файла без расширения.
            width: Ширина (0 = оригинал).
            height: Высота (0 = оригинал).

        Returns:
            QPixmap или None.
        """
        cache_key = f"pixmap:{name}:{width}:{height}"

        cached = self._pixmap_cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            from PySide6.QtGui import QPixmap

            path = self._find_image(name)
            if path is None:
                logger.warning("Изображение не найдено: %s", name)
                return None

            pixmap = QPixmap(str(path))

            if width > 0 and height > 0:
                pixmap = pixmap.scaled(
                    width, height,
                    aspectMode=1,  # Qt.KeepAspectRatio
                    mode=1,         # Qt.SmoothTransformation
                )

            self._pixmap_cache.put(cache_key, pixmap)
            logger.debug("Загружено изображение: %s (%dx%d)", name, width, height)
            return pixmap

        except ImportError:
            logger.warning("PySide6 не установлен — изображения недоступны")
            return None

    def _find_image(self, name: str) -> Optional[Path]:
        """
        Найти файл изображения по имени.

        Args:
            name: Имя без расширения.

        Returns:
            Путь к файлу или None.
        """
        base_path = self._assets_dir / self.IMAGES_DIR / name

        # Пробуем разные расширения
        for ext in self.IMAGE_EXTENSIONS:
            path = Path(str(base_path) + ext)
            if path.exists():
                return path

        # Пробуем без поддиректории
        if "/" in name or "\\" in name:
            filename = Path(name).name
            for ext in self.IMAGE_EXTENSIONS:
                path = self._assets_dir / self.IMAGES_DIR / (filename + ext)
                if path.exists():
                    return path

        return None

    # ========================================================================
    # СТИЛИ (QSS)
    # ========================================================================

    def load_stylesheet(self, name: str) -> str:
        """
        Загрузить таблицу стилей (QSS).

        Args:
            name: Имя файла (например, "styles/main_style.qss").

        Returns:
            Строка со стилями (пустая, если файл не найден).
        """
        if name in self._stylesheet_cache:
            return self._stylesheet_cache[name]

        path = self._assets_dir / self.STYLES_DIR / Path(name).name
        if not path.exists():
            path = self._assets_dir / name

        if not path.exists():
            logger.warning("Файл стилей не найден: %s", name)
            return ""

        try:
            with open(path, "r", encoding="utf-8") as f:
                stylesheet = f.read()

            self._stylesheet_cache[name] = stylesheet
            logger.debug("Загружен stylesheet: %s", name)
            return stylesheet

        except OSError as e:
            logger.error("Ошибка загрузки стилей: %s", e)
            return ""

    # ========================================================================
    # ЗВУКИ (ЗАГЛУШКА)
    # ========================================================================

    def get_sound_path(self, name: str) -> Optional[Path]:
        """
        Получить путь к звуковому файлу.

        Args:
            name: Имя файла (например, "dice_roll.wav").

        Returns:
            Путь к файлу или None.
        """
        path = self._assets_dir / self.SOUNDS_DIR / name
        if path.exists():
            return path
        return None

    # ========================================================================
    # УПРАВЛЕНИЕ КЕШЕМ
    # ========================================================================

    def clear_cache(self) -> None:
        """Очистить все кеши."""
        self._icon_cache.clear()
        self._pixmap_cache.clear()
        self._stylesheet_cache.clear()
        logger.debug("Кеш ресурсов очищен")

    def get_cache_stats(self) -> dict[str, int]:
        """
        Получить статистику кеша.

        Returns:
            Словарь с размерами кешей.
        """
        return {
            "icons": self._icon_cache.size,
            "pixmaps": self._pixmap_cache.size,
            "stylesheets": len(self._stylesheet_cache),
        }

    # ========================================================================
    # ПРЕДЗАГРУЗКА
    # ========================================================================

    def preload_common(self) -> None:
        """
        Предзагрузить часто используемые ресурсы.

        Загружает основные иконки и изображения для ускорения работы.
        """
        common_resources = [
            "board/start",
            "board/jail",
            "board/free_parking",
            "board/go_to_jail",
            "dice/dice_1",
            "dice/dice_6",
            "tokens/player_red",
            "tokens/player_blue",
        ]

        for name in common_resources:
            self.get_pixmap(name, 60, 60)

        logger.info("Предзагружено %d ресурсов", len(common_resources))