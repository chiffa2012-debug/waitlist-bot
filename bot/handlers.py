from __future__ import annotations

from datetime import datetime, timedelta

from aiogram import F, Router
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from .config import Settings
from .keyboards import (
    admin_removal_confirmation,
    admins_keyboard,
    add_confirmation_keyboard,
    cancel_keyboard,
    entry_actions,
    main_menu,
    single_action,
    skip_keyboard,
    status_confirmation,
)
from .models import EntryStatus
from .repositories import WaitlistRepository
from .scheduler import WaitlistChecker
from .states import AddEntry, AdminManagement
from .utils import (
    format_added,
    format_entry,
    is_valid_phone,
    normalize_optional,
    parse_desired_date_and_time,
    parse_time,
)


HELP_TEXT = """Лист ожидания помогает не забыть клиентов и проверяет окна Yclients.

/add — добавить клиента
/list — актуальный лист
/today — заявки на сегодня
/tomorrow — заявки на завтра
/done — отметить клиента записанным
/delete — удалить заявку
/check — проверить окна
/admins — добавить или удалить администраторов
/help — эта инструкция

Бот ничего не записывает в Yclients автоматически. Когда появится окно, свяжитесь с клиентом и оформите запись обычным способом."""


def build_router(
    settings: Settings,
    repository: WaitlistRepository,
    checker: WaitlistChecker,
) -> Router:
    router = Router(name="waitlist")

    async def show_entries(
        message: Message,
        title: str,
        desired_date=None,
        action: str | None = None,
    ) -> None:
        entries = await repository.list_active(desired_date)
        if not entries:
            await message.answer("Активных заявок нет.", reply_markup=main_menu())
            return
        await message.answer(f"{title}: {len(entries)}")
        for entry in entries:
            if action == "booked":
                markup = single_action(entry.id, "booked", "Отметить записанным")
            elif action == "deleted":
                markup = single_action(entry.id, "deleted", "Удалить")
            else:
                markup = entry_actions(entry.id)
            await message.answer(format_entry(entry), reply_markup=markup)

    async def begin_add(message: Message, state: FSMContext) -> None:
        await state.clear()
        await state.set_state(AddEntry.name)
        await message.answer("Введите имя клиента.", reply_markup=cancel_keyboard())

    async def send_admins(message: Message) -> None:
        if not message.from_user or not await repository.is_owner(message.from_user.id):
            await message.answer("Управлять администраторами может только владелец бота.")
            return
        admins = await repository.list_admins()
        lines = ["Администраторы:"]
        for admin in admins:
            role = "владелец" if admin.is_owner else "администратор"
            name = admin.full_name or (f"@{admin.username}" if admin.username else "имя пока неизвестно")
            lines.append(f"• {name} — {admin.telegram_id} ({role})")
        lines.append("\nДля добавления нужен числовой Telegram ID пользователя.")
        await message.answer("\n".join(lines), reply_markup=admins_keyboard(admins))

    @router.message(CommandStart())
    async def start(message: Message, state: FSMContext) -> None:
        await state.clear()
        await message.answer(
            "Лист ожидания готов. Добавляйте клиентов, а бот напомнит, когда в Yclients появится окно.",
            reply_markup=main_menu(),
        )

    @router.message(Command("help"))
    @router.message(F.text == "Помощь")
    async def help_message(message: Message) -> None:
        await message.answer(HELP_TEXT, reply_markup=main_menu())

    @router.message(Command("admins"))
    @router.message(Command("remove_admin"))
    @router.message(F.text == "Администраторы")
    async def admins_list(message: Message) -> None:
        await send_admins(message)

    @router.message(Command("add_admin"))
    async def add_admin_command(message: Message, state: FSMContext) -> None:
        if not message.from_user or not await repository.is_owner(message.from_user.id):
            await message.answer("Добавлять администраторов может только владелец бота.")
            return
        await state.set_state(AdminManagement.add_id)
        await message.answer(
            "Отправьте числовой Telegram ID нового администратора.\n"
            "Он увидит свой ID, если напишет этому боту /start.",
            reply_markup=cancel_keyboard(),
        )

    @router.message(StateFilter(AdminManagement), Command("cancel"))
    @router.message(StateFilter(AdminManagement), F.text.casefold() == "отмена")
    async def cancel_admin_action(message: Message, state: FSMContext) -> None:
        await state.clear()
        await message.answer("Действие отменено.", reply_markup=main_menu())

    @router.message(AdminManagement.add_id)
    async def add_admin_id(message: Message, state: FSMContext) -> None:
        if not message.from_user or not await repository.is_owner(message.from_user.id):
            await state.clear()
            await message.answer("Добавлять администраторов может только владелец бота.")
            return
        raw_id = (message.text or "").strip()
        if not raw_id.isdigit() or int(raw_id) <= 0:
            await message.answer("Нужен числовой Telegram ID, например 123456789.")
            return
        telegram_id = int(raw_id)
        added = await repository.add_admin(telegram_id, message.from_user.id)
        await state.clear()
        if added:
            await message.answer(
                f"Администратор {telegram_id} добавлен.\n"
                "Попросите его открыть бота и отправить /start.",
                reply_markup=main_menu(),
            )
        else:
            await message.answer("Этот пользователь уже является администратором.", reply_markup=main_menu())

    @router.message(Command("add"))
    @router.message(F.text == "Добавить клиента")
    async def add(message: Message, state: FSMContext) -> None:
        await begin_add(message, state)

    @router.message(StateFilter(AddEntry), Command("cancel"))
    @router.message(StateFilter(AddEntry), F.text.casefold() == "отмена")
    async def cancel_add(message: Message, state: FSMContext) -> None:
        await state.clear()
        await message.answer("Добавление отменено.", reply_markup=main_menu())

    @router.message(AddEntry.name)
    async def add_name(message: Message, state: FSMContext) -> None:
        name = (message.text or "").strip()
        if not 2 <= len(name) <= 100:
            await message.answer("Имя должно содержать от 2 до 100 символов.")
            return
        await state.update_data(client_name=name)
        await state.set_state(AddEntry.phone)
        await message.answer("Введите телефон клиента.")

    @router.message(AddEntry.phone)
    async def add_phone(message: Message, state: FSMContext) -> None:
        phone = (message.text or "").strip()
        if not is_valid_phone(phone) or len(phone) > 50:
            await message.answer("В телефоне должно быть минимум 7 цифр. Попробуйте ещё раз.")
            return
        await state.update_data(phone=phone)
        await state.set_state(AddEntry.desired_date)
        await message.answer(
            "На какую дату клиент хотел записаться?\n"
            "Например: 22.07.2026, 2026-07-22, сегодня или завтра."
        )

    @router.message(AddEntry.desired_date)
    async def add_date(message: Message, state: FSMContext) -> None:
        try:
            desired_date, desired_time = parse_desired_date_and_time(
                message.text or "", settings.timezone
            )
        except ValueError as exc:
            await message.answer(str(exc))
            return
        if desired_date < datetime.now(settings.timezone).date():
            await message.answer("Дата уже прошла. Укажите сегодня или будущую дату.")
            return
        await state.update_data(
            desired_date=desired_date.isoformat(), desired_time=desired_time
        )
        if desired_time:
            await state.set_state(AddEntry.comment)
            await message.answer(
                f"Понял: {desired_date.strftime('%d.%m.%Y')} в {desired_time}.\n"
                "Добавьте комментарий или нажмите «Пропустить».",
                reply_markup=skip_keyboard(),
            )
            return
        await state.set_state(AddEntry.desired_time)
        await message.answer(
            "Введите желаемое время, например 15:30, или нажмите «Пропустить».",
            reply_markup=skip_keyboard(),
        )

    @router.message(AddEntry.desired_time)
    async def add_time(message: Message, state: FSMContext) -> None:
        raw = (message.text or "").strip()
        if raw.casefold() == "пропустить":
            desired_time = None
        else:
            try:
                desired_time = parse_time(raw)
            except ValueError as exc:
                await message.answer(str(exc))
                return
        await state.update_data(desired_time=desired_time)
        await state.set_state(AddEntry.comment)
        await message.answer(
            "Добавьте комментарий или нажмите «Пропустить».",
            reply_markup=skip_keyboard(),
        )

    @router.message(AddEntry.comment)
    async def add_comment(message: Message, state: FSMContext) -> None:
        raw = (message.text or "").strip()
        comment = None if raw.casefold() == "пропустить" else normalize_optional(raw)
        if comment and len(comment) > 1000:
            await message.answer("Комментарий слишком длинный. Сократите его до 1000 символов.")
            return
        await state.update_data(comment=comment)
        data = await state.get_data()
        desired_date = datetime.fromisoformat(data["desired_date"]).date()
        preview = (
            "Проверьте заявку:\n\n"
            f"Имя: {data['client_name']}\n"
            f"Телефон: {data['phone']}\n"
            f"Дата: {desired_date.strftime('%d.%m.%Y')}\n"
            f"Время: {data.get('desired_time') or 'не указано'}\n"
            f"Комментарий: {comment or 'нет'}"
        )
        await state.set_state(AddEntry.confirmation)
        await message.answer(preview, reply_markup=add_confirmation_keyboard())

    @router.callback_query(AddEntry.confirmation, F.data == "add:confirm")
    async def confirm_add(callback: CallbackQuery, state: FSMContext) -> None:
        data = await state.get_data()
        entry = await repository.add(
            client_name=data["client_name"],
            phone=data["phone"],
            desired_date=datetime.fromisoformat(data["desired_date"]).date(),
            desired_time=data.get("desired_time"),
            comment=data.get("comment"),
        )
        await state.clear()
        await callback.answer("Добавлено")
        if callback.message:
            await callback.message.answer(format_added(entry), reply_markup=main_menu())

    @router.callback_query(AddEntry.confirmation, F.data == "add:cancel")
    async def cancel_add_callback(callback: CallbackQuery, state: FSMContext) -> None:
        await state.clear()
        await callback.answer("Отменено")
        if callback.message:
            await callback.message.answer("Добавление отменено.", reply_markup=main_menu())

    @router.message(Command("list"))
    @router.message(F.text == "Лист ожидания")
    async def list_entries(message: Message) -> None:
        await show_entries(message, "Лист ожидания")

    @router.message(Command("today"))
    @router.message(F.text == "Сегодня")
    async def today(message: Message) -> None:
        value = datetime.now(settings.timezone).date()
        await show_entries(message, "Ждут запись на сегодня", value)

    @router.message(Command("tomorrow"))
    @router.message(F.text == "Завтра")
    async def tomorrow(message: Message) -> None:
        value = datetime.now(settings.timezone).date() + timedelta(days=1)
        await show_entries(message, "Ждут запись на завтра", value)

    @router.message(Command("done"))
    async def done(message: Message) -> None:
        await show_entries(message, "Кого отметить записанным", action="booked")

    @router.message(Command("delete"))
    async def delete(message: Message) -> None:
        await show_entries(message, "Какую заявку удалить", action="deleted")

    @router.message(Command("check"))
    @router.message(F.text == "Проверить окна")
    async def check_all(message: Message) -> None:
        readiness_error = settings.yclients_readiness_error
        if readiness_error:
            await message.answer(readiness_error, reply_markup=main_menu())
            return
        await message.answer("Проверяю окна…")
        results = await checker.check_waitlist_entries()
        if not results:
            await message.answer("Активных заявок нет.", reply_markup=main_menu())
            return
        errors = [result.error for result in results if result.error]
        with_slots = sum(bool(result.slots) for result in results)
        sent = sum(result.notification_sent for result in results)
        summary = (
            f"Проверено заявок: {len(results)}\n"
            f"С доступными окнами: {with_slots}\n"
            f"Новых уведомлений: {sent}"
        )
        if errors:
            summary += f"\nОшибок: {len(errors)}\n{errors[0]}"
        await message.answer(summary, reply_markup=main_menu())

    @router.callback_query(F.data.startswith("entry:"))
    async def entry_callback(callback: CallbackQuery) -> None:
        if not callback.data:
            return
        _, action, raw_id = callback.data.split(":", 2)
        entry_id = int(raw_id)
        entry = await repository.get(entry_id)
        if entry is None or entry.status not in {EntryStatus.WAITING, EntryStatus.NOTIFIED}:
            await callback.answer("Заявка уже обработана или не найдена.", show_alert=True)
            return

        if action == "check":
            readiness_error = settings.yclients_readiness_error
            if readiness_error:
                await callback.answer()
                if callback.message:
                    await callback.message.answer(readiness_error)
                return
            await callback.answer("Проверяю…")
            result = await checker.check_entry(entry)
            if callback.message:
                if result.error:
                    await callback.message.answer(f"Не удалось проверить заявку #{entry.id}: {result.error}")
                elif not result.slots:
                    await callback.message.answer(f"Для заявки #{entry.id} свободных окон пока нет.")
                elif not result.notification_sent:
                    await callback.message.answer(
                        f"Для заявки #{entry.id} есть окна: {', '.join(result.slots[:10])}.\n"
                        "Повторное уведомление не отправлено из-за ограничения 6 часов."
                    )
            return

        if action == "waiting":
            await repository.set_status(entry_id, EntryStatus.WAITING)
            await callback.answer("Оставлено в ожидании")
            if callback.message:
                await callback.message.answer("Заявка оставлена в листе ожидания.", reply_markup=main_menu())
            return

        if action in {"booked", "deleted"}:
            prompt = (
                "Отметить клиента записанным?"
                if action == "booked"
                else "Удалить эту заявку?"
            )
            await callback.answer()
            if callback.message:
                await callback.message.answer(
                    prompt, reply_markup=status_confirmation(entry_id, action)
                )

    @router.callback_query(F.data.startswith("confirm:"))
    async def confirm_status(callback: CallbackQuery) -> None:
        if not callback.data:
            return
        _, action, raw_id = callback.data.split(":", 2)
        if action == "cancel":
            await callback.answer("Отменено")
            if callback.message:
                await callback.message.edit_reply_markup(reply_markup=None)
            return
        current = await repository.get(int(raw_id))
        if current is None or current.status not in {
            EntryStatus.WAITING,
            EntryStatus.NOTIFIED,
        }:
            await callback.answer("Заявка уже обработана или не найдена.", show_alert=True)
            return
        status = EntryStatus.BOOKED if action == "booked" else EntryStatus.DELETED
        entry = await repository.set_status(int(raw_id), status)
        await callback.answer("Готово")
        if callback.message:
            await callback.message.edit_reply_markup(reply_markup=None)
            await callback.message.answer(
                "Клиент отмечен записанным."
                if status == EntryStatus.BOOKED
                else "Заявка удалена.",
                reply_markup=main_menu(),
            )

    @router.callback_query(F.data.startswith("admin:"))
    async def admin_callback(callback: CallbackQuery, state: FSMContext) -> None:
        if not callback.from_user or not await repository.is_owner(callback.from_user.id):
            await callback.answer(
                "Управлять администраторами может только владелец бота.", show_alert=True
            )
            return
        if not callback.data:
            return
        parts = callback.data.split(":")
        action = parts[1]
        if action == "add":
            await state.set_state(AdminManagement.add_id)
            await callback.answer()
            if callback.message:
                await callback.message.answer(
                    "Отправьте числовой Telegram ID нового администратора.",
                    reply_markup=cancel_keyboard(),
                )
            return
        if action == "cancel":
            await callback.answer("Отменено")
            if callback.message:
                await callback.message.edit_reply_markup(reply_markup=None)
            return
        if len(parts) != 3 or not parts[2].isdigit():
            await callback.answer("Некорректная команда.", show_alert=True)
            return
        telegram_id = int(parts[2])
        if action == "remove":
            await callback.answer()
            if callback.message:
                await callback.message.answer(
                    f"Удалить администратора {telegram_id}?",
                    reply_markup=admin_removal_confirmation(telegram_id),
                )
            return
        if action == "confirm_remove":
            removed = await repository.remove_admin(telegram_id)
            await callback.answer("Удалён" if removed else "Не удалось удалить")
            if callback.message:
                await callback.message.edit_reply_markup(reply_markup=None)
                await callback.message.answer(
                    "Администратор удалён."
                    if removed
                    else "Владельца удалить нельзя или администратор уже удалён.",
                    reply_markup=main_menu(),
                )

    @router.message()
    async def fallback(message: Message) -> None:
        await message.answer("Выберите действие в меню или используйте /help.", reply_markup=main_menu())

    return router
