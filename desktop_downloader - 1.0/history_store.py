from __future__ import annotations

import os
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class DownloadRecord:
    id: int
    url: str
    status: str
    progress: str
    details: str
    destination: str
    created_at: str


class DownloadHistory:
    def __init__(self, database_path: Path | None = None) -> None:
        if database_path is None:
            data_root = (
                os.environ.get("LOCALAPPDATA")
                or os.environ.get("XDG_DATA_HOME")
                or str(Path.home() / ".local" / "share")
            )
            database_path = Path(data_root) / "SmartDownloader" / "history.sqlite3"
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS downloads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT NOT NULL,
                    status TEXT NOT NULL,
                    progress TEXT NOT NULL DEFAULT '—',
                    details TEXT NOT NULL DEFAULT '',
                    destination TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.commit()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def add(self, url: str, status: str, destination: str) -> int:
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        with closing(self._connect()) as connection:
            cursor = connection.execute(
                """
                INSERT INTO downloads (url, status, destination, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (url, status, destination, now, now),
            )
            connection.commit()
            return int(cursor.lastrowid)

    def update(
        self,
        record_id: int,
        status: str,
        progress: str,
        details: str,
        destination: str,
    ) -> None:
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        with closing(self._connect()) as connection:
            connection.execute(
                """
                UPDATE downloads
                SET status = ?, progress = ?, details = ?, destination = ?, updated_at = ?
                WHERE id = ?
                """,
                (status, progress, details, destination, now, record_id),
            )
            connection.commit()

    def list_records(self) -> list[DownloadRecord]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT id, url, status, progress, details, destination, created_at
                FROM downloads ORDER BY id DESC
                """
            ).fetchall()
        return [DownloadRecord(**dict(row)) for row in rows]

    def mark_unfinished_interrupted(self) -> None:
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        with closing(self._connect()) as connection:
            connection.execute(
                """
                UPDATE downloads
                SET status = 'Interrupted', updated_at = ?
                WHERE status NOT IN ('Complete', 'Failed', 'Cancelled', 'Interrupted')
                """,
                (now,),
            )
            connection.commit()

    def delete(self, record_id: int) -> None:
        with closing(self._connect()) as connection:
            connection.execute("DELETE FROM downloads WHERE id = ?", (record_id,))
            connection.commit()
