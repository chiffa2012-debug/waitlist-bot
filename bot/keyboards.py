from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from .models import Admin


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


def single_action(entry_id: int, action: str, label: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=label, callback_data=f"entry:{action}:{entry_id}")]
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
