from __future__ import annotations

import html
import re
from typing import Any
from urllib.parse import quote

import httpx

from app.config import settings


class ExternalSearchFacade:
    async def search(self, query: str) -> dict[str, Any]:
        if not settings.external_search_enabled:
            return {
                "ok": False,
                "configured": False,
                "answer": "",
                "results": [],
                "sources": [],
                "detail": "未启用外部动态信息搜索。",
            }

        if settings.external_search_engine != "duckduckgo":
            return {
                "ok": False,
                "configured": False,
                "answer": "",
                "results": [],
                "sources": [],
                "detail": f"暂不支持的搜索引擎：{settings.external_search_engine}",
            }

        return await self._duckduckgo_search(query)

    async def _duckduckgo_search(self, query: str) -> dict[str, Any]:
        url = f"https://duckduckgo.com/html/?q={quote(query)}"
        try:
            async with httpx.AsyncClient(
                timeout=settings.external_search_timeout_seconds,
                follow_redirects=True,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
                    )
                },
            ) as client:
                response = await client.get(url)
                response.raise_for_status()
        except Exception as exc:
            return {
                "ok": False,
                "configured": True,
                "answer": "",
                "results": [],
                "sources": [],
                "detail": f"外部搜索失败：{exc}",
            }

        results = self._parse_results(response.text)[: settings.external_search_max_results]
        sources = [item["url"] for item in results if item.get("url")]
        answer = self._format_answer(query, results)
        return {
            "ok": bool(results),
            "configured": True,
            "answer": answer,
            "results": results,
            "sources": sources,
            "detail": "" if results else "未检索到足够的外部公开信息。",
        }

    def _parse_results(self, raw_html: str) -> list[dict[str, str]]:
        pattern = re.compile(
            r'<a rel="nofollow" class="result__a" href="(?P<url>[^"]+)">(?P<title>.*?)</a>.*?'
            r'<a class="result__snippet" href="[^"]+">(?P<snippet>.*?)</a>',
            re.S,
        )
        results: list[dict[str, str]] = []
        for match in pattern.finditer(raw_html):
            title = self._clean_html(match.group("title"))
            snippet = self._clean_html(match.group("snippet"))
            url = html.unescape(match.group("url"))
            if not title or not url:
                continue
            results.append({"title": title, "snippet": snippet, "url": url})
        return results

    @staticmethod
    def _clean_html(value: str) -> str:
        cleaned = re.sub(r"<.*?>", "", value)
        cleaned = html.unescape(cleaned)
        return re.sub(r"\s+", " ", cleaned).strip()

    @staticmethod
    def _format_answer(query: str, results: list[dict[str, str]]) -> str:
        if not results:
            return "这个问题需要依赖外部公开信息，但我暂时没有检索到稳定结果，建议以实际现场信息为准。"
        top = results[0]
        snippet = top.get("snippet") or top.get("title") or ""
        snippet = snippet[:120].rstrip("，。； ")
        return f"根据外部公开信息，{snippet}。如有变动，请以现场实际情况为准。"
