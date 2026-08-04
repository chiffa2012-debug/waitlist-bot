from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from bot.utils import parse_desired_date, parse_desired_date_and_time


TIMEZONE = ZoneInfo("Europe/Amsterdam")
NOW = datetime(2026, 7, 22, 12, 0, tzinfo=TIMEZONE)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("22.07.2026", "2026-07-22"),
        ("2026-07-22", "2026-07-22"),
        ("сегодня", "2026-07-22"),
        ("завтра", "2026-07-23"),
    ],
)
def test_parse_desired_date(raw: str, expected: str) -> None:
    assert parse_desired_date(raw, TIMEZONE, NOW).isoformat() == expected


def test_parse_desired_date_rejects_unknown_format() -> None:
    with pytest.raises(ValueError):
        parse_desired_date("когда-нибудь летом", TIMEZONE, NOW)


@pytest.mark.parametrize(
    ("raw", "expected_date", "expected_time"),
    [
        ("на завтра", "2026-07-23", None),
        ("завтра в 16:00", "2026-07-23", "16:00"),
        ("16:00 завтра", "2026-07-23", "16:00"),
        ("на 25.07.2026 к 15:30", "2026-07-25", "15:30"),
        ("25 07 2026", "2026-07-25", None),
        ('завтра в 16 часов"', "2026-07-23", "16:00"),
        ("завтра в 16", "2026-07-23", "16:00"),
        ("завтра в 9 утра", "2026-07-23", "09:00"),
        ("завтра в 6 вечера", "2026-07-23", "18:00"),
        ("завтра 16 ч", "2026-07-23", "16:00"),
    ],
)
def test_parse_natural_date_and_time(
    raw: str, expected_date: str, expected_time: str | None
) -> None:
    parsed_date, parsed_time = parse_desired_date_and_time(raw, TIMEZONE, NOW)
    assert parsed_date.isoformat() == expected_date
    assert parsed_time == expected_time
