from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, AsyncIterator, Optional
from urllib.parse import urljoin

import httpx

from app.config import settings
from app.models import BackendTurnResult, PendingConfirmation
from app.services.search import canonical_pricing_command, looks_like_confirmation, looks_like_rejection, to_speak_text


READ_ONLY_TOOLS = {
    "health_overview",
    "stores_overview",
    "list_room_types",
    "store_detail",
    "get_automation_settings",
    "get_revenue_parameters",
}
PREVIEW_TOOLS = {
    "run_operating_summary",
    "generate_current_pricing_strategy",
    "get_pricing_recommendation",
    "get_bulk_pricing_plan",
    "get_pricing_calendar",
    "get_latest_execution_summary",
    "run_store_revenue_review",
    "get_execution_overview",
}
PUSH_TOOLS = {
    "push_revenue_operating_summary",
    "push_revenue_cycle_summary",
    "push_revenue_execution_result",
    "push_revenue_review_request",
    "push_revenue_review_summary",
    "push_review_operations_analysis",
    "push_price_gap_diagnosis",
    "push_negative_review_alert",
    "push_store_feishu_test_message",
}
HIGH_RISK_TOOLS = {
    "confirm_current_pricing_strategy",
    "approve_execution",
    "reject_execution",
    "run_pms_reprice",
}
ALL_REVENUE_TOOLS = READ_ONLY_TOOLS | PREVIEW_TOOLS | PUSH_TOOLS | HIGH_RISK_TOOLS
SIDE_EFFECT_TOOLS = {
    "run_operating_summary",
    "run_store_revenue_review",
    "generate_current_pricing_strategy",
    "push_revenue_operating_summary",
    "push_revenue_cycle_summary",
    "push_revenue_review_summary",
    "push_store_feishu_test_message",
}
SIDE_EFFECT_IDEMPOTENCY_SECONDS = 45.0
TOOL_FAMILIES: dict[str, str] = {
    "run_operating_summary": "operating_summary",
    "run_store_revenue_review": "revenue_review",
    "generate_current_pricing_strategy": "pricing_plan",
    "push_revenue_operating_summary": "operating_summary_push",
    "push_revenue_cycle_summary": "pricing_cycle_push",
    "push_revenue_review_summary": "revenue_review_push",
    "push_store_feishu_test_message": "feishu_test_push",
}
RERUN_HINTS = [
    "重新",
    "重来",
    "重发",
    "重跑",
    "再来",
    "再做",
    "再来一次",
    "再来一版",
    "重新来",
    "重新跑",
    "重新生成",
    "重新发",
    "再发一次",
    "重发一次",
    "重跑一次",
    "再做一次",
]

VOICE_COMMAND_ACTIONS: dict[str, tuple[str, dict[str, Any]]] = {
    "收益分析": ("run_operating_summary", {"send_feishu": True}),
    "昨日复盘": ("run_store_revenue_review", {"send_feishu": True}),
    "调价方案": ("generate_current_pricing_strategy", {"days": 3, "send_feishu": True}),
}
VOICE_COMMAND_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("收益分析", ("收益分析", "发收益分析", "做收益分析", "来个收益分析", "给我收益分析", "帮我做收益分析")),
    ("昨日复盘", ("昨日复盘", "昨天复盘", "发昨日复盘", "发昨天复盘", "来个昨日复盘", "给我昨日复盘")),
    ("调价方案", ("调价方案", "生成调价方案", "来个调价方案", "给我调价方案", "出一版调价方案")),
)
VOICE_PUSH_KEYWORDS: tuple[tuple[str, tuple[str, ...], dict[str, Any]], ...] = (
    (
        "push_store_feishu_test_message",
        (
            "飞书测试",
            "测试飞书",
            "发飞书测试",
            "来个飞书测试",
            "做个飞书测试",
            "给我来个飞书测试",
            "帮我发个飞书测试",
        ),
        {},
    ),
    (
        "push_revenue_operating_summary",
        (
            "经营摘要",
            "发经营摘要",
            "推送经营摘要",
            "把经营摘要发到飞书",
            "来个经营摘要",
            "做个经营摘要",
            "给我来个经营摘要",
            "帮我发经营摘要",
        ),
        {},
    ),
    (
        "push_revenue_review_summary",
        (
            "昨日复盘发飞书",
            "发昨日复盘",
            "推送昨日复盘",
            "把昨天复盘发群里",
            "把昨日复盘发到飞书",
            "来个昨日复盘推送",
            "做个昨日复盘推送",
            "给我发个昨日复盘",
            "帮我推送昨日复盘",
        ),
        {},
    ),
)

