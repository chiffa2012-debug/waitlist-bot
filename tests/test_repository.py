import sqlite3
from datetime import date

import pytest

from bot.db import Database
from bot.models import EntryStatus
from bot.repositories import WaitlistRepository


@pytest.mark.asyncio
async def test_past_entries_leave_the_active_list(tmp_path) -> None:
    database = Database(tmp_path / "waitlist.db")
    await database.connect()
    repository = WaitlistRepository(database)
    try:
        old = await repository.add("Анна", "+79991234567", date(2026, 7, 20), None, None)
        soon = await repository.add("Мария", "+79995556677", date(2026, 7, 25), None, None)
        today = date(2026, 7, 22)

        assert [item.id for item in await repository.list_active(not_before=today)] == [
            soon.id
        ]
        assert [item.id for item in await repository.list_expired(today)] == [old.id]
        # Без фильтра поведение прежнее: видны обе.
        assert len(await repository.list_active()) == 2
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_duplicate_is_found_regardless_of_phone_format(tmp_path) -> None:
    database = Database(tmp_path / "waitlist.db")
    await database.connect()
    repository = WaitlistRepository(database)
    day = date(2026, 7, 25)
    try:
        entry = await repository.add(
            "Анна", "+7 999 123-45-67", day, "15:00", None, service_id=456
        )

        found = await repository.find_active_duplicate("89991234567", day, 456)
        assert found is not None and found.id == entry.id

        # Другая дата, другая услуга и другой клиент дублями не считаются.
        assert await repository.find_active_duplicate(
            "89991234567", date(2026, 7, 26), 456
        ) is None
        assert await repository.find_active_duplicate("89991234567", day, 789) is None
        assert await repository.find_active_duplicate("89995556677", day, 456) is None

        # Закрытая заявка перестаёт быть дублем.
        await repository.set_status(entry.id, EntryStatus.BOOKED)
        assert await repository.find_active_duplicate("89991234567", day, 456) is None
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_service_and_staff_are_stored(tmp_path) -> None:
    database = Database(tmp_path / "waitlist.db")
    await database.connect()
    repository = WaitlistRepository(database)
    try:
        entry = await repository.add(
            "Анна",
            "+79991234567",
            date(2026, 7, 25),
            "15:00",
            None,
            service_id=456,
            service_title="Комбинированный маникюр",
            staff_id=77,
            staff_name="Юлия",
        )
        stored = await repository.get(entry.id)
        assert stored is not None
        assert (stored.service_id, stored.service_title) == (456, "Комбинированный маникюр")
        assert (stored.staff_id, stored.staff_name) == (77, "Юлия")
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_old_database_without_service_columns_is_migrated(tmp_path) -> None:
    path = tmp_path / "waitlist.db"
    legacy = sqlite3.connect(path)
    legacy.executescript(
        """
        CREATE TABLE waitlist_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_name TEXT NOT NULL,
            phone TEXT NOT NULL,
            desired_date TEXT NOT NULL,
            desired_time TEXT NULL,
            comment TEXT NULL,
            status TEXT NOT NULL DEFAULT 'waiting',
            last_notified_at TEXT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        INSERT INTO waitlist_entries (
            client_name, phone, desired_date, status, created_at, updated_at
        ) VALUES ('Старая заявка', '+79991234567', '2026-07-25', 'waiting',
                  '2026-07-22T10:00:00+00:00', '2026-07-22T10:00:00+00:00');
        """
    )
    legacy.commit()
    legacy.close()

    database = Database(path)
    await database.connect()
    try:
        entry = await WaitlistRepository(database).get(1)
        assert entry is not None
        assert entry.client_name == "Старая заявка"
        assert entry.service_id is None and entry.staff_name is None
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_entry_lifecycle(tmp_path) -> None:
    database = Database(tmp_path / "waitlist.db")
    await database.connect()
    repository = WaitlistRepository(database)
    try:
        entry = await repository.add(
            "Анна", "+79991234567", date(2026, 7, 25), "15:00", "к Марии"
        )
        assert entry.status == EntryStatus.WAITING
        assert [item.id for item in await repository.list_active()] == [entry.id]

        updated = await repository.set_status(entry.id, EntryStatus.BOOKED)
        assert updated is not None and updated.status == EntryStatus.BOOKED
        assert await repository.list_active() == []
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_first_admin_claim_is_stable(tmp_path) -> None:
    database = Database(tmp_path / "waitlist.db")
    await database.connect()
    repository = WaitlistRepository(database)
    try:
        assert await repository.claim_admin(111) == 111
        assert await repository.claim_admin(222) == 111
        assert await repository.is_owner(111)
        assert not await repository.is_admin(222)
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_owner_can_add_and_remove_other_admins(tmp_path) -> None:
    database = Database(tmp_path / "waitlist.db")
    await database.connect()
    repository = WaitlistRepository(database)
    try:
        await repository.claim_admin(111, username="owner", full_name="Владелец")
        assert await repository.add_admin(222, added_by=111)
        assert not await repository.add_admin(222, added_by=111)
        assert await repository.is_admin(222)
        assert await repository.list_admin_ids() == [111, 222]

        assert not await repository.remove_admin(111)
        assert await repository.remove_admin(222)
        assert not await repository.is_admin(222)
    finally:
        await database.close()
