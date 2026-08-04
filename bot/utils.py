from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from .models import EntryStatus, WaitlistEntry


DATE_FORMATS = ("%d.%m.%Y", "%Y-%m-%d")
STATUS_LABELS = {
    EntryStatus.WAITING: "ожидает",
    EntryStatus.NOTIFIED: "уведомлён",
    EntryStatus.BOOKED: "записан",
    EntryStatus.DELETED: "удалён",
}


def extract_natural_time(value: str) -> str | None:
    normalized = value.strip().lower().replace("ё", "е")
    exact = re.search(r"(?<!\d)([01]\d|2[0-3]):([0-5]\d)(?!\d)", normalized)
    if exact:
        return exact.group(0)

    word_time = re.search(
        r"(?<!\d)([01]?\d|2[0-3])\s*"
        r"(?:час(?:а|ов)?|ч\.?)\s*(утра|дня|вечера|ночи)?",
        normalized,
    )
    short_time = re.search(
        r"\bв\s+([01]?\d|2[0-3])(?:\s*(утра|дня|вечера|ночи))?\b",
        normalized,
    )
    match = word_time or short_time
    if not match:
        return None
    hour = int(match.group(1))
    period = match.group(2)
    if period in {"дня", "вечера"} and hour < 12:
        hour += 12
    elif period == "ночи" and hour == 12:
        hour = 0
    return f"{hour:02d}:00"


def parse_desired_date(value: str, timezone: ZoneInfo, now: datetime | None = None) -> date:
    parsed_date, _ = parse_desired_date_and_time(value, timezone, now)
    return parsed_date


def parse_desired_date_and_time(
    value: str, timezone: ZoneInfo, now: datetime | None = None
) -> tuple[date, str | None]:
    normalized = value.strip().lower()
    today = (now or datetime.now(timezone)).astimezone(timezone).date()
    desired_time = extract_natural_time(normalized)

    if re.search(r"\bсегодня\b", normalized):
        return today, desired_time
    if re.search(r"\bзавтра\b", normalized):
        return today + timedelta(days=1), desired_time

    candidates: list[tuple[str, str]] = []
    iso_match = re.search(r"\b\d{4}-\d{1,2}-\d{1,2}\b", normalized)
    if iso_match:
        candidates.append((iso_match.group(0), "%Y-%m-%d"))
    local_match = re.search(
        r"(?<!\d)(\d{1,2})[.\-/\s]+(\d{1,2})[.\-/\s]+(\d{2,4})(?!\d)",
        normalized,
    )
    if local_match:
        day, month, year = local_match.groups()
        date_format = "%d.%m.%y" if len(year) == 2 else "%d.%m.%Y"
        candidates.append((f"{day}.{month}.{year}", date_format))

    for candidate, date_format in candidates:
        try:
            return datetime.strptime(candidate, date_format).date(), desired_time
        except ValueError:
            continue
    raise ValueError(
        "Напишите дату, например: «на завтра», «завтра в 16:00», "
        "22.07.2026 или 2026-07-22."
    )


def is_valid_phone(value: str) -> bool:
    return len(re.sub(r"\D", "", value)) >= 7


def normalize_optional(value: str) -> str | None:
    cleaned = value.strip()
    return cleaned or None


def parse_time(value: str) -> str:
    cleaned = value.strip()
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", cleaned):
        raise ValueError("Введите время в формате ЧЧ:ММ, например 15:30.")
    return cleaned


def format_entry(entry: WaitlistEntry) -> str:
    return (
        f"#{entry.id}\n"
        f"Имя: {entry.client_name}\n"
        f"Телефон: {entry.phone}\n"
        f"Дата: {entry.desired_date.strftime('%d.%m.%Y')}\n"
        f"Время: {entry.desired_time or 'не указано'}\n"
        f"Комментарий: {entry.comment or 'нет'}\n"
        f"Статус: {STATUS_LABELS[entry.status]}"
    )


def format_added(entry: WaitlistEntry) -> str:
    return "Клиент добавлен в лист ожидания.\n\n" + format_entry(entry).split("\n", 1)[1]
