import pytest

from bot.utils import is_valid_phone, parse_time


@pytest.mark.parametrize(
    "phone",
    ["+7 999 123-45-67", "89991234567", "1234567"],
)
def test_phone_with_at_least_seven_digits_is_valid(phone: str) -> None:
    assert is_valid_phone(phone)


@pytest.mark.parametrize("phone", ["", "abc", "+7 12-34"])
def test_short_phone_is_invalid(phone: str) -> None:
    assert not is_valid_phone(phone)


def test_time_validation() -> None:
    assert parse_time("15:30") == "15:30"
    with pytest.raises(ValueError):
        parse_time("25:10")
