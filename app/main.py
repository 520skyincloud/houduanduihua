from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path
from threading import Lock
from time import perf_counter
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app.config import settings
from app.integrations.volcengine import (
    VolcengineRTCOpenAPI,
    VoiceChatPayloadFactory,
    generate_rtc_token,
)
from app.models import BackendTurnResult, PresenceState, RTCSessionState
from app.services.faq_store import FAQStore
from app.services.lobby import LobbyCoordinator
from app.services.memory import MemoryFacade
from app.services.ragflow import RAGFlowFacade
from app.services.revenue_mcp import RevenueMCPService
from app.services.search import chunk_speak_text, decide_turn_route, resolve_answer


app = FastAPI(title=settings.app_name)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

store = FAQStore(settings.faq_index_path)
ragflow = RAGFlowFacade(store)
memory = MemoryFacade()
revenue_mcp = RevenueMCPService()
lobby = LobbyCoordinator()
rtc_openapi = VolcengineRTCOpenAPI()
voice_chat_factory = VoiceChatPayloadFactory()
state_lock = Lock()
voicechat_callback_log: list[dict[str, Any]] = []


class BootstrapRequest(BaseModel):
    client_id: str = "lobby-screen"
    transport: str = "volcengine-rtc"


class PresenceRequest(BaseModel):
    source: str = "camera"


class QueryRequest(BaseModel):
    user_text: str
    source: str = "rtc-subtitle"


class InterruptRequest(BaseModel):
    reason: str = "barge-in"


class CallbackPayload(BaseModel):
    payload: dict[str, Any]


class AgentCommandAckRequest(BaseModel):
    command: str
    ok: bool = True
    detail: str = ""
    turn_id: Optional[int] = None


def _make_room_id() -> str:
    return f"{settings.hotel_id}-{uuid.uuid4().hex[:10]}"


def _make_user_id() -> str:
    return f"user-{uuid.uuid4().hex[:8]}"


def _make_ai_user_id() -> str:
    return f"ai-avatar-{uuid.uuid4().hex[:8]}"


def _session_warnings() -> list[str]:
    warnings: list[str] = []
    if (
        settings.effective_dialog_path != "unconfigured"
        and settings.volcengine_primary_dialog_path != settings.effective_dialog_path
    ):
        warnings.append(
            f"当前请求主链为 {settings.volcengine_primary_dialog_path}，"
            f"但实际生效主链为 {settings.effective_dialog_path}。"
        )
    if not settings.volcengine_rtc_app_id:
        warnings.append("缺少 VOLCENGINE_RTC_APP_ID，前端无法真正进 RTC 房间。")
    if not settings.volcengine_rtc_app_key:
        warnings.append("缺少 VOLCENGINE_RTC_APP_KEY，后端无法生成 RTC Token。")
    if not rtc_openapi.ready:
        warnings.append("缺少 VOLCENGINE_ACCESS_KEY_ID / VOLCENGINE_SECRET_ACCESS_KEY，无法调用 StartVoiceChat。")
    if not voice_chat_factory.ready:
        warnings.append(
            "缺少 VoiceChat 场景参数。建议直接配置 VOLCENGINE_VOICE_CHAT_OVERRIDES_JSON，"
            "或补齐 S2SConfig / ASR/TTS / LLM 参数。"
        )
    if settings.volcengine_primary_dialog_path == "s2s" and settings.volcengine_voice_chat_version != "2024-12-01":
        warnings.append("S2S 主链要求 StartVoiceChat 固定使用 2024-12-01 版本。")
    if settings.volcengine_enable_s2s and not settings.s2s_ready:
        warnings.append(
            "已开启 S2S 主链，但缺少可用的 S2SConfig。"
            "可以提供 VOLCENGINE_S2S_CONFIG_JSON，"
            "也可以只提供 VOLCENGINE_S2S_APP_ID / VOLCENGINE_S2S_TOKEN / VOLCENGINE_S2S_MODEL。"
        )
    if settings.volcengine_primary_dialog_path in {"asr_tts", "asr-llm-tts", "cascade"} and not settings.asr_tts_ready:
        warnings.append(
            "已选择 ASR -> LLM -> TTS 主链，但 ASR/TTS/LLM 参数未补齐。"
        )
    if settings.volcengine_enable_memory and settings.volcengine_voice_chat_version != "2024-12-01":
        warnings.append("长期记忆仅支持 StartVoiceChat(2024-12-01)。")
    if settings.volcengine_enable_memory and not settings.memory_ready:
        if settings.memory_api_ready:
            warnings.append(
                "RTC 原生长期记忆尚未配置 VOLCENGINE_MEMORY_CONFIG_JSON，"
                "当前先使用后端 Memory API。"
            )
        else:
            warnings.append("已开启长期记忆，但缺少 VOLCENGINE_MEMORY_CONFIG_JSON。")
    if settings.volcengine_memory_api_key and not settings.memory_api_ready:
        warnings.append("已提供记忆库 API Key，但后端 Memory API 配置仍不完整。")
    if not settings.volcengine_callback_base_url:
        warnings.append("缺少 VOLCENGINE_CALLBACK_BASE_URL，火山服务端回调暂时无法固定到公网地址。")
    if settings.volcengine_avatar_enabled and (
        not settings.volcengine_avatar_app_id
        or not settings.volcengine_avatar_token
        or not settings.volcengine_avatar_role
    ):
        warnings.append("已启用数字人，但 AvatarAppID / AvatarToken / AvatarRole 未补齐。")
    if settings.revenue_mcp_enabled and not settings.revenue_mcp_ready:
        warnings.append("已开启收益调价 MCP，但缺少可用的 SSE MCP 地址。")
    return warnings


