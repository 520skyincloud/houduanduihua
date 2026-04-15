from __future__ import annotations

from typing import Any

from volcenginesdkcore import ApiClient, Configuration, UniversalApi, UniversalInfo

from app.config import settings


class VolcengineRTCOpenAPI:
    def __init__(self) -> None:
        configuration = Configuration()
        configuration.ak = settings.volcengine_access_key_id or ""
        configuration.sk = settings.volcengine_secret_access_key or ""
        configuration.region = settings.volcengine_region
        configuration.host = settings.volcengine_rtc_host
        configuration.read_timeout = 15.0
        configuration.connect_timeout = 5.0
        configuration.debug = settings.debug_mode
        self._api = UniversalApi(ApiClient(configuration))
        self._version = settings.volcengine_voice_chat_version

    @property
    def ready(self) -> bool:
        return bool(
            settings.volcengine_access_key_id
            and settings.volcengine_secret_access_key
            and settings.volcengine_rtc_host
        )

    def _call(self, action: str, body: dict[str, Any], version: str | None = None) -> dict[str, Any]:
        if not self.ready:
            raise RuntimeError("Volcengine RTC OpenAPI credentials are not configured.")
        info = UniversalInfo(
            method="POST",
            service="rtc",
            version=version or self._version,
            action=action,
            content_type="application/json",
        )
        response = self._api.do_call(info, body)
        return dict(response) if isinstance(response, dict) else {"result": response}

    def start_voice_chat(self, body: dict[str, Any]) -> dict[str, Any]:
        return self._call("StartVoiceChat", body)

    def update_voice_chat(self, body: dict[str, Any]) -> dict[str, Any]:
        return self._call("UpdateVoiceChat", body)

    def stop_voice_chat(self, body: dict[str, Any]) -> dict[str, Any]:
        return self._call("StopVoiceChat", body)
