from zoneinfo import ZoneInfo

import httpx
import pytest

from bot.config import Settings
from bot.yclients_client import YclientsClient


def build_settings(tmp_path) -> Settings:
    return Settings(
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


def build_client(settings: Settings, handler, requests: list[str]) -> YclientsClient:
    def tracking(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        return handler(request)

    client = YclientsClient(settings)
    client.client = httpx.AsyncClient(
        base_url=settings.yclients_base_url,
        transport=httpx.MockTransport(tracking),
        headers={"Authorization": "test"},
    )
    return client


def default_handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path.endswith("/book_services/123"):
        return httpx.Response(
            200,
            json={
                "data": {
                    "services": [
                        {"id": 456, "title": "Комбинированный маникюр"},
                        {"id": 789, "title": "Коррекция бровей"},
                    ]
                }
            },
        )
    if path.endswith("/book_staff/123"):
        return httpx.Response(
            200,
            json={
                "data": [
                    {"id": 77, "name": "Юлия", "bookable": True},
                    {"id": 78, "name": "Уволенная", "bookable": True, "fired": 1},
                ]
            },
        )
    if path.endswith("/book_times/123/0/2026-07-25"):
        return httpx.Response(
            200,
            json={
                "data": [
                    {"time": "15:00"},
                    {"datetime": "2026-07-25T15:30:00+08:00"},
                    {"time": "мусор"},
                ]
            },
        )
    if path.endswith("/book_times/123/77/2026-07-25"):
        return httpx.Response(200, json={"data": [{"time": "16:30"}]})
    return httpx.Response(404, json={"message": "not found"})


@pytest.mark.asyncio
async def test_slots_for_any_staff_use_single_request(tmp_path) -> None:
    settings = build_settings(tmp_path)
    requests: list[str] = []
    client = build_client(settings, default_handler, requests)
    try:
        assert await client.get_available_slots("2026-07-25", service_id=456) == [
            "15:00",
            "15:30",
        ]
    finally:
        await client.close()
    # Один запрос на дату вместо обхода всех мастеров.
    assert len(requests) == 1
    assert "/book_times/123/0/2026-07-25" in requests[0]
    assert "service_ids%5B%5D=456" in requests[0]


@pytest.mark.asyncio
async def test_slots_for_selected_staff(tmp_path) -> None:
    settings = build_settings(tmp_path)
    requests: list[str] = []
    client = build_client(settings, default_handler, requests)
    try:
        assert await client.get_available_slots(
            "2026-07-25", service_id=456, staff_id=77
        ) == ["16:30"]
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_services_are_cached_and_searchable(tmp_path) -> None:
    settings = build_settings(tmp_path)
    requests: list[str] = []
    client = build_client(settings, default_handler, requests)
    try:
        assert await client.search_services("маник") == [(456, "Комбинированный маникюр")]
        assert await client.search_services("бров") == [(789, "Коррекция бровей")]
        assert await client.search_services("депиляция") == []
    finally:
        await client.close()
    assert len(requests) == 1  # второй поиск взял услуги из кэша


@pytest.mark.asyncio
async def test_fired_staff_is_not_offered(tmp_path) -> None:
    settings = build_settings(tmp_path)
    client = build_client(settings, default_handler, [])
    try:
        assert await client.get_staff(456) == [(77, "Юлия")]
    finally:
        await client.close()
