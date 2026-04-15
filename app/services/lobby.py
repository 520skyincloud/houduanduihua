from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any, Dict, Iterable

from app.config import settings
from app.models import PendingConfirmation, PresenceState, RTCSessionState, RTCTurnState, SessionCommand


class LobbyCoordinator:
    def __init__(self) -> None:
        self._sessions: Dict[str, RTCSessionState] = {}

    def create_session(
        self,
        client_id: str,
        transport: str,
        rtc_token: str,
        room_id: str,
        user_id: str,
        ai_user_id: str,
    ) -> RTCSessionState:
        now = time.time()
        session = RTCSessionState(
            session_id=uuid.uuid4().hex[:16],
            client_id=client_id,
            transport=transport,
            room_id=room_id,
            user_id=user_id,
            ai_user_id=ai_user_id,
            rtc_token=rtc_token,
            task_id=uuid.uuid4().hex,
            created_ts=now,
            last_seen_ts=now,
            presence=PresenceState(),
        )
        self._sessions[session.session_id] = session
        self.publish_event(
            session.session_id,
            "session",
            {
                "state": session.state,
                "room_id": session.room_id,
                "user_id": session.user_id,
                "ai_user_id": session.ai_user_id,
            },
        )
        return session

    def get_session(self, session_id: str) -> RTCSessionState:
        if session_id not in self._sessions:
            raise KeyError(session_id)
        return self._sessions[session_id]

    def list_sessions(self) -> Iterable[RTCSessionState]:
        return self._sessions.values()

    def publish_event(self, session_id: str, kind: str, payload: dict[str, Any]) -> SessionCommand:
        session = self.get_session(session_id)
        session.last_seen_ts = time.time()
        session.event_seq += 1
        event = SessionCommand(
            event_id=session.event_seq,
            kind=kind,
            payload=payload,
            created_ts=session.last_seen_ts,
        )
        session.event_queue.put_nowait(
            {
                "event_id": event.event_id,
                "kind": event.kind,
                "payload": event.payload,
                "created_ts": event.created_ts,
            }
        )
        return event

    def set_state(self, session_id: str, state: str, detail: str | None = None) -> None:
        session = self.get_session(session_id)
        session.state = state
        payload: dict[str, Any] = {"state": state}
        if detail:
            payload["detail"] = detail
        self.publish_event(session_id, "state", payload)

    def mark_rtc_connected(self, session_id: str) -> None:
        session = self.get_session(session_id)
        session.rtc_connected = True
        self.publish_event(
            session_id,
            "connection",
            {"rtc_connected": True, "voice_chat_started": session.voice_chat_started},
        )

    def mark_voice_chat_started(self, session_id: str) -> None:
        session = self.get_session(session_id)
        session.voice_chat_started = True
        self.publish_event(
            session_id,
            "connection",
            {"rtc_connected": session.rtc_connected, "voice_chat_started": True},
        )

    def mark_voice_chat_stopped(self, session_id: str) -> None:
        session = self.get_session(session_id)
        session.voice_chat_started = False
        self.publish_event(
            session_id,
            "connection",
            {"rtc_connected": session.rtc_connected, "voice_chat_started": False},
        )

    def register_presence(self, session_id: str) -> dict[str, object]:
        session = self.get_session(session_id)
        now = time.time()
        session.last_seen_ts = now
        should_greet = (
            not session.presence.active
            or now - session.presence.last_trigger_ts >= settings.greeting_cooldown_seconds
        )
        session.presence.active = True
        session.presence.last_seen_ts = now
        session.state = "greeting" if should_greet else "idle"
        if should_greet:
            session.presence.last_trigger_ts = now
            self.publish_event(
                session_id,
                "subtitle",
                {"speaker": "ai", "text": settings.greeting_text, "turn_id": 0},
            )
        self.publish_event(
            session_id,
            "presence",
            {"should_greet": should_greet, "state": session.state},
        )
        return {
            "session_id": session.session_id,
            "state": session.state,
            "should_greet": should_greet,
            "greeting_text": settings.greeting_text,
        }

    def start_turn(self, session_id: str, user_text: str) -> RTCTurnState:
        return self.start_turn_with_owner(session_id, user_text, "backend", "default-backend")

    def start_turn_with_owner(
        self,
        session_id: str,
        user_text: str,
        owner: str,
        route_reason: str,
        intent: str = "unknown",
    ) -> RTCTurnState:
        session = self.get_session(session_id)
        session.active_turn_id += 1
        session.last_seen_ts = time.time()
        session.state = "thinking" if owner == "backend" else "listening"
        session.last_turn = RTCTurnState(
            turn_id=session.active_turn_id,
            user_text=user_text,
            status="processing",
            created_ts=session.last_seen_ts,
            owner=owner,
            intent=intent,
            route_reason=route_reason,
            processing_started_ts=session.last_seen_ts,
        )
        self.publish_event(
            session_id,
            "turn_started",
            {
                "turn_id": session.active_turn_id,
                "user_text": user_text,
                "state": session.state,
                "owner": owner,
                "intent": intent,
                "route_reason": route_reason,
            },
        )
        return session.last_turn

    def mark_transition_sent(self, session_id: str, turn_id: int) -> bool:
        session = self.get_session(session_id)
        if not session.last_turn or session.last_turn.turn_id != turn_id:
            return False
        if turn_id <= session.interrupted_turn_id:
            return False
        session.last_turn.transition_sent = True
        return True

    def finish_turn(
        self,
        session_id: str,
        turn_id: int,
        status: str,
        display_text: str,
        speak_text: str,
        processing_ms: float,
        state: str,
        action_state: str = "none",
        metadata: dict[str, Any] | None = None,
        pending_confirmation: PendingConfirmation | None = None,
        clear_pending_confirmation: bool = False,
    ) -> dict[str, object]:
        session = self.get_session(session_id)
        discarded = (
            turn_id != session.active_turn_id
            or turn_id <= session.interrupted_turn_id
            or not session.last_turn
        )
        if not discarded and session.last_turn:
            session.last_turn.status = status
            session.last_turn.completed_ts = time.time()
            session.last_turn.display_text = display_text
            session.last_turn.speak_text = speak_text
            session.last_turn.processing_ms = processing_ms
            session.last_turn.action_state = action_state
            session.last_turn.metadata = metadata or {}
            session.state = state
            session.metrics["last_processing_ms"] = processing_ms
            if clear_pending_confirmation:
                session.pending_confirmation = None
            if pending_confirmation is not None:
                session.pending_confirmation = pending_confirmation
        return {
            "discarded": discarded,
            "active_turn_id": session.active_turn_id,
        }

    def get_pending_confirmation(self, session_id: str) -> PendingConfirmation | None:
        session = self.get_session(session_id)
        pending = session.pending_confirmation
        if pending is None:
            return None
        if pending.expires_ts <= time.time():
            session.pending_confirmation = None
            self.publish_event(
                session_id,
                "pricing_confirmation",
                {"status": "expired"},
            )
            return None
        return pending

    def clear_pending_confirmation(self, session_id: str) -> None:
        session = self.get_session(session_id)
        session.pending_confirmation = None
        self.publish_event(
            session_id,
            "pricing_confirmation",
            {"status": "cleared"},
        )

    def interrupt(self, session_id: str, reason: str) -> dict[str, object]:
        session = self.get_session(session_id)
        session.interrupted_turn_id = session.active_turn_id
        session.state = "interrupted"
        session.last_seen_ts = time.time()
        self.publish_event(
            session_id,
            "state",
            {"state": "interrupted", "detail": "当前播报已被打断。"},
        )
        return {
            "session_id": session.session_id,
            "state": session.state,
            "reason": reason,
            "interrupted_turn_id": session.interrupted_turn_id,
        }

    def record_callback(self, session_id: str, callback_type: str, payload: dict[str, Any]) -> None:
        session = self.get_session(session_id)
        session.callback_events = (session.callback_events + [{"type": callback_type, "payload": payload}])[-30:]
        self.publish_event(
            session_id,
            "callback",
            {"callback_type": callback_type, "payload": payload},
        )

    def snapshot(self, session_id: str) -> dict[str, object]:
        session = self.get_session(session_id)
        return {
            "session_id": session.session_id,
            "client_id": session.client_id,
            "transport": session.transport,
            "room_id": session.room_id,
            "user_id": session.user_id,
            "ai_user_id": session.ai_user_id,
            "task_id": session.task_id,
            "state": session.state,
            "active_turn_id": session.active_turn_id,
            "interrupted_turn_id": session.interrupted_turn_id,
            "rtc_connected": session.rtc_connected,
            "voice_chat_started": session.voice_chat_started,
            "presence_active": session.presence.active,
            "last_error": session.last_error,
            "metrics": session.metrics,
            "last_turn": (
                {
                    "turn_id": session.last_turn.turn_id,
                    "user_text": session.last_turn.user_text,
                    "status": session.last_turn.status,
                    "owner": session.last_turn.owner,
                    "intent": session.last_turn.intent,
                    "route_reason": session.last_turn.route_reason,
                    "transition_sent": session.last_turn.transition_sent,
                    "processing_ms": session.last_turn.processing_ms,
                    "action_state": session.last_turn.action_state,
                    "metadata": session.last_turn.metadata,
                }
                if session.last_turn
                else None
            ),
            "pending_confirmation": (
                {
                    "tool_name": session.pending_confirmation.tool_name,
                    "execution_id": session.pending_confirmation.execution_id,
                    "store_id": session.pending_confirmation.store_id,
                    "expires_ts": session.pending_confirmation.expires_ts,
                    "action_label": session.pending_confirmation.action_label,
                }
                if session.pending_confirmation
                else None
            ),
            "callback_count": len(session.callback_events),
        }

    def set_error(self, session_id: str, message: str) -> None:
        session = self.get_session(session_id)
        session.state = "error"
        session.last_error = message
        self.publish_event(session_id, "error", {"message": message})

    def reset_presence_if_idle(self, session_id: str) -> None:
        session = self.get_session(session_id)
        if not session.presence.active:
            return
        if time.time() - session.presence.last_seen_ts >= settings.presence_reset_seconds:
            session.presence.active = False
            session.state = "idle"

    async def next_event(self, session_id: str) -> dict[str, Any]:
        session = self.get_session(session_id)
        return await session.event_queue.get()
