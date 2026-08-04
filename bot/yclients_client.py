from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from .config import Settings


logger = logging.getLogger(__name__)


class YclientsError(RuntimeError):
    """A short, safe-to-display Yclients integration error."""


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

    async def get_available_slots(self, desired_date: str) -> list[str]:
        readiness_error = self.settings.yclients_readiness_error
        if readiness_error:
            raise YclientsError(readiness_error)

        company_id = self.settings.yclients_company_id
        service_id = self.settings.yclients_service_id
        staff_id = self.settings.yclients_staff_id
        assert company_id is not None and service_id is not None

        staff_items = await self._get(
            f"/book_staff/{company_id}",
            params=[("service_id", str(service_id))],
        )
        if not isinstance(staff_items, list):
            raise YclientsError("Yclients вернул неожиданный список мастеров")

        bookable_staff = [
            item
            for item in staff_items
            if isinstance(item, dict)
            and item.get("bookable") is not False
            and not item.get("fired")
            and not item.get("is_fired")
        ]
        if staff_id is not None:
            bookable_staff = [
                item for item in bookable_staff if str(item.get("id")) == str(staff_id)
            ]
        if not bookable_staff:
            return []

        async def fetch_times(item: dict[str, Any]) -> list[str]:
            current_staff_id = item.get("id")
            data = await self._get(
                f"/book_times/{company_id}/{current_staff_id}/{desired_date}",
                params=[("service_ids[]", str(service_id))],
            )
            if not isinstance(data, list):
                return []
            result: list[str] = []
            for slot in data:
                if not isinstance(slot, dict):
                    continue
                value = str(slot.get("time") or slot.get("datetime") or "")
                if "T" in value:
                    value = value.split("T", 1)[1][:5]
                elif " " in value:
                    value = value.split(" ", 1)[1][:5]
                else:
                    value = value[:5]
                if len(value) == 5 and value[2] == ":":
                    result.append(value)
            return result

        responses = await asyncio.gather(
            *(fetch_times(item) for item in bookable_staff[:12]),
            return_exceptions=True,
        )
        successful_calls = 0
        slots: set[str] = set()
        first_error: Exception | None = None
        for response in responses:
            if isinstance(response, Exception):
                first_error = first_error or response
                continue
            successful_calls += 1
            slots.update(response)
        if successful_calls == 0 and first_error is not None:
            raise YclientsError(str(first_error)) from first_error
        return sorted(slots)
