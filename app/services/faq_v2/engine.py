from __future__ import annotations

from dataclasses import asdict
from functools import lru_cache
from pathlib import Path
from time import perf_counter
from typing import Any

from .data import load_faq_v2_entries
from .lexicon import get_clarify_question
from .normalize import normalize_faq_text
from .retrieve import detect_faq_signals, retrieve_faq_candidates
from .rerank import get_clarify_message, rerank_faq_candidates
from .types import FaqMatch, FaqResolution


DIRECT_THRESHOLD = 0.78
ALIAS_DIRECT_THRESHOLD = 0.58
CLARIFY_THRESHOLD = 0.5
MIN_MARGIN = 0.12


def _build_top_matches(query: str, limit: int) -> list[FaqMatch]:
    entries = load_faq_v2_entries()
    retrieved = retrieve_faq_candidates(query, entries, max(5, limit))
    return rerank_faq_candidates(query, retrieved)[:limit]


def _decide_faq(top_matches: list[FaqMatch]) -> tuple[str, float, str | None, str | None]:
    top1 = top_matches[0] if top_matches else None
    if top1 is None:
        return "miss", 0.0, None, None

    top2 = top_matches[1] if len(top_matches) > 1 else None
    margin = (top1.score - top2.score) if top2 else top1.score
    same_bucket = bool(top2 and top1.intent == top2.intent and top1.subIntent == top2.subIntent)
    has_alias_signal = any(reason.startswith("alias_exact:") or reason.startswith("alias_contains:") for reason in top1.reasons)

    if top1.score >= DIRECT_THRESHOLD and (margin >= MIN_MARGIN or same_bucket):
        return "direct", top1.score, top1.answer, None

    if top1.score >= ALIAS_DIRECT_THRESHOLD and has_alias_signal and top1.intent != "handoff":
        if not top2 or margin >= 0.08 or same_bucket:
            return "direct", top1.score, top1.answer, None

    if top1.intent == "handoff" and top1.score >= 0.66 and any(
        reason.startswith("alias_") or reason.startswith("signal:") or reason.startswith("handoff:") for reason in top1.reasons
    ):
        return "direct", top1.score, top1.answer, None

    if top1.score >= CLARIFY_THRESHOLD:
        return "clarify", top1.score, None, get_clarify_question(top1.intent) or get_clarify_message(top1.intent)

    return "miss", top1.score, None, None


def resolve_faq_v2_query(query: str, options: dict[str, Any] | None = None) -> FaqResolution:
    started = perf_counter()
    trimmed = query.strip()
    normalized_query = normalize_faq_text(trimmed)
    if not trimmed:
        return FaqResolution(
            decision="miss",
            answer=None,
            clarifyQuestion=None,
            confidence=0.0,
            topMatches=[],
            normalizedQuery=normalized_query,
        )

    limit = int(options.get("limit", 5)) if options else 5
    top_matches = _build_top_matches(trimmed, limit)
    query_signals = detect_faq_signals(trimmed)

    if "pet" in query_signals and not any(match.intent == "pet" for match in top_matches):
        return FaqResolution(
            decision="miss",
            answer=None,
            clarifyQuestion=None,
            confidence=0.0,
            topMatches=top_matches,
            normalizedQuery=normalized_query,
            elapsedMs=round((perf_counter() - started) * 1000, 2),
        )

    if "pool" in query_signals and not any(match.intent == "pool" for match in top_matches):
        return FaqResolution(
            decision="miss",
            answer=None,
            clarifyQuestion=None,
            confidence=0.0,
            topMatches=top_matches,
            normalizedQuery=normalized_query,
            elapsedMs=round((perf_counter() - started) * 1000, 2),
        )

    decision, confidence, answer, clarify_question = _decide_faq(top_matches)
    return FaqResolution(
        decision=decision,  # type: ignore[arg-type]
        answer=answer.strip() if isinstance(answer, str) and answer.strip() else None,
        clarifyQuestion=clarify_question,
        confidence=round(confidence, 4),
        topMatches=top_matches,
        normalizedQuery=normalized_query,
        topMatch=top_matches[0] if top_matches else None,
        elapsedMs=round((perf_counter() - started) * 1000, 2),
    )


class FaqV2Experiment:
    def __init__(self) -> None:
        self._entries = load_faq_v2_entries()

    @property
    def items(self) -> list[dict[str, Any]]:
        return [entry.to_dict() for entry in self._entries]

    def query(self, query: str, limit: int = 5) -> dict[str, Any]:
        resolution = resolve_faq_v2_query(query, {"limit": limit})
        payload = resolution.to_dict()
        payload["top_match"] = payload.get("top_match") or (payload["topMatches"][0] if payload["topMatches"] else None)
        return payload

    def benchmark(self) -> dict[str, Any]:
        cases = [
            {"query": "有没有停车场", "expect_any": ["免费停车", "地上停车场", "停车场"], "forbid": ["充电桩"]},
            {"query": "停车场怎么收费", "expect_any": ["免费", "停车场"]},
            {"query": "停车场在哪", "expect_any": ["繁华大道辅路", "停车场入口"]},
            {"query": "酒店有早餐吗", "expect_any": ["暂不提供早餐", "不提供早餐"]},
            {"query": "退房时间几点", "expect_any": ["12点", "退房时间"], "forbid": ["入住"]},
            {"query": "发票怎么开", "expect_any": ["电子", "发票", "小程序"]},
            {"query": "有没有暗房", "expect_any": ["没有暗房", "有窗户"]},
            {"query": "有没有一次性剃须刀", "expect_any": ["剃须刀", "洗衣房"]},
            {"query": "健身房在哪", "expect_any": ["不提供健身房", "周边"]},
            {"query": "你们有游泳池吗", "expect_not_found": True},
        ]
        rows: list[dict[str, Any]] = []
        passed = 0
        total_elapsed = 0.0
        for case in cases:
            result = self.query(case["query"])
            total_elapsed += float(result.get("elapsed_ms") or 0.0)
            top_answer = ((result.get("top_match") or {}).get("answer") or "")
            answer_norm = normalize_faq_text(top_answer)
            ok = False
            if case.get("expect_not_found"):
                ok = result["decision"] == "miss"
            else:
                expected = [normalize_faq_text(item) for item in case.get("expect_any", [])]
                forbidden = [normalize_faq_text(item) for item in case.get("forbid", [])]
                ok = result["decision"] == "direct" and any(token in answer_norm for token in expected)
                if ok and forbidden:
                    ok = not any(token in answer_norm for token in forbidden)
            if ok:
                passed += 1
            rows.append(
                {
                    "query": case["query"],
                    "ok": ok,
                    "decision": result["decision"],
                    "elapsed_ms": result.get("elapsed_ms"),
                    "top_match": result.get("top_match"),
                }
            )

        return {
            "cases": rows,
            "passed": passed,
            "total": len(cases),
            "accuracy": round(passed / len(cases), 4),
            "avg_elapsed_ms": round(total_elapsed / len(cases), 2),
        }
