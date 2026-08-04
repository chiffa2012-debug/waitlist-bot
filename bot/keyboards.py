from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from .models import Admin, WaitlistEntry


MENU_BUTTONS = (
    "Добавить клиента",
    "Лист ожидания",
    "Проверить окна",
    "Сегодня",
    "Завтра",
    "Администраторы",
    "Помощь",
)


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Добавить клиента"), KeyboardButton(text="Лист ожидания")],
            [KeyboardButton(text="Проверить окна"), KeyboardButton(text="Сегодня")],
            [KeyboardButton(text="Завтра"), KeyboardButton(text="Администраторы")],
            [KeyboardButton(text="Помощь")],
        ],
        resize_keyboard=True,
        input_field_placeholder="Выберите действие",
    )


def skip_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Пропустить")], [KeyboardButton(text="Отмена")]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def cancel_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Отмена")]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def add_confirmation_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Добавить", callback_data="add:confirm")],
            [InlineKeyboardButton(text="Отмена", callback_data="add:cancel")],
        ]
    )


def duplicate_confirmation() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Всё равно добавить", callback_data="add:force")],
            [InlineKeyboardButton(text="Отмена", callback_data="add:cancel")],
        ]
    )


def options_keyboard(
    prefix: str,
    options: list[tuple[int, str]],
    extra: tuple[str, str] | None = None,
) -> InlineKeyboardMarkup:
    """Список вариантов «id — название» одной кнопкой на строку."""
    rows = [
        [InlineKeyboardButton(text=title[:60], callback_data=f"{prefix}:{option_id}")]
        for option_id, title in options
    ]
    if extra is not None:
        rows.append([InlineKeyboardButton(text=extra[0], callback_data=extra[1])])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def entries_index(entries: list[WaitlistEntry]) -> InlineKeyboardMarkup:
    """Кнопки-номера заявок под общим списком."""
    buttons = [
        InlineKeyboardButton(text=f"#{entry.id}", callback_data=f"entry:open:{entry.id}")
        for entry in entries
    ]
    rows = [buttons[index : index + 4] for index in range(0, len(buttons), 4)]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def entry_actions(entry_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Записан", callback_data=f"entry:booked:{entry_id}"
                ),
                InlineKeyboardButton(
                    text="Удалить", callback_data=f"entry:deleted:{entry_id}"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Проверить окна", callback_data=f"entry:check:{entry_id}"
                )
            ],
        ]
    )


def status_confirmation(entry_id: int, status: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Да, подтвердить",
                    callback_data=f"confirm:{status}:{entry_id}",
                )
            ],
            [InlineKeyboardButton(text="Отмена", callback_data=f"confirm:cancel:{entry_id}")],
        ]
    )


def notification_actions(entry_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Отметить записанным", callback_data=f"entry:booked:{entry_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="Оставить в ожидании", callback_data=f"entry:waiting:{entry_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="Удалить", callback_data=f"entry:deleted:{entry_id}"
                )
            ],
        ]
    )


def admins_keyboard(admins: list[Admin]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text="Добавить администратора", callback_data="admin:add")]
    ]
    for admin in admins:
        if not admin.is_owner:
            label = admin.username and f"@{admin.username}" or str(admin.telegram_id)
            rows.append(
                [
                    InlineKeyboardButton(
                        text=f"Удалить {label}",
                        callback_data=f"admin:remove:{admin.telegram_id}",
                    )
                ]
            )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_removal_confirmation(telegram_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Да, удалить администратора",
                    callback_data=f"admin:confirm_remove:{telegram_id}",
                )
            ],
            [InlineKeyboardButton(text="Отмена", callback_data="admin:cancel")],
        ]
    )
