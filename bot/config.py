from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv


def _optional_int(name: str) -> int | None:
    value = os.getenv(name, "").strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{name} должен быть целым числом") from exc


def _boolean(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} должен быть true или false")


def database_path_from_url(database_url: str) -> Path:
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        raise ValueError("Поддерживается только DATABASE_URL вида sqlite:///path/to/file.db")
    raw_path = database_url[len(prefix) :]
    if not raw_path:
        raise ValueError("В DATABASE_URL не указан путь к файлу")
    path = Path(raw_path)
    if not path.is_absolute():
        path = Path.cwd() / path
    return path.resolve()


@dataclass(frozen=True, slots=True)
class Settings:
    telegram_bot_token: str
    admin_telegram_id: int | None
    timezone: ZoneInfo
    database_path: Path
    yclients_enabled: bool
    yclients_base_url: str
    yclients_bearer_token: str
    yclients_user_token: str
    yclients_company_id: int | None
    yclients_staff_id: int | None
    yclients_service_id: int | None
    yclients_check_interval_minutes: int
    notification_cooldown_hours: int = 6

    @classmethod
    def from_env(cls, env_file: str | Path | None = None) -> "Settings":
        load_dotenv(dotenv_path=env_file, override=False)
        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        if not token:
            raise ValueError("Не задан TELEGRAM_BOT_TOKEN")

        timezone_name = os.getenv("TIMEZONE", "Europe/Amsterdam").strip()
        try:
            timezone = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"Неизвестный TIMEZONE: {timezone_name}") from exc

        interval = _optional_int("YCLIENTS_CHECK_INTERVAL_MINUTES") or 15
        if interval < 1:
            raise ValueError("YCLIENTS_CHECK_INTERVAL_MINUTES должен быть не меньше 1")

        return cls(
            telegram_bot_token=token,
            admin_telegram_id=_optional_int("ADMIN_TELEGRAM_ID"),
            timezone=timezone,
            database_path=database_path_from_url(
                os.getenv("DATABASE_URL", "sqlite:///waitlist.db").strip()
            ),
            yclients_enabled=_boolean("YCLIENTS_ENABLED", False),
            yclients_base_url=os.getenv(
                "YCLIENTS_BASE_URL", "https://api.yclients.com/api/v1"
            ).strip().rstrip("/"),
            yclients_bearer_token=os.getenv("YCLIENTS_BEARER_TOKEN", "").strip(),
            yclients_user_token=os.getenv("YCLIENTS_USER_TOKEN", "").strip(),
            yclients_company_id=_optional_int("YCLIENTS_COMPANY_ID"),
            yclients_staff_id=_optional_int("YCLIENTS_STAFF_ID"),
            yclients_service_id=_optional_int("YCLIENTS_SERVICE_ID"),
            yclients_check_interval_minutes=interval,
        )

    @property
    def yclients_readiness_error(self) -> str | None:
        if not self.yclients_enabled:
            return (
                "Проверка Yclients выключена. Включите YCLIENTS_ENABLED=true "
                "и заполните ключи в .env."
            )
        missing: list[str] = []
        for name, value in (
            ("YCLIENTS_BEARER_TOKEN", self.yclients_bearer_token),
            ("YCLIENTS_USER_TOKEN", self.yclients_user_token),
            ("YCLIENTS_COMPANY_ID", self.yclients_company_id),
            ("YCLIENTS_SERVICE_ID", self.yclients_service_id),
        ):
            if value in (None, ""):
                missing.append(name)
        if missing:
            return "Для проверки Yclients заполните: " + ", ".join(missing) + "."
        return None