def _config_groups() -> dict[str, object]:
    callback_urls = settings.callback_urls()
    return {
        "rtc": {
            "configured": bool(settings.volcengine_rtc_app_id and settings.volcengine_rtc_app_key),
            "app_id": settings.volcengine_rtc_app_id,
            "validate_with": "POST /api/bootstrap + Web RTC joinRoom",
        },
        "openapi": {
            "configured": rtc_openapi.ready,
            "version": settings.volcengine_voice_chat_version,
            "validate_with": "POST /api/rtc/sessions/{session_id}/start",
        },
        "realtime_api_key": {
            "configured": bool(settings.volcengine_realtime_api_key),
            "usage": "豆包实时语音快速 API 接入，不替代 RTC AppId/AppKey",
        },
        "s2s": {
            "enabled": settings.volcengine_enable_s2s,
            "configured": settings.s2s_ready,
            "primary": settings.volcengine_primary_dialog_path == "s2s",
            "effective": settings.effective_dialog_path == "s2s",
            "source": settings.s2s_config_source,
            "validate_with": "StartVoiceChat 成功 + room binary message + 首答/打断",
        },
        "memory": {
            "enabled": settings.volcengine_enable_memory,
            "configured": settings.memory_ready,
            "source": settings.memory_config_source,
            "supported_version": settings.volcengine_voice_chat_version == "2024-12-01",
            "validate_with": "多轮连续对话观察记忆命中",
        },
        "memory_api": {
            "configured": settings.memory_api_ready,
            "base_url": settings.volcengine_memory_api_base_url,
            "collection_name": settings.volcengine_memory_collection_name,
            "project_name": settings.volcengine_memory_project_name,
            "validate_with": "GET /api/validate/memory",
        },
        "backend_fallback": {
            "enabled": settings.volcengine_use_backend_fallback,
            "ragflow_search_url": settings.ragflow_search_url,
            "validate_with": "POST /api/rtc/sessions/{session_id}/utterances",
        },
        "revenue_mcp": {
            "enabled": settings.revenue_mcp_enabled,
            "configured": settings.revenue_mcp_ready,
            "sse_url": settings.revenue_mcp_sse_url,
            "api_health_url": settings.revenue_mcp_api_health_url,
            "validate_with": "GET /api/validate/revenue-mcp",
        },
        "asr_tts_backup": {
            "configured": settings.asr_tts_ready,
            "primary": settings.volcengine_primary_dialog_path in {"asr_tts", "asr-llm-tts", "cascade"},
            "effective": settings.effective_dialog_path == "asr_tts",
            "validate_with": "关闭 S2S 或缺失 S2SConfig 时启动 VoiceChat",
        },
        "callbacks": {
            "configured": bool(settings.volcengine_callback_base_url),
            "base_url": settings.volcengine_callback_base_url,
            "urls": callback_urls,
            "validate_with": "公网访问 /api/volcengine/callbacks/* 并在 5 秒内返回 200",
        },
        "avatar": {
            "official_avatar_enabled": settings.volcengine_avatar_enabled,
            "self_avatar_mount_id": settings.self_avatar_mount_id,
            "mode": settings.self_avatar_mode,
        },
    }