LATEST_RESULT_QUERY_KEYWORDS = [
    "最新调价结果",
    "最近一次调价结果",
    "调价结果怎么样",
    "飞书发了吗",
    "最新执行结果",
    "最近结果",
    "最近一次执行结果",
    "执行结果怎么样",
    "最新结果怎么样",
]

INTENT_FILLER_WORDS = [
    "小丽",
    "你好",
    "您好",
    "麻烦",
    "请",
]


class RevenueMCPError(Exception):
    pass


@dataclass
class MCPToolCallResult:
    structured_content: Any
    content: list[dict[str, Any]]
    is_error: bool = False

    @property
    def text(self) -> str:
        parts = [
            item.get("text", "").strip()
            for item in self.content
            if isinstance(item, dict) and item.get("type") == "text"
        ]
        return "\n".join(part for part in parts if part)


class _SSEEventStream:
    def __init__(self, response: httpx.Response) -> None:
        self._line_iterator = response.aiter_lines()

    async def next_event(self) -> dict[str, str]:
        event_name = "message"
        data_parts: list[str] = []

        async for line in self._line_iterator:
            if line == "":
                if data_parts or event_name:
                    return {"event": event_name, "data": "\n".join(data_parts)}
                event_name = "message"
                data_parts = []
                continue

            if line.startswith(":"):
                continue
            if line.startswith("event:"):
                event_name = line[6:].strip() or "message"
                continue
            if line.startswith("data:"):
                data_parts.append(line[5:].lstrip())

        raise EOFError("MCP SSE connection closed unexpectedly.")


class _RevenueMCPSession:
    def __init__(self, client: httpx.AsyncClient, stream: _SSEEventStream, endpoint_url: str) -> None:
        self._client = client
        self._stream = stream
        self._endpoint_url = endpoint_url
        self._request_id = 0

    async def initialize(self) -> dict[str, Any]:
        result = await self.request(
            "initialize",
            {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {
                    "name": "hotel-lobby-assistant",
                    "version": "1.0.0",
                },
            },
        )
        await self.notify("notifications/initialized")
        return result

    async def list_tools(self) -> list[dict[str, Any]]:
        result = await self.request("tools/list")
        tools = result.get("tools")
        return tools if isinstance(tools, list) else []

    async def call_tool(self, name: str, arguments: Optional[dict[str, Any]] = None) -> MCPToolCallResult:
        result = await self.request(
            "tools/call",
            {"name": name, "arguments": arguments or {}},
        )
        content = result.get("content")
        return MCPToolCallResult(
            structured_content=result.get("structuredContent"),
            content=content if isinstance(content, list) else [],
            is_error=bool(result.get("isError", False)),
        )

    async def request(self, method: str, params: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        self._request_id += 1
        request_id = self._request_id
        payload: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
        }
        if params is not None:
            payload["params"] = params

        response = await self._client.post(self._endpoint_url, json=payload)
        response.raise_for_status()
        return await self._wait_for_response(request_id)

    async def notify(self, method: str, params: Optional[dict[str, Any]] = None) -> None:
        payload: dict[str, Any] = {
            "jsonrpc": "2.0",
            "method": method,
        }
        if params is not None:
            payload["params"] = params

        response = await self._client.post(self._endpoint_url, json=payload)
        response.raise_for_status()

    async def _wait_for_response(self, request_id: int) -> dict[str, Any]:
        timeout = settings.revenue_mcp_timeout_seconds
        while True:
            event = await asyncio.wait_for(self._stream.next_event(), timeout=timeout)
            if event["event"] != "message" or not event["data"]:
                continue
            packet = json.loads(event["data"])
            if packet.get("id") != request_id:
                continue
            if "error" in packet:
                error = packet["error"] or {}
                raise RevenueMCPError(
                    f"MCP {packet.get('id')} {error.get('message', 'unknown error')}"
                )
            return packet.get("result") or {}


