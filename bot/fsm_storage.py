from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from aiogram.fsm.state import State
from aiogram.fsm.storage.base import BaseStorage, StateType, StorageKey

from .db import Database


class SQLiteFSMStorage(BaseStorage):
    """Persistent aiogram FSM storage using the application's SQLite database."""

    def __init__(self, database: Database) -> None:
        self.database = database

    @staticmethod
    def _key(key: StorageKey) -> tuple[int, int, int, int, str, str]:
        return (
            key.bot_id,
            key.chat_id,
            key.user_id,
            key.thread_id or 0,
            key.business_connection_id or "",
            key.destiny,
        )

    async def set_state(self, key: StorageKey, state: StateType = None) -> None:
        connection = self.database.require_connection()
        state_value = state.state if isinstance(state, State) else state
        await connection.execute(
            """
            INSERT INTO fsm_storage (
                bot_id, chat_id, user_id, thread_id, business_connection_id,
                destiny, state, data_json, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, '{}', ?)
            ON CONFLICT (
                bot_id, chat_id, user_id, thread_id, business_connection_id, destiny
            ) DO UPDATE SET state = excluded.state, updated_at = excluded.updated_at
            """,
            (*self._key(key), state_value, datetime.now(timezone.utc).isoformat()),
        )
        await connection.commit()

    async def get_state(self, key: StorageKey) -> str | None:
        connection = self.database.require_connection()
        cursor = await connection.execute(
            """
            SELECT state FROM fsm_storage
            WHERE bot_id = ? AND chat_id = ? AND user_id = ? AND thread_id = ?
              AND business_connection_id = ? AND destiny = ?
            """,
            self._key(key),
        )
        row = await cursor.fetchone()
        return row["state"] if row else None

    async def set_data(self, key: StorageKey, data: Mapping[str, Any]) -> None:
        connection = self.database.require_connection()
        encoded = json.dumps(dict(data), ensure_ascii=False, separators=(",", ":"))
        await connection.execute(
            """
            INSERT INTO fsm_storage (
                bot_id, chat_id, user_id, thread_id, business_connection_id,
                destiny, state, data_json, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?)
            ON CONFLICT (
                bot_id, chat_id, user_id, thread_id, business_connection_id, destiny
            ) DO UPDATE SET data_json = excluded.data_json, updated_at = excluded.updated_at
            """,
            (*self._key(key), encoded, datetime.now(timezone.utc).isoformat()),
        )
        await connection.commit()

    async def get_data(self, key: StorageKey) -> dict[str, Any]:
        connection = self.database.require_connection()
        cursor = await connection.execute(
            """
            SELECT data_json FROM fsm_storage
            WHERE bot_id = ? AND chat_id = ? AND user_id = ? AND thread_id = ?
              AND business_connection_id = ? AND destiny = ?
            """,
            self._key(key),
        )
        row = await cursor.fetchone()
        if not row:
            return {}
        decoded = json.loads(row["data_json"])
        return decoded if isinstance(decoded, dict) else {}

    async def close(self) -> None:
        # The Database lifecycle is owned by bot.main.
        return None
