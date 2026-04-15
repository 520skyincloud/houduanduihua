from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from dotenv import find_dotenv, load_dotenv

from import_faq import read_xlsx_rows


DEFAULT_ADD_URL = (
    "https://api-knowledgebase.mlp.cn-beijing.volces.com/api/memory/session/add"
)
TRANSFER_ANSWER = "转接"


@dataclass(frozen=True)
class SessionRecord:
    row_number: int
    session_id: str
    question: str
    answer: str
    user_time: int
    assistant_time: int
    metadata_time: int

    def to_payload(
        self,
        *,
        collection_name: str,
        project_name: str,
        default_user_id: str,
        default_user_name: str,
        default_assistant_id: str,
        default_assistant_name: str,
    ) -> dict[str, Any]:
        return {
            "collection_name": collection_name,
            "project_name": project_name,
            "session_id": self.session_id,
            "messages": [
                {
                    "role": "user",
                    "content": self.question,
                    "time": self.user_time,
                },
                {
                    "role": "assistant",
                    "content": self.answer,
                    "time": self.assistant_time,
                },
            ],
            "metadata": {
                "default_user_id": default_user_id,
                "default_user_name": default_user_name,
                "default_assistant_id": default_assistant_id,
                "default_assistant_name": default_assistant_name,
                "time": self.metadata_time,
            },
        }


def sanitize_session_prefix(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_]+", "_", value).strip("_")
    if not cleaned:
        cleaned = "faq_import"
    if not cleaned[0].isalpha():
        cleaned = f"faq_{cleaned}"
    return cleaned[:48]


def default_session_prefix(input_path: Path) -> str:
    digest = hashlib.md5(str(input_path.resolve()).encode("utf-8")).hexdigest()[:8]
    stem = sanitize_session_prefix(input_path.stem)
    return sanitize_session_prefix(f"{stem}_{digest}")


def build_session_id(prefix: str, row_number: int, question: str, answer: str) -> str:
    digest = hashlib.md5(f"{question}\n{answer}".encode("utf-8")).hexdigest()[:10]
    return f"{prefix}_r{row_number:04d}_{digest}"


def build_records(
    rows: list[tuple[str, str, int]],
    *,
    session_prefix: str,
    base_time_ms: int,
    skip_transfer: bool,
) -> tuple[list[SessionRecord], int]:
    records: list[SessionRecord] = []
    skipped_rows = 0
    for offset, (question, answer, row_number) in enumerate(rows):
        question = question.strip()
        answer = answer.strip()
        if not question or not answer:
            skipped_rows += 1
            continue
        if skip_transfer and answer == TRANSFER_ANSWER:
            skipped_rows += 1
            continue

        user_time = base_time_ms + offset * 2
        assistant_time = user_time + 1
        records.append(
            SessionRecord(
                row_number=row_number,
                session_id=build_session_id(session_prefix, row_number, question, answer),
                question=question,
                answer=answer,
                user_time=user_time,
                assistant_time=assistant_time,
                metadata_time=assistant_time,
            )
        )
    return records, skipped_rows