def _faq_to_backend_result(resolved: Any) -> BackendTurnResult:
    state = "handoff" if resolved.status == "handoff" else "speaking"
    return BackendTurnResult(
        status=resolved.status,
        display_text=resolved.display_text,
        speak_text=resolved.speak_text,
        state=state,
        confidence=resolved.confidence,
        needs_handoff=resolved.needs_handoff,
    )


def _decide_turn_owner(session_id: str, user_text: str) -> dict[str, object]:
    if settings.effective_dialog_path == "unconfigured":
        return {
            "owner": "backend",
            "intent": "faq",
            "confidence": 1.0,
            "reason": "dialog-ai-unconfigured-backend",
        }

    pending_confirmation = lobby.get_pending_confirmation(session_id)
    decision = decide_turn_route(
        user_text,
        store.items,
        has_pending_confirmation=bool(pending_confirmation),
        faq_route_mode=settings.volcengine_faq_route_mode,
    )
    if settings.pure_s2s_enabled:
        return {
            "owner": "s2s",
            "intent": decision.intent,
            "confidence": max(decision.confidence, 0.99),
            "reason": "pure-s2s-test-mode",
        }
    if decision.owner == "s2s" and settings.effective_dialog_path == "unconfigured" and settings.volcengine_use_backend_fallback:
        return {
            "owner": "backend",
            "intent": decision.intent,
            "confidence": decision.confidence,
            "reason": "dialog-ai-not-ready-fallback",
        }
    return {
        "owner": decision.owner,
        "intent": decision.intent,
        "confidence": decision.confidence,
        "reason": decision.reason,
    }


def _resolve_session_for_payload(payload: Any) -> str | None:
    if isinstance(payload, dict):
        direct_keys = (
            payload.get("SessionId"),
            payload.get("session_id"),
            payload.get("TaskId"),
            payload.get("task_id"),
            payload.get("RoomId"),
            payload.get("room_id"),
        )
        for candidate in direct_keys:
            if not candidate:
                continue
            with state_lock:
                for session in lobby.list_sessions():
                    if candidate in {
                        session.session_id,
                        session.task_id,
                        session.room_id,
                    }:
                        return session.session_id
        for value in payload.values():
            resolved = _resolve_session_for_payload(value)
            if resolved:
                return resolved
    if isinstance(payload, list):
        for item in payload:
            resolved = _resolve_session_for_payload(item)
            if resolved:
                return resolved
    return None


def _record_global_voicechat_callback(kind: str, payload: dict[str, Any]) -> None:
    voicechat_callback_log.append(
        {
            "kind": kind,
            "payload": payload,
        }
    )
    del voicechat_callback_log[:-50]


async def _start_voice_chat(session_id: str) -> dict[str, Any]:
    with state_lock:
        session = lobby.get_session(session_id)
        if session.voice_chat_started:
            return {
                "started": True,
                "already_started": True,
                "task_id": session.task_id,
                "effective_dialog_path": settings.effective_dialog_path,
            }
        if not rtc_openapi.ready or not voice_chat_factory.ready:
            return {
                "started": False,
                "warnings": _session_warnings(),
                "effective_dialog_path": settings.effective_dialog_path,
            }
        payload = voice_chat_factory.build_start_payload(session)

    response = await asyncio.to_thread(rtc_openapi.start_voice_chat, payload)
    with state_lock:
        lobby.mark_voice_chat_started(session_id)
        lobby.publish_event(
            session_id,
            "voice_chat",
            {"action": "start", "response": response, "task_id": session.task_id},
        )
    return {
        "started": True,
        "response": response,
        "task_id": session.task_id,
        "effective_dialog_path": settings.effective_dialog_path,
    }


