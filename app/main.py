from __future__ import annotations

import asyncio
import base64
import json
import uuid
from pathlib import Path
from threading import Lock
from time import perf_counter
from typing import Any, Optional

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
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
from app.services.external_search import ExternalSearchFacade
from app.services.fastgpt import FastGPTFacade
from app.services.lobby import LobbyCoordinator
from app.services.memory import MemoryFacade
from app.services.revenue_mcp import RevenueMCPService
from app.services.search import (
    chunk_speak_text,
    decide_turn_route,
    looks_like_hotel_faq_request,
    normalize_text,
    vision_requires_hotel_facts,
)
from app.services.vision import VisionFacade


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
fastgpt = FastGPTFacade()
memory = MemoryFacade()
revenue_mcp = RevenueMCPService()
external_search = ExternalSearchFacade()
vision = VisionFacade()
lobby = LobbyCoordinator()
rtc_openapi = VolcengineRTCOpenAPI()
voice_chat_factory = VoiceChatPayloadFactory()
state_lock = Lock()
voicechat_callback_log: list[dict[str, Any]] = []
voice_chat_command_locks: dict[str, asyncio.Lock] = {}
INTERRUPT_GATE_TIMEOUT_MS = 320
INTERRUPT_GATE_POLL_MS = 40

class BootstrapRequest(BaseModel):
    client_id: str = "lobby-screen"
    transport: str = "volcengine-rtc"


class PresenceRequest(BaseModel):
    source: str = "camera"


class QueryRequest(BaseModel):
    user_text: str
    source: str = "rtc-subtitle"


class VisionAnalyzeResponse(BaseModel):
    ok: bool
    configured: bool
    scene_summary: str
    detected_text: str
    objects: list[Any]
    confidence: float
    detail: str = ""


class InterruptRequest(BaseModel):
    reason: str = "barge-in"


class CallbackPayload(BaseModel):
    payload: dict[str, Any]


class AgentCommandAckRequest(BaseModel):
    command: str
    ok: bool = True
    detail: str = ""
    turn_id: Optional[int] = None
    turn_token: Optional[str] = None


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


def _turn_fields(session: RTCSessionState | None) -> dict[str, Any]:
    if session is None or session.last_turn is None:
        return {}
    turn = session.last_turn
    return {
        "turn_id": turn.turn_id,
        "turn_token": turn.turn_token,
        "owner": turn.owner,
        "phase": turn.phase,
        "chain": turn.chain,
    }


def _event_matches_current_turn(
    payload: dict[str, Any],
    session: RTCSessionState,
) -> tuple[bool, int | None, str | None]:
    turn_id = payload.get("turn_id")
    turn_token = payload.get("turn_token")
    if isinstance(turn_id, str) and turn_id.isdigit():
        turn_id = int(turn_id)
    elif not isinstance(turn_id, int):
        turn_id = None
    if turn_token is not None:
        turn_token = str(turn_token)
    matches = bool(
        turn_id is not None
        and turn_id == session.active_turn_id
        and turn_token
        and turn_token == session.active_turn_token
    )
    return matches, turn_id, turn_token


def _decode_subtitle_server_message(payload: dict[str, Any]) -> dict[str, Any] | None:
    message = payload.get("message")
    if not isinstance(message, str) or not message:
        return None
    try:
        raw = base64.b64decode(message)
    except Exception:
        return None
    if len(raw) < 8 or raw[:4] != b"subv":
        return None
    expected_length = int.from_bytes(raw[4:8], "big")
    body = raw[8:]
    if expected_length != len(body):
        return None
    try:
        decoded = json.loads(body.decode("utf-8"))
    except Exception:
        return None
    if not isinstance(decoded, dict):
        return None
    return decoded