class RevenueMCPService:
    def __init__(self) -> None:
        self._tool_cache: list[dict[str, Any]] = []
        self._side_effect_cache: dict[str, tuple[float, BackendTurnResult]] = {}
        self._task_results: dict[str, dict[str, Any]] = {}
        self._session_family_tasks: dict[tuple[str, str], dict[str, Any]] = {}

    @property
    def enabled(self) -> bool:
        return settings.revenue_mcp_ready

    @property
    def sse_url(self) -> str:
        return settings.revenue_mcp_sse_url

    @asynccontextmanager
    async def _session(self) -> AsyncIterator[_RevenueMCPSession]:
        timeout = settings.revenue_mcp_timeout_seconds
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, read=timeout),
            follow_redirects=True,
            headers={"Accept": "text/event-stream"},
        ) as client:
            async with client.stream("GET", self.sse_url) as response:
                response.raise_for_status()
                stream = _SSEEventStream(response)
                endpoint = await self._read_endpoint(stream)
                session = _RevenueMCPSession(client, stream, endpoint)
                await session.initialize()
                yield session

    async def _read_endpoint(self, stream: _SSEEventStream) -> str:
        timeout = settings.revenue_mcp_timeout_seconds
        while True:
            event = await asyncio.wait_for(stream.next_event(), timeout=timeout)
            if event["event"] != "endpoint":
                continue
            return urljoin(self.sse_url, event["data"])

    async def list_tools(self, force_refresh: bool = False) -> list[dict[str, Any]]:
        if self._tool_cache and not force_refresh:
            return self._tool_cache
        async with self._session() as session:
            self._tool_cache = await session.list_tools()
            return self._tool_cache

    async def call_tool(self, name: str, arguments: Optional[dict[str, Any]] = None) -> MCPToolCallResult:
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                async with self._session() as session:
                    result = await session.call_tool(name, arguments)
                if result.is_error:
                    raise RevenueMCPError(result.text or f"MCP tool {name} returned isError=true")
                return result
            except Exception as exc:
                last_error = exc
                if attempt == 0:
                    await asyncio.sleep(0.15)
                    continue
                raise
        raise RevenueMCPError(str(last_error) if last_error else f"MCP tool {name} failed")

    async def validate_connectivity(self) -> dict[str, Any]:
        report: dict[str, Any] = {
            "configured": self.enabled,
            "sse_url": self.sse_url,
            "api_health_url": settings.revenue_mcp_api_health_url,
        }
        if not self.enabled:
            report["ok"] = False
            report["detail"] = "未启用收益 MCP。"
            return report

        try:
            async with httpx.AsyncClient(timeout=settings.revenue_mcp_timeout_seconds) as client:
                api_response = await client.get(settings.revenue_mcp_api_health_url)
                report["api_health_status"] = api_response.status_code
                report["api_health_ok"] = api_response.is_success
                if api_response.is_success:
                    report["api_health_payload"] = api_response.json()
        except Exception as exc:
            report["api_health_ok"] = False
            report["api_health_error"] = str(exc)

        try:
            tools = await self.list_tools(force_refresh=True)
            report["tool_count"] = len(tools)
            report["tool_names"] = [tool.get("name") for tool in tools]
            report["required_tool_groups"] = {
                "read_only": sorted(READ_ONLY_TOOLS & set(report["tool_names"])),
                "preview": sorted(PREVIEW_TOOLS & set(report["tool_names"])),
                "high_risk": sorted(HIGH_RISK_TOOLS & set(report["tool_names"])),
            }
            health_result = await self.call_tool("health_overview", {})
            report["sample_health_overview"] = (
                health_result.structured_content if health_result.structured_content is not None else health_result.text
            )
            report["ok"] = True
        except Exception as exc:
            report["ok"] = False
            report["mcp_error"] = str(exc)
        return report

    async def validate_tool(self, tool_name: str) -> dict[str, Any]:
        if tool_name not in ALL_REVENUE_TOOLS:
            return {
                "ok": False,
                "detail": f"未收录工具 {tool_name}。",
            }
        arguments = self._validation_arguments(tool_name)
        try:
            result = await self.call_tool(tool_name, arguments)
            return {
                "ok": True,
                "tool_name": tool_name,
                "arguments": arguments,
                "structured_content": result.structured_content,
                "text": result.text,
            }
        except Exception as exc:
            return {
                "ok": False,
                "tool_name": tool_name,
                "arguments": arguments,
                "detail": str(exc),
            }

    async def resolve_query(
        self,
        session_id: str,
        query: str,
        pending_confirmation: Optional[PendingConfirmation],
    ) -> BackendTurnResult:
        try:
            if pending_confirmation and (looks_like_confirmation(query) or looks_like_rejection(query)):
                return await self._handle_confirmation(query, pending_confirmation)

            action = self._classify_query(query)
            if action is None:
                return BackendTurnResult(
                    status="not_found",
                    display_text="这类收益问题我还没有稳定的处理路径，您可以换个说法，或者稍后由运营同学处理。",
                    speak_text="这类收益问题我暂时还不能稳定处理，您可以换个说法。",
                    state="pricing_rejected",
                    action_state="pricing_rejected",
                )

            normalized_query = self._normalize_query(query)
            family = TOOL_FAMILIES.get(action["tool_name"])
            if family is not None:
                cached_result = self._get_recent_family_dispatch(session_id, family, normalized_query)
                if cached_result is not None:
                    return cached_result

            if action["mode"] == "pending":
                pending = self._build_pending_confirmation(
                    tool_name=action["tool_name"],
                    arguments=action["arguments"],
                    query=query,
                )
                return BackendTurnResult(
                    status="pending_confirmation",
                    display_text=pending.display_preview,
                    speak_text=pending.speak_preview,
                    state="pricing_confirm_pending",
                    action_state="pricing_confirm_pending",
                    pending_confirmation=pending,
                    metadata={"tool_name": pending.tool_name, "arguments": pending.arguments},
                )

            if family is not None and action["mode"] == "call":
                return self._enqueue_side_effect_task(
                    session_id=session_id,
                    family=family,
                    tool_name=action["tool_name"],
                    arguments=action["arguments"],
                    normalized_query=normalized_query,
                )

            tool_result = await self.call_tool(action["tool_name"], action["arguments"])
            payload = tool_result.structured_content
            if not isinstance(payload, dict):
                payload = {"text": tool_result.text}

            if action["tool_name"] == "generate_current_pricing_strategy":
                result = self._format_strategy_preview(payload, query)
                self._remember_side_effect_result(action["tool_name"], normalized_query, result)
                return result
            if action["tool_name"] == "get_latest_execution_summary":
                return self._format_latest_execution(payload)
            if action["tool_name"] == "run_operating_summary":
                result = self._format_operating_summary(payload)
                self._remember_side_effect_result(action["tool_name"], normalized_query, result)
                return result
            if action["tool_name"] == "run_store_revenue_review":
                result = self._format_revenue_review(payload)
                self._remember_side_effect_result(action["tool_name"], normalized_query, result)
                return result
            if action["tool_name"] == "get_execution_overview":
                return self._format_execution_overview(payload)
            return self._format_generic_preview(action["tool_name"], payload, tool_result.text)
        except Exception as exc:
            detail = "当前操作暂时没有完成，您可以稍后再试。"
            return BackendTurnResult(
                status="error",
                display_text=detail,
                speak_text="当前操作暂时没有完成，您可以稍后再试。",
                state="error",
                action_state="pricing_rejected",
                metadata={"error": str(exc)},
            )

    def _get_recent_family_dispatch(
        self,
        session_id: str,
        family: str,
        normalized_query: str,
    ) -> Optional[BackendTurnResult]:
        allow_rerun = any(keyword in normalized_query for keyword in RERUN_HINTS)
        task = self._session_family_tasks.get((session_id, family))
        if not task or allow_rerun:
            return None
        created_ts = float(task.get("created_at") or 0.0)
        if time.time() - created_ts > SIDE_EFFECT_IDEMPOTENCY_SECONDS:
            return None
        return BackendTurnResult(
            status="pricing_preview",
            display_text="刚刚同类操作已经帮您触发了，这次先不重复发送。",
            speak_text="刚刚同类操作已经帮您触发了，这次先不重复发送。",
            state="pricing_preview",
            action_state="pricing_preview",
            metadata={
                "duplicate_suppressed": True,
                "source": "pricing-family-idempotency",
                "family": family,
                "task_id": task.get("task_id"),
                "status": task.get("status"),
            },
        )

    def _enqueue_side_effect_task(
        self,
        *,
        session_id: str,
        family: str,
        tool_name: str,
        arguments: dict[str, Any],
        normalized_query: str,
    ) -> BackendTurnResult:
        task_id = uuid.uuid4().hex
        created_at = time.time()
        record = {
            "task_id": task_id,
            "family": family,
            "tool_name": tool_name,
            "arguments": dict(arguments),
            "normalized_query": normalized_query,
            "status": "queued",
            "created_at": created_at,
            "completed_at": None,
        }
        self._task_results[task_id] = record
        self._session_family_tasks[(session_id, family)] = record
        asyncio.create_task(
            self._run_side_effect_task(
                session_id=session_id,
                family=family,
                task_id=task_id,
                tool_name=tool_name,
                arguments=dict(arguments),
                normalized_query=normalized_query,
            )
        )
        return self._build_async_confirmation(family, task_id)

    async def _run_side_effect_task(
        self,
        *,
        session_id: str,
        family: str,
        task_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        normalized_query: str,
    ) -> None:
        record = self._task_results.get(task_id)
        if record is None:
            return
        record["status"] = "running"
        try:
            tool_result = await self.call_tool(tool_name, arguments)
            payload = tool_result.structured_content
            if not isinstance(payload, dict):
                payload = {"text": tool_result.text}
            if tool_name == "generate_current_pricing_strategy":
                result = self._format_strategy_preview(payload, "")
            elif tool_name == "run_operating_summary":
                result = self._format_operating_summary(payload)
            elif tool_name == "run_store_revenue_review":
                result = self._format_revenue_review(payload)
            else:
                result = self._format_generic_preview(tool_name, payload, tool_result.text)
            self._remember_side_effect_result(tool_name, normalized_query, result)
            record["status"] = "completed"
            record["result"] = result
            record["payload"] = payload
        except Exception as exc:
            record["status"] = "failed"
            record["error"] = str(exc)
        finally:
            record["completed_at"] = time.time()
            active = self._session_family_tasks.get((session_id, family))
            if active and active.get("task_id") == task_id:
                self._session_family_tasks[(session_id, family)] = record

    @staticmethod
    def _build_async_confirmation(family: str, task_id: str) -> BackendTurnResult:
        mapping = {
            "operating_summary": (
                "收益分析任务已创建，结果会继续发送到飞书。",
                "好的，正在为您生成收益分析。",
            ),
            "revenue_review": (
                "昨日复盘任务已创建，结果会继续发送到飞书。",
                "好的，正在为您生成昨日复盘。",
            ),
            "pricing_plan": (
                "调价方案任务已创建，结果会继续发送到飞书。",
                "好的，正在为您生成调价方案。",
            ),
        }
        display_text, speak_text = mapping.get(
            family,
            ("任务已创建，结果会继续发送到飞书。", "好的，正在为您处理。"),
        )
        return BackendTurnResult(
            status="pricing_preview",
            display_text=display_text,
            speak_text=speak_text,
            state="pricing_preview",
            action_state="pricing_preview",
            metadata={"task_id": task_id, "family": family, "async_dispatched": True},
        )

    def _classify_query(self, query: str) -> Optional[dict[str, Any]]:
        normalized_query = self._normalize_query(query)
        explicit_command = self._match_explicit_voice_command(normalized_query)
        if explicit_command is not None:
            tool_name, arguments = explicit_command
            return {
                "mode": "call",
                "tool_name": tool_name,
                "arguments": arguments,
            }
        contains_push = any(keyword in query for keyword in ["飞书", "推送", "群里", "发群"])
        contains_no_push = any(
            keyword in normalized_query
            for keyword in [
                "别发群",
                "不要发群",
                "不用发群",
                "不发群",
                "别推送",
                "不要推送",
                "不用推送",
                "不推送",
                "别发飞书",
                "不要发飞书",
                "不用发飞书",
                "不发飞书",
            ]
        )
        should_send_feishu = contains_push or not contains_no_push

        execution_id = self._extract_execution_id(query)
        rejection_reason = self._extract_rejection_reason(query)

        if any(keyword in normalized_query for keyword in LATEST_RESULT_QUERY_KEYWORDS):
            return {
                "mode": "call",
                "tool_name": "get_latest_execution_summary",
                "arguments": {},
            }
        if execution_id and any(keyword in normalized_query for keyword in ["执行详情", "执行单", "execution"]):
            return {
                "mode": "call",
                "tool_name": "get_execution_overview",
                "arguments": {"execution_id": execution_id},
            }
        if execution_id and any(keyword in normalized_query for keyword in ["批准", "通过", "审批通过"]):
            return {
                "mode": "pending",
                "tool_name": "approve_execution",
                "arguments": {"execution_id": execution_id},
            }
        if execution_id and any(keyword in normalized_query for keyword in ["拒绝", "驳回"]):
            arguments = {"execution_id": execution_id}
            if rejection_reason:
                arguments["reason"] = rejection_reason
            return {
                "mode": "pending",
                "tool_name": "reject_execution",
                "arguments": arguments,
            }
        return None

    @staticmethod
    def _match_explicit_voice_command(normalized_query: str) -> Optional[tuple[str, dict[str, Any]]]:
        for tool_name, keywords, arguments in VOICE_PUSH_KEYWORDS:
            if any(keyword in normalized_query for keyword in keywords):
                return tool_name, dict(arguments)
        for family, keywords in VOICE_COMMAND_KEYWORDS:
            if any(keyword in normalized_query for keyword in keywords):
                return VOICE_COMMAND_ACTIONS[family]
        family = canonical_pricing_command(normalized_query)
        if family is None:
            return None
        return VOICE_COMMAND_ACTIONS.get(family)

    @staticmethod
    def _normalize_query(query: str) -> str:
        normalized = re.sub(r"[，。！？、,.!?\s]+", "", query)
        for filler in INTENT_FILLER_WORDS:
            normalized = normalized.replace(filler, "")
        normalized = normalized.replace("的", "")
        return normalized

    def _get_recent_side_effect_result(
        self,
        tool_name: str,
        normalized_query: str,
    ) -> Optional[BackendTurnResult]:
        if tool_name not in SIDE_EFFECT_TOOLS:
            return None
        allow_rerun = any(keyword in normalized_query for keyword in RERUN_HINTS)
        exact_cache_key = f"{tool_name}:{normalized_query}"
        tool_cache_key = f"{tool_name}:__tool__"
        cached = self._side_effect_cache.get(exact_cache_key)
        if not cached and not allow_rerun:
            cached = self._side_effect_cache.get(tool_cache_key)
        if not cached:
            return None
        created_ts, result = cached
        if time.time() - created_ts > SIDE_EFFECT_IDEMPOTENCY_SECONDS:
            self._side_effect_cache.pop(exact_cache_key, None)
            self._side_effect_cache.pop(tool_cache_key, None)
            return None
        return BackendTurnResult(
            status=result.status,
            display_text=result.display_text,
            speak_text="刚刚这类操作我已经帮您触发了，这次先不重复发送。",
            state=result.state,
            confidence=result.confidence,
            needs_handoff=result.needs_handoff,
            action_state=result.action_state,
            metadata={**result.metadata, "duplicate_suppressed": True},
        )

    def _remember_side_effect_result(
        self,
        tool_name: str,
        normalized_query: str,
        result: BackendTurnResult,
    ) -> None:
        if tool_name not in SIDE_EFFECT_TOOLS:
            return
        created_ts = time.time()
        exact_cache_key = f"{tool_name}:{normalized_query}"
        tool_cache_key = f"{tool_name}:__tool__"
        self._side_effect_cache[exact_cache_key] = (created_ts, result)
        self._side_effect_cache[tool_cache_key] = (created_ts, result)

    async def _handle_confirmation(
        self,
        query: str,
        pending_confirmation: PendingConfirmation,
    ) -> BackendTurnResult:
        if looks_like_rejection(query):
            if pending_confirmation.tool_name == "reject_execution":
                tool_result = await self.call_tool(
                    pending_confirmation.tool_name,
                    {**pending_confirmation.arguments, "confirm": True},
                )
                payload = tool_result.structured_content if isinstance(tool_result.structured_content, dict) else {}
                execution_id = payload.get("execution_id") or pending_confirmation.execution_id
                text = f"已拒绝执行 {execution_id}，系统会同步后续状态。"
                return BackendTurnResult(
                    status="pricing_rejected",
                    display_text=text,
                    speak_text=text,
                    state="pricing_rejected",
                    action_state="pricing_rejected",
                    metadata=payload,
                    clear_pending_confirmation=True,
                )
            text = "好的，我已取消这次调价执行，不会继续下发。"
            return BackendTurnResult(
                status="pricing_rejected",
                display_text=text,
                speak_text=text,
                state="pricing_rejected",
                action_state="pricing_rejected",
                clear_pending_confirmation=True,
            )

        tool_result = await self.call_tool(
            pending_confirmation.tool_name,
            {**pending_confirmation.arguments, "confirm": True},
        )
        payload = tool_result.structured_content if isinstance(tool_result.structured_content, dict) else {}
        if pending_confirmation.tool_name == "confirm_current_pricing_strategy":
            return self._format_confirm_execution(payload, clear_pending_confirmation=True)
        if pending_confirmation.tool_name == "approve_execution":
            execution_id = payload.get("execution_id") or pending_confirmation.execution_id
            applied_updates = payload.get("applied_updates")
            text = f"已批准执行 {execution_id}。" + (
                f"当前已应用 {applied_updates} 条调价。" if applied_updates is not None else ""
            )
            return BackendTurnResult(
                status="pricing_executed",
                display_text=text,
                speak_text=text,
                state="pricing_executed",
                action_state="pricing_executed",
                metadata=payload,
                clear_pending_confirmation=True,
            )
        return self._format_generic_execution(payload, pending_confirmation, clear_pending_confirmation=True)

    def _format_strategy_preview(self, payload: dict[str, Any], query: str) -> BackendTurnResult:
        execution_id = payload.get("execution_id")
        store_name = payload.get("store_name", "当前门店")
        total_updates = payload.get("total_updates", 0)
        review_required_count = payload.get("review_required_count", 0)
        summary = payload.get("summary") or "策略预演已生成。"
        display_text = (
            f"{store_name} 当前调价策略已生成。\n"
            f"execution_id：{execution_id}\n"
            f"共 {total_updates} 条建议，需复核 {review_required_count} 条。\n"
            f"{summary}"
        )
        speak_text = (
            f"我已经生成当前调价策略，共 {total_updates} 条建议，"
            f"其中 {review_required_count} 条需要复核。"
            "如果确认执行，您可以直接说按这个策略执行。"
        )
        pending = PendingConfirmation(
            tool_name="confirm_current_pricing_strategy",
            arguments={
                "execution_id": execution_id,
                "store_id": payload.get("store_id") or settings.revenue_mcp_default_store_id,
            },
            execution_id=execution_id,
            store_id=payload.get("store_id") or settings.revenue_mcp_default_store_id,
            display_preview=display_text,
            speak_preview="这版调价策略已经准备好。如果您确认执行，可以直接说按这个策略执行。",
            created_ts=time.time(),
            expires_ts=time.time() + settings.revenue_mcp_confirmation_ttl_seconds,
            action_label="确认执行当前调价策略",
            metadata=payload,
        )
        return BackendTurnResult(
            status="pricing_preview",
            display_text=display_text,
            speak_text=speak_text,
            state="pricing_preview",
            action_state="pricing_confirm_pending",
            metadata=payload,
            pending_confirmation=pending,
        )

    def _format_confirm_execution(
        self,
        payload: dict[str, Any],
        clear_pending_confirmation: bool = False,
    ) -> BackendTurnResult:
        execution_id = payload.get("execution_id")
        applied_updates = payload.get("applied_updates")
        feishu_status = payload.get("feishu_status") or "unknown"
        display_text = (
            f"当前调价策略已执行。\nexecution_id：{execution_id}\n"
            f"应用条数：{applied_updates}\n飞书状态：{feishu_status}"
        )
        speak_text = (
            f"当前调价策略已经执行，共应用 {applied_updates or 0} 条。"
            f"飞书状态是 {feishu_status}。"
        )
        return BackendTurnResult(
            status="pricing_executed",
            display_text=display_text,
            speak_text=speak_text,
            state="pricing_executed",
            action_state="pricing_executed",
            metadata=payload,
            clear_pending_confirmation=clear_pending_confirmation,
        )

    def _format_latest_execution(self, payload: dict[str, Any]) -> BackendTurnResult:
        if payload.get("status") == "empty":
            text = payload.get("message") or "当前还没有找到可复盘的调价执行记录。"
            return BackendTurnResult(
                status="pricing_preview",
                display_text=text,
                speak_text=text,
                state="pricing_preview",
                action_state="pricing_preview",
                metadata=payload,
            )
        display_text = (
            f"最新调价执行结果\nexecution_id：{payload.get('execution_id')}\n"
            f"状态：{payload.get('execution_status')}\n"
            f"飞书状态：{payload.get('execution_feishu_status')}\n"
            f"摘要：{payload.get('summary') or '无'}"
        )
        speak_text = to_speak_text(
            f"最近一次调价执行状态是 {payload.get('execution_status', '未知')}，"
            f"飞书状态是 {payload.get('execution_feishu_status', '未知')}。"
        )
        return BackendTurnResult(
            status="pricing_preview",
            display_text=display_text,
            speak_text=speak_text,
            state="pricing_preview",
            action_state="pricing_preview",
            metadata=payload,
        )

    def _format_operating_summary(self, payload: dict[str, Any]) -> BackendTurnResult:
        text = payload.get("detail") or payload.get("summary") or payload.get("status") or "经营摘要已处理。"
        business_date = payload.get("business_date")
        speak_text = (
            f"{business_date or '今天'}的收益分析已经生成，并已发送到飞书。"
            if payload.get("feishu_status") == "sent_via_app"
            else f"{business_date or '今天'}的收益分析已经生成。"
        )
        return BackendTurnResult(
            status="pricing_preview",
            display_text=str(text),
            speak_text=speak_text,
            state="pricing_preview",
            action_state="pricing_preview",
            metadata=payload,
        )

    def _format_revenue_review(self, payload: dict[str, Any]) -> BackendTurnResult:
        detail = payload.get("detail") or payload.get("summary") or payload.get("status") or "昨日策略复盘已处理。"
        review_date = payload.get("review_date") or "昨日"
        execution_count = payload.get("execution_count")
        if execution_count:
            speak_text = (
                f"{review_date}的复盘已经生成，基于 {execution_count} 条策略样本分析，"
                + ("并已发送到飞书。" if payload.get("feishu_status") == "sent_via_app" else "您可以查看详情。")
            )
        else:
            speak_text = f"{review_date}的复盘已经生成，但可用样本不足。"
        return BackendTurnResult(
            status="pricing_preview",
            display_text=str(detail),
            speak_text=speak_text,
            state="pricing_preview",
            action_state="pricing_preview",
            metadata=payload,
        )

    def _format_execution_overview(self, payload: dict[str, Any]) -> BackendTurnResult:
        execution = payload.get("execution") or {}
        result_summary = payload.get("result_summary") or {}
        text = (
            f"execution_id：{execution.get('id')}\n"
            f"状态：{execution.get('status')}\n"
            f"摘要：{execution.get('summary')}\n"
            f"应用条数：{result_summary.get('applied_updates')}"
        )
        speak_text = to_speak_text(
            f"这次调价执行状态是 {execution.get('status', '未知')}，"
            f"共应用 {result_summary.get('applied_updates', 0)} 条。"
        )
        return BackendTurnResult(
            status="pricing_preview",
            display_text=text,
            speak_text=speak_text,
            state="pricing_preview",
            action_state="pricing_preview",
            metadata=payload,
        )

    def _format_generic_preview(
        self,
        tool_name: str,
        payload: dict[str, Any],
        fallback_text: str,
    ) -> BackendTurnResult:
        text = fallback_text or json.dumps(payload, ensure_ascii=False, indent=2)
        display_text = f"{tool_name} 已返回结果。\n{text}"
        speak_text = to_speak_text(f"{tool_name} 已返回结果。")
        return BackendTurnResult(
            status="pricing_preview",
            display_text=display_text,
            speak_text=speak_text,
            state="pricing_preview",
            action_state="pricing_preview",
            metadata=payload,
        )

    def _format_generic_execution(
        self,
        payload: dict[str, Any],
        pending_confirmation: PendingConfirmation,
        clear_pending_confirmation: bool = False,
    ) -> BackendTurnResult:
        detail = payload.get("detail") or payload.get("status") or pending_confirmation.action_label
        text = f"{pending_confirmation.action_label} 已完成。{detail}"
        return BackendTurnResult(
            status="pricing_executed",
            display_text=text,
            speak_text=to_speak_text(text),
            state="pricing_executed",
            action_state="pricing_executed",
            metadata=payload,
            clear_pending_confirmation=clear_pending_confirmation,
        )

    def _build_pending_confirmation(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        query: str,
    ) -> PendingConfirmation:
        execution_id = arguments.get("execution_id")
        store_id = arguments.get("store_id") or settings.revenue_mcp_default_store_id
        action_label = {
            "approve_execution": "批准待审批调价",
            "reject_execution": "拒绝待审批调价",
            "run_pms_reprice": "执行 PMS 调价",
        }.get(tool_name, "执行高风险收益操作")
        display_preview = (
            f"检测到高风险收益操作：{action_label}\n"
            f"execution_id：{execution_id or '未提供'}\n"
            "请再次明确确认后，我才会执行。"
        )
        speak_preview = "这是高风险操作。请再次明确确认，我才会继续执行。"
        now = time.time()
        return PendingConfirmation(
            tool_name=tool_name,
            arguments=arguments,
            display_preview=display_preview,
            speak_preview=speak_preview,
            created_ts=now,
            expires_ts=now + settings.revenue_mcp_confirmation_ttl_seconds,
            execution_id=execution_id,
            store_id=store_id,
            action_label=action_label,
            metadata={"source_query": query},
        )

    @staticmethod
    def _extract_execution_id(query: str) -> Optional[int]:
        match = re.search(r"(\d{2,})", query)
        return int(match.group(1)) if match else None

    @staticmethod
    def _extract_rejection_reason(query: str) -> Optional[str]:
        for marker in ("原因是", "因为", "理由是", "原因", "理由"):
            if marker in query:
                reason = query.split(marker, 1)[1].strip(" ：:，,。")
                return reason or None
        return None

    @staticmethod
    def _validation_arguments(tool_name: str) -> dict[str, Any]:
        if tool_name in {
            "push_revenue_operating_summary",
            "push_revenue_cycle_summary",
            "push_revenue_review_summary",
            "push_review_operations_analysis",
            "push_price_gap_diagnosis",
            "push_negative_review_alert",
            "push_store_feishu_test_message",
        }:
            return {}
        if tool_name in {"push_revenue_execution_result", "push_revenue_review_request"}:
            return {"execution_id": 999999}
        if tool_name == "generate_current_pricing_strategy":
            return {"days": 3, "send_feishu": False}
        if tool_name == "run_store_revenue_review":
            return {"send_feishu": False}
        if tool_name in {"approve_execution", "reject_execution"}:
            return {"execution_id": 999999, "confirm": False}
        if tool_name == "confirm_current_pricing_strategy":
            return {"confirm": False}
        if tool_name == "run_pms_reprice":
            return {
                "payload_json": json.dumps(
                    {
                        "pricing": {
                            "room_type_ids": [1],
                            "start_date": "2026-04-16",
                            "end_date": "2026-04-17",
                        },
                        "automation": {"dry_run": True},
                    },
                    ensure_ascii=False,
                ),
                "confirm": False,
            }
        return {}
