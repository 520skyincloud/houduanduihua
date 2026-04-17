from __future__ import annotations

import hashlib
import time
from typing import Any

import httpx

from app.config import settings


class FastGPTFacade:
    def __init__(self) -> None:
        self._token: str | None = None
        self._last_login_at: float = 0.0

    async def validate(self, query: str) -> dict[str, Any]:
        started = time.perf_counter()
        if not settings.fastgpt_enabled:
            return {
                "ok": False,
                "configured": False,
                "detail": "未启用 FastGPT 酒店知识检索。",
            }
        if not settings.fastgpt_ready:
            return {
                "ok": False,
                "configured": False,
                "detail": (
                    "FastGPT 直连接口配置不完整，请检查 "
                    "FASTGPT_BASE_URL / FASTGPT_USERNAME / FASTGPT_PASSWORD / FASTGPT_DATASET_ID。"
                ),
            }
        try:
            result = await self.search(query, chat_id="validate-fastgpt")
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

    async def search(self, query: str, chat_id: str | None = None) -> dict[str, Any]:
        payload = await self.search_dataset(query, chat_id=chat_id or "hotel-fact")
        quotes = self._quotes_from_search(payload)
        top1 = quotes[0] if quotes else {}
        answer = str(top1.get("a") or "").strip()
        matched_question = str(top1.get("q") or "").strip()
        score = self._score_value(top1.get("score"))
        return {
            "hit": bool(answer),
            "answer": answer or None,
            "matched_question": matched_question or None,
            "score": score,
            "route": "customer_service",
            "route_label": "search_test_direct",
            "dataset_id": settings.fastgpt_dataset_id,
            "dataset_name": settings.fastgpt_dataset_name,
            "quotes": quotes,
            "top1": top1 or None,
            "source": "fastgpt",
            "raw": payload,
        }

    async def search_dataset(self, query: str, chat_id: str) -> dict[str, Any]:
        timeout = settings.fastgpt_timeout_seconds
        async with httpx.AsyncClient(
            base_url=settings.fastgpt_base_url.rstrip("/"),
            timeout=httpx.Timeout(timeout, read=timeout),
            follow_redirects=True,
        ) as client:
            response = await self._request_with_auth(
                client,
                "POST",
                "/api/core/dataset/searchTest",
                json={
                    "datasetId": settings.fastgpt_dataset_id,
                    "text": query,
                    "chatId": chat_id,
                    "usingReRank": True,
                    "rerankModel": settings.fastgpt_rerank_model,
                },
            )
            payload = self._decode(response)
            if response.status_code >= 400:
                raise RuntimeError(
                    f"FastGPT searchTest 失败: status={response.status_code} payload={payload}"
                )
            return payload

    async def _request_with_auth(
        self,
        client: httpx.AsyncClient,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> httpx.Response:
        await self._ensure_logged_in(client)
        response = await client.request(
            method,
            url,
            headers=self._auth_headers(),
            **kwargs,
        )
        if not self._should_refresh_auth(response):
            return response
        self._token = None
        self._last_login_at = 0.0
        await self._ensure_logged_in(client)
        return await client.request(
            method,
            url,
            headers=self._auth_headers(),
            **kwargs,
        )

    def _should_refresh_auth(self, response: httpx.Response) -> bool:
        if response.status_code == 401:
            return True
        try:
            payload = response.json()
        except Exception:
            return False
        if not isinstance(payload, dict):
            return False
        code = str(payload.get("code") or "").strip()
        status_text = str(payload.get("statusText") or "").strip().lower()
        message = str(payload.get("message") or "").strip().lower()
        return code == "403" or status_text == "unauthorization" or "403" in message

    async def _ensure_logged_in(self, client: httpx.AsyncClient) -> None:
        if self._token and (time.time() - self._last_login_at) < 1800:
            return
        prelogin = await client.get(
            "/api/support/user/account/preLogin",
            params={"username": settings.fastgpt_username},
        )
        prelogin_payload = self._decode(prelogin)
        code = str((prelogin_payload.get("data") or {}).get("code") or "").strip()
        if not code:
            raise RuntimeError(f"FastGPT preLogin 未返回验证码: {prelogin_payload}")
        login = await client.post(
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
        login_payload = self._decode(login)
        if int(login_payload.get("code") or 500) != 200:
            raise RuntimeError(
                f"FastGPT 登录失败: code={login_payload.get('code')} "
                f"message={login_payload.get('message')}"
            )
        token = str((login_payload.get("data") or {}).get("token") or "").strip()
        if not token:
            raise RuntimeError(f"FastGPT 登录成功但未返回 token: {login_payload}")
        self._token = token
        self._last_login_at = time.time()

    def _auth_headers(self) -> dict[str, str]:
        if not self._token:
            return {}
        return {"token": self._token}

    @staticmethod
    def _decode(response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except Exception as exc:
            raise RuntimeError(
                f"FastGPT 返回非 JSON: status={response.status_code} body={response.text[:200]}"
            ) from exc
        return payload if isinstance(payload, dict) else {"raw": payload}

    @staticmethod
    def _quotes_from_search(payload: dict[str, Any]) -> list[dict[str, Any]]:
        items = ((payload.get("data") or {}).get("list") or [])[:5]
        quotes: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            quotes.append(
                {
                    "q": item.get("q", ""),
                    "a": item.get("a", ""),
                    "sourceName": item.get("sourceName", ""),
                    "datasetId": item.get("datasetId", ""),
                    "collectionId": item.get("collectionId", ""),
                    "score": item.get("score", []),
                }
            )
        return quotes

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
            best = 0.0
            for item in score:
                value = FastGPTFacade._score_value(item)
                if value > best:
                    best = value
            return best
        if isinstance(score, dict):
            for key in ("value", "score", "similarity", "distance"):
                if key in score:
                    return FastGPTFacade._score_value(score.get(key))
        return 0.0