async def _wait_for_interrupt_gate(session_id: str, turn_id: int, turn_token: str) -> str:
    deadline = perf_counter() + (INTERRUPT_GATE_TIMEOUT_MS / 1000)
    while perf_counter() < deadline:
        with state_lock:
            status = lobby.interrupt_gate_status(session_id, turn_id, turn_token)
        if not status["is_current"]:
            return "stale"
        if status["acked"]:
            return "acked"
        if not status["active"]:
            return "closed"
        await asyncio.sleep(INTERRUPT_GATE_POLL_MS / 1000)
    with state_lock:
        gate_event = lobby.close_interrupt_gate(session_id, turn_id, turn_token, "timeout")
        if gate_event:
            lobby.publish_event(session_id, "state", gate_event)
    return "timeout"


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
        "revenue_mcp": {
            "enabled": settings.revenue_mcp_enabled,
            "configured": settings.revenue_mcp_ready,
            "sse_url": settings.revenue_mcp_sse_url,
            "api_health_url": settings.revenue_mcp_api_health_url,
            "validate_with": "GET /api/validate/revenue-mcp",
        },
        "fastgpt": {
            "enabled": settings.fastgpt_enabled,
            "configured": settings.fastgpt_ready,
            "base_url": settings.fastgpt_base_url,
            "dataset_id": settings.fastgpt_dataset_id,
            "dataset_name": settings.fastgpt_dataset_name,
            "validate_with": "GET /api/validate/fastgpt?q=...",
            "usage": "酒店事实问题唯一知识入口。",
        },
        "volcengine_native_websearch": {
            "enabled": settings.volcengine_llm_websearch_enabled,
            "configured": settings.volcengine_llm_websearch_ready,
            "function_name": settings.volcengine_llm_websearch_function_name,
            "validate_with": "GET /api/validate/voice-chat-payload + 外部动态信息走 S2S/LLMConfig",
            "usage": "火山官方联网问答 Agent / WebSearchAgentConfig，优先用于天气、交通、周边等动态问题。",
        },
        "external_search": {
            "enabled": settings.external_search_enabled,
            "configured": settings.external_search_enabled,
            "engine": settings.external_search_engine,
            "validate_with": "GET /api/validate/external-search?q=天气怎么样",
            "usage": "后端兜底联网搜索，仅在未启用火山官方联网问答 Agent 时处理外部动态信息。",
        },
        "volcengine_native_vision": {
            "enabled": settings.volcengine_llm_vision_enabled,
            "configured": settings.volcengine_llm_vision_ready,
            "camera_enabled": settings.volcengine_enable_camera_vision,
            "validate_with": "GET /api/validate/voice-chat-payload + RTC 视频采集/发布",
            "usage": "火山官方视觉理解能力，通过 LLMConfig.VisionConfig 接入；启用摄像头后可供主链直接感知画面。",
        },
        "vision": {
            "enabled": settings.vision_analysis_enabled,
            "configured": bool(settings.vision_analysis_url),
            "validate_with": "GET /api/validate/vision-config + POST /api/vision/analyze",
            "usage": "后端图片分析兜底，仅在未启用火山官方视觉链或上传图片场景下使用。",
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


def _fastgpt_to_backend_result(result: dict[str, Any]) -> BackendTurnResult:
    answer = str(result.get("answer") or "").strip()
    matched_question = str(result.get("matched_question") or "").strip()
    score = float(result.get("score") or 0.0)
    route = str(result.get("route") or "").strip()
    route_label = str(result.get("route_label") or "").strip()
    dataset_name = str(result.get("dataset_name") or "").strip()
    if result.get("hit") and answer:
        return BackendTurnResult(
            status="answered",
            display_text=answer,
            speak_text=answer,
            state="speaking",
            confidence=score,
            metadata={
                "source": "fastgpt",
                "matched_question": matched_question,
                "score": score,
                "route": route,
                "route_label": route_label,
                "dataset_name": dataset_name,
                "quotes": result.get("quotes") or [],
            },
        )
    not_found = "这个我这边暂时没查到准确信息，您也可以直接联系前台确认一下。"
    return BackendTurnResult(
        status="not_found",
        display_text=not_found,
        speak_text=not_found,
        state="speaking",
        confidence=score,
        metadata={
            "source": "fastgpt",
            "matched_question": matched_question,
            "score": score,
            "route": route,
            "route_label": route_label,
            "dataset_name": dataset_name,
            "fallback_miss": True,
        },
    )


def _build_not_found_result(source: str, chain: str = "hotel_fact_chain") -> BackendTurnResult:
    not_found = "这个我这边暂时没查到准确信息，您也可以直接联系前台确认一下。"
    return BackendTurnResult(
        status="not_found",
        display_text=not_found,
        speak_text=not_found,
        state="speaking",
        metadata={
            "source": source,
            "chain": chain,
            "grounding_source": source,
            "confidence_band": "low",
        },
    )


def _attach_chain_metadata(
    result: BackendTurnResult,
    chain: str,
    grounding_source: str,
    tool_calls: list[str] | None = None,
    **extra: Any,
) -> BackendTurnResult:
    metadata = dict(result.metadata)
    metadata.setdefault("source", grounding_source)
    metadata["chain"] = chain
    metadata["grounding_source"] = grounding_source
    metadata["tool_calls"] = tool_calls or []
    metadata["confidence_band"] = (
        "high" if result.confidence >= 0.85 else "medium" if result.confidence >= 0.6 else "low"
    )
    metadata.update(extra)
    result.metadata = metadata
    return result


async def _resolve_hotel_fact_result(user_text: str) -> BackendTurnResult:
    if settings.fastgpt_enabled and settings.fastgpt_ready:
        fastgpt_result = await fastgpt.search(user_text)
        if fastgpt_result.get("hit"):
            return _attach_chain_metadata(
                _fastgpt_to_backend_result(fastgpt_result),
                "hotel_fact_chain",
                "fastgpt",
                ["fastgpt"],
            )

    result = _build_not_found_result("fastgpt")
    result.metadata["configured"] = bool(settings.fastgpt_enabled and settings.fastgpt_ready)
    result.metadata["tool_calls"] = ["fastgpt"] if settings.fastgpt_enabled else []
    return result


def _external_info_to_backend_result(result: dict[str, Any]) -> BackendTurnResult:
    if result.get("ok") and result.get("answer"):
        answer = str(result.get("answer") or "").strip()
        return BackendTurnResult(
            status="answered",
            display_text=answer,
            speak_text=answer,
            state="external_searching",
            confidence=0.8 if result.get("results") else 0.45,
            metadata={
                "source": "web",
                "web_sources": result.get("sources") or [],
                "results": result.get("results") or [],
            },
        )
    answer = "这个问题需要参考外部公开信息，但我暂时没有检索到稳定结果，建议以实际现场信息为准。"
    return BackendTurnResult(
        status="not_found",
        display_text=answer,
        speak_text=answer,
        state="external_searching",
        confidence=0.0,
        metadata={
            "source": "web",
            "web_sources": result.get("sources") or [],
            "detail": result.get("detail") or "",
        },
    )


def _vision_to_backend_result(result: dict[str, Any], question: str, needs_fact_resolution: bool) -> BackendTurnResult:
    if result.get("ok") and not needs_fact_resolution:
        observed_bits = [
            str(result.get("scene_summary") or "").strip(),
            str(result.get("detected_text") or "").strip(),
        ]
        answer = "；".join(bit for bit in observed_bits if bit) or "我看到了这张图，但暂时没有提取到稳定的文字或关键物体信息。"
        return BackendTurnResult(
            status="answered",
            display_text=answer,
            speak_text=answer,
            state="vision_processing",
            confidence=float(result.get("confidence") or 0.0),
            metadata={
                "source": "vision",
                "vision_result": result,
                "question": question,
            },
        )
    answer = "这张图片我暂时还不能稳定判断，尤其涉及酒店规则或业务时，我不能直接猜测。"
    return BackendTurnResult(
        status="not_found",
        display_text=answer,
        speak_text=answer,
        state="vision_processing",
        confidence=float(result.get("confidence") or 0.0),
        metadata={
            "source": "vision",
            "vision_result": result,
            "question": question,
            "needs_fact_resolution": needs_fact_resolution,
        },
    )


def _decide_turn_owner(session_id: str, user_text: str) -> dict[str, object]:
    if settings.effective_dialog_path == "unconfigured":
        return {
            "owner": "backend",
            "intent": "faq",
            "confidence": 1.0,
            "reason": "dialog-ai-unconfigured-backend",
            "chain": "hotel_fact_chain",
            "requires_grounding": True,
            "grounding_source": "rule",
            "allow_freeform_answer": False,
        }

    pending_confirmation = lobby.get_pending_confirmation(session_id)
    decision = decide_turn_route(
        user_text,
        store.items,
        has_pending_confirmation=bool(pending_confirmation),
        faq_route_mode=settings.volcengine_faq_route_mode,
    )
    if decision.intent in {"pricing", "pricing_confirm"}:
        return {
            "owner": "backend",
            "intent": decision.intent,
            "confidence": decision.confidence,
            "reason": decision.reason,
            "chain": decision.chain,
            "requires_grounding": decision.requires_grounding,
            "grounding_source": decision.grounding_source,
            "allow_freeform_answer": decision.allow_freeform_answer,
        }
    if decision.intent in {"vision", "external_info"}:
        native_llm_chain_active = settings.effective_dialog_path != "unconfigured"
        if (
            decision.intent == "external_info"
            and native_llm_chain_active
            and settings.volcengine_llm_websearch_ready
        ):
            return {
                "owner": "native",
                "intent": decision.intent,
                "confidence": decision.confidence,
                "reason": "volcengine-native-websearch",
                "chain": "social_chain",
                "requires_grounding": True,
                "grounding_source": "web",
                "allow_freeform_answer": True,
            }
        if (
            decision.intent == "vision"
            and native_llm_chain_active
            and settings.volcengine_llm_vision_ready
            and settings.volcengine_enable_camera_vision
        ):
            return {
                "owner": "native",
                "intent": decision.intent,
                "confidence": decision.confidence,
                "reason": "volcengine-native-vision",
                "chain": "vision_chain",
                "requires_grounding": True,
                "grounding_source": "vision",
                "allow_freeform_answer": False,
            }
        return {
            "owner": "backend",
            "intent": decision.intent,
            "confidence": decision.confidence,
            "reason": decision.reason,
            "chain": decision.chain,
            "requires_grounding": decision.requires_grounding,
            "grounding_source": decision.grounding_source,
            "allow_freeform_answer": decision.allow_freeform_answer,
        }
    if decision.intent == "faq" or looks_like_hotel_faq_request(normalize_text(user_text)):
        return {
            "owner": "backend",
            "intent": "faq",
            "confidence": max(decision.confidence, 0.8),
            "reason": "hotel-knowledge-fastgpt-priority",
            "chain": "hotel_fact_chain",
            "requires_grounding": True,
            "grounding_source": "faq",
            "allow_freeform_answer": False,
        }
    if settings.pure_s2s_enabled:
        return {
            "owner": "native",
            "intent": decision.intent,
            "confidence": max(decision.confidence, 0.99),
            "reason": "pure-s2s-test-mode",
            "chain": "social_chain",
            "requires_grounding": False,
            "grounding_source": "none",
            "allow_freeform_answer": True,
        }
    if decision.owner == "native" and settings.effective_dialog_path == "unconfigured" and settings.volcengine_use_backend_fallback:
        return {
            "owner": "backend",
            "intent": decision.intent,
            "confidence": decision.confidence,
            "reason": "dialog-ai-not-ready-fallback",
            "chain": "hotel_fact_chain",
            "requires_grounding": True,
            "grounding_source": "rule",
            "allow_freeform_answer": False,
        }
    return {
        "owner": decision.owner,
        "intent": decision.intent,
        "confidence": decision.confidence,
        "reason": decision.reason,
        "chain": decision.chain,
        "requires_grounding": decision.requires_grounding,
        "grounding_source": decision.grounding_source,
        "allow_freeform_answer": decision.allow_freeform_answer,
    }


def _resolve_session_for_payload(payload: Any) -> str | None:
    if isinstance(payload, dict):
        decoded_subtitle = _decode_subtitle_server_message(payload)
        if decoded_subtitle:
            entries = decoded_subtitle.get("data") or []
            candidate_user_ids = {
                str(item.get("userId"))
                for item in entries
                if isinstance(item, dict) and item.get("userId")
            }
            if candidate_user_ids:
                with state_lock:
                    for session in lobby.list_sessions():
                        if session.user_id in candidate_user_ids or session.ai_user_id in candidate_user_ids:
                            return session.session_id
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


def _get_voice_chat_command_lock(session_id: str) -> asyncio.Lock:
    lock = voice_chat_command_locks.get(session_id)
    if lock is None:
        lock = asyncio.Lock()
        voice_chat_command_locks[session_id] = lock
    return lock


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

    command_lock = _get_voice_chat_command_lock(session_id)
    try:
        async with command_lock:
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
    turn_token: str,
    user_text: str,
    route: dict[str, object],
) -> None:
    start_ts = perf_counter()
    transition_delay_ms = settings.answer_timeout_ms
    should_send_transition = route["intent"] in {"pricing", "pricing_confirm"}
    if should_send_transition:
        transition_delay_ms = max(settings.answer_timeout_ms, 1200)

    async def send_transition() -> None:
        await asyncio.sleep(transition_delay_ms / 1000)
        with state_lock:
            if not lobby.mark_transition_sent(session_id, turn_id):
                return
            session = lobby.get_session(session_id)
            lobby.publish_event(
                session_id,
                "subtitle",
                {
                    **_turn_fields(session),
                    "speaker": "ai",
                    "text": settings.transition_text,
                    "turn_id": turn_id,
                    "kind": "transition",
                    "is_final": False,
                },
            )
        await _send_voice_chat_command(
            session_id,
            "ExternalTextToSpeech",
            settings.transition_text,
            1,
        )

    transition_task = asyncio.create_task(send_transition()) if should_send_transition else None
    interrupt_gate = "not_needed"
    with state_lock:
        pending_confirmation = lobby.get_pending_confirmation(session_id)
        phase_payload = lobby.mark_turn_phase(session_id, turn_id, "backend_processing")
        if phase_payload and route["owner"] == "backend":
            gate_payload = lobby.begin_interrupt_gate(session_id, turn_id, "backend-owned-turn")
            if gate_payload:
                lobby.publish_event(session_id, "state", gate_payload)
                phase_payload = None
    if route["owner"] == "backend":
        interrupt_gate = await _wait_for_interrupt_gate(session_id, turn_id, turn_token)
        if interrupt_gate == "stale":
            return
        with state_lock:
            processing_payload = lobby.mark_turn_phase(session_id, turn_id, "backend_processing")
            if processing_payload:
                session = lobby.get_session(session_id)
                lobby.publish_event(
                    session_id,
                    "state",
                    {
                        **processing_payload,
                        "state": "thinking",
                        "detail": "后端正在生成当前轮答案。",
                        "interrupt_gate": interrupt_gate,
                    },
                )

    try:
        if route["intent"] in {"pricing", "pricing_confirm"}:
            resolved = _attach_chain_metadata(
                await revenue_mcp.resolve_query(session_id, user_text, pending_confirmation),
                str(route.get("chain") or "hotel_fact_chain"),
                "mcp",
                ["revenue_mcp"],
            )
        elif route["intent"] == "external_info":
            resolved = _attach_chain_metadata(
                _external_info_to_backend_result(await external_search.search(user_text)),
                "hotel_fact_chain",
                "web",
                ["external_search"],
            )
        elif route["intent"] == "vision":
            resolved = _attach_chain_metadata(
                BackendTurnResult(
                    status="not_found",
                    display_text="如果您希望我看图识别，请先上传或抓拍一张图片，我再帮您分析。",
                    speak_text="如果您希望我看图识别，请先上传或抓拍一张图片，我再帮您分析。",
                    state="vision_processing",
                    confidence=0.0,
                ),
                "vision_chain",
                "vision",
                ["vision"],
            )
        elif route["intent"] == "faq":
            resolved = await _resolve_hotel_fact_result(user_text)
        else:
            resolved = _attach_chain_metadata(
                BackendTurnResult(
                    status="not_found",
                    display_text="这类内容我先保持闲聊处理，如果您是在问酒店具体信息，可以直接说得更明确一点。",
                    speak_text="这类内容我先保持闲聊处理，如果您是在问酒店具体信息，可以直接说得更明确一点。",
                    state="speaking",
                    confidence=0.0,
                ),
                "social_chain",
                "none",
                [],
            )
    except Exception as exc:
        resolved = BackendTurnResult(
            status="error",
            display_text=f"后端处理失败：{exc}",
            speak_text="当前这一轮处理失败，我先为您保留会话，您可以再说一次。",
            state="error",
            metadata={"error": str(exc)},
        )
    processing_ms = round((perf_counter() - start_ts) * 1000, 2)
    resolved.metadata.setdefault("turn_token", turn_token)
    resolved.metadata.setdefault("owner", route["owner"])
    resolved.metadata.setdefault("final_source", "turn_result")
    resolved.metadata.setdefault("interrupt_gate", interrupt_gate)
    resolved.metadata.setdefault("discard_reason", "")

    if transition_task and not transition_task.done():
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
        session = lobby.get_session(session_id)
        lobby.mark_turn_phase(session_id, turn_id, "completed")
        lobby.publish_event(
            session_id,
            "state",
            {
                **_turn_fields(session),
                "state": resolved.state,
                "detail": resolved.display_text,
                "turn_id": turn_id,
                "action_state": resolved.action_state,
                "interrupt_gate": interrupt_gate,
            },
        )
        lobby.publish_event(
            session_id,
            "turn_result",
            {
                **_turn_fields(session),
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
                "owner": route["owner"],
            },
        )
        lobby.publish_event(
            session_id,
            "subtitle",
            {
                **_turn_fields(session),
                "speaker": "ai",
                "text": resolved.display_text,
                "turn_id": turn_id,
                "kind": "final",
                "is_final": True,
            },
        )
        lobby.mark_turn_phase(session_id, turn_id, "tts_queued")
    for chunk in chunk_speak_text(resolved.speak_text):
        with state_lock:
            speak_payload = lobby.mark_turn_phase(session_id, turn_id, "speaking")
            if speak_payload:
                session = lobby.get_session(session_id)
                lobby.publish_event(
                    session_id,
                    "state",
                    {
                        **_turn_fields(session),
                        "state": "speaking",
                        "detail": resolved.display_text,
                        "action_state": resolved.action_state,
                        "interrupt_gate": interrupt_gate,
                    },
                )
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


