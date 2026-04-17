from __future__ import annotations
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
                "configured": bool(settings.vision_analysis_url),
                "scene_summary": "",
                "detected_text": "",
                "objects": [],
                "confidence": 0.0,
                "detail": "未收到有效图片内容。",
            }

        if not settings.vision_analysis_enabled or not settings.vision_analysis_url:
            return {
                "ok": False,
                "configured": False,
                "scene_summary": "当前视觉识别服务尚未配置，暂时无法稳定识别这张图片内容。",
                "detected_text": "",
                "objects": [],
                "confidence": 0.0,
                "detail": "未配置 VISION_ANALYSIS_URL 或未启用视觉识别。",
                "image_meta": {
                    "filename": filename,
                    "content_type": content_type,
                    "size_bytes": len(content),
                },
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
            }

        return {
            "ok": bool(payload.get("scene_summary") or payload.get("detected_text") or payload.get("objects")),
            "configured": True,
            "scene_summary": str(payload.get("scene_summary") or "").strip(),
            "detected_text": str(payload.get("detected_text") or "").strip(),
            "objects": payload.get("objects") if isinstance(payload.get("objects"), list) else [],
            "confidence": float(payload.get("confidence") or 0.0),
            "detail": str(payload.get("detail") or "").strip(),
            "raw": payload,
        }
