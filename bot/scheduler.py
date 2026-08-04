from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .config import Settings
from .keyboards import notification_actions
from .models import CheckResult, WaitlistEntry
from .repositories import WaitlistRepository
from .yclients_client import YclientsClient, YclientsError


logger = logging.getLogger(__name__)


def slot_minutes(value: str) -> int:
    try:
        hours, minutes = value.split(":", 1)
        return int(hours) * 60 + int(minutes)
    except (ValueError, AttributeError):
        return 24 * 60


def drop_past_slots(
    slots: list[str], desired_date: date, now_local: datetime
) -> list[str]:
    """Для сегодняшней даты убирает окна, время которых уже прошло."""
    if desired_date != now_local.date():
        return slots
    current = now_local.hour * 60 + now_local.minute
    return [slot for slot in slots if slot_minutes(slot) > current]


def slots_near_desired_time(
    slots: list[str], desired_time: str | None, tolerance_hours: int
) -> list[str]:
    """Оставляет окна рядом с желаемым временем и сортирует по близости к нему."""
    if not desired_time:
        return slots
    target = slot_minutes(desired_time)
    ordered = sorted(slots, key=lambda value: abs(slot_minutes(value) - target))
    if tolerance_hours <= 0:
        return ordered
    limit = tolerance_hours * 60
    return [slot for slot in ordered if abs(slot_minutes(slot) - target) <= limit]


class WaitlistChecker:
    def __init__(
        self,
        settings: Settings,
        repository: WaitlistRepository,
        yclients: YclientsClient,
        bot: Bot,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.yclients = yclients
        self.bot = bot

    def _now_local(self) -> datetime:
        return datetime.now(self.settings.timezone)

    def _notification_is_due(self, entry: WaitlistEntry, now: datetime) -> bool:
        if entry.last_notified_at is None:
            return True
        last = entry.last_notified_at
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        return now - last.astimezone(timezone.utc) >= timedelta(
            hours=self.settings.notification_cooldown_hours
        )

    async def _fetch_slots(
        self, entry: WaitlistEntry, cache: dict | None = None
    ) -> list[str]:
        """Свободные окна на дату заявки. Одинаковые заявки делят один запрос."""
        key = (entry.service_id, entry.staff_id, entry.desired_date)
        if cache is not None and key in cache:
            cached = cache[key]
            if isinstance(cached, Exception):
                raise cached
            return cached
        try:
            slots = await self.yclients.get_available_slots(
                entry.desired_date.isoformat(), entry.service_id, entry.staff_id
            )
        except YclientsError as exc:
            if cache is not None:
                cache[key] = exc
            raise
        slots = drop_past_slots(slots, entry.desired_date, self._now_local())
        if cache is not None:
            cache[key] = slots
        return slots

    async def check_entry(
        self, entry: WaitlistEntry, cache: dict | None = None
    ) -> CheckResult:
        now = datetime.now(timezone.utc)
        try:
            slots = slots_near_desired_time(
                await self._fetch_slots(entry, cache),
                entry.desired_time,
                self.settings.slot_time_tolerance_hours,
            )
            if not slots or not self._notification_is_due(entry, now):
                return CheckResult(entry_id=entry.id, slots=slots)

            slot_lines = "\n".join(f"- {slot}" for slot in slots[:10])
            message = (
                "Похоже, появилось свободное окно для клиента из листа ожидания.\n\n"
                f"Клиент: {entry.client_name}\n"
                f"Телефон: {entry.phone}\n"
                f"Услуга: {entry.service_title or 'не указана'}\n"
                f"Мастер: {entry.staff_name or 'любой'}\n"
                f"Желаемая дата: {entry.desired_date.strftime('%d.%m.%Y')}\n"
                f"Желаемое время: {entry.desired_time or 'не указано'}\n"
                f"Найденные окна:\n{slot_lines}\n\n"
                "Не забудьте связаться с клиентом и записать его."
            )
            admin_ids = await self.repository.list_admin_ids()
            if not admin_ids:
                raise RuntimeError("Не определён Telegram ID администратора")
            delivered = 0
            for admin_id in admin_ids:
                try:
                    await self.bot.send_message(
                        chat_id=admin_id,
                        text=message,
                        reply_markup=notification_actions(entry.id),
                    )
                    delivered += 1
                except Exception as exc:
                    logger.warning(
                        "Could not notify admin %s for entry #%s: %s",
                        admin_id,
                        entry.id,
                        exc,
                    )
            if delivered == 0:
                raise RuntimeError("Не удалось доставить уведомление администраторам")
            await self.repository.mark_notified(entry.id, now)
            return CheckResult(entry_id=entry.id, slots=slots, notification_sent=True)
        except (YclientsError, RuntimeError) as exc:
            logger.warning("Waitlist entry #%s check failed: %s", entry.id, exc)
            return CheckResult(entry_id=entry.id, slots=[], error=str(exc))
        except Exception:  # Telegram/network errors must not stop the whole job.
            logger.exception("Unexpected waitlist entry #%s check failure", entry.id)
            return CheckResult(
                entry_id=entry.id,
                slots=[],
                error="Не удалось завершить проверку. Попробуйте позже.",
            )

    async def check_waitlist_entries(self) -> list[CheckResult]:
        if self.settings.yclients_readiness_error:
            return [
                CheckResult(
                    entry_id=0,
                    slots=[],
                    error=self.settings.yclients_readiness_error,
                )
            ]
        entries = await self.repository.list_active(not_before=self._now_local().date())
        cache: dict = {}
        return [await self.check_entry(entry, cache) for entry in entries]


def build_scheduler(settings: Settings, checker: WaitlistChecker) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=settings.timezone)
    if settings.yclients_enabled:
        scheduler.add_job(
            checker.check_waitlist_entries,
            trigger="interval",
            minutes=settings.yclients_check_interval_minutes,
            id="check_waitlist",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
        )
    return scheduler
