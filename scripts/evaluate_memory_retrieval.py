from __future__ import annotations

import argparse
import json
import os
import random
import time
from pathlib import Path
from typing import Any

import httpx
from dotenv import find_dotenv, load_dotenv


DEFAULT_SEARCH_URL = "https://api-knowledgebase.mlp.cn-beijing.volces.com/api/memory/search"


def load_manifest(path: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            items.append(json.loads(line))
    return items


def select_cases(
    items: list[dict[str, Any]],
    *,
    limit: int,
    seed: int,
    mode: str,
) -> list[dict[str, Any]]:
    if limit <= 0 or limit >= len(items):
        limit = len(items)

    if mode == "first":
        return items[:limit]

    rng = random.Random(seed)
    return rng.sample(items, limit)


def extract_answer(original_messages: str) -> str:
    answer = ""
    for line in original_messages.splitlines():
        if "hotel_faq_assistant" in line and ":" in line:
            answer = line.split(":", 1)[1].strip()
    return answer


def extract_question(original_messages: str) -> str:
    for line in original_messages.splitlines():
        if "hotel_lobby_user" in line and ":" in line:
            return line.split(":", 1)[1].strip()
    return ""


def classify_case(expected_answer: str) -> str:
    return "handoff" if expected_answer.strip() == "转接" else "direct"


def build_payload(
    query: str,
    *,
    collection_name: str,
    project_name: str,
    user_id: str,
    assistant_id: str | None,
    limit: int,
) -> dict[str, Any]:
    filter_payload: dict[str, Any] = {
        "user_id": user_id,
        "memory_type": ["event_v1"],
    }
    if assistant_id:
        filter_payload["assistant_id"] = assistant_id

    return {
        "collection_name": collection_name,
        "project_name": project_name,
        "query": query,
        "limit": limit,
        "filter": filter_payload,
    }


def summarize_results(cases: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(cases)
    top1_ok = sum(1 for case in cases if case["top1_exact_match"])
    topk_ok = sum(1 for case in cases if case["topk_contains_exact"])
    no_hit = sum(1 for case in cases if not case["hits"])

    by_type: dict[str, dict[str, int]] = {}
    for label in {"direct", "handoff"}:
        scoped = [case for case in cases if case["case_type"] == label]
        if not scoped:
            continue
        by_type[label] = {
            "total": len(scoped),
            "top1_exact_match": sum(1 for case in scoped if case["top1_exact_match"]),
            "topk_contains_exact": sum(1 for case in scoped if case["topk_contains_exact"]),
            "no_hit": sum(1 for case in scoped if not case["hits"]),
        }

    misses = [
        {
            "row_number": case["row_number"],
            "query": case["query"],
            "expected_answer": case["expected_answer"],
            "top1_answer": case["top1_answer"],
            "top1_score": case["top1_score"],
        }
        for case in cases
        if not case["top1_exact_match"]
    ]

    return {
        "total": total,
        "top1_exact_match": top1_ok,
        "top1_exact_match_rate": round((top1_ok / total) * 100, 2) if total else 0,
        "topk_contains_exact": topk_ok,
        "topk_contains_exact_rate": round((topk_ok / total) * 100, 2) if total else 0,
        "no_hit": no_hit,
        "by_type": by_type,
        "top1_misses": misses[:20],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("data/memory_session_manifest_lis_south_station.jsonl"),
    )
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--sample-mode", choices=["random", "first"], default="random")
    parser.add_argument("--seed", type=int, default=20260415)
    parser.add_argument(
        "--search-url",
        default=os.getenv("VOLCENGINE_MEMORY_SEARCH_API_URL", DEFAULT_SEARCH_URL),
    )
    parser.add_argument(
        "--collection-name",
        default=os.getenv("VOLCENGINE_MEMORY_COLLECTION_NAME", "jiudianwenti"),
    )
    parser.add_argument(
        "--project-name",
        default=os.getenv("VOLCENGINE_MEMORY_PROJECT_NAME", "default"),
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("VOLCENGINE_MEMORY_API_KEY", ""),
    )
    parser.add_argument(
        "--user-id",
        default=os.getenv("VOLCENGINE_MEMORY_DEFAULT_USER_ID", "hotel_lobby_user"),
    )
    parser.add_argument("--assistant-id", default="hotel_faq_assistant")
    parser.add_argument("--search-limit", type=int, default=3)
    parser.add_argument("--throttle-seconds", type=float, default=0.1)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> None:
    dotenv_path = find_dotenv(usecwd=True)
    if dotenv_path:
        load_dotenv(dotenv_path)

    args = parse_args()
    if not args.api_key:
        raise SystemExit("VOLCENGINE_MEMORY_API_KEY 未配置，无法执行评测。")

    items = load_manifest(args.manifest)
    cases = select_cases(
        items,
        limit=args.limit,
        seed=args.seed,
        mode=args.sample_mode,
    )

    headers = {
        "Authorization": f"Bearer {args.api_key}",
        "Content-Type": "application/json",
    }

    evaluated_cases: list[dict[str, Any]] = []
    with httpx.Client(timeout=args.timeout) as client:
        for case in cases:
            payload = build_payload(
                case["question"],
                collection_name=args.collection_name,
                project_name=args.project_name,
                user_id=args.user_id,
                assistant_id=args.assistant_id or None,
                limit=args.search_limit,
            )
            response = client.post(args.search_url, headers=headers, json=payload)
            response.raise_for_status()
            body = response.json()
            results = (body.get("data") or {}).get("result_list") or []

            hits = []
            for result in results:
                original_messages = (result.get("memory_info") or {}).get(
                    "original_messages", ""
                )
                hits.append(
                    {
                        "score": result.get("score"),
                        "session_id": result.get("session_id"),
                        "matched_question": extract_question(original_messages),
                        "matched_answer": extract_answer(original_messages),
                        "memory_type": result.get("memory_type"),
                        "summary": (result.get("memory_info") or {}).get("summary", ""),
                    }
                )

            top1 = hits[0] if hits else None
            expected_answer = case["answer"]
            top1_answer = top1["matched_answer"] if top1 else ""
            topk_contains_exact = any(
                hit["matched_answer"] == expected_answer for hit in hits
            )

            evaluated_cases.append(
                {
                    "row_number": case["row_number"],
                    "query": case["question"],
                    "expected_answer": expected_answer,
                    "case_type": classify_case(expected_answer),
                    "top1_exact_match": top1_answer == expected_answer,
                    "topk_contains_exact": topk_contains_exact,
                    "top1_score": top1["score"] if top1 else None,
                    "top1_session_id": top1["session_id"] if top1 else "",
                    "top1_question": top1["matched_question"] if top1 else "",
                    "top1_answer": top1_answer,
                    "hits": hits,
                }
            )

            if args.throttle_seconds > 0:
                time.sleep(args.throttle_seconds)

    payload = {
        "meta": {
            "manifest": str(args.manifest),
            "search_url": args.search_url,
            "collection_name": args.collection_name,
            "project_name": args.project_name,
            "sample_mode": args.sample_mode,
            "seed": args.seed,
            "requested_limit": args.limit,
            "actual_limit": len(evaluated_cases),
            "search_limit": args.search_limit,
        },
        "summary": summarize_results(evaluated_cases),
        "cases": evaluated_cases,
    }

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    print(json.dumps(payload["meta"], ensure_ascii=False, indent=2))
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
