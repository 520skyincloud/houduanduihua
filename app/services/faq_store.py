from __future__ import annotations

import json
from pathlib import Path

from app.models import FAQItem


class FAQStore:
    def __init__(self, faq_index_path: Path) -> None:
        self._faq_index_path = faq_index_path
        self._items: list[FAQItem] = []
        self.reload()

    def reload(self) -> None:
        if not self._faq_index_path.exists():
            self._items = []
            return

        payload = json.loads(self._faq_index_path.read_text(encoding="utf-8"))
        self._items = [
            FAQItem(
                faq_id=item["faq_id"],
                hotel_id=item["hotel_id"],
                standard_answer=item["standard_answer"],
                aliases=item["aliases"],
                answer_type=item["answer_type"],
                source_rows=item.get("source_rows", []),
            )
            for item in payload.get("items", [])
        ]

    @property
    def items(self) -> list[FAQItem]:
        return self._items

    def stats(self) -> dict[str, int]:
        return {
            "faq_items": len(self._items),
            "direct": sum(1 for item in self._items if item.answer_type == "direct"),
            "handoff": sum(1 for item in self._items if item.answer_type == "handoff"),
            "invalid": sum(1 for item in self._items if item.answer_type == "invalid"),
        }
