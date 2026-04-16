from __future__ import annotations

import hashlib
import re
import sqlite3
import subprocess
import time
from pathlib import Path
from typing import Any

import httpx

from app.config import settings


class FastGPTFacade:
    def __init__(self) -> None:
        self._cookies: httpx.Cookies | None = None
        self._last_login_at: float = 0.0
        self._cookie_header: str | None = None

    async def validate(self, query: str) -> dict[str, Any]:
        started = time.perf_counter()
        if not settings.fastgpt_enabled:
            return {
                "ok": False,
                "configured": False,
                "detail": "未启用 FastGPT fallback。",
            }
        if not settings.fastgpt_ready:
            return {
                "ok": False,
                "configured": False,
                "detail": "FastGPT 基础配置不完整，请检查 FASTGPT_BASE_URL / USERNAME / PASSWORD / DATASET_ID。",
            }
        try:
            result = await self.search(query)
            return {
                "ok": True,
                "configured": True,
                "result": result,
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
            }
        except Exception as exc:
            return {
                "ok": False,
                "configured": True,
                "detail": str(exc),
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
            }

    async def search(self, query: str) -> dict[str, Any]:
        timeout = settings.fastgpt_timeout_seconds
        async with httpx.AsyncClient(
            base_url=settings.fastgpt_base_url.rstrip("/"),
            timeout=httpx.Timeout(timeout, read=timeout),
            follow_redirects=True,
        ) as client:
            await self._ensure_logged_in(client)
            response = await client.post(
                "/api/core/dataset/searchTest",
                json={
                    "datasetId": settings.fastgpt_dataset_id,
                    "text": query,
                },
                cookies=self._cookies,
                headers=self._auth_headers(),
            )
            payload = self._decode(response)
            candidate = self._extract_candidate(payload)
            return {
                "hit": candidate is not None and self._score_value(candidate.get("score")) >= settings.fastgpt_min_score,
                "answer": candidate.get("answer") if candidate else None,
                "matched_question": candidate.get("question") if candidate else None,
                "score": self._score_value(candidate.get("score")) if candidate else 0.0,
                "source": "fastgpt",
                "raw": payload,
            }

    async def _ensure_logged_in(self, client: httpx.AsyncClient) -> None:
        if (
            self._cookies is not None or self._cookie_header is not None
        ) and (time.time() - self._last_login_at) < 1800:
            return
        browser_cookie = self._load_browser_cookie()
        if browser_cookie:
            if await self._probe_browser_cookie(client, browser_cookie):
                self._cookie_header = f"{settings.fastgpt_browser_cookie_name}={browser_cookie}"
                self._cookies = None
                self._last_login_at = time.time()
                return
        code = await self._prelogin(client)
        await self._login(client, code)
        self._cookies = client.cookies.copy()
        self._cookie_header = None
        self._last_login_at = time.time()

    async def _prelogin(self, client: httpx.AsyncClient) -> str:
        response = await client.get(
            "/api/support/user/account/preLogin",
            params={"username": settings.fastgpt_username},
        )
        payload = self._decode(response)
        code = str((payload.get("data") or {}).get("code") or "").strip()
        if not code:
            raise RuntimeError(f"FastGPT preLogin 未返回验证码: {payload}")
        return code

    async def _login(self, client: httpx.AsyncClient, code: str) -> None:
        response = await client.post(
            "/api/support/user/account/loginByPassword",
            json={
                "username": settings.fastgpt_username,
                "password": hashlib.sha256(
                    (settings.fastgpt_password or "").encode("utf-8")
                ).hexdigest(),
                "code": code,
                "language": settings.fastgpt_language,
            },
        )
        payload = self._decode(response)
        if int(payload.get("code") or 500) != 200:
            raise RuntimeError(
                f"FastGPT 登录失败: code={payload.get('code')} message={payload.get('message')}"
            )

    @staticmethod
    def _decode(response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except Exception as exc:
            raise RuntimeError(
                f"FastGPT 返回非 JSON: status={response.status_code} body={response.text[:200]}"
            ) from exc
        if response.status_code >= 400:
            return payload if isinstance(payload, dict) else {"raw": payload}
        return payload if isinstance(payload, dict) else {"raw": payload}

    @staticmethod
    def _extract_cookie_value(decrypted: bytes) -> str | None:
        text = decrypted.decode("latin1", "ignore")
        match = re.search(r"([0-9a-f]{24,}:[A-Za-z0-9._:-]{10,})", text)
        if match:
            return match.group(1)
        stripped = text.strip()
        return stripped or None

    @staticmethod
    def _chrome_safe_storage_key() -> bytes | None:
        result = subprocess.run(
            [
                "security",
                "find-generic-password",
                "-a",
                "Chrome",
                "-s",
                "Chrome Safe Storage",
                "-w",
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return None
        secret = result.stdout.strip()
        if not secret:
            return None
        return hashlib.pbkdf2_hmac(
            "sha1", secret.encode("utf-8"), b"saltysalt", 1003, 16
        )

    def _load_browser_cookie(self) -> str | None:
        cookie_db = settings.fastgpt_browser_cookie_db
        if not cookie_db:
            return None
        cookie_path = Path(cookie_db)
        if not cookie_path.exists():
            return None
        key = self._chrome_safe_storage_key()
        if key is None:
            return None
        try:
            conn = sqlite3.connect(f"file:{cookie_path}?mode=ro", uri=True)
            try:
                row = conn.execute(
                    """
                    SELECT value, hex(encrypted_value)
                    FROM cookies
                    WHERE host_key = ? AND name = ?
                    ORDER BY expires_utc DESC
                    LIMIT 1
                    """,
                    (
                        settings.fastgpt_browser_cookie_domain,
                        settings.fastgpt_browser_cookie_name,
                    ),
                ).fetchone()
            finally:
                conn.close()
        except Exception:
            return None
        if not row:
            return None
        value, encrypted_hex = row
        if value:
            return value
        if not encrypted_hex:
            return None
        cipher_hex = encrypted_hex[6:]
        if not cipher_hex:
            return None
        result = subprocess.run(
            (
                "echo "
                + cipher_hex
                + " | xxd -r -p | openssl enc -aes-128-cbc -d -K "
                + key.hex()
                + " -iv 20202020202020202020202020202020"
            ),
            shell=True,
            capture_output=True,
        )
        if result.returncode != 0:
            return None
        return self._extract_cookie_value(result.stdout)

    async def _probe_browser_cookie(
        self, client: httpx.AsyncClient, cookie_value: str
    ) -> bool:
        response = await client.get(
            "/api/support/user/account/tokenLogin",
            headers={"Cookie": f"{settings.fastgpt_browser_cookie_name}={cookie_value}"},
        )
        payload = self._decode(response)
        return int(payload.get("code") or 500) == 200

    def _auth_headers(self) -> dict[str, str] | None:
        if self._cookie_header:
            return {"Cookie": self._cookie_header}
        return None

    @staticmethod
    def _score_value(score: Any) -> float:
        if isinstance(score, (int, float)):
            return float(score)
        if isinstance(score, str):
            try:
                return float(score)
            except Exception:
                return 0.0
        if isinstance(score, list):
            for item in score:
                if isinstance(item, dict) and item.get("value") is not None:
                    return FastGPTFacade._score_value(item.get("value"))
                value = FastGPTFacade._score_value(item)
                if value:
                    return value
        if isinstance(score, dict):
            for key in ("value", "score", "similarity", "distance"):
                if key in score:
                    return FastGPTFacade._score_value(score.get(key))
        return 0.0

    @staticmethod
    def _extract_candidate(payload: dict[str, Any]) -> dict[str, Any] | None:
        data = payload.get("data")
        if isinstance(data, dict):
            items = data.get("list")
            if isinstance(items, list) and items:
                first = items[0]
                if isinstance(first, dict):
                    return {
                        "answer": first.get("a") or first.get("answer"),
                        "question": first.get("q") or first.get("question") or first.get("sourceName"),
                        "score": first.get("score"),
                    }
        queue: list[Any] = [payload]
        while queue:
            current = queue.pop(0)
            if isinstance(current, dict):
                if any(key in current for key in ("answer", "question", "score")):
                    answer = current.get("answer") or current.get("a")
                    question = current.get("question") or current.get("q") or current.get("name")
                    score = current.get("score") or current.get("similarity") or current.get("distance")
                    if answer or question or score is not None:
                        return {
                            "answer": answer,
                            "question": question,
                            "score": score if score is not None else 0.0,
                        }
                queue.extend(current.values())
            elif isinstance(current, list):
                queue.extend(current)
        return None
