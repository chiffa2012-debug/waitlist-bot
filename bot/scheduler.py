from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .config import Settings
from .keyboards import notification_actions
from .models import CheckResult, WaitlistEntry
from .repositories import WaitlistRepository
from .yclients_client import YclientsClient, YclientsError


logger = logging.getLogger(__name__)


def _slot_minutes(value: str) -> int:
    try:
        hours, minutes = value.split(":", 1)
        return int(hours) * 60 + int(minutes)
    except (ValueError, AttributeError):
        return 24 * 60


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

    def _notification_is_due(self, entry: WaitlistEntry, now: datetime) -> bool:
        if entry.last_notified_at is None:
            return True
        last = entry.last_notified_at
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        return now - last.astimezone(timezone.utc) >= timedelta(
            hours=self.settings.notification_cooldown_hours
        )

    async def check_entry(self, entry: WaitlistEntry) -> CheckResult:
        now = datetime.now(timezone.utc)
        try:
            slots = await self.yclients.get_available_slots(entry.desired_date.isoformat())
            if not slots or not self._notification_is_due(entry, now):
                return CheckResult(entry_id=entry.id, slots=slots)

            ordered_slots = slots
            if entry.desired_time:
                target = _slot_minutes(entry.desired_time)
                ordered_slots = sorted(
                    slots, key=lambda value: abs(_slot_minutes(value) - target)
                )
            visible_slots = ordered_slots[:10]
            slot_lines = "\n".join(f"- {slot}" for slot in visible_slots)
            message = (
                "Похоже, появилось свободное окно для клиента из листа ожидания.\n\n"
                f"Клиент: {entry.client_name}\n"
                f"Телефон: {entry.phone}\n"
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
            return CheckResult(
                entry_id=entry.id, slots=slots, notification_sent=True
            )
        except (YclientsError, RuntimeError) as exc:
            logger.warning("Waitlist entry #%s check failed: %s", entry.id, exc)
            return CheckResult(entry_id=entry.id, slots=[], error=str(exc))
        except Exception as exc:  # Telegram/network errors must not stop the whole job.
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
        entries = await self.repository.list_active()
        results: list[CheckResult] = []
        for entry in entries:
            results.append(await self.check_entry(entry))
        return results


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


async def check_waitlist_entries(checker: WaitlistChecker) -> list[CheckResult]:
    """Public entry point useful for manual calls and tests."""
    return await checker.check_waitlist_entries()
