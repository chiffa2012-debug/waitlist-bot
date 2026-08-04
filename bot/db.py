from __future__ import annotations

from pathlib import Path

import aiosqlite


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS waitlist_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_name TEXT NOT NULL,
    phone TEXT NOT NULL,
    desired_date TEXT NOT NULL,
    desired_time TEXT NULL,
    comment TEXT NULL,
    status TEXT NOT NULL DEFAULT 'waiting'
        CHECK (status IN ('waiting', 'notified', 'booked', 'deleted')),
    last_notified_at TEXT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_waitlist_active_date
ON waitlist_entries(status, desired_date);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS admins (
    telegram_id INTEGER PRIMARY KEY,
    is_owner INTEGER NOT NULL DEFAULT 0 CHECK (is_owner IN (0, 1)),
    username TEXT NULL,
    full_name TEXT NULL,
    added_at TEXT NOT NULL,
    added_by INTEGER NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_admins_single_owner
ON admins(is_owner) WHERE is_owner = 1;

CREATE TABLE IF NOT EXISTS fsm_storage (
    bot_id INTEGER NOT NULL,
    chat_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    thread_id INTEGER NOT NULL DEFAULT 0,
    business_connection_id TEXT NOT NULL DEFAULT '',
    destiny TEXT NOT NULL DEFAULT 'default',
    state TEXT NULL,
    data_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL,
    PRIMARY KEY (
        bot_id, chat_id, user_id, thread_id, business_connection_id, destiny
    )
);
"""


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.connection: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = await aiosqlite.connect(self.path)
        self.connection.row_factory = aiosqlite.Row
        await self.connection.executescript(SCHEMA)
        await self.connection.execute(
            """
            INSERT OR IGNORE INTO admins (
                telegram_id, is_owner, added_at, added_by
            )
            SELECT CAST(value AS INTEGER), 1, datetime('now'), NULL
            FROM settings
            WHERE key = 'admin_telegram_id'
              AND value GLOB '[0-9]*'
              AND NOT EXISTS (SELECT 1 FROM admins WHERE is_owner = 1)
            """
        )
        await self.connection.commit()

    async def close(self) -> None:
        if self.connection is not None:
            await self.connection.close()
            self.connection = None

    def require_connection(self) -> aiosqlite.Connection:
        if self.connection is None:
            raise RuntimeError("База данных не подключена")
        return self.connection