@app.get("/stage", response_class=HTMLResponse)
async def stage(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        "stage.html",
        {
            "request": request,
            "app_name": settings.app_name,
            "hotel_id": settings.hotel_id,
            "embed_mode": False,
        },
    )


@app.get("/stage-panel", response_class=HTMLResponse)
async def stage_panel(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        "stage.html",
        {
            "request": request,
            "app_name": settings.app_name,
            "hotel_id": settings.hotel_id,
            "embed_mode": True,
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


@app.get("/api/validate/fastgpt")
async def validate_fastgpt(q: str) -> dict[str, object]:
    return {
        "source": "fastgpt-service",
        **await fastgpt.validate(q),
    }


@app.get("/api/validate/external-search")
async def validate_external_search(q: str) -> dict[str, object]:
    return {
        "source": "external-search",
        "native_websearch_enabled": settings.volcengine_llm_websearch_ready,
        **await external_search.search(q),
    }


@app.get("/api/validate/vision-config")
async def validate_vision_config() -> dict[str, object]:
    return {
        "ok": True,
        "enabled": settings.vision_analysis_enabled,
        "configured": bool(settings.vision_analysis_url),
        "timeout_seconds": settings.vision_analysis_timeout_seconds,
        "native_vision_enabled": settings.volcengine_llm_vision_ready,
        "camera_vision_enabled": settings.volcengine_enable_camera_vision,
    }


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
            "turn_detection_mode": settings.volcengine_asr_turn_detection_mode,
            "subtitle_mode": 1,
            "greeting_text": settings.greeting_text,
            "transition_text": settings.transition_text,
            "callback_urls": settings.callback_urls(),
            "native_websearch_enabled": settings.volcengine_llm_websearch_ready,
            "native_vision_enabled": settings.volcengine_llm_vision_ready,
            "camera_vision_enabled": settings.volcengine_enable_camera_vision,
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
            session = lobby.get_session(session_id)
            applies_to_current_turn = False
            if request.command == "interrupt" and request.ok:
                ack_payload = lobby.mark_interrupt_ack(
                    session_id,
                    turn_id=request.turn_id,
                    turn_token=request.turn_token,
                )
                if ack_payload:
                    applies_to_current_turn = True
                    lobby.publish_event(session_id, "state", ack_payload)
            lobby.publish_event(
                session_id,
                "callback",
                {
                    **_turn_fields(session),
                    "callback_type": "agent_command_ack",
                    "command": request.command,
                    "ok": request.ok,
                    "detail": request.detail,
                    "turn_id": request.turn_id,
                    "turn_token": request.turn_token,
                    "applies_to_current_turn": applies_to_current_turn,
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
            normalized_user_text = normalize_text(request.user_text)
            if route["intent"] not in {"pricing", "pricing_confirm"} and looks_like_hotel_faq_request(normalized_user_text):
                route = {
                    "owner": "backend",
                    "intent": "faq",
                    "confidence": max(float(route.get("confidence") or 0.0), 0.8),
                    "reason": "hotel-faq-fastgpt-entry-priority",
                    "chain": "hotel_fact_chain",
                    "requires_grounding": True,
                    "grounding_source": "faq",
                    "allow_freeform_answer": False,
                }
            turn = lobby.start_turn_with_owner(
                session_id,
                request.user_text,
                route["owner"],
                route["reason"],
                route["intent"],
                str(route.get("chain") or "hotel_fact_chain"),
            )
            session = lobby.get_session(session_id)
            lobby.publish_event(
                session_id,
                "subtitle",
                {
                    **_turn_fields(session),
                    "speaker": "user",
                    "text": request.user_text,
                    "turn_id": turn.turn_id,
                    "kind": request.source,
                    "is_final": request.source in {"manual", "stage-chip", "manual-chip", "external", "rtc-paragraph", "rtc-paragraph-preempted"},
                },
            )
            if route["owner"] == "backend":
                interrupt_payload = lobby.mark_turn_phase(session_id, turn.turn_id, "interrupting")
                lobby.publish_event(
                    session_id,
                    "state",
                    {
                        **(interrupt_payload or _turn_fields(session)),
                        "state": "thinking",
                        "detail": (
                            "本轮问题已切到后端收益链。"
                            if route["intent"] in {"pricing", "pricing_confirm"}
                            else (
                                "本轮问题已切到后端视觉识别链。"
                                if route.get("chain") == "vision_chain"
                                else "本轮问题已切到后端知识/规则链。"
                            )
                        ),
                        "turn_id": turn.turn_id,
                        "interrupt_gate": "interrupting",
                    },
                )
                if request.source != "rtc-paragraph-preempted":
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
                        **_turn_fields(session),
                        "state": "listening",
                        "detail": "本轮问题保持在火山原生 VoiceChat 主链。",
                        "turn_id": turn.turn_id,
                    },
                )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="RTC session not found") from exc

    if route["owner"] == "backend":
        asyncio.create_task(_process_turn(session_id, turn.turn_id, turn.turn_token, request.user_text, route))
    return {
        "session_id": session_id,
        "turn_id": turn.turn_id,
        "turn_token": turn.turn_token,
        "accepted": True,
        "owner": route["owner"],
        "intent": route["intent"],
        "chain": route.get("chain"),
        "phase": turn.phase,
        "route_reason": route["reason"],
        "confidence": route["confidence"],
        "processing_ms": round((perf_counter() - started) * 1000, 2),
        "transition_after_ms": settings.answer_timeout_ms,
        "transition_text": settings.transition_text if route["intent"] in {"pricing", "pricing_confirm"} else "",
    }


@app.post("/api/vision/analyze", response_model=VisionAnalyzeResponse)
async def analyze_vision(
    file: UploadFile = File(...),
    question: str = Form(""),
) -> VisionAnalyzeResponse:
    content = await file.read()
    result = await vision.analyze(
        content=content,
        filename=file.filename or "vision-upload",
        content_type=file.content_type or "application/octet-stream",
        question=question,
    )
    return VisionAnalyzeResponse(**{key: result.get(key) for key in VisionAnalyzeResponse.model_fields})


@app.post("/api/rtc/sessions/{session_id}/vision-turn")
async def rtc_vision_turn(
    session_id: str,
    file: UploadFile = File(...),
    question: str = Form(""),
) -> dict[str, object]:
    started = perf_counter()
    try:
        with state_lock:
            lobby.get_session(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="RTC session not found") from exc

    content = await file.read()
    vision_result = await vision.analyze(
        content=content,
        filename=file.filename or "vision-upload",
        content_type=file.content_type or "application/octet-stream",
        question=question,
    )
    normalized_question = normalize_text(question)
    needs_fact_resolution = vision_requires_hotel_facts(normalized_question)
    vision_ready_for_fact = bool(vision_result.get("ok")) and float(vision_result.get("confidence") or 0.0) >= 0.35
    if needs_fact_resolution and vision_ready_for_fact:
        observed_context = " ".join(
            part
            for part in [
                str(vision_result.get("scene_summary") or "").strip(),
                str(vision_result.get("detected_text") or "").strip(),
            ]
            if part
        ).strip()
        fact_query = question if not observed_context else f"{question} 图片内容：{observed_context}"
        resolved = await _resolve_hotel_fact_result(fact_query)
        resolved = _attach_chain_metadata(
            resolved,
            "vision_chain",
            "vision",
            ["vision", "hotel_fact_chain"],
            vision_result=vision_result,
        )
    else:
        resolved = _attach_chain_metadata(
            _vision_to_backend_result(vision_result, question, needs_fact_resolution),
            "vision_chain",
            "vision",
            ["vision"],
            vision_result=vision_result,
        )

    for chunk in chunk_speak_text(resolved.speak_text):
        await _send_voice_chat_command(
            session_id,
            "ExternalTextToSpeech",
            chunk,
            1,
        )
    return {
        "session_id": session_id,
        "accepted": True,
        "question": question,
        "chain": "vision_chain",
        "owner": "backend",
        "needs_fact_resolution": needs_fact_resolution,
        "vision_result": vision_result,
        "result": {
            "status": resolved.status,
            "display_text": resolved.display_text,
            "speak_text": resolved.speak_text,
            "metadata": resolved.metadata,
        },
        "processing_ms": round((perf_counter() - started) * 1000, 2),
    }


@app.post("/api/volcengine/callbacks/subtitles")
async def volcengine_subtitle_callback(request: Request) -> dict[str, object]:
    payload = await request.json()
    decoded_subtitle = _decode_subtitle_server_message(payload)
    if decoded_subtitle:
        payload = {
            **payload,
            "decoded_subtitle": decoded_subtitle,
        }
    _record_global_voicechat_callback("subtitles", payload)
    session_id = _resolve_session_for_payload(payload)
    if session_id:
        with state_lock:
            session = lobby.get_session(session_id)
            subtitle_event_payload = decoded_subtitle or payload
            matches, turn_id, turn_token = _event_matches_current_turn(subtitle_event_payload, session)
            lobby.record_callback(
                session_id,
                "subtitles",
                payload,
                applies_to_current_turn=matches,
                turn_id=turn_id,
                turn_token=turn_token,
            )
            if decoded_subtitle:
                for item in decoded_subtitle.get("data") or []:
                    if not isinstance(item, dict):
                        continue
                    speaker = "user"
                    user_id = str(item.get("userId") or "")
                    if user_id == session.ai_user_id:
                        speaker = "ai"
                    lobby.publish_event(
                        session_id,
                        "subtitle",
                        {
                            **_turn_fields(session),
                            "speaker": speaker,
                            "text": str(item.get("text") or ""),
                            "kind": "final" if item.get("definite") else "partial",
                            "is_final": bool(item.get("definite")),
                            "sequence": item.get("sequence"),
                            "round_id": item.get("roundId"),
                            "source": "server-subtitle-callback",
                        },
                    )
    return {"ok": True}


@app.post("/api/volcengine/callbacks/state")
async def volcengine_state_callback(request: Request) -> dict[str, object]:
    payload = await request.json()
    _record_global_voicechat_callback("state", payload)
    session_id = _resolve_session_for_payload(payload)
    if session_id:
        with state_lock:
            session = lobby.get_session(session_id)
            matches, turn_id, turn_token = _event_matches_current_turn(payload, session)
            lobby.record_callback(
                session_id,
                "state",
                payload,
                applies_to_current_turn=matches,
                turn_id=turn_id,
                turn_token=turn_token,
            )
    return {"ok": True}


@app.post("/api/volcengine/callbacks/task")
async def volcengine_task_callback(request: Request) -> dict[str, object]:
    payload = await request.json()
    _record_global_voicechat_callback("task", payload)
    session_id = _resolve_session_for_payload(payload)
    if session_id:
        with state_lock:
            session = lobby.get_session(session_id)
            matches, turn_id, turn_token = _event_matches_current_turn(payload, session)
            lobby.record_callback(
                session_id,
                "task",
                payload,
                applies_to_current_turn=matches,
                turn_id=turn_id,
                turn_token=turn_token,
            )
    return {"ok": True}


@app.post("/api/volcengine/callbacks/voicechat")
async def volcengine_voicechat_callback(request: Request) -> dict[str, object]:
    payload = await request.json()
    _record_global_voicechat_callback("voicechat", payload)
    session_id = _resolve_session_for_payload(payload)
    if session_id:
        with state_lock:
            session = lobby.get_session(session_id)
            matches, turn_id, turn_token = _event_matches_current_turn(payload, session)
            lobby.record_callback(
                session_id,
                "voicechat",
                payload,
                applies_to_current_turn=matches,
                turn_id=turn_id,
                turn_token=turn_token,
            )
    return {"ok": True}


@app.post("/api/presence")
async def presence(request: PresenceRequest) -> dict[str, object]:
    bootstrap_payload = await bootstrap(BootstrapRequest())
    return await rtc_presence(bootstrap_payload["session_id"], request)


@app.post("/api/query")
async def query(request: QueryRequest) -> dict[str, object]:
    bootstrap_payload = await bootstrap(BootstrapRequest())
    return await rtc_utterance(bootstrap_payload["session_id"], request)