def write_manifest(path: Path, records: list[SessionRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(
                json.dumps(
                    {
                        "row_number": record.row_number,
                        "session_id": record.session_id,
                        "question": record.question,
                        "answer": record.answer,
                        "metadata_time": record.metadata_time,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )


async def upload_record(
    client: httpx.AsyncClient,
    record: SessionRecord,
    *,
    url: str,
    headers: dict[str, str],
    collection_name: str,
    project_name: str,
    default_user_id: str,
    default_user_name: str,
    default_assistant_id: str,
    default_assistant_name: str,
    retries: int,
) -> dict[str, Any]:
    payload = record.to_payload(
        collection_name=collection_name,
        project_name=project_name,
        default_user_id=default_user_id,
        default_user_name=default_user_name,
        default_assistant_id=default_assistant_id,
        default_assistant_name=default_assistant_name,
    )

    last_error = "unknown"
    for attempt in range(1, retries + 1):
        try:
            response = await client.post(url, headers=headers, json=payload)
            body = response.json()
        except (httpx.HTTPError, json.JSONDecodeError) as exc:
            last_error = str(exc)
        else:
            if response.status_code == 200 and body.get("code") == 0:
                data = body.get("data") or {}
                return {
                    "ok": True,
                    "row_number": record.row_number,
                    "session_id": record.session_id,
                    "remote_session_id": data.get("session_id"),
                    "request_id": body.get("request_id"),
                }

            last_error = (
                f"http={response.status_code}, "
                f"code={body.get('code')}, message={body.get('message')}"
            )
            if response.status_code not in {429, 500, 502, 503, 504}:
                break

        if attempt < retries:
            await asyncio.sleep(min(2 ** (attempt - 1), 5))

    return {
        "ok": False,
        "row_number": record.row_number,
        "session_id": record.session_id,
        "error": last_error,
    }


async def upload_records(
    records: list[SessionRecord],
    *,
    url: str,
    api_key: str,
    collection_name: str,
    project_name: str,
    default_user_id: str,
    default_user_name: str,
    default_assistant_id: str,
    default_assistant_name: str,
    concurrency: int,
    retries: int,
    throttle_seconds: float,
    timeout: float,
) -> list[dict[str, Any]]:
    semaphore = asyncio.Semaphore(concurrency)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=timeout) as client:
        async def worker(record: SessionRecord) -> dict[str, Any]:
            async with semaphore:
                result = await upload_record(
                    client,
                    record,
                    url=url,
                    headers=headers,
                    collection_name=collection_name,
                    project_name=project_name,
                    default_user_id=default_user_id,
                    default_user_name=default_user_name,
                    default_assistant_id=default_assistant_id,
                    default_assistant_name=default_assistant_name,
                    retries=retries,
                )
                if throttle_seconds > 0:
                    await asyncio.sleep(throttle_seconds)
                return result

        return await asyncio.gather(*(worker(record) for record in records))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument(
        "--api-url",
        default=os.getenv("VOLCENGINE_MEMORY_ADD_API_URL", DEFAULT_ADD_URL),
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
        "--default-user-id",
        default=os.getenv("VOLCENGINE_MEMORY_DEFAULT_USER_ID", "hotel_lobby_user"),
    )
    parser.add_argument("--default-user-name", default="HotelGuest")
    parser.add_argument("--default-assistant-id", default="hotel_faq_assistant")
    parser.add_argument("--default-assistant-name", default="丽斯未来酒店")
    parser.add_argument("--session-prefix", default="")
    parser.add_argument("--manifest-output", type=Path)
    parser.add_argument("--base-time-ms", type=int, default=0)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--throttle-seconds", type=float, default=0.0)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--skip-transfer", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    dotenv_path = find_dotenv(usecwd=True)
    if dotenv_path:
        load_dotenv(dotenv_path)

    args = parse_args()
    rows = read_xlsx_rows(args.input)
    session_prefix = sanitize_session_prefix(
        args.session_prefix or default_session_prefix(args.input)
    )
    base_time_ms = args.base_time_ms or int(time.time() * 1000)

    records, skipped_rows = build_records(
        rows,
        session_prefix=session_prefix,
        base_time_ms=base_time_ms,
        skip_transfer=args.skip_transfer,
    )

    if args.limit > 0:
        records = records[: args.limit]

    if args.manifest_output:
        write_manifest(args.manifest_output, records)

    total_transfer = sum(1 for record in records if record.answer == TRANSFER_ANSWER)
    print(
        json.dumps(
            {
                "input": str(args.input),
                "collection_name": args.collection_name,
                "project_name": args.project_name,
                "session_prefix": session_prefix,
                "total_rows": len(rows),
                "skipped_rows": skipped_rows,
                "records_to_upload": len(records),
                "transfer_records": total_transfer,
                "throttle_seconds": args.throttle_seconds,
                "manifest_output": str(args.manifest_output) if args.manifest_output else None,
                "dry_run": args.dry_run,
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    if args.dry_run:
        return

    if not args.api_key:
        raise SystemExit("VOLCENGINE_MEMORY_API_KEY 未配置，无法执行导入。")
    if not args.collection_name:
        raise SystemExit("VOLCENGINE_MEMORY_COLLECTION_NAME 未配置，无法执行导入。")

    results = asyncio.run(
        upload_records(
            records,
            url=args.api_url,
            api_key=args.api_key,
            collection_name=args.collection_name,
            project_name=args.project_name,
            default_user_id=args.default_user_id,
            default_user_name=args.default_user_name,
            default_assistant_id=args.default_assistant_id,
            default_assistant_name=args.default_assistant_name,
            concurrency=max(args.concurrency, 1),
            retries=max(args.retries, 1),
            throttle_seconds=max(args.throttle_seconds, 0.0),
            timeout=args.timeout,
        )
    )

    success = [item for item in results if item["ok"]]
    failed = [item for item in results if not item["ok"]]
    summary = {
        "uploaded": len(success),
        "failed": len(failed),
        "first_failed": failed[:10],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
