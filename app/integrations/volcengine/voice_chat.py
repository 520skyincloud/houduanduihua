from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.config import settings
from app.models import RTCSessionState


def _deep_merge(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in overrides.items():
        if (
            key in merged
            and isinstance(merged[key], dict)
            and isinstance(value, dict)
        ):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


class VoiceChatPayloadFactory:
    def build_start_payload(self, session: RTCSessionState) -> dict[str, Any]:
        dialog_path = settings.effective_dialog_path
        config = {
            "LLMConfig": self._build_llm_config(),
            "AvatarConfig": self._build_avatar_config(),
            "InterruptMode": 0,
            "SubtitleConfig": {
                "SubtitleMode": 1,
            },
        }
        if dialog_path == "s2s":
            config["S2SConfig"] = self._build_s2s_config()
            if (
                settings.volcengine_tts_app_id
                and settings.volcengine_tts_access_token
                and settings.volcengine_tts_secret_key
            ):
                # Keep ExternalTextToSpeech available with a configured cloned voice
                # even when the main dialog path uses native S2S.
                config["TTSConfig"] = self._build_tts_config()
        else:
            config["ASRConfig"] = self._build_asr_config()
            config["TTSConfig"] = self._build_tts_config()

        if settings.memory_ready:
            config["MemoryConfig"] = self._build_memory_config()

        payload = {
            "AppId": settings.volcengine_rtc_app_id,
            "RoomId": session.room_id,
            "TaskId": session.task_id,
            "AgentConfig": {
                "TargetUserId": [session.user_id],
                "UserId": session.ai_user_id,
                "EnableConversationStateCallback": settings.volcengine_enable_callback_state,
            },
            "Config": config,
        }
        return _deep_merge(payload, settings.volcengine_voice_chat_overrides_json)

    def build_stop_payload(self, session: RTCSessionState) -> dict[str, Any]:
        return {
            "AppId": settings.volcengine_rtc_app_id,
            "RoomId": session.room_id,
            "TaskId": session.task_id,
        }

    def build_update_payload(self, session: RTCSessionState, command: dict[str, Any]) -> dict[str, Any]:
        return {
            "AppId": settings.volcengine_rtc_app_id,
            "RoomId": session.room_id,
            "TaskId": session.task_id,
            **command,
        }

    @property
    def ready(self) -> bool:
        if not settings.volcengine_rtc_app_id:
            return False
        if settings.volcengine_voice_chat_overrides_json:
            return True
        if settings.volcengine_avatar_enabled and (
            not settings.volcengine_avatar_app_id
            or not settings.volcengine_avatar_token
            or not settings.volcengine_avatar_role
        ):
            return False
        if settings.effective_dialog_path == "s2s":
            return bool(settings.volcengine_llm_endpoint_id)
        if settings.effective_dialog_path == "asr_tts":
            return settings.asr_tts_ready
        return False

    def _build_asr_config(self) -> dict[str, Any]:
        provider_params: dict[str, Any] = {
            "Mode": settings.volcengine_asr_mode,
            "AppId": settings.volcengine_asr_app_id,
            "AccessToken": settings.volcengine_asr_access_token,
        }
        if settings.volcengine_asr_api_resource_id:
            provider_params["ApiResourceId"] = settings.volcengine_asr_api_resource_id
        elif settings.volcengine_asr_cluster:
            provider_params["Cluster"] = settings.volcengine_asr_cluster
        if (
            settings.volcengine_asr_secret_key
            and not settings.volcengine_asr_api_resource_id
        ):
            provider_params["SecretKey"] = settings.volcengine_asr_secret_key
        if settings.volcengine_asr_stream_mode is not None:
            provider_params["StreamMode"] = settings.volcengine_asr_stream_mode
        if settings.volcengine_asr_enable_nonstream:
            provider_params["enable_nonstream"] = True
        if settings.volcengine_asr_hotwords:
            provider_params["HotWords"] = settings.volcengine_asr_hotwords
        if settings.volcengine_asr_contexts:
            provider_params["ContextTexts"] = settings.volcengine_asr_contexts
        asr_payload: dict[str, Any] = {
            "Provider": settings.volcengine_asr_provider,
            "TurnDetectionMode": settings.volcengine_asr_turn_detection_mode,
            "ProviderParams": provider_params,
        }
        if settings.volcengine_asr_vad_silence_time is not None:
            asr_payload["VADConfig"] = {
                "SilenceTime": settings.volcengine_asr_vad_silence_time,
            }
        return asr_payload

    def _build_tts_config(self) -> dict[str, Any]:
        audio_payload: dict[str, Any] = {
            "voice_type": settings.volcengine_tts_voice_type,
        }
        if settings.volcengine_tts_speech_rate is not None:
            audio_payload["speech_rate"] = settings.volcengine_tts_speech_rate
        else:
            audio_payload.update(
                {
                    "speed_ratio": settings.volcengine_tts_speed_ratio,
                    "pitch_ratio": settings.volcengine_tts_pitch_ratio,
                    "volume_ratio": settings.volcengine_tts_volume_ratio,
                }
            )

        provider_params: dict[str, Any] = {
            "app": {
                "appid": settings.volcengine_tts_app_id,
                "token": settings.volcengine_tts_access_token,
            },
            "audio": audio_payload,
        }
        if settings.volcengine_tts_cluster and settings.volcengine_tts_provider != "volcano_bidirection":
            provider_params["app"]["cluster"] = settings.volcengine_tts_cluster
        if settings.volcengine_tts_secret_key and settings.volcengine_tts_provider != "volcano_bidirection":
            provider_params["app"]["secret_key"] = settings.volcengine_tts_secret_key
        if settings.volcengine_tts_resource_id:
            provider_params["ResourceId"] = settings.volcengine_tts_resource_id

        return {
            "Provider": settings.volcengine_tts_provider,
            "ProviderParams": provider_params,
        }

    def _build_llm_config(self) -> dict[str, Any]:
        system_messages = list(settings.volcengine_llm_system_messages)
        payload: dict[str, Any] = {
            "Mode": settings.volcengine_llm_mode,
            "SystemMessages": system_messages,
            "VisionConfig": {
                "Enable": False,
            },
        }
        if settings.volcengine_llm_thinking_type:
            payload["ThinkingType"] = settings.volcengine_llm_thinking_type
        if settings.volcengine_llm_endpoint_id:
            payload["EndPointId"] = settings.volcengine_llm_endpoint_id
        return payload

    def _build_s2s_config(self) -> dict[str, Any]:
        if settings.volcengine_s2s_config_json:
            return dict(settings.volcengine_s2s_config_json)
        else:
            return {
                "OutputMode": settings.volcengine_s2s_output_mode,
                "Provider": settings.volcengine_s2s_provider,
                "ProviderParams": {
                    "app": {
                        "appid": settings.volcengine_s2s_app_id,
                        "token": settings.volcengine_s2s_token,
                    },
                    "model": settings.volcengine_s2s_model,
                },
            }

    def _build_avatar_config(self) -> dict[str, Any]:
        return {
            "Enabled": settings.volcengine_avatar_enabled,
            "AvatarType": settings.volcengine_avatar_type,
            "AvatarRole": settings.volcengine_avatar_role,
            "BackgroundUrl": settings.volcengine_avatar_background_url,
            "VideoBitrate": settings.volcengine_avatar_video_bitrate,
            "AvatarAppID": settings.volcengine_avatar_app_id,
            "AvatarToken": settings.volcengine_avatar_token,
        }

    def _build_memory_config(self) -> dict[str, Any]:
        if settings.volcengine_memory_config_json:
            return dict(settings.volcengine_memory_config_json)

        filter_payload: dict[str, Any] = {
            "memory_type": settings.volcengine_memory_native_types,
        }
        if settings.volcengine_memory_native_user_ids:
            filter_payload["user_id"] = settings.volcengine_memory_native_user_ids
        elif settings.volcengine_memory_default_user_id:
            # Keep RTC native retrieval aligned with the already-validated hotel memory user scope.
            filter_payload["user_id"] = [settings.volcengine_memory_default_user_id]
        if settings.volcengine_memory_native_assistant_ids:
            filter_payload["assistant_id"] = settings.volcengine_memory_native_assistant_ids

        return {
            "Enable": True,
            "Provider": "volc",
            "ProviderParams": {
                "collection_name": settings.volcengine_memory_native_collection_name,
                "limit": settings.volcengine_memory_native_limit,
                "filter": filter_payload,
                "transition_words": settings.volcengine_memory_native_transition_words,
            },
            "Score": settings.volcengine_memory_native_score,
        }
