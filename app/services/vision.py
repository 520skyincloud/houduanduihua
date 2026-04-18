from __future__ import annotations

import base64
import json
import re
from typing import Any

import httpx

from app.config import settings


class VisionFacade:
    async def analyze(
        self,
        content: bytes,
        filename: str,
        content_type: str,
        question: str = "",
    ) -> dict[str, Any]:
        if not content:
            return {
                "ok": False,
                "configured": self._configured(),
                "scene_summary": "",
                "detected_text": "",
                "objects": [],
                "confidence": 0.0,
                "detail": "未收到有效图片内容。",
            }

        if not settings.vision_analysis_enabled:
            return {
                "ok": False,
                "configured": self._configured(),
                "scene_summary": "当前视觉识别服务尚未启用，暂时无法稳定识别这张图片内容。",
                "detected_text": "",
                "objects": [],
                "confidence": 0.0,
                "detail": "未启用 VISION_ANALYSIS_ENABLED。",
                "provider": settings.vision_analysis_provider,
                "image_meta": self._image_meta(filename, content_type, content),
            }

        provider = settings.vision_analysis_provider
        if provider == "openai_compatible":
            return await self._analyze_openai_compatible(content, filename, content_type, question)
        if provider == "custom":
            return await self._analyze_custom(content, filename, content_type, question)
        return {
            "ok": False,
            "configured": False,
            "scene_summary": "当前视觉识别供应商配置无效，暂时无法识别这张图片内容。",
            "detected_text": "",
            "objects": [],
            "confidence": 0.0,
            "detail": f"不支持的视觉识别 provider：{provider}",
            "provider": provider,
            "image_meta": self._image_meta(filename, content_type, content),
        }

    def _configured(self) -> bool:
        return settings.vision_analysis_ready

    @staticmethod
    def _image_meta(filename: str, content_type: str, content: bytes) -> dict[str, Any]:
        return {
            "filename": filename,
            "content_type": content_type,
            "size_bytes": len(content),
        }

    async def _analyze_custom(
        self,
        content: bytes,
        filename: str,
        content_type: str,
        question: str,
    ) -> dict[str, Any]:
        if not settings.vision_analysis_url:
            return {
                "ok": False,
                "configured": False,
                "scene_summary": "当前视觉识别服务尚未配置，暂时无法稳定识别这张图片内容。",
                "detected_text": "",
                "objects": [],
                "confidence": 0.0,
                "detail": "未配置 VISION_ANALYSIS_URL。",
                "provider": "custom",
                "image_meta": self._image_meta(filename, content_type, content),
            }

        headers: dict[str, str] = {}
        if settings.vision_analysis_api_key:
            headers["Authorization"] = f"Bearer {settings.vision_analysis_api_key}"

        files = {
            "file": (filename or "vision-upload", content, content_type or "application/octet-stream")
        }
        data = {"question": question}
        try:
            async with httpx.AsyncClient(timeout=settings.vision_analysis_timeout_seconds) as client:
                response = await client.post(
                    settings.vision_analysis_url,
                    headers=headers,
                    data=data,
                    files=files,
                )
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:
            return {
                "ok": False,
                "configured": True,
                "scene_summary": "视觉识别请求失败，当前无法确认图片内容。",
                "detected_text": "",
                "objects": [],
                "confidence": 0.0,
                "detail": f"视觉识别失败：{exc}",
                "provider": "custom",
            }

        return self._normalize_payload(payload, provider="custom")

    async def _analyze_openai_compatible(
        self,
        content: bytes,
        filename: str,
        content_type: str,
        question: str,
    ) -> dict[str, Any]:
        if not (settings.vision_analysis_base_url and settings.vision_analysis_model and settings.vision_analysis_api_key):
            return {
                "ok": False,
                "configured": False,
                "scene_summary": "当前视觉模型尚未完整配置，暂时无法识别这张图片内容。",
                "detected_text": "",
                "objects": [],
                "confidence": 0.0,
                "detail": "需要同时配置 VISION_ANALYSIS_BASE_URL / VISION_ANALYSIS_MODEL / VISION_ANALYSIS_API_KEY。",
                "provider": "openai_compatible",
                "image_meta": self._image_meta(filename, content_type, content),
            }

        mime_type = content_type or "image/jpeg"
        data_url = f"data:{mime_type};base64,{base64.b64encode(content).decode('utf-8')}"
        prompt = (
            "你是一个中文视觉理解助手。请根据图片和用户问题输出 JSON，"
            '字段固定为 scene_summary、detected_text、objects、confidence、detail。'
            "scene_summary 用一句中文总结画面；detected_text 只写图片里能读到的文字；"
            "objects 是字符串数组；confidence 取 0 到 1 之间的小数；detail 用一句中文说明判断依据。"
            "如果用户没有提具体问题，也请按画面内容给出结果。"
            "只输出 JSON 对象，不要输出数组，不要输出额外解释。"
        )
        if question.strip():
            prompt += f" 用户问题：{question.strip()}"

        payload = {
            "model": settings.vision_analysis_model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                }
            ],
            "temperature": 0.2,
            "max_tokens": settings.vision_analysis_max_tokens,
        }
        headers = {
            "Authorization": f"Bearer {settings.vision_analysis_api_key}",
            "Content-Type": "application/json",
        }
        endpoint = f"{settings.vision_analysis_base_url}/chat/completions"
        try:
            async with httpx.AsyncClient(timeout=settings.vision_analysis_timeout_seconds) as client:
                response = await client.post(endpoint, headers=headers, json=payload)
                response.raise_for_status()
                raw = response.json()
        except Exception as exc:
            return {
                "ok": False,
                "configured": True,
                "scene_summary": "视觉识别请求失败，当前无法确认图片内容。",
                "detected_text": "",
                "objects": [],
                "confidence": 0.0,
                "detail": f"视觉识别失败：{exc}",
                "provider": "openai_compatible",
            }

        message = raw.get("choices", [{}])[0].get("message", {})
        content_text = message.get("content", "")
        parsed = self._extract_json(content_text)
        if parsed is None:
            parsed = self._extract_json(message.get("reasoning_content", ""))
        if parsed is None:
            return {
                "ok": False,
                "configured": True,
                "scene_summary": "视觉模型返回成功，但结果格式无法解析。",
                "detected_text": "",
                "objects": [],
                "confidence": 0.0,
                "detail": "未能从模型输出中解析结构化 JSON。",
                "provider": "openai_compatible",
                "raw": raw,
            }
        normalized = self._normalize_payload(parsed, provider="openai_compatible")
        normalized["raw"] = raw
        return normalized

    @staticmethod
    def _extract_json(content: Any) -> dict[str, Any] | None:
        if isinstance(content, dict):
            return content
        if not isinstance(content, str):
            return None
        text = content.strip()
        if not text:
            return None
        for candidate in (text, re.sub(r"^```json\s*|\s*```$", "", text, flags=re.S)):
            try:
                parsed = json.loads(candidate)
            except Exception:
                continue
            if isinstance(parsed, dict):
                return parsed
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            return None
        try:
            parsed = json.loads(match.group(0))
        except Exception:
            return None
        return parsed if isinstance(parsed, dict) else None

    @staticmethod
    def _normalize_payload(payload: dict[str, Any], provider: str) -> dict[str, Any]:
        scene_summary = str(payload.get("scene_summary") or "").strip()
        detected_text_raw = payload.get("detected_text")
        if isinstance(detected_text_raw, list):
            detected_text = "；".join(
                str(item).strip()
                for item in detected_text_raw
                if str(item).strip()
            )
        else:
            detected_text = str(detected_text_raw or "").strip()
        objects = payload.get("objects") if isinstance(payload.get("objects"), list) else []
        confidence_raw = payload.get("confidence")
        try:
            confidence = float(confidence_raw or 0.0)
        except Exception:
            confidence = 0.0
        return {
            "ok": bool(scene_summary or detected_text or objects),
            "configured": True,
            "scene_summary": scene_summary,
            "detected_text": detected_text,
            "objects": [str(item).strip() for item in objects if str(item).strip()],
            "confidence": max(0.0, min(confidence, 1.0)),
            "detail": str(payload.get("detail") or "").strip(),
            "provider": provider,
        }
