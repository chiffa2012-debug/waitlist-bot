from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum


class EntryStatus(StrEnum):
    WAITING = "waiting"
    NOTIFIED = "notified"
    BOOKED = "booked"
    DELETED = "deleted"


ACTIVE_STATUSES = (EntryStatus.WAITING, EntryStatus.NOTIFIED)


@dataclass(slots=True)
class WaitlistEntry:
    id: int
    client_name: str
    phone: str
    desired_date: date
    desired_time: str | None
    comment: str | None
    status: EntryStatus
    last_notified_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class CheckResult:
    entry_id: int
    slots: list[str]
    notification_sent: bool = False
    error: str | None = None


@dataclass(slots=True)
class Admin:
    telegram_id: int
    is_owner: bool
    username: str | None
    full_name: str | None
    added_at: datetime
    added_by: int | None
