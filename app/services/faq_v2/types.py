from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Literal, Optional


FaqDecision = Literal["direct", "clarify", "miss"]


@dataclass
class FaqEntry:
    id: str
    canonicalQuestion: str
    aliases: list[str]
    answer: str
    intent: str
    subIntent: str
    keywords: list[str]
    negativeKeywords: list[str] = field(default_factory=list)
    handoff: bool = False
    clarifyGroup: Optional[str] = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class FaqMatch:
    id: str
    canonicalQuestion: str
    answer: str
    intent: str
    subIntent: str
    score: float
    reasons: list[str]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class FaqResolution:
    decision: FaqDecision
    answer: Optional[str]
    clarifyQuestion: Optional[str]
    confidence: float
    topMatches: list[FaqMatch]
    normalizedQuery: str
    topMatch: Optional[FaqMatch] = None
    elapsedMs: float = 0.0

    def to_dict(self) -> dict[str, object]:
        return {
            "decision": self.decision,
            "answer": self.answer,
            "clarifyQuestion": self.clarifyQuestion,
            "confidence": self.confidence,
            "topMatches": [item.to_dict() for item in self.topMatches],
            "top_match": self.topMatch.to_dict() if self.topMatch else None,
            "normalizedQuery": self.normalizedQuery,
            "elapsed_ms": self.elapsedMs,
        }
