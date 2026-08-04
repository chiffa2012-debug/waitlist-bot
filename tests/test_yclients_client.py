import json
from zoneinfo import ZoneInfo

import httpx
import pytest

from bot.config import Settings
from bot.yclients_client import YclientsClient


@pytest.mark.asyncio
async def test_get_available_slots_uses_verified_read_only_endpoints(tmp_path) -> None:
    settings = Settings(
        telegram_bot_token="",
        admin_telegram_id=1,
        timezone=ZoneInfo("Europe/Amsterdam"),
        database_path=tmp_path / "waitlist.db",
        yclients_enabled=True,
        yclients_base_url="https://api.yclients.com/api/v1",
        yclients_bearer_token="test-bearer",
        yclients_user_token="test-user",
        yclients_company_id=123,
        yclients_staff_id=None,
        yclients_service_id=456,
        yclients_check_interval_minutes=15,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.startswith("/api/v1/")
        if request.url.path.endswith("/book_staff/123"):
            return httpx.Response(200, json={"data": [{"id": 77, "bookable": True}]})
        if request.url.path.endswith("/book_times/123/77/2026-07-25"):
            return httpx.Response(
                200,
                json={"data": [{"time": "15:00"}, {"datetime": "2026-07-25T15:30:00+08:00"}]},
            )
        return httpx.Response(404, text=json.dumps({"message": "not found"}))

    client = YclientsClient(settings)
    await client.client.aclose()
    client.client = httpx.AsyncClient(
        base_url=settings.yclients_base_url,
        transport=httpx.MockTransport(handler),
        headers={"Authorization": "test"},
    )
    try:
        assert await client.get_available_slots("2026-07-25") == ["15:00", "15:30"]
    finally:
        await client.close()