async def _stop_voice_chat(session_id: str) -> dict[str, Any]:
    with state_lock:
        session = lobby.get_session(session_id)
        if not session.voice_chat_started:
            return {"stopped": True, "already_stopped": True}
        if not rtc_openapi.ready:
            session.voice_chat_started = False
            return {"stopped": True, "warnings": _session_warnings()}
        payload = voice_chat_factory.build_stop_payload(session)

    response = await asyncio.to_thread(rtc_openapi.stop_voice_chat, payload)
    with state_lock:
        lobby.mark_voice_chat_stopped(session_id)
        lobby.publish_event(
            session_id,
            "voice_chat",
            {"action": "stop", "response": response, "task_id": session.task_id},
        )
    return {"stopped": True, "response": response}


async def _send_voice_chat_command(
    session_id: str,
    command: str,
    message: str = "",
    interrupt_mode: int = 1,
    **extra: Any,
) -> dict[str, Any]:
    with state_lock:
        session = lobby.get_session(session_id)
        if not session.voice_chat_started:
            return {"sent": False, "reason": "voice-chat-not-started"}
        if not rtc_openapi.ready:
            return {"sent": False, "reason": "openapi-not-ready"}
        payload = voice_chat_factory.build_update_payload(
            session,
            {
                "Command": command,
                "InterruptMode": interrupt_mode,
                "Message": message,
                **extra,
            },
        )

    try:
        response = await asyncio.to_thread(rtc_openapi.update_voice_chat, payload)
    except Exception as exc:
        with state_lock:
            lobby.publish_event(
                session_id,
                "callback",
                {
                    "callback_type": "voicechat_command_error",
                    "command": command,
                    "error": str(exc),
                },
            )
            lobby.set_error(session_id, f"UpdateVoiceChat({command}) 调用失败：{exc}")
        return {"sent": False, "reason": "update-failed", "error": str(exc)}
    with state_lock:
        lobby.publish_event(
            session_id,
            "voice_chat",
            {
                "action": "update",
                "command": command,
                "response": response,
            },
        )
    return {"sent": True, "response": response}


async def _process_turn(
    session_id: str,
    turn_id: int,
    user_text: str,
    route: dict[str, object],
) -> None:
    start_ts = perf_counter()

    async def send_transition() -> None:
        await asyncio.sleep(settings.answer_timeout_ms / 1000)
        with state_lock:
            if not lobby.mark_transition_sent(session_id, turn_id):
                return
            lobby.publish_event(
                session_id,
                "subtitle",
                {
                    "speaker": "ai",
                    "text": settings.transition_text,
                    "turn_id": turn_id,
                    "kind": "transition",
                },
            )
        await _send_voice_chat_command(
            session_id,
            "ExternalTextToSpeech",
            settings.transition_text,
            1,
        )

    transition_task = asyncio.create_task(send_transition())
    with state_lock:
        pending_confirmation = lobby.get_pending_confirmation(session_id)

    try:
        if route["intent"] in {"pricing", "pricing_confirm"}:
            resolved = await revenue_mcp.resolve_query(user_text, pending_confirmation)
        elif route["intent"] == "faq":
            resolved = _faq_to_backend_result(resolve_answer(user_text, store.items))
        else:
            resolved = _faq_to_backend_result(await ragflow.resolve(user_text))
    except Exception as exc:
        resolved = BackendTurnResult(
            status="error",
            display_text=f"后端处理失败：{exc}",
            speak_text="当前这一轮处理失败，我先为您保留会话，您可以再说一次。",
            state="error",
            metadata={"error": str(exc)},
        )
    processing_ms = round((perf_counter() - start_ts) * 1000, 2)

    if not transition_task.done():
        transition_task.cancel()
        try:
            await transition_task
        except asyncio.CancelledError:
            pass

    with state_lock:
        turn_state = lobby.finish_turn(
            session_id,
            turn_id,
            resolved.status,
            resolved.display_text,
            resolved.speak_text,
            processing_ms,
            resolved.state,
            resolved.action_state,
            resolved.metadata,
            resolved.pending_confirmation,
            resolved.clear_pending_confirmation,
        )
        if turn_state["discarded"]:
            return
        lobby.publish_event(
            session_id,
            "state",
            {
                "state": resolved.state,
                "detail": resolved.display_text,
                "turn_id": turn_id,
                "action_state": resolved.action_state,
            },
        )
        lobby.publish_event(
            session_id,
            "turn_result",
            {
                "turn_id": turn_id,
                "status": resolved.status,
                "display_text": resolved.display_text,
                "speak_text": resolved.speak_text,
                "confidence": resolved.confidence,
                "needs_handoff": resolved.needs_handoff,
                "processing_ms": processing_ms,
                "state": resolved.state,
                "action_state": resolved.action_state,
                "metadata": resolved.metadata,
            },
        )
        lobby.publish_event(
            session_id,
            "subtitle",
            {
                "speaker": "ai",
                "text": resolved.display_text,
                "turn_id": turn_id,
                "kind": "final",
            },
        )
    for chunk in chunk_speak_text(resolved.speak_text):
        await _send_voice_chat_command(
            session_id,
            "ExternalTextToSpeech",
            chunk,
            1,
        )


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "app_name": settings.app_name,
            "hotel_id": settings.hotel_id,
        },
    )


