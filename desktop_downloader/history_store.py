from __future__ import annotations

import os
import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit


@dataclass(frozen=True)
class DownloadRecord:
    id: int
    url: str
    status: str
    progress: str
    details: str
    destination: str
    created_at: str
    hidden: bool
    options: dict = field(default_factory=dict)


def normalize_url(url: str) -> str:
    parsed = urlsplit(url.strip())
    scheme = parsed.scheme.lower()
    hostname = (parsed.hostname or "").lower()
    try:
        port = parsed.port
    except ValueError:
        return url.strip().casefold()
    if port and not (scheme == "http" and port == 80) and not (scheme == "https" and port == 443):
        hostname = f"{hostname}:{port}"
    return parsed._replace(scheme=scheme, netloc=hostname, fragment="").geturl()


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
                    updated_at TEXT NOT NULL,
                    hidden INTEGER NOT NULL DEFAULT 0,
                    options_json TEXT NOT NULL DEFAULT '{}'
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(downloads)")
            }
            if "hidden" not in columns:
                connection.execute(
                    "ALTER TABLE downloads ADD COLUMN hidden INTEGER NOT NULL DEFAULT 0"
                )
            if "options_json" not in columns:
                connection.execute(
                    "ALTER TABLE downloads ADD COLUMN options_json TEXT NOT NULL DEFAULT '{}'"
                )
            connection.commit()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def add(
        self,
        url: str,
        status: str,
        destination: str,
        options: dict | None = None,
    ) -> int:
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        with closing(self._connect()) as connection:
            cursor = connection.execute(
                """
                INSERT INTO downloads
                    (url, status, destination, created_at, updated_at, options_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (url, status, destination, now, now, json.dumps(options or {})),
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
        options: dict | None = None,
    ) -> None:
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        with closing(self._connect()) as connection:
            connection.execute(
                """
                UPDATE downloads
                SET status = ?, progress = ?, details = ?, destination = ?,
                    updated_at = ?,
                    options_json = COALESCE(?, options_json)
                WHERE id = ?
                """,
                (
                    status,
                    progress,
                    details,
                    destination,
                    now,
                    json.dumps(options) if options is not None else None,
                    record_id,
                ),
            )
            connection.commit()

    def list_records(self, include_hidden: bool = False) -> list[DownloadRecord]:
        where_clause = "" if include_hidden else "WHERE hidden = 0"
        with closing(self._connect()) as connection:
            rows = connection.execute(
                f"""
                SELECT id, url, status, progress, details, destination, created_at,
                    hidden, options_json
                FROM downloads {where_clause} ORDER BY id DESC
                """
            ).fetchall()
        return [self._record_from_row(row) for row in rows]

    def find_by_url(self, url: str) -> DownloadRecord | None:
        normalized = normalize_url(url)
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT id, url, status, progress, details, destination, created_at,
                    hidden, options_json
                FROM downloads
                WHERE status = 'Complete'
                ORDER BY id DESC
                """
            ).fetchall()
        for row in rows:
            if normalize_url(row["url"]) == normalized:
                return self._record_from_row(row)
        return None

    @staticmethod
    def _record_from_row(row: sqlite3.Row) -> DownloadRecord:
        values = dict(row)
        try:
            options = json.loads(values.pop("options_json", "{}"))
        except json.JSONDecodeError as error:
            raise sqlite3.DatabaseError(
                f"Invalid saved options for download {values.get('id')}: {error}"
            ) from error
        if not isinstance(options, dict):
            raise sqlite3.DatabaseError(
                f"Saved options for download {values.get('id')} must be a JSON object."
            )
        values["hidden"] = bool(values["hidden"])
        values["options"] = options
        return DownloadRecord(**values)

    def get_setting(self, key: str, default: str = "") -> str:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT value FROM settings WHERE key = ?",
                (key,),
            ).fetchone()
        return row["value"] if row is not None else default

    def set_setting(self, key: str, value: str) -> None:
        with closing(self._connect()) as connection:
            connection.execute(
                """
                INSERT INTO settings (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, value),
            )
            connection.commit()

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

    def set_hidden(self, record_id: int, hidden: bool) -> None:
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        with closing(self._connect()) as connection:
            connection.execute(
                "UPDATE downloads SET hidden = ?, updated_at = ? WHERE id = ?",
                (int(hidden), now, record_id),
            )
            connection.commit()

    def delete(self, record_id: int) -> None:
        self.set_hidden(record_id, True)
