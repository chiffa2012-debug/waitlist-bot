from aiogram.fsm.state import State, StatesGroup


class AddEntry(StatesGroup):
    name = State()
    phone = State()
    service = State()
    staff = State()
    desired_date = State()
    desired_time = State()
    comment = State()
    confirmation = State()


class AdminManagement(StatesGroup):
    add_id = State()