@app.get("/api/health")
async def health() -> dict[str, object]:
    return {
        "ok": True,
        "port": settings.app_port,
        "hotel_id": settings.hotel_id,
        "faq_stats": store.stats(),
        "volcengine": {
            "rtc_app_configured": bool(settings.volcengine_rtc_app_id and settings.volcengine_rtc_app_key),
            "openapi_ready": rtc_openapi.ready,
            "voice_chat_ready": voice_chat_factory.ready,
            "primary_dialog_path": settings.volcengine_primary_dialog_path,
            "effective_dialog_path": settings.effective_dialog_path,
            "voice_chat_version": settings.volcengine_voice_chat_version,
        },
        "config_groups": _config_groups(),
        "warnings": _session_warnings(),
    }


@app.get("/api/validate/config-groups")
async def validate_config_groups() -> dict[str, object]:
    return {
        "ok": True,
        "groups": _config_groups(),
        "warnings": _session_warnings(),
    }


@app.get("/api/validate/callback-manifest")
async def validate_callback_manifest() -> dict[str, object]:
    return {
        "ok": True,
        "base_url": settings.volcengine_callback_base_url,
        "urls": settings.callback_urls(),
        "requires_public_https": True,
    }


@app.get("/api/validate/voicechat-callbacks")
async def validate_voicechat_callbacks() -> dict[str, object]:
    return {
        "ok": True,
        "count": len(voicechat_callback_log),
        "items": voicechat_callback_log[-20:],
    }


@app.get("/api/validate/voicechat-latency")
async def validate_voicechat_latency() -> dict[str, object]:
    rounds: dict[tuple[str | None, str | None, int | None], dict[str, object]] = {}
    for item in voicechat_callback_log:
        payload = item.get("payload", {})
        event_data = payload.get("EventData")
        if not event_data:
            continue
        try:
            parsed = json.loads(event_data)
        except json.JSONDecodeError:
            continue
        key = (
            parsed.get("RoomId"),
            parsed.get("TaskId"),
            parsed.get("RoundID"),
        )
        bucket = rounds.setdefault(
            key,
            {
                "room_id": parsed.get("RoomId"),
                "task_id": parsed.get("TaskId"),
                "round_id": parsed.get("RoundID"),
                "user_id": parsed.get("UserID"),
                "stages": {},
                "error": parsed.get("ErrorInfo", {}),
            },
        )
        bucket["stages"][parsed.get("RunStage")] = parsed.get("EventTime")
        bucket["error"] = parsed.get("ErrorInfo", {})

    def _delta(stages: dict[str, int], start: str, end: str) -> int | None:
        left = stages.get(start)
        right = stages.get(end)
        if left is None or right is None:
            return None
        return int(right) - int(left)

    items: list[dict[str, object]] = []
    for bucket in rounds.values():
        stages = bucket["stages"]
        items.append(
            {
                "room_id": bucket["room_id"],
                "task_id": bucket["task_id"],
                "round_id": bucket["round_id"],
                "user_id": bucket["user_id"],
                "stages": sorted(stages.keys()),
                "error": bucket["error"],
                "begin_to_asr_ms": _delta(stages, "beginAsking", "asrFinish"),
                "asr_to_reasoning_ms": _delta(stages, "asrFinish", "reasoningStart"),
                "reasoning_to_llm_ms": _delta(stages, "reasoningStart", "llmOutput"),
                "llm_to_answer_ms": _delta(stages, "llmOutput", "answerStart"),
                "begin_to_answer_ms": _delta(stages, "beginAsking", "answerStart"),
                "begin_to_finish_ms": _delta(stages, "beginAsking", "answerFinish"),
            }
        )
    items.sort(key=lambda row: (str(row["task_id"]), int(row["round_id"] or 0)))
    return {
        "ok": True,
        "faq_route_mode": settings.volcengine_faq_route_mode,
        "items": items[-20:],
    }


