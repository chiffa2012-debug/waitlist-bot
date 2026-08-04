from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from bot.models import WaitlistEntry, EntryStatus
from bot.scheduler import (
    WaitlistChecker,
    dates_to_check,
    drop_past_slots,
    slots_near_desired_time,
)
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
    def __init__(self, slots_by_date: dict[str, list[str]] | None = None) -> None:
        self.calls: list[tuple] = []
        self.slots_by_date = slots_by_date
        self.default = ["10:00", "16:30", "19:00"]

    async def get_available_slots(self, desired_date, service_id=None, staff_id=None):
        self.calls.append((desired_date, service_id, staff_id))
        if self.slots_by_date is None:
            return self.default
        return self.slots_by_date.get(desired_date, [])


class FakeRepository:
    def __init__(self) -> None:
        self.notified: list[int] = []

    async def list_admin_ids(self) -> list[int]:
        return [111]

    async def mark_notified(self, entry_id: int, when) -> None:
        self.notified.append(entry_id)


class FakeBot:
    def __init__(self) -> None:
        self.messages: list[str] = []

    async def send_message(self, chat_id, text, reply_markup=None) -> None:
        self.messages.append(text)


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


def test_dates_to_check_covers_days_before_the_desired_one() -> None:
    today = date(2026, 7, 22)
    assert dates_to_check(date(2026, 7, 25), today, early_days=7) == [
        date(2026, 7, 22),
        date(2026, 7, 23),
        date(2026, 7, 24),
        date(2026, 7, 25),
    ]
    # Далёкая дата обрезается окном early_days, прошлое не проверяется.
    assert dates_to_check(date(2026, 8, 30), today, early_days=2) == [
        date(2026, 8, 28),
        date(2026, 8, 29),
        date(2026, 8, 30),
    ]
    assert dates_to_check(date(2026, 7, 25), today, early_days=0) == [date(2026, 7, 25)]
    assert dates_to_check(today, today, early_days=7) == [today]


@pytest.mark.asyncio
async def test_same_service_date_and_staff_share_one_request(tmp_path) -> None:
    yclients = FakeYclients()
    checker = WaitlistChecker(build_settings(tmp_path), repository=None, yclients=yclients, bot=None)
    cache: dict = {}

    await checker._fetch_slots(build_entry(1), cache=cache)
    await checker._fetch_slots(build_entry(2), cache=cache)
    await checker._fetch_slots(build_entry(3, staff_id=77), cache=cache)

    assert len(yclients.calls) == 2  # третья заявка отличается мастером


@pytest.mark.asyncio
async def test_earlier_window_triggers_notification(tmp_path) -> None:
    today = datetime.now(build_settings(tmp_path).timezone).date()
    desired = today + timedelta(days=3)
    earlier = today + timedelta(days=1)
    yclients = FakeYclients({earlier.isoformat(): ["16:30"]})
    repository = FakeRepository()
    bot = FakeBot()
    checker = WaitlistChecker(build_settings(tmp_path), repository, yclients, bot)

    result = await checker.check_entry(build_entry(1, "16:00", desired_date=desired))

    assert result.notification_sent
    assert result.slots == []  # на саму желаемую дату окон нет
    assert result.early_slots == [f"{earlier.strftime('%d.%m')} 16:30"]
    assert "Освободилось раньше" in bot.messages[0]
    assert repository.notified == [1]


@pytest.mark.asyncio
async def test_no_windows_means_no_message(tmp_path) -> None:
    today = datetime.now(build_settings(tmp_path).timezone).date()
    bot = FakeBot()
    checker = WaitlistChecker(build_settings(tmp_path), FakeRepository(), FakeYclients({}), bot)

    result = await checker.check_entry(build_entry(1, desired_date=today + timedelta(days=3)))

    assert not result.notification_sent
    assert bot.messages == []
