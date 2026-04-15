from __future__ import annotations

from typing import Any

import httpx

from app.config import settings


class MemoryFacade:
    @staticmethod
    def _event_filter(user_id: str | None = None) -> dict[str, Any]:
        filter_payload: dict[str, Any] = {
            "user_id": user_id or settings.volcengine_memory_default_user_id,
            "memory_type": ["event_v1"],
        }
        if settings.volcengine_memory_native_assistant_ids:
            filter_payload["assistant_id"] = settings.volcengine_memory_native_assistant_ids
        return filter_payload

    @staticmethod
    def _profile_filter(user_id: str | None = None) -> dict[str, Any]:
        filter_payload: dict[str, Any] = {
            "user_id": user_id or settings.volcengine_memory_default_user_id,
            "memory_type": ["profile_v1"],
        }
        if settings.volcengine_memory_native_assistant_ids:
            filter_payload["assistant_id"] = settings.volcengine_memory_native_assistant_ids
        return filter_payload

    async def get_context(
        self,
        query: str,
        conversation_id: str,
        user_id: str | None = None,
    ) -> dict[str, Any] | None:
        if not settings.memory_api_ready:
            return None

        payload = {
            "collection_name": settings.volcengine_memory_collection_name,
            "project_name": settings.volcengine_memory_project_name,
            "conversation_id": conversation_id,
            "query": query,
            "event_search_config": {
                "filter": self._event_filter(user_id),
                "limit": 10,
                "time_decay_config": {
                    "weight": 0.5,
                    "no_decay_period": 3,
                },
            },
            "profile_search_config": {
                "filter": self._profile_filter(user_id),
                "limit": 1,
            },
        }
        headers = {
            "Authorization": f"Bearer {settings.volcengine_memory_api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                settings.volcengine_memory_api_base_url,
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            return response.json()