@app.get("/api/validate/ragflow")
async def validate_ragflow() -> dict[str, object]:
    if not settings.ragflow_search_url:
        return {
            "ok": False,
            "configured": False,
            "detail": "未配置 RAGFLOW_SEARCH_URL。",
        }
    resolved = await ragflow._resolve_remote("酒店在什么位置")
    return {
        "ok": resolved is not None,
        "configured": True,
        "resolved": resolved is not None,
        "sample_answer": resolved.display_text if resolved else "",
    }


@app.get("/api/validate/memory")
async def validate_memory() -> dict[str, object]:
    if not settings.memory_api_ready:
        return {
            "ok": False,
            "configured": False,
            "detail": "未配置完整的后端 Memory API 参数。",
        }
    try:
        payload = await memory.get_context(
            query="有没有一次性剃须刀？",
            conversation_id="validation_conversation",
            user_id=settings.volcengine_memory_default_user_id,
        )
        return {
            "ok": True,
            "configured": True,
            "resolved": payload is not None,
            "payload": payload or {},
        }
    except Exception as exc:
        return {
            "ok": False,
            "configured": True,
            "detail": str(exc),
        }


@app.get("/api/validate/revenue-mcp")
async def validate_revenue_mcp() -> dict[str, object]:
    if not settings.revenue_mcp_enabled:
        return {
            "ok": False,
            "configured": False,
            "detail": "未启用收益调价 MCP。",
        }
    return await revenue_mcp.validate_connectivity()


@app.get("/api/validate/revenue-mcp/tools/{tool_name}")
async def validate_revenue_mcp_tool(tool_name: str) -> dict[str, object]:
    return await revenue_mcp.validate_tool(tool_name)


@app.get("/api/validate/voice-chat-payload")
async def validate_voice_chat_payload() -> dict[str, object]:
    preview_session = RTCSessionState(
        session_id="preview-session",
        client_id="preview",
        transport="volcengine-rtc",
        room_id="preview-room",
        user_id="preview-user",
        ai_user_id="preview-ai",
        rtc_token="",
        task_id="preview-task",
        created_ts=0.0,
        last_seen_ts=0.0,
        presence=PresenceState(),
    )
    payload = voice_chat_factory.build_start_payload(preview_session)
    return {
        "ok": True,
        "version": settings.volcengine_voice_chat_version,
        "primary_dialog_path": settings.volcengine_primary_dialog_path,
        "effective_dialog_path": settings.effective_dialog_path,
        "payload": payload,
    }


@app.post("/api/bootstrap")
async def bootstrap(request: BootstrapRequest) -> dict[str, object]:
    started = perf_counter()
    room_id = _make_room_id()
    user_id = _make_user_id()
    ai_user_id = _make_ai_user_id()
    rtc_token = ""
    if settings.volcengine_rtc_app_id and settings.volcengine_rtc_app_key:
        rtc_token = generate_rtc_token(
            settings.volcengine_rtc_app_id,
            settings.volcengine_rtc_app_key,
            room_id,
            user_id,
            settings.volcengine_token_expire_seconds,
        )
    with state_lock:
        session = lobby.create_session(
            request.client_id,
            request.transport,
            rtc_token,
            room_id,
            user_id,
            ai_user_id,
        )
    return {
        "session_id": session.session_id,
        "processing_ms": round((perf_counter() - started) * 1000, 2),
        "warnings": _session_warnings(),
        "rtc": {
            "app_id": settings.volcengine_rtc_app_id,
            "room_id": session.room_id,
            "user_id": session.user_id,
            "ai_user_id": session.ai_user_id,
            "token": session.rtc_token,
            "transport": session.transport,
        },
        "voice_chat": {
            "ready": rtc_openapi.ready and voice_chat_factory.ready,
            "command_channel": settings.volcengine_command_channel,
            "task_id": session.task_id,
            "version": settings.volcengine_voice_chat_version,
            "primary_dialog_path": settings.volcengine_primary_dialog_path,
            "effective_dialog_path": settings.effective_dialog_path,
            "pure_s2s_enabled": settings.pure_s2s_enabled,
            "faq_route_mode": settings.volcengine_faq_route_mode,
            "s2s_enabled": settings.volcengine_enable_s2s,
            "s2s_ready": settings.s2s_ready,
            "memory_enabled": settings.volcengine_enable_memory,
            "memory_ready": settings.memory_ready,
            "turn_detection_mode": 1,
            "subtitle_mode": 1,
            "greeting_text": settings.greeting_text,
            "transition_text": settings.transition_text,
            "callback_urls": settings.callback_urls(),
        },
        "pricing": {
            "revenue_mcp_enabled": settings.revenue_mcp_enabled,
            "revenue_mcp_sse_url": settings.revenue_mcp_sse_url,
            "confirmation_ttl_seconds": settings.revenue_mcp_confirmation_ttl_seconds,
        },
        "sdk": {
            "esm_url": settings.volcengine_frontend_sdk_url,
        },
        "avatar": {
            "official_avatar_enabled": settings.volcengine_avatar_enabled,
            "self_avatar_mount_id": settings.self_avatar_mount_id,
            "self_avatar_mode": settings.self_avatar_mode,
        },
    }


