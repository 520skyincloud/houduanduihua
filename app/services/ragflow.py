from __future__ import annotations

from typing import Any

import httpx

from app.config import settings
from app.models import ResolvedAnswer
from app.services.faq_store import FAQStore
from app.services.search import resolve_answer, to_speak_text


class RAGFlowFacade:
    def __init__(self, store: FAQStore) -> None:
        self._store = store

    async def resolve(self, query: str) -> ResolvedAnswer:
        remote = await self._resolve_remote(query)
        if remote is not None:
            return remote
        return resolve_answer(query, self._store.items)

    async def _resolve_remote(self, query: str) -> ResolvedAnswer | None:
        if not settings.ragflow_search_url:
            return None

        headers = {"Content-Type": "application/json"}
        if settings.ragflow_api_key:
            headers["Authorization"] = f"Bearer {settings.ragflow_api_key}"

        body: dict[str, Any] = {
            "question": query,
            "query": query,
            "dataset_id": settings.ragflow_dataset_id,
            "top_k": 3,
        }

        try:
            async with httpx.AsyncClient(timeout=settings.ragflow_timeout_seconds) as client:
                response = await client.post(settings.ragflow_search_url, headers=headers, json=body)
                response.raise_for_status()
        except Exception:
            return None

        payload = response.json()
        answer = self._extract_text(payload)
        if not answer:
            return None

        return ResolvedAnswer(
            status="answered",
            faq_id=None,
            confidence=1.0,
            needs_handoff=False,
            display_text=answer,
            speak_text=to_speak_text(answer),
        )

    def _extract_text(self, payload: Any) -> str:
        if isinstance(payload, str):
            return payload
        if isinstance(payload, list):
            for item in payload:
                text = self._extract_text(item)
                if text:
                    return text
            return ""
        if not isinstance(payload, dict):
            return ""

        for key in ("answer", "content", "text", "message"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

        for key in ("data", "results", "records", "chunks"):
            value = payload.get(key)
            text = self._extract_text(value)
            if text:
                return text
        return ""
