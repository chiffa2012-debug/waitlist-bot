from __future__ import annotations

from datetime import date, datetime, timezone

from .db import Database
from .models import ACTIVE_STATUSES, Admin, EntryStatus, WaitlistEntry


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _entry_from_row(row: object) -> WaitlistEntry:
    return WaitlistEntry(
        id=row["id"],
        client_name=row["client_name"],
        phone=row["phone"],
        desired_date=date.fromisoformat(row["desired_date"]),
        desired_time=row["desired_time"],
        comment=row["comment"],
        status=EntryStatus(row["status"]),
        last_notified_at=(
            datetime.fromisoformat(row["last_notified_at"])
            if row["last_notified_at"]
            else None
        ),
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


def _admin_from_row(row: object) -> Admin:
    return Admin(
        telegram_id=row["telegram_id"],
        is_owner=bool(row["is_owner"]),
        username=row["username"],
        full_name=row["full_name"],
        added_at=datetime.fromisoformat(row["added_at"]),
        added_by=row["added_by"],
    )


class WaitlistRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def add(
        self,
        client_name: str,
        phone: str,
        desired_date: date,
        desired_time: str | None,
        comment: str | None,
    ) -> WaitlistEntry:
        connection = self.database.require_connection()
        now = _utc_now().isoformat()
        cursor = await connection.execute(
            """
            INSERT INTO waitlist_entries (
                client_name, phone, desired_date, desired_time, comment,
                status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, 'waiting', ?, ?)
            """,
            (client_name, phone, desired_date.isoformat(), desired_time, comment, now, now),
        )
        await connection.commit()
        entry = await self.get(int(cursor.lastrowid))
        if entry is None:
            raise RuntimeError("Не удалось прочитать созданную заявку")
        return entry

    async def get(self, entry_id: int) -> WaitlistEntry | None:
        connection = self.database.require_connection()
        cursor = await connection.execute(
            "SELECT * FROM waitlist_entries WHERE id = ?", (entry_id,)
        )
        row = await cursor.fetchone()
        return _entry_from_row(row) if row else None

    async def list_active(self, desired_date: date | None = None) -> list[WaitlistEntry]:
        connection = self.database.require_connection()
        placeholders = ",".join("?" for _ in ACTIVE_STATUSES)
        parameters: list[object] = [status.value for status in ACTIVE_STATUSES]
        query = f"SELECT * FROM waitlist_entries WHERE status IN ({placeholders})"
        if desired_date is not None:
            query += " AND desired_date = ?"
            parameters.append(desired_date.isoformat())
        query += " ORDER BY desired_date, COALESCE(desired_time, '99:99'), created_at"
        cursor = await connection.execute(query, parameters)
        return [_entry_from_row(row) for row in await cursor.fetchall()]

    async def set_status(self, entry_id: int, status: EntryStatus) -> WaitlistEntry | None:
        connection = self.database.require_connection()
        await connection.execute(
            "UPDATE waitlist_entries SET status = ?, updated_at = ? WHERE id = ?",
            (status.value, _utc_now().isoformat(), entry_id),
        )
        await connection.commit()
        return await self.get(entry_id)

    async def mark_notified(self, entry_id: int, notified_at: datetime) -> WaitlistEntry | None:
        connection = self.database.require_connection()
        timestamp = notified_at.astimezone(timezone.utc).isoformat()
        await connection.execute(
            """
            UPDATE waitlist_entries
            SET status = 'notified', last_notified_at = ?, updated_at = ?
            WHERE id = ? AND status IN ('waiting', 'notified')
            """,
            (timestamp, timestamp, entry_id),
        )
        await connection.commit()
        return await self.get(entry_id)

    async def get_claimed_admin_id(self) -> int | None:
        connection = self.database.require_connection()
        cursor = await connection.execute(
            "SELECT telegram_id FROM admins WHERE is_owner = 1 LIMIT 1"
        )
        row = await cursor.fetchone()
        return int(row["telegram_id"]) if row else None

    async def claim_admin(
        self,
        telegram_id: int,
        username: str | None = None,
        full_name: str | None = None,
    ) -> int:
        connection = self.database.require_connection()
        now = _utc_now().isoformat()
        await connection.execute(
            """
            INSERT OR IGNORE INTO admins (
                telegram_id, is_owner, username, full_name, added_at, added_by
            )
            SELECT ?, 1, ?, ?, ?, NULL
            WHERE NOT EXISTS (SELECT 1 FROM admins WHERE is_owner = 1)
            """,
            (telegram_id, username, full_name, now),
        )
        owner_id = await self.get_claimed_admin_id()
        if owner_id == telegram_id:
            await connection.execute(
                """
                UPDATE admins SET username = ?, full_name = ?
                WHERE telegram_id = ?
                """,
                (username, full_name, telegram_id),
            )
        await connection.execute(
            "INSERT OR REPLACE INTO settings(key, value) VALUES ('admin_telegram_id', ?)",
            (str(owner_id or telegram_id),),
        )
        await connection.commit()
        claimed = await self.get_claimed_admin_id()
        if claimed is None:
            raise RuntimeError("Не удалось сохранить администратора")
        return claimed

    async def ensure_configured_admin(self, telegram_id: int) -> None:
        connection = self.database.require_connection()
        owner_id = await self.get_claimed_admin_id()
        if owner_id is None:
            await self.claim_admin(telegram_id)
            return
        await connection.execute(
            """
            INSERT OR IGNORE INTO admins (
                telegram_id, is_owner, added_at, added_by
            ) VALUES (?, 0, ?, ?)
            """,
            (telegram_id, _utc_now().isoformat(), owner_id),
        )
        await connection.commit()

    async def is_admin(self, telegram_id: int) -> bool:
        connection = self.database.require_connection()
        cursor = await connection.execute(
            "SELECT 1 FROM admins WHERE telegram_id = ?", (telegram_id,)
        )
        return await cursor.fetchone() is not None

    async def is_owner(self, telegram_id: int) -> bool:
        connection = self.database.require_connection()
        cursor = await connection.execute(
            "SELECT is_owner FROM admins WHERE telegram_id = ?", (telegram_id,)
        )
        row = await cursor.fetchone()
        return bool(row and row["is_owner"])

    async def list_admins(self) -> list[Admin]:
        connection = self.database.require_connection()
        cursor = await connection.execute(
            "SELECT * FROM admins ORDER BY is_owner DESC, added_at, telegram_id"
        )
        return [_admin_from_row(row) for row in await cursor.fetchall()]

    async def list_admin_ids(self) -> list[int]:
        return [admin.telegram_id for admin in await self.list_admins()]

    async def add_admin(self, telegram_id: int, added_by: int) -> bool:
        connection = self.database.require_connection()
        cursor = await connection.execute(
            """
            INSERT OR IGNORE INTO admins (
                telegram_id, is_owner, added_at, added_by
            ) VALUES (?, 0, ?, ?)
            """,
            (telegram_id, _utc_now().isoformat(), added_by),
        )
        await connection.commit()
        return cursor.rowcount > 0

    async def remove_admin(self, telegram_id: int) -> bool:
        connection = self.database.require_connection()
        cursor = await connection.execute(
            "DELETE FROM admins WHERE telegram_id = ? AND is_owner = 0",
            (telegram_id,),
        )
        await connection.commit()
        return cursor.rowcount > 0

    async def update_admin_identity(
        self, telegram_id: int, username: str | None, full_name: str | None
    ) -> None:
        connection = self.database.require_connection()
        await connection.execute(
            """
            UPDATE admins SET username = ?, full_name = ?
            WHERE telegram_id = ?
            """,
            (username, full_name, telegram_id),
        )
        await connection.commit()