@app.post("/api/rtc/sessions/{session_id}/connected")
async def rtc_connected(session_id: str) -> dict[str, object]:
    try:
        with state_lock:
            lobby.mark_rtc_connected(session_id)
            snapshot = lobby.snapshot(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="RTC session not found") from exc
    return snapshot


@app.post("/api/rtc/sessions/{session_id}/start")
async def start_rtc_voice_chat(session_id: str) -> dict[str, object]:
    try:
        return await _start_voice_chat(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="RTC session not found") from exc
    except Exception as exc:
        with state_lock:
            lobby.set_error(session_id, f"StartVoiceChat 调用失败：{exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/rtc/sessions/{session_id}/stop")
async def stop_rtc_voice_chat(session_id: str) -> dict[str, object]:
    try:
        return await _stop_voice_chat(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="RTC session not found") from exc
    except Exception as exc:
        with state_lock:
            lobby.set_error(session_id, f"StopVoiceChat 调用失败：{exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/rtc/sessions/{session_id}/agent-command-acks")
async def rtc_agent_command_ack(
    session_id: str, request: AgentCommandAckRequest
) -> dict[str, object]:
    try:
        with state_lock:
            lobby.get_session(session_id)
            lobby.publish_event(
                session_id,
                "callback",
                {
                    "callback_type": "agent_command_ack",
                    "command": request.command,
                    "ok": request.ok,
                    "detail": request.detail,
                    "turn_id": request.turn_id,
                },
            )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="RTC session not found") from exc
    return {"ok": True}


@app.get("/api/rtc/sessions/{session_id}/events")
async def rtc_session_events(session_id: str) -> StreamingResponse:
    try:
        with state_lock:
            lobby.get_session(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="RTC session not found") from exc

    async def stream() -> Any:
        yield "event: ready\ndata: {}\n\n"
        while True:
            try:
                payload = await asyncio.wait_for(lobby.next_event(session_id), timeout=15)
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
            except asyncio.TimeoutError:
                yield ": keep-alive\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/rtc/sessions/{session_id}")
async def get_rtc_session(session_id: str) -> dict[str, object]:
    try:
        with state_lock:
            return lobby.snapshot(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="RTC session not found") from exc


@app.post("/api/rtc/sessions/{session_id}/presence")
async def rtc_presence(session_id: str, _: PresenceRequest) -> dict[str, object]:
    started = perf_counter()
    try:
        with state_lock:
            payload = lobby.register_presence(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="RTC session not found") from exc
    if payload.get("should_greet"):
        await _send_voice_chat_command(
            session_id,
            "ExternalTextToSpeech",
            settings.greeting_text,
            1,
        )
    return {
        "processing_ms": round((perf_counter() - started) * 1000, 2),
        **payload,
    }


