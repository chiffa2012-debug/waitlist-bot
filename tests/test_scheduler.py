from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from bot.models import WaitlistEntry, EntryStatus
from bot.scheduler import WaitlistChecker, drop_past_slots, slots_near_desired_time
from tests.test_yclients_client import build_settings


TIMEZONE = ZoneInfo("Europe/Amsterdam")


def build_entry(entry_id: int, desired_time: str | None = None, **overrides) -> WaitlistEntry:
    values = dict(
        id=entry_id,
        client_name="Анна",
        phone="+79991234567",
        desired_date=date(2026, 7, 25),
        desired_time=desired_time,
        comment=None,
        service_id=456,
        service_title="Комбинированный маникюр",
        staff_id=None,
        staff_name=None,
        status=EntryStatus.WAITING,
        last_notified_at=None,
        created_at=datetime(2026, 7, 22, 10, 0),
        updated_at=datetime(2026, 7, 22, 10, 0),
    )
    values.update(overrides)
    return WaitlistEntry(**values)


class FakeYclients:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def get_available_slots(self, desired_date, service_id=None, staff_id=None):
        self.calls.append((desired_date, service_id, staff_id))
        return ["10:00", "16:30", "19:00"]


def test_past_slots_are_dropped_only_for_today() -> None:
    now = datetime(2026, 7, 25, 16, 0, tzinfo=TIMEZONE)
    assert drop_past_slots(["10:00", "16:30"], date(2026, 7, 25), now) == ["16:30"]
    assert drop_past_slots(["10:00", "16:30"], date(2026, 7, 26), now) == [
        "10:00",
        "16:30",
    ]


def test_slots_are_limited_to_desired_time_window() -> None:
    slots = ["10:00", "16:30", "19:00"]
    assert slots_near_desired_time(slots, "16:00", tolerance_hours=3) == ["16:30", "19:00"]
    assert slots_near_desired_time(slots, "16:00", tolerance_hours=1) == ["16:30"]
    # Без желаемого времени и с выключенным допуском ничего не отсекаем.
    assert slots_near_desired_time(slots, None, tolerance_hours=3) == slots
    assert slots_near_desired_time(slots, "16:00", tolerance_hours=0) == [
        "16:30",
        "19:00",
        "10:00",
    ]


@pytest.mark.asyncio
async def test_same_service_date_and_staff_share_one_request(tmp_path) -> None:
    yclients = FakeYclients()
    checker = WaitlistChecker(build_settings(tmp_path), repository=None, yclients=yclients, bot=None)
    cache: dict = {}

    await checker._fetch_slots(build_entry(1), cache)
    await checker._fetch_slots(build_entry(2), cache)
    await checker._fetch_slots(build_entry(3, staff_id=77), cache)

    assert len(yclients.calls) == 2  # третья заявка отличается мастером
