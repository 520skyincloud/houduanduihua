from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any
from typing import Literal
from typing import Optional


AnswerType = Literal["direct", "handoff", "invalid"]
TurnIntent = Literal["faq", "handoff", "chitchat", "unknown", "pricing", "pricing_confirm"]
TurnOwner = Literal["backend", "s2s"]
SessionState = Literal[
    "idle",
    "greeting",
    "listening",
    "thinking",
    "speaking",
    "interrupted",
    "handoff",
    "error",
    "pricing_intent",
    "pricing_preview",
    "pricing_confirm_pending",
    "pricing_executing",
    "pricing_executed",
    "pricing_rejected",
]
ActionState = Literal[
    "none",
    "pricing_preview",
    "pricing_confirm_pending",
    "pricing_executing",
    "pricing_executed",
    "pricing_rejected",
]


@dataclass
class FAQItem:
    faq_id: str
    hotel_id: str
    standard_answer: str
    aliases: list[str]
    answer_type: AnswerType
    source_rows: list[int] = field(default_factory=list)


@dataclass
class SearchResult:
    faq_id: Optional[str]
    confidence: float
    answer_type: AnswerType
    standard_answer: str
    matched_alias: Optional[str] = None


@dataclass
class ResolvedAnswer:
    status: Literal["answered", "handoff", "not_found"]
    faq_id: Optional[str]
    confidence: float
    needs_handoff: bool
    display_text: str
    speak_text: str


@dataclass
class PendingConfirmation:
    tool_name: str
    arguments: dict[str, Any]
    display_preview: str
    speak_preview: str
    created_ts: float
    expires_ts: float
    confirmation_required: bool = True
    execution_id: Optional[int] = None
    store_id: Optional[int] = None
    action_label: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class BackendTurnResult:
    status: str
    display_text: str
    speak_text: str
    state: SessionState
    confidence: float = 1.0
    needs_handoff: bool = False
    action_state: ActionState = "none"
    metadata: dict[str, Any] = field(default_factory=dict)
    pending_confirmation: Optional[PendingConfirmation] = None
    clear_pending_confirmation: bool = False


@dataclass
class TurnRouteDecision:
    owner: TurnOwner
    intent: TurnIntent
    confidence: float
    reason: str


@dataclass
class PresenceState:
    active: bool = False
    last_trigger_ts: float = 0.0
    last_seen_ts: float = 0.0


@dataclass
class RTCTurnState:
    turn_id: int
    user_text: str
    status: str
    created_ts: float
    owner: TurnOwner = "backend"
    intent: TurnIntent = "unknown"
    route_reason: str = ""
    transition_sent: bool = False
    processing_started_ts: float = 0.0
    completed_ts: float = 0.0
    display_text: str = ""
    speak_text: str = ""
    processing_ms: float = 0.0
    action_state: ActionState = "none"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RTCSessionState:
    session_id: str
    client_id: str
    transport: str
    room_id: str
    user_id: str
    ai_user_id: str
    rtc_token: str
    created_ts: float
    last_seen_ts: float
    state: SessionState = "idle"
    task_id: str = ""
    active_turn_id: int = 0
    interrupted_turn_id: int = 0
    last_turn: Optional[RTCTurnState] = None
    presence: PresenceState = field(default_factory=PresenceState)
    event_seq: int = 0
    rtc_connected: bool = False
    voice_chat_started: bool = False
    last_error: Optional[str] = None
    callback_events: list[dict[str, Any]] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)
    pending_confirmation: Optional[PendingConfirmation] = None
    event_queue: asyncio.Queue[dict[str, Any]] = field(default_factory=asyncio.Queue)


@dataclass
class SessionCommand:
    event_id: int
    kind: str
    payload: dict[str, Any]
    created_ts: float
