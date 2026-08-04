from datetime import date

import pytest

from bot.db import Database
from bot.models import EntryStatus
from bot.repositories import WaitlistRepository


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
