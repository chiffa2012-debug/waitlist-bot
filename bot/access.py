from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from .config import Settings
from .repositories import WaitlistRepository


class AdminOnlyMiddleware(BaseMiddleware):
    def __init__(self, settings: Settings, repository: WaitlistRepository) -> None:
        self.settings = settings
        self.repository = repository

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user is None:
            return None

        is_start = isinstance(event, Message) and bool(
            event.text and event.text.split(maxsplit=1)[0] == "/start"
        )
        owner_id = await self.repository.get_claimed_admin_id()
        if owner_id is None and is_start:
            await self.repository.claim_admin(
                user.id, username=user.username, full_name=user.full_name
            )

        if not await self.repository.is_admin(user.id):
            text = (
                "У вас нет доступа к этому боту.\n"
                f"Ваш Telegram ID: {user.id}. Передайте его владельцу бота."
            )
            if isinstance(event, CallbackQuery):
                await event.answer(text, show_alert=True)
            elif isinstance(event, Message):
                await event.answer(text)
            return None

        await self.repository.update_admin_identity(
            user.id, username=user.username, full_name=user.full_name
        )

        return await handler(event, data)