@app.post("/api/rtc/sessions/{session_id}/interrupt")
async def rtc_interrupt(session_id: str, request: InterruptRequest) -> dict[str, object]:
    try:
        with state_lock:
            payload = lobby.interrupt(session_id, request.reason)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="RTC session not found") from exc
    await _send_voice_chat_command(
        session_id,
        "interrupt",
        "",
        1,
        Reason=request.reason,
    )
    return payload


@app.post("/api/rtc/sessions/{session_id}/utterances")
async def rtc_utterance(session_id: str, request: QueryRequest) -> dict[str, object]:
    started = perf_counter()
    try:
        with state_lock:
            route = _decide_turn_owner(session_id, request.user_text)
            turn = lobby.start_turn_with_owner(
                session_id,
                request.user_text,
                route["owner"],
                route["reason"],
                route["intent"],
            )
            lobby.publish_event(
                session_id,
                "subtitle",
                {
                    "speaker": "user",
                    "text": request.user_text,
                    "turn_id": turn.turn_id,
                    "kind": request.source,
                },
            )
            if route["owner"] == "backend":
                lobby.publish_event(
                    session_id,
                    "state",
                    {
                        "state": "thinking",
                        "detail": (
                            "本轮问题已切到后端收益链。"
                            if route["intent"] in {"pricing", "pricing_confirm"}
                            else "本轮问题已切到后端知识/规则链。"
                        ),
                        "turn_id": turn.turn_id,
                    },
                )
                asyncio.create_task(
                    _send_voice_chat_command(
                        session_id,
                        "interrupt",
                        "",
                        1,
                        Reason="backend-owned-turn",
                    )
                )
            else:
                lobby.publish_event(
                    session_id,
                    "state",
                    {
                        "state": "listening",
                        "detail": "本轮问题保持在 S2S 主链。",
                        "turn_id": turn.turn_id,
                    },
                )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="RTC session not found") from exc

    if route["owner"] == "backend":
        asyncio.create_task(_process_turn(session_id, turn.turn_id, request.user_text, route))
    return {
        "session_id": session_id,
        "turn_id": turn.turn_id,
        "accepted": True,
        "owner": route["owner"],
        "intent": route["intent"],
        "route_reason": route["reason"],
        "confidence": route["confidence"],
        "processing_ms": round((perf_counter() - started) * 1000, 2),
        "transition_after_ms": settings.answer_timeout_ms,
        "transition_text": settings.transition_text,
    }


@app.post("/api/volcengine/callbacks/subtitles")
async def volcengine_subtitle_callback(request: Request) -> dict[str, object]:
    payload = await request.json()
    _record_global_voicechat_callback("subtitles", payload)
    session_id = _resolve_session_for_payload(payload)
    if session_id:
        with state_lock:
            lobby.record_callback(session_id, "subtitles", payload)
    return {"ok": True}


@app.post("/api/volcengine/callbacks/state")
async def volcengine_state_callback(request: Request) -> dict[str, object]:
    payload = await request.json()
    _record_global_voicechat_callback("state", payload)
    session_id = _resolve_session_for_payload(payload)
    if session_id:
        with state_lock:
            lobby.record_callback(session_id, "state", payload)
    return {"ok": True}


@app.post("/api/volcengine/callbacks/task")
async def volcengine_task_callback(request: Request) -> dict[str, object]:
    payload = await request.json()
    _record_global_voicechat_callback("task", payload)
    session_id = _resolve_session_for_payload(payload)
    if session_id:
        with state_lock:
            lobby.record_callback(session_id, "task", payload)
    return {"ok": True}


@app.post("/api/volcengine/callbacks/voicechat")
async def volcengine_voicechat_callback(request: Request) -> dict[str, object]:
    payload = await request.json()
    _record_global_voicechat_callback("voicechat", payload)
    session_id = _resolve_session_for_payload(payload)
    if session_id:
        with state_lock:
            lobby.record_callback(session_id, "voicechat", payload)
    return {"ok": True}


@app.post("/api/presence")
async def presence(request: PresenceRequest) -> dict[str, object]:
    bootstrap_payload = await bootstrap(BootstrapRequest())
    return await rtc_presence(bootstrap_payload["session_id"], request)


@app.post("/api/query")
async def query(request: QueryRequest) -> dict[str, object]:
    bootstrap_payload = await bootstrap(BootstrapRequest())
    return await rtc_utterance(bootstrap_payload["session_id"], request)
