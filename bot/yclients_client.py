from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from .config import Settings


logger = logging.getLogger(__name__)

SERVICES_CACHE_TTL_SECONDS = 6 * 60 * 60
ANY_STAFF_ID = 0


class YclientsError(RuntimeError):
    """A short, safe-to-display Yclients integration error."""


def extract_slot_time(slot: Any) -> str | None:
    """Приводит слот Yclients к «ЧЧ:ММ»."""
    if not isinstance(slot, dict):
        return None
    value = str(slot.get("time") or slot.get("datetime") or "")
    if "T" in value:
        value = value.split("T", 1)[1][:5]
    elif " " in value:
        value = value.split(" ", 1)[1][:5]
    else:
        value = value[:5]
    return value if len(value) == 5 and value[2] == ":" else None


class YclientsClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = httpx.AsyncClient(
            base_url=settings.yclients_base_url,
            timeout=httpx.Timeout(20.0),
            headers={
                "Accept": "application/vnd.yclients.v2+json",
                "Content-Type": "application/json",
                "Authorization": (
                    f"Bearer {settings.yclients_bearer_token}, "
                    f"User {settings.yclients_user_token}"
                ),
            },
        )
        self._services_cache: list[tuple[int, str]] | None = None
        self._services_cached_at = 0.0

    async def close(self) -> None:
        await self.client.aclose()

    async def _get(self, path: str, params: list[tuple[str, str]] | None = None) -> Any:
        try:
            response = await self.client.get(path.lstrip("/"), params=params)
            response.raise_for_status()
            body = response.json()
            return body.get("data", body) if isinstance(body, dict) else body
        except httpx.HTTPStatusError as exc:
            message = f"Yclients вернул HTTP {exc.response.status_code}"
            try:
                body = exc.response.json()
                message = body.get("meta", {}).get("message") or body.get("message") or message
            except (ValueError, AttributeError):
                pass
            logger.warning("Yclients API error: %s", message)
            raise YclientsError(str(message)) from exc
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("Yclients connection/response error: %s", exc)
            raise YclientsError("Yclients временно недоступен") from exc

    def _require_ready(self) -> int:
        readiness_error = self.settings.yclients_readiness_error
        if readiness_error:
            raise YclientsError(readiness_error)
        company_id = self.settings.yclients_company_id
        assert company_id is not None
        return company_id

    async def get_services(self) -> list[tuple[int, str]]:
        """Онлайн-услуги филиала: (id, название). Кэш на 6 часов."""
        now = time.monotonic()
        if (
            self._services_cache is not None
            and now - self._services_cached_at < SERVICES_CACHE_TTL_SECONDS
        ):
            return self._services_cache

        company_id = self._require_ready()
        data = await self._get(f"/book_services/{company_id}")
        raw = data.get("services") if isinstance(data, dict) else data
        if not isinstance(raw, list):
            raise YclientsError("Yclients вернул неожиданный список услуг")
        services = [
            (int(item["id"]), str(item.get("title") or "").strip())
            for item in raw
            if isinstance(item, dict) and item.get("id") is not None
        ]
        self._services_cache = [item for item in services if item[1]]
        self._services_cached_at = now
        return self._services_cache

    async def search_services(self, query: str, limit: int = 8) -> list[tuple[int, str]]:
        needle = query.strip().casefold().replace("ё", "е")
        services = await self.get_services()
        if not needle:
            return services[:limit]
        matches = [
            item for item in services if needle in item[1].casefold().replace("ё", "е")
        ]
        return matches[:limit]

    async def get_staff(self, service_id: int, limit: int = 12) -> list[tuple[int, str]]:
        """Мастера, доступные для услуги: (id, имя)."""
        company_id = self._require_ready()
        items = await self._get(
            f"/book_staff/{company_id}", params=[("service_id", str(service_id))]
        )
        if not isinstance(items, list):
            raise YclientsError("Yclients вернул неожиданный список мастеров")
        staff = [
            (int(item["id"]), str(item.get("name") or "").strip())
            for item in items
            if isinstance(item, dict)
            and item.get("id") is not None
            and item.get("bookable") is not False
            and not item.get("fired")
            and not item.get("is_fired")
        ]
        return [item for item in staff if item[1]][:limit]

    async def get_available_slots(
        self,
        desired_date: str,
        service_id: int | None = None,
        staff_id: int | None = None,
    ) -> list[str]:
        """Свободные окна на дату. staff_id=None — сразу по всем мастерам."""
        company_id = self._require_ready()
        service_id = service_id or self.settings.yclients_service_id
        if service_id is None:
            raise YclientsError(
                "Не выбрана услуга. Укажите её в заявке или заполните "
                "YCLIENTS_SERVICE_ID в .env."
            )

        data = await self._get(
            f"/book_times/{company_id}/{staff_id or ANY_STAFF_ID}/{desired_date}",
            params=[("service_ids[]", str(service_id))],
        )
        if not isinstance(data, list):
            return []
        slots = {value for value in map(extract_slot_time, data) if value}
        return sorted(slots)
