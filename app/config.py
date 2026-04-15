import json
import os
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv
from pydantic import BaseModel


BASE_DIR = Path(__file__).resolve().parent.parent
for env_path in (BASE_DIR / ".env", BASE_DIR / ".env.local"):
    if env_path.exists():
        load_dotenv(env_path, override=False)


def _parse_bool(value: Optional[str], default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_json(value: Optional[str], default: Any) -> Any:
    if not value:
        return default
    return json.loads(value)


def _trim_trailing_slash(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    trimmed = value.strip().rstrip("/")
    return trimmed or None


class Settings(BaseModel):
    app_name: str = "Hotel Lobby Assistant"
    app_port: int = int(os.getenv("APP_PORT", "12000"))
    hotel_id: str = os.getenv("HOTEL_ID", "lis-south-station")
    faq_index_path: Path = Path(
        os.getenv("FAQ_INDEX_PATH", str(BASE_DIR / "data" / "faq_index.json"))
    )
    ragflow_base_url: Optional[str] = os.getenv("RAGFLOW_BASE_URL")
    ragflow_api_key: Optional[str] = os.getenv("RAGFLOW_API_KEY")
    ragflow_search_url: Optional[str] = os.getenv("RAGFLOW_SEARCH_URL")
    ragflow_dataset_id: Optional[str] = os.getenv("RAGFLOW_DATASET_ID")
    ragflow_timeout_seconds: float = float(os.getenv("RAGFLOW_TIMEOUT_SECONDS", "8"))
    revenue_mcp_enabled: bool = _parse_bool(os.getenv("REVENUE_MCP_ENABLED"), True)
    revenue_mcp_sse_url: str = os.getenv(
        "REVENUE_MCP_SSE_URL", "http://127.0.0.1:8765/sse"
    )
    revenue_mcp_public_base_url: str = os.getenv(
        "REVENUE_MCP_PUBLIC_BASE_URL", "http://115.190.15.200:18765"
    )
    revenue_mcp_api_health_url: str = os.getenv(
        "REVENUE_MCP_API_HEALTH_URL", "http://127.0.0.1:8001/health"
    )
    revenue_mcp_timeout_seconds: float = float(
        os.getenv("REVENUE_MCP_TIMEOUT_SECONDS", "15")
    )
    revenue_mcp_default_store_id: Optional[int] = (
        int(os.getenv("REVENUE_MCP_DEFAULT_STORE_ID"))
        if os.getenv("REVENUE_MCP_DEFAULT_STORE_ID")
        else None
    )
    revenue_mcp_confirmation_ttl_seconds: int = int(
        os.getenv("REVENUE_MCP_CONFIRMATION_TTL_SECONDS", "120")
    )
    revenue_mcp_project_path: Path = Path(
        os.getenv("REVENUE_MCP_PROJECT_PATH", "/Users/sky/Project/New project voice")
    )

    answer_timeout_ms: int = int(os.getenv("ANSWER_TIMEOUT_MS", "250"))
    greeting_cooldown_seconds: int = int(os.getenv("GREETING_COOLDOWN_SECONDS", "60"))
    presence_reset_seconds: int = int(os.getenv("PRESENCE_RESET_SECONDS", "15"))
    greeting_text: str = os.getenv(
        "GREETING_TEXT",
        "欢迎来到丽斯未来酒店，我是ai助手小丽，有任何需要帮助的地方您可以问我。",
    )
    transition_text: str = os.getenv(
        "TRANSITION_TEXT",
        "您好，我帮您查一下，请稍等。",
    )

    volcengine_primary_dialog_path: str = os.getenv(
        "VOLCENGINE_PRIMARY_DIALOG_PATH", "s2s"
    )
    volcengine_force_pure_s2s: bool = _parse_bool(
        os.getenv("VOLCENGINE_FORCE_PURE_S2S"), False
    )
    volcengine_faq_route_mode: str = os.getenv(
        "VOLCENGINE_FAQ_ROUTE_MODE", "hybrid_risk_split"
    )
    volcengine_region: str = os.getenv("VOLCENGINE_REGION", "cn-north-1")
    volcengine_rtc_host: str = os.getenv("VOLCENGINE_RTC_HOST", "rtc.volcengineapi.com")
    volcengine_access_key_id: Optional[str] = os.getenv("VOLCENGINE_ACCESS_KEY_ID")
    volcengine_secret_access_key: Optional[str] = os.getenv("VOLCENGINE_SECRET_ACCESS_KEY")
    volcengine_rtc_app_id: Optional[str] = os.getenv("VOLCENGINE_RTC_APP_ID")
    volcengine_rtc_app_key: Optional[str] = os.getenv("VOLCENGINE_RTC_APP_KEY")
    volcengine_realtime_api_key: Optional[str] = os.getenv("VOLCENGINE_REALTIME_API_KEY")
    volcengine_voice_chat_version: str = os.getenv(
        "VOLCENGINE_VOICE_CHAT_VERSION", "2024-12-01"
    )
    volcengine_token_expire_seconds: int = int(
        os.getenv("VOLCENGINE_TOKEN_EXPIRE_SECONDS", "86400")
    )
    volcengine_frontend_sdk_url: str = os.getenv(
        "VOLCENGINE_FRONTEND_SDK_URL",
        "https://cdn.jsdelivr.net/npm/@volcengine/rtc@4.66.20/+esm",
    )
    volcengine_voice_chat_overrides_json: dict[str, Any] = _parse_json(
        os.getenv("VOLCENGINE_VOICE_CHAT_OVERRIDES_JSON"), {}
    )
    volcengine_command_channel: str = os.getenv(
        "VOLCENGINE_COMMAND_CHANNEL", "room_binary_message"
    )
    volcengine_callback_base_url: Optional[str] = _trim_trailing_slash(
        os.getenv("VOLCENGINE_CALLBACK_BASE_URL")
    )

    volcengine_asr_app_id: Optional[str] = os.getenv("VOLCENGINE_ASR_APP_ID")
    volcengine_asr_access_token: Optional[str] = os.getenv("VOLCENGINE_ASR_ACCESS_TOKEN")
    volcengine_asr_secret_key: Optional[str] = os.getenv("VOLCENGINE_ASR_SECRET_KEY")
    volcengine_asr_cluster: str = os.getenv(
        "VOLCENGINE_ASR_CLUSTER", "volcengine_streaming_common"
    )
    volcengine_asr_provider: str = os.getenv("VOLCENGINE_ASR_PROVIDER", "volcano")
    volcengine_asr_mode: str = os.getenv("VOLCENGINE_ASR_MODE", "smallmodel")
    volcengine_asr_api_resource_id: Optional[str] = os.getenv(
        "VOLCENGINE_ASR_API_RESOURCE_ID"
    )
    volcengine_asr_stream_mode: Optional[int] = (
        int(os.getenv("VOLCENGINE_ASR_STREAM_MODE"))
        if os.getenv("VOLCENGINE_ASR_STREAM_MODE")
        else None
    )
    volcengine_asr_turn_detection_mode: int = int(
        os.getenv("VOLCENGINE_ASR_TURN_DETECTION_MODE", "0")
    )
    volcengine_asr_vad_silence_time: Optional[int] = (
        int(os.getenv("VOLCENGINE_ASR_VAD_SILENCE_TIME"))
        if os.getenv("VOLCENGINE_ASR_VAD_SILENCE_TIME")
        else None
    )
    volcengine_asr_enable_nonstream: bool = _parse_bool(
        os.getenv("VOLCENGINE_ASR_ENABLE_NONSTREAM"), True
    )
    volcengine_asr_hotwords: list[str] = _parse_json(
        os.getenv("VOLCENGINE_ASR_HOTWORDS_JSON"), []
    )
    volcengine_asr_contexts: list[str] = _parse_json(
        os.getenv("VOLCENGINE_ASR_CONTEXTS_JSON"), []
    )

    volcengine_tts_provider: str = os.getenv(
        "VOLCENGINE_TTS_PROVIDER", "volcano_bidirection"
    )
    volcengine_tts_app_id: Optional[str] = os.getenv("VOLCENGINE_TTS_APP_ID")
    volcengine_tts_access_token: Optional[str] = os.getenv("VOLCENGINE_TTS_ACCESS_TOKEN")
    volcengine_tts_secret_key: Optional[str] = os.getenv("VOLCENGINE_TTS_SECRET_KEY")
    volcengine_tts_cluster: str = os.getenv("VOLCENGINE_TTS_CLUSTER", "volcano_tts")
    volcengine_tts_resource_id: Optional[str] = os.getenv("VOLCENGINE_TTS_RESOURCE_ID")
    volcengine_tts_voice_type: str = os.getenv(
        "VOLCENGINE_TTS_VOICE_TYPE", "BV001_streaming"
    )
    volcengine_tts_speech_rate: Optional[int] = (
        int(os.getenv("VOLCENGINE_TTS_SPEECH_RATE"))
        if os.getenv("VOLCENGINE_TTS_SPEECH_RATE")
        else None
    )
    volcengine_tts_speed_ratio: float = float(
        os.getenv("VOLCENGINE_TTS_SPEED_RATIO", "1")
    )
    volcengine_tts_pitch_ratio: float = float(
        os.getenv("VOLCENGINE_TTS_PITCH_RATIO", "1")
    )
    volcengine_tts_volume_ratio: float = float(
        os.getenv("VOLCENGINE_TTS_VOLUME_RATIO", "1")
    )

    volcengine_llm_mode: str = os.getenv("VOLCENGINE_LLM_MODE", "ArkV3")
    volcengine_llm_endpoint_id: Optional[str] = os.getenv("VOLCENGINE_LLM_ENDPOINT_ID")
    volcengine_llm_model_name: Optional[str] = os.getenv("VOLCENGINE_LLM_MODEL_NAME")
    volcengine_llm_thinking_type: Optional[str] = os.getenv(
        "VOLCENGINE_LLM_THINKING_TYPE", "disabled"
    )
    volcengine_llm_system_messages: list[str] = _parse_json(
        os.getenv("VOLCENGINE_LLM_SYSTEM_MESSAGES_JSON"),
        [
            (
                "你是丽斯未来酒店展厅数字人接待助手。"
                "酒店固定知识必须严格遵循外部知识库或记忆库返回结果，不编造，不扩写。"
                "凡是早餐、停车、发票、入住退房、路线、楼层、设施、用品、会议室这类酒店事实问题，"
                "只能依据命中的知识内容作答；若没有明确命中，就直接说明暂未查询到准确信息，不能猜。"
                "酒店事实题先直接说结论，再补一句必要信息，不要寒暄，不要铺垫。"
                "当命中内容里有关键事实时，优先原样复述关键事实本身，例如是否免费、入口从哪条路进入、需要提前几分钟联系等。"
                "不要把用户画像或无关偏好当成酒店事实答案。"
                "当业务系统需要接管回答时，保持自然停顿，避免与外部播报抢话。"
            )
        ],
    )
    volcengine_enable_s2s: bool = _parse_bool(
        os.getenv("VOLCENGINE_ENABLE_S2S"), True
    )
    volcengine_s2s_provider: str = os.getenv("VOLCENGINE_S2S_PROVIDER", "volcano")
    volcengine_s2s_app_id: Optional[str] = os.getenv("VOLCENGINE_S2S_APP_ID")
    volcengine_s2s_token: Optional[str] = os.getenv("VOLCENGINE_S2S_TOKEN")
    volcengine_s2s_model: Optional[str] = os.getenv("VOLCENGINE_S2S_MODEL")
    volcengine_s2s_output_mode: int = int(os.getenv("VOLCENGINE_S2S_OUTPUT_MODE", "1"))
    volcengine_s2s_config_json: dict[str, Any] = _parse_json(
        os.getenv("VOLCENGINE_S2S_CONFIG_JSON"), {}
    )
    volcengine_enable_memory: bool = _parse_bool(
        os.getenv("VOLCENGINE_ENABLE_MEMORY"), True
    )
    volcengine_memory_config_json: dict[str, Any] = _parse_json(
        os.getenv("VOLCENGINE_MEMORY_CONFIG_JSON"), {}
    )
    volcengine_memory_native_collection_name: str = os.getenv(
        "VOLCENGINE_MEMORY_NATIVE_COLLECTION_NAME",
        os.getenv("VOLCENGINE_MEMORY_COLLECTION_NAME", "jiudianwenti"),
    )
    volcengine_memory_native_limit: int = int(
        os.getenv("VOLCENGINE_MEMORY_NATIVE_LIMIT", "3")
    )
    volcengine_memory_native_score: float = float(
        os.getenv("VOLCENGINE_MEMORY_NATIVE_SCORE", "0.7")
    )
    volcengine_memory_native_transition_words: str = os.getenv(
        "VOLCENGINE_MEMORY_NATIVE_TRANSITION_WORDS", "根据您的历史记录："
    )
    volcengine_memory_native_user_ids: list[str] = _parse_json(
        os.getenv("VOLCENGINE_MEMORY_NATIVE_USER_IDS_JSON"),
        [],
    )
    volcengine_memory_native_assistant_ids: list[str] = _parse_json(
        os.getenv("VOLCENGINE_MEMORY_NATIVE_ASSISTANT_IDS_JSON"),
        [],
    )
    volcengine_memory_native_types: list[str] = _parse_json(
        os.getenv("VOLCENGINE_MEMORY_NATIVE_TYPES_JSON"),
        [],
    )
    volcengine_memory_api_base_url: str = os.getenv(
        "VOLCENGINE_MEMORY_API_BASE_URL",
        "https://api-knowledgebase.mlp.cn-beijing.volces.com/api/memory/get_context",
    )
    volcengine_memory_api_key: Optional[str] = os.getenv("VOLCENGINE_MEMORY_API_KEY")
    volcengine_memory_project_name: str = os.getenv(
        "VOLCENGINE_MEMORY_PROJECT_NAME", "default"
    )
    volcengine_memory_collection_name: str = os.getenv(
        "VOLCENGINE_MEMORY_COLLECTION_NAME", "jiudianwenti"
    )
    volcengine_memory_default_user_id: str = os.getenv(
        "VOLCENGINE_MEMORY_DEFAULT_USER_ID", "hotel_lobby_user"
    )
    volcengine_use_backend_fallback: bool = _parse_bool(
        os.getenv("VOLCENGINE_USE_BACKEND_FALLBACK"), True
    )

    volcengine_avatar_enabled: bool = _parse_bool(
        os.getenv("VOLCENGINE_AVATAR_ENABLED"), False
    )
    volcengine_avatar_type: str = os.getenv("VOLCENGINE_AVATAR_TYPE", "3min")
    volcengine_avatar_role: Optional[str] = os.getenv("VOLCENGINE_AVATAR_ROLE")
    volcengine_avatar_background_url: str = os.getenv(
        "VOLCENGINE_AVATAR_BACKGROUND_URL", ""
    )
    volcengine_avatar_video_bitrate: int = int(
        os.getenv("VOLCENGINE_AVATAR_VIDEO_BITRATE", "2000")
    )
    volcengine_avatar_app_id: Optional[str] = os.getenv("VOLCENGINE_AVATAR_APP_ID")
    volcengine_avatar_token: Optional[str] = os.getenv("VOLCENGINE_AVATAR_TOKEN")

    volcengine_enable_callback_state: bool = _parse_bool(
        os.getenv("VOLCENGINE_ENABLE_CALLBACK_STATE"), True
    )
    volcengine_callback_secret: Optional[str] = os.getenv("VOLCENGINE_CALLBACK_SECRET")
    self_avatar_mount_id: str = os.getenv("SELF_AVATAR_MOUNT_ID", "selfAvatarMount")
    self_avatar_mode: str = os.getenv("SELF_AVATAR_MODE", "container")

    debug_mode: bool = _parse_bool(os.getenv("DEBUG_MODE"), False)

    def callback_urls(self) -> dict[str, Optional[str]]:
        if not self.volcengine_callback_base_url:
            return {"voicechat": None, "subtitles": None, "state": None, "task": None}
        return {
            "voicechat": f"{self.volcengine_callback_base_url}/api/volcengine/callbacks/voicechat",
            "subtitles": f"{self.volcengine_callback_base_url}/api/volcengine/callbacks/subtitles",
            "state": f"{self.volcengine_callback_base_url}/api/volcengine/callbacks/state",
            "task": f"{self.volcengine_callback_base_url}/api/volcengine/callbacks/task",
        }

    @property
    def faq_prefers_s2s_memory(self) -> bool:
        return self.volcengine_faq_route_mode in {"s2s_memory", "hybrid_risk_split"}

    @property
    def pure_s2s_enabled(self) -> bool:
        return self.volcengine_primary_dialog_path == "s2s" and self.volcengine_force_pure_s2s

    @property
    def effective_dialog_path(self) -> str:
        preferred = self.volcengine_primary_dialog_path.strip().lower()
        if preferred == "s2s" and self.s2s_ready:
            return "s2s"
        if preferred in {"asr_tts", "asr-llm-tts", "cascade"} and self.asr_tts_ready:
            return "asr_tts"
        if self.s2s_ready:
            return "s2s"
        if self.asr_tts_ready:
            return "asr_tts"
        return "unconfigured"

    @property
    def revenue_mcp_ready(self) -> bool:
        return self.revenue_mcp_enabled and bool(self.revenue_mcp_sse_url)

    @property
    def s2s_ready(self) -> bool:
        if not self.volcengine_enable_s2s:
            return False
        return bool(self.volcengine_s2s_config_json) or bool(
            self.volcengine_s2s_app_id and self.volcengine_s2s_token
        )

    @property
    def s2s_config_source(self) -> str:
        if self.volcengine_s2s_config_json:
            return "json"
        if self.volcengine_s2s_app_id and self.volcengine_s2s_token:
            return "simple-env"
        return "missing"

    @property
    def memory_ready(self) -> bool:
        if not self.volcengine_enable_memory:
            return False
        if self.volcengine_memory_config_json:
            return True
        has_subject = bool(
            self.volcengine_memory_native_user_ids
            or self.volcengine_memory_native_assistant_ids
        )
        return bool(
            self.volcengine_memory_native_collection_name
            and self.volcengine_memory_native_types
            and has_subject
        )

    @property
    def memory_config_source(self) -> str:
        if self.volcengine_memory_config_json:
            return "json"
        if self.memory_ready:
            return "simple-env"
        return "missing"

    @property
    def memory_api_ready(self) -> bool:
        return bool(
            self.volcengine_memory_api_base_url
            and self.volcengine_memory_api_key
            and self.volcengine_memory_collection_name
            and self.volcengine_memory_project_name
        )

    @property
    def asr_tts_ready(self) -> bool:
        return bool(
            self.volcengine_asr_app_id
            and self.volcengine_asr_access_token
            and self.volcengine_asr_secret_key
            and self.volcengine_tts_app_id
            and self.volcengine_tts_access_token
            and self.volcengine_tts_secret_key
            and self.volcengine_llm_endpoint_id
        )


settings = Settings()
