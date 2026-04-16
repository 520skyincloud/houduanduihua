from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from .lexicon import FAQ_DOMAIN_TERMS, SIGNAL_PATTERNS
from .normalize import build_char_ngrams, compact_faq_text, extract_matched_terms, jaccard_similarity, normalize_faq_text
from .types import FaqEntry


BROAD_INTENT_SIGNALS = {
    "parking",
    "invoice",
    "checkout",
    "breakfast",
    "location",
    "handoff",
    "pet",
    "pool",
    "wifi",
    "voice_control",
    "projector",
    "laundry",
    "laundry_access",
    "luggage",
    "room",
    "amenity",
    "meeting",
    "gym",
    "frontdesk",
    "nearby",
    "service",
    "tech",
    "facility",
}

GENERIC_QUESTION_PATTERNS = [re.compile(pattern) for pattern in [r"怎么", r"如何", r"怎么办", r"怎样", r"可以吗", r"能吗", r"行吗", r"要不要", r"是否"]]


@dataclass
class RetrievedFaqCandidate:
    entry: FaqEntry
    score: float
    reasons: list[str]
    matchedAliases: list[str]
    matchedKeywords: list[str]
    matchedSignals: list[str]
    queryCompact: str
    querySignals: list[str]


def detect_faq_signals(query: str) -> list[str]:
    normalized = normalize_faq_text(query)
    signals: set[str] = set()

    for signal, pattern in SIGNAL_PATTERNS:
        if re.search(pattern, normalized):
            signals.add(signal)

    for pattern in GENERIC_QUESTION_PATTERNS:
        if pattern.search(normalized):
            signals.add("generic_question")
            break

    return list(signals)


def _split_signals(signals: list[str]) -> dict[str, list[str]]:
    intent_signals: list[str] = []
    sub_intent_signals: list[str] = []
    generic_signals: list[str] = []

    for signal in signals:
        if signal == "generic_question":
            generic_signals.append(signal)
            continue
        if signal in BROAD_INTENT_SIGNALS:
            intent_signals.append(signal)
        else:
            sub_intent_signals.append(signal)

    return {
        "intent_signals": intent_signals,
        "sub_intent_signals": sub_intent_signals,
        "generic_signals": generic_signals,
    }


def _score_alias(query_compact: str, alias: str) -> tuple[float, Optional[str], str]:
    alias_compact = compact_faq_text(alias)
    if not alias_compact:
        return 0.0, None, alias_compact
    if alias_compact == query_compact:
        return 1.0, f"alias_exact:{alias}", alias_compact

    contains = query_compact in alias_compact or alias_compact in query_compact
    alias_ngrams2 = build_char_ngrams(alias_compact, [2])
    alias_ngrams3 = build_char_ngrams(alias_compact, [3])
    query_ngrams2 = build_char_ngrams(query_compact, [2])
    query_ngrams3 = build_char_ngrams(query_compact, [3])
    ngram_score = max(jaccard_similarity(query_ngrams2, alias_ngrams2), jaccard_similarity(query_ngrams3, alias_ngrams3))
    contains_score = 0.92 if contains else 0.0
    score = max(contains_score, ngram_score * 0.85)
    return score, (f"alias_contains:{alias}" if contains else None), alias_compact


def retrieve_faq_candidates(query: str, entries: list[FaqEntry], limit: int = 5) -> list[RetrievedFaqCandidate]:
    query_compact = compact_faq_text(query)
    query_signals = detect_faq_signals(query)
    signal_groups = _split_signals(query_signals)
    query_terms = extract_matched_terms(query, list(FAQ_DOMAIN_TERMS))
    query_ngrams2 = build_char_ngrams(query_compact, [2])
    query_ngrams3 = build_char_ngrams(query_compact, [3])

    candidates: list[RetrievedFaqCandidate] = []
    for entry in entries:
        best_alias_score = 0.0
        best_alias_reason: Optional[str] = None
        matched_aliases: list[str] = []
        for alias in entry.aliases:
            alias_score, alias_reason, _ = _score_alias(query_compact, alias)
            if alias_score > best_alias_score:
                best_alias_score = alias_score
                best_alias_reason = alias_reason
            if alias_reason:
                matched_aliases.append(alias)

        entry_keywords = entry.keywords or extract_matched_terms(" ".join([entry.canonicalQuestion, entry.answer]), list(FAQ_DOMAIN_TERMS))
        matched_keywords = [term for term in query_terms if term in entry_keywords]
        keyword_score = min(0.42, len(matched_keywords) * 0.13) if matched_keywords else 0.0

        entry_signals = {entry.intent, entry.subIntent, entry.clarifyGroup or ""}
        matched_signals = [signal for signal in query_signals if signal in entry_signals]
        signal_score = min(0.6, len(matched_signals) * 0.3) if matched_signals else 0.0

        canonical_compact = compact_faq_text(entry.canonicalQuestion)
        question_overlap = max(
            jaccard_similarity(query_ngrams2, build_char_ngrams(canonical_compact, [2])),
            jaccard_similarity(query_ngrams3, build_char_ngrams(canonical_compact, [3])),
        )
        contains_canonical = bool(canonical_compact) and (
            query_compact in canonical_compact or canonical_compact in query_compact
        )
        canonical_boost = 0.22 if contains_canonical else 0.0
        length_penalty = 0.08 if len(query_compact) <= 4 else 0.0
        score = max(
            0.0,
            min(
                1.0,
                best_alias_score * 0.55
                + canonical_boost
                + question_overlap * 0.15
                + keyword_score
                + signal_score
                - length_penalty,
            ),
        )

        reasons = []
        if best_alias_reason:
            reasons.append(best_alias_reason)
        if question_overlap > 0:
            reasons.append(f"ngram:{question_overlap:.2f}")
        if matched_keywords:
            reasons.append(f"keyword:{','.join(matched_keywords[:4])}")
        if matched_signals:
            reasons.append(f"signal:{','.join(matched_signals)}")
        if signal_groups["generic_signals"]:
            reasons.append("generic_question")

        candidates.append(
            RetrievedFaqCandidate(
                entry=entry,
                score=round(score, 4),
                reasons=reasons,
                matchedAliases=matched_aliases,
                matchedKeywords=matched_keywords,
                matchedSignals=matched_signals,
                queryCompact=query_compact,
                querySignals=query_signals,
            )
        )

    candidates.sort(key=lambda item: item.score, reverse=True)
    return candidates[:limit]
