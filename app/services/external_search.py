from __future__ import annotations

from datetime import datetime
import re
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from app.config import settings


LOCAL_TIME_KEYWORDS = [
    "今天几号",
    "几月几号",
    "几月几日",
    "星期几",
    "礼拜几",
    "周几",
    "现在几点",
    "现在时间",
    "日期",
    "年份",
    "哪一年",
    "什么年份",
]


class ExternalSearchFacade:
    async def search(self, query: str) -> dict[str, Any]:
        if not settings.external_search_enabled:
            return self._disabled("未启用外部动态信息搜索。")
        if settings.external_search_engine != "aliyun":
            return self._disabled(f"暂不支持的搜索引擎：{settings.external_search_engine}")
        if self._looks_like_local_time_query(query):
            return self._local_time_answer(query)
        return await self._aliyun_search(query)

    @staticmethod
    def _disabled(detail: str) -> dict[str, Any]:
        return {
            "ok": False,
            "configured": False,
            "answer": "",
            "results": [],
            "sources": [],
            "detail": detail,
        }

    @staticmethod
    def _looks_like_local_time_query(query: str) -> bool:
        normalized = re.sub(r"\s+", "", str(query or "")).lower()
        return any(keyword in normalized for keyword in LOCAL_TIME_KEYWORDS)

    @staticmethod
    def _local_time_answer(query: str) -> dict[str, Any]:
        now = datetime.now(ZoneInfo("Asia/Shanghai"))
        normalized = re.sub(r"\s+", "", str(query or "")).lower()
        weekday_map = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]

        if any(token in normalized for token in ["现在几点", "现在时间"]):
            answer = f"现在是北京时间{now.hour}点{now.minute:02d}分。以上为当前本地时间信息，仅供参考。"
        elif any(token in normalized for token in ["星期几", "礼拜几", "周几"]):
            answer = f"今天是{weekday_map[now.weekday()]}。以上为当前本地日期信息，仅供参考。"
        elif any(token in normalized for token in ["年份", "哪一年", "什么年份"]):
            answer = f"现在是{now.year}年。以上为当前本地日期信息，仅供参考。"
        else:
            answer = f"今天是{now.year}年{now.month}月{now.day}日，{weekday_map[now.weekday()]}。以上为当前本地日期信息，仅供参考。"

        return {
            "ok": True,
            "configured": True,
            "answer": answer,
            "results": [],
            "sources": [],
            "detail": "",
            "raw": {"source": "local_time"},
        }

    async def _aliyun_search(self, query: str) -> dict[str, Any]:
        if not settings.external_search_ready:
            return self._disabled("未完整配置阿里云官方联网搜索。")

        payload = {
            "model": settings.external_search_aliyun_model,
            "input": {
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "你是酒店数字人的联网搜索助手。请基于联网搜索结果，用中文给出适合直接播报的自然口语答案。"
                            "要求：1）只回答外部动态公开信息；2）先说结论，再补一句提醒；"
                            "3）必须明确这是外部公开信息，仅供参考；4）控制在两句话内；"
                            "5）不要输出项目符号、编号、链接。"
                        ),
                    },
                    {
                        "role": "user",
                        "content": query,
                    },
                ],
            },
            "parameters": {
                "enable_search": True,
                "search_options": {
                    "forced_search": True,
                    "enable_source": True,
                    "search_strategy": "turbo",
                },
                "result_format": "message",
                "temperature": 0.2,
                "max_tokens": 220,
            },
        }
        headers = {
            "Authorization": f"Bearer {settings.external_search_aliyun_api_key}",
            "Content-Type": "application/json",
        }
        endpoint = self._dashscope_generation_endpoint()
        try:
            async with httpx.AsyncClient(timeout=settings.external_search_timeout_seconds) as client:
                response = await client.post(endpoint, headers=headers, json=payload)
                response.raise_for_status()
                raw = response.json()
        except Exception as exc:
            return {
                "ok": False,
                "configured": True,
                "answer": "",
                "results": [],
                "sources": [],
                "detail": f"阿里云联网搜索失败：{exc}",
            }

        output = raw.get("output") or {}
        search_info = output.get("search_info") or {}
        results, sources = self._extract_search_evidence(search_info)
        message = output.get("choices", [{}])[0].get("message", {})
        answer = self._extract_text(message.get("content", ""))
        answer = self._normalize_answer(answer)
        if not results:
            return {
                "ok": False,
                "configured": True,
                "answer": "",
                "results": [],
                "sources": [],
                "detail": "阿里云返回了文本，但没有可验证的联网搜索证据（search_info 为空）。",
                "raw": raw,
            }
        return {
            "ok": bool(answer),
            "configured": True,
            "answer": answer,
            "results": results,
            "sources": sources,
            "detail": "" if answer else "阿里云联网搜索未返回可用答案。",
            "raw": raw,
        }

    @staticmethod
    def _dashscope_generation_endpoint() -> str:
        base = settings.external_search_aliyun_base_url.rstrip("/")
        if "/compatible-mode" in base:
            base = base.split("/compatible-mode", 1)[0]
        return f"{base}/api/v1/services/aigc/text-generation/generation"

    @staticmethod
    def _extract_text(content: Any) -> str:
        if isinstance(content, list):
            text = "".join(
                str(item.get("text") or "")
                for item in content
                if isinstance(item, dict)
            )
            return text.strip()
        return str(content or "").strip()

    @staticmethod
    def _normalize_answer(answer: str) -> str:
        text = re.sub(r"\s+", " ", answer or "").strip().strip('"')
        if not text:
            return ""
        if "仅供参考" not in text:
            text = f"{text} 以上为外部公开信息，仅供参考。"
        return text[:220]

    @staticmethod
    def _extract_search_evidence(search_info: Any) -> tuple[list[dict[str, Any]], list[str]]:
        if not isinstance(search_info, dict):
            return [], []

        candidate_lists: list[list[Any]] = []
        for key in ("items", "results", "sources", "source_list", "search_results"):
            value = search_info.get(key)
            if isinstance(value, list):
                candidate_lists.append(value)

        results: list[dict[str, Any]] = []
        sources: list[str] = []
        seen_sources: set[str] = set()
        for entries in candidate_lists:
            for item in entries:
                if not isinstance(item, dict):
                    continue
                title = str(item.get("title") or item.get("name") or "").strip()
                url = str(item.get("url") or item.get("link") or "").strip()
                snippet = str(item.get("snippet") or item.get("content") or item.get("summary") or "").strip()
                result = {
                    "title": title,
                    "url": url,
                    "snippet": snippet,
                }
                if any(result.values()):
                    results.append(result)
                if url and url not in seen_sources:
                    seen_sources.add(url)
                    sources.append(url)
        return results, sources
