"""
server/backup/backup_manager.py

Менеджер резервного копирования.

Обеспечивает:
- Создание резервных копий базы данных
- Ротацию старых бэкапов
- Восстановление из бэкапа
- Экспорт конфигураций и логов

Python: 3.13+
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from shared.env_config import EnvConfig

logger = logging.getLogger("billionaire.server")


# ============================================================================
# МЕНЕДЖЕР РЕЗЕРВНОГО КОПИРОВАНИЯ
# ============================================================================

class BackupManager:
    """
    Менеджер резервного копирования.

    Создаёт и управляет резервными копиями БД, конфигураций и логов.
    Поддерживает автоматическую ротацию старых бэкапов.

    Usage:
        manager = BackupManager(env_config)
        path = await manager.create_backup()
        await manager.restore_backup(path)
    """

    def __init__(
        self,
        env_config: EnvConfig,
        backup_dir: str = "backups",
        retention_days: int = 30,
        max_backups: int = 100,
    ) -> None:
        """
        Инициализация менеджера бэкапов.

        Args:
            env_config: Конфигурация окружения.
            backup_dir: Директория для хранения бэкапов.
            retention_days: Срок хранения бэкапов в днях.
            max_backups: Максимальное количество бэкапов.
        """
        self._env_config = env_config
        self._backup_dir: Path = Path(backup_dir)
        self._retention_days: int = retention_days
        self._max_backups: int = max_backups

        # Создаём директорию
        self._backup_dir.mkdir(parents=True, exist_ok=True)

    # ========================================================================
    # СОЗДАНИЕ БЭКАПА
    # ========================================================================

    async def create_backup(
        self,
        backup_type: str = "full",
        include_logs: bool = False,
    ) -> Optional[str]:
        """
        Создать резервную копию.

        Args:
            backup_type: Тип бэкапа ("full", "database", "configs").
            include_logs: Включить ли логи в бэкап.

        Returns:
            Путь к созданному бэкапу или None при ошибке.
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_name = f"backup_{backup_type}_{timestamp}_{str(uuid4())[:8]}"
        backup_path = self._backup_dir / backup_name
        backup_path.mkdir(parents=True, exist_ok=True)

        logger.info(
            "Создание бэкапа: %s (тип: %s)",
            backup_name,
            backup_type,
        )

        try:
            if backup_type in ("full", "database"):
                await self._backup_database(backup_path)

            if backup_type in ("full", "configs"):
                await self._backup_configs(backup_path)

            if include_logs:
                await self._backup_logs(backup_path)

            # Создаём метаданные
            self._create_metadata(backup_path, backup_type)

            # Архивируем
            archive_path = await self._create_archive(backup_path)

            # Удаляем временную директорию
            shutil.rmtree(backup_path, ignore_errors=True)

            logger.info(
                "Бэкап создан: %s (размер: %s)",
                archive_path,
                self._format_size(os.path.getsize(archive_path)),
            )

            # Запускаем ротацию
            await self._rotate_backups()

            return str(archive_path)

        except Exception as e:
            logger.error("Ошибка создания бэкапа: %s", e)
            # Удаляем незавершённый бэкап
            shutil.rmtree(backup_path, ignore_errors=True)
            return None

    async def _backup_database(self, backup_path: Path) -> None:
        """
        Создать дамп базы данных.

        Args:
            backup_path: Путь для сохранения.
        """
        db_name = self._env_config.DB_NAME
        db_user = self._env_config.DB_USER
        db_host = self._env_config.DB_HOST
        db_port = self._env_config.DB_PORT

        dump_file = backup_path / "database.sql"

        # Используем pg_dump
        env = os.environ.copy()
        env["PGPASSWORD"] = self._env_config.DB_PASSWORD

        cmd = [
            "pg_dump",
            "-h", db_host,
            "-p", str(db_port),
            "-U", db_user,
            "-d", db_name,
            "-f", str(dump_file),
            "--no-owner",
            "--no-acl",
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        _, stderr = await process.communicate()

        if process.returncode != 0:
            error_msg = stderr.decode("utf-8", errors="replace")
            raise RuntimeError(f"Ошибка pg_dump: {error_msg}")

        logger.debug("Дамп БД создан: %s", dump_file)

    async def _backup_configs(self, backup_path: Path) -> None:
        """
        Скопировать конфигурационные файлы.

        Args:
            backup_path: Путь для сохранения.
        """
        configs_dir = Path("configs")
        if configs_dir.exists():
            dest = backup_path / "configs"
            shutil.copytree(configs_dir, dest, ignore=shutil.ignore_patterns("*.pyc", "__pycache__"))
            logger.debug("Конфигурации скопированы")

    async def _backup_logs(self, backup_path: Path) -> None:
        """
        Скопировать логи.

        Args:
            backup_path: Путь для сохранения.
        """
        logs_dir = Path("logs")
        if logs_dir.exists():
            dest = backup_path / "logs"
            shutil.copytree(logs_dir, dest, ignore=shutil.ignore_patterns("*.pyc"))
            logger.debug("Логи скопированы")

    def _create_metadata(self, backup_path: Path, backup_type: str) -> None:
        """
        Создать файл метаданных бэкапа.

        Args:
            backup_path: Путь к бэкапу.
            backup_type: Тип бэкапа.
        """
        import json

        metadata = {
            "backup_type": backup_type,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "database": self._env_config.DB_NAME,
            "version": "1.0.0",
        }

        meta_file = backup_path / "metadata.json"
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)

    async def _create_archive(self, source_path: Path) -> Path:
        """
        Создать архив бэкапа.

        Args:
            source_path: Исходная директория.

        Returns:
            Путь к архиву.
        """
        archive_path = Path(str(source_path) + ".tar.gz")

        cmd = [
            "tar",
            "-czf",
            str(archive_path),
            "-C", str(source_path.parent),
            source_path.name,
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        await process.communicate()

        return archive_path

    # ========================================================================
    # ВОССТАНОВЛЕНИЕ
    # ========================================================================

    async def restore_backup(self, backup_path: str) -> bool:
        """
        Восстановить из резервной копии.

        Args:
            backup_path: Путь к файлу бэкапа (.tar.gz).

        Returns:
            True, если восстановление выполнено.
        """
        logger.info("Восстановление из бэкапа: %s", backup_path)

        archive = Path(backup_path)
        if not archive.exists():
            logger.error("Файл бэкапа не найден: %s", backup_path)
            return False

        # Распаковываем
        extract_dir = self._backup_dir / "restore_temp"
        extract_dir.mkdir(parents=True, exist_ok=True)

        try:
            cmd = ["tar", "-xzf", str(archive), "-C", str(extract_dir)]
            process = await asyncio.create_subprocess_exec(*cmd)
            await process.communicate()

            # Находим распакованную директорию
            extracted = list(extract_dir.iterdir())
            if not extracted:
                logger.error("Архив пуст")
                return False

            restore_source = extracted[0]

            # Восстанавливаем БД
            sql_file = restore_source / "database.sql"
            if sql_file.exists():
                await self._restore_database(sql_file)

            # Восстанавливаем конфиги
            configs_dir = restore_source / "configs"
            if configs_dir.exists():
                shutil.rmtree("configs", ignore_errors=True)
                shutil.copytree(configs_dir, "configs")

            logger.info("Восстановление из бэкапа завершено")
            return True

        except Exception as e:
            logger.error("Ошибка восстановления: %s", e)
            return False
        finally:
            shutil.rmtree(extract_dir, ignore_errors=True)

    async def _restore_database(self, sql_file: Path) -> None:
        """
        Восстановить базу данных из SQL-дампа.

        Args:
            sql_file: Путь к SQL-файлу.
        """
        db_name = self._env_config.DB_NAME
        db_user = self._env_config.DB_USER
        db_host = self._env_config.DB_HOST
        db_port = self._env_config.DB_PORT

        env = os.environ.copy()
        env["PGPASSWORD"] = self._env_config.DB_PASSWORD

        cmd = [
            "psql",
            "-h", db_host,
            "-p", str(db_port),
            "-U", db_user,
            "-d", db_name,
            "-f", str(sql_file),
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        _, stderr = await process.communicate()

        if process.returncode != 0:
            error_msg = stderr.decode("utf-8", errors="replace")
            raise RuntimeError(f"Ошибка восстановления БД: {error_msg}")

        logger.info("База данных восстановлена")

    # ========================================================================
    # РОТАЦИЯ
    # ========================================================================

    async def _rotate_backups(self) -> None:
        """
        Выполнить ротацию старых бэкапов.

        Удаляет бэкапы старше retention_days и при превышении max_backups.
        """
        backups = sorted(
            self._backup_dir.glob("backup_*.tar.gz"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

        cutoff_time = time.time() - (self._retention_days * 86400)
        deleted = 0

        for backup in backups:
            # Удаляем по возрасту
            if backup.stat().st_mtime < cutoff_time:
                backup.unlink()
                deleted += 1
                continue

            # Удаляем лишние сверх лимита
            if len(backups) - deleted > self._max_backups:
                backup.unlink()
                deleted += 1

        if deleted > 0:
            logger.info("Ротация бэкапов: удалено %d старых файлов", deleted)

    # ========================================================================
    # ИНФОРМАЦИЯ
    # ========================================================================

    def list_backups(self) -> list[dict[str, Any]]:
        """
        Получить список всех бэкапов.

        Returns:
            Список словарей с информацией о бэкапах.
        """
        backups = sorted(
            self._backup_dir.glob("backup_*.tar.gz"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

        result: list[dict[str, Any]] = []
        for backup in backups:
            stat = backup.stat()
            result.append({
                "filename": backup.name,
                "path": str(backup),
                "size": stat.st_size,
                "size_formatted": self._format_size(stat.st_size),
                "created_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                "age_days": (time.time() - stat.st_mtime) / 86400,
            })

        return result

    def get_backup_count(self) -> int:
        """
        Получить количество бэкапов.

        Returns:
            Количество файлов бэкапов.
        """
        return len(list(self._backup_dir.glob("backup_*.tar.gz")))

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        """
        Форматировать размер в читаемый вид.

        Args:
            size_bytes: Размер в байтах.

        Returns:
            Строка (например, "1.5 MB").
        """
        for unit in ["B", "KB", "MB", "GB"]:
            if size_bytes < 1024:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f} TB"

    def get_stats(self) -> dict:
        """
        Получить статистику менеджера бэкапов.

        Returns:
            Словарь с метриками.
        """
        return {
            "backup_dir": str(self._backup_dir.absolute()),
            "backup_count": self.get_backup_count(),
            "retention_days": self._retention_days,
            "max_backups": self._max_backups,
        }