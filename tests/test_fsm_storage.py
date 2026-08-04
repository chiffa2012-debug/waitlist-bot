from aiogram.fsm.storage.base import StorageKey
import pytest

from bot.db import Database
from bot.fsm_storage import SQLiteFSMStorage


@pytest.mark.asyncio
async def test_fsm_state_survives_storage_recreation(tmp_path) -> None:
    database = Database(tmp_path / "waitlist.db")
    await database.connect()
    key = StorageKey(bot_id=1, chat_id=2, user_id=3)
    first = SQLiteFSMStorage(database)
    try:
        await first.set_state(key, "AddEntry:desired_date")
        await first.set_data(key, {"client_name": "Анна", "phone": "+79991234567"})

        second = SQLiteFSMStorage(database)
        assert await second.get_state(key) == "AddEntry:desired_date"
        assert await second.get_data(key) == {
            "client_name": "Анна",
            "phone": "+79991234567",
        }
    finally:
        await database.close()
