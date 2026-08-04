from __future__ import annotations

import argparse
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import SimpleEventIsolation
from aiogram.types import BotCommand

from .access import AdminOnlyMiddleware
from .config import Settings
from .db import Database
from .handlers import build_router
from .fsm_storage import SQLiteFSMStorage
from .repositories import WaitlistRepository
from .scheduler import WaitlistChecker, build_scheduler
from .yclients_client import YclientsClient


COMMANDS = [
    BotCommand(command="start", description="Главное меню"),
    BotCommand(command="add", description="Добавить клиента"),
    BotCommand(command="list", description="Лист ожидания"),
    BotCommand(command="today", description="На сегодня"),
    BotCommand(command="tomorrow", description="На завтра"),
    BotCommand(command="expired", description="Заявки с прошедшей датой"),
    BotCommand(command="done", description="Отметить записанным"),
    BotCommand(command="delete", description="Удалить заявку"),
    BotCommand(command="check", description="Проверить окна"),
    BotCommand(command="admins", description="Управление администраторами"),
    BotCommand(command="add_admin", description="Добавить администратора"),
    BotCommand(command="remove_admin", description="Удалить администратора"),
    BotCommand(command="help", description="Помощь"),
]


async def smoke_check(settings: Settings) -> None:
    database = Database(settings.database_path)
    await database.connect()
    try:
        repository = WaitlistRepository(database)
        await repository.list_active()
        print(f"OK: SQLite готова: {settings.database_path}")
        print(
            "OK: Yclients: "
            + (settings.yclients_readiness_error or "конфигурация заполнена")
        )
    finally:
        await database.close()


async def run_bot(settings: Settings) -> None:
    database = Database(settings.database_path)
    await database.connect()
    repository = WaitlistRepository(database)
    if settings.admin_telegram_id is not None:
        await repository.ensure_configured_admin(settings.admin_telegram_id)
    bot = Bot(token=settings.telegram_bot_token)
    yclients = YclientsClient(settings)
    checker = WaitlistChecker(settings, repository, yclients, bot)
    scheduler = build_scheduler(settings, checker)

    router = build_router(settings, repository, checker, yclients)
    access = AdminOnlyMiddleware(settings, repository)
    router.message.outer_middleware(access)
    router.callback_query.outer_middleware(access)

    dispatcher = Dispatcher(
        storage=SQLiteFSMStorage(database),
        events_isolation=SimpleEventIsolation(),
    )
    dispatcher.include_router(router)
    await bot.set_my_commands(COMMANDS)
    scheduler.start()

    try:
        await dispatcher.start_polling(bot)
    finally:
        scheduler.shutdown(wait=False)
        await yclients.close()
        await bot.session.close()
        await database.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Telegram-бот «Лист ожидания»")
    parser.add_argument(
        "--smoke-check",
        action="store_true",
        help="проверить конфигурацию и SQLite без подключения к Telegram/Yclients",
    )
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    args = parse_args()
    try:
        settings = Settings.from_env()
        if args.smoke_check:
            asyncio.run(smoke_check(settings))
        else:
            asyncio.run(run_bot(settings))
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception as exc:
        logging.getLogger(__name__).error("Не удалось запустить бота: %s", exc)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
