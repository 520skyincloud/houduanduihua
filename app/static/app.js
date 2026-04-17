const dom = {
  userSubtitleText: document.getElementById("userSubtitleText"),
  aiSubtitleText: document.getElementById("aiSubtitleText"),
  speakText: document.getElementById("speakText"),
  statusChip: document.getElementById("statusChip"),
  connectionChip: document.getElementById("connectionChip"),
  metricText: document.getElementById("metricText"),
  sessionText: document.getElementById("sessionText"),
  thinkingText: document.getElementById("thinkingText"),
  liveCaptionText: document.getElementById("liveCaptionText"),
  rtcSubtitleDebugText: document.getElementById("rtcSubtitleDebugText"),
  pricingStateText: document.getElementById("pricingStateText"),
  callbackText: document.getElementById("callbackText"),
  knowledgeText: document.getElementById("knowledgeText"),
  warningText: document.getElementById("warningText"),
  avatarStatus: document.getElementById("avatarStatus"),
  avatarVideo: document.getElementById("avatarVideo"),
  selfAvatarMount: document.getElementById("selfAvatarMount"),
  rtcStreamMount: document.getElementById("rtcStreamMount"),
  micBtn: document.getElementById("micBtn"),
  presenceBtn: document.getElementById("presenceBtn"),
  interruptBtn: document.getElementById("interruptBtn"),
};

const MESSAGE_TYPE = {
  SUBTITLE: "subv",
  BRIEF: "conv",
  FUNCTION_CALL: "tool",
};

const AGENT_BRIEF = {
  UNKNOWN: 0,
  LISTENING: 1,
  THINKING: 2,
  SPEAKING: 3,
  INTERRUPTED: 4,
  FINISHED: 5,
};

const COMMAND = {
  INTERRUPT: "interrupt",
  EXTERNAL_TEXT_TO_SPEECH: "ExternalTextToSpeech",
  EXTERNAL_TEXT_TO_LLM: "ExternalTextToLLM",
};

const PRICING_COMMAND_ALIASES = {
  "收益分析": [
    "生成收益分析",
    "给我生成收益分析",
    "帮我生成收益分析",
    "来个收益分析",
    "做个收益分析",
    "来一版收益分析",
    "做一版收益分析",
  ],
  "昨日复盘": [
    "生成昨日复盘",
    "给我生成昨日复盘",
    "帮我生成昨日复盘",
    "来个昨日复盘",
    "做个昨日复盘",
    "来一版昨日复盘",
    "做一版昨日复盘",
  ],
  "调价方案": [
    "生成调价方案",
    "给我生成调价方案",
    "帮我生成调价方案",
    "来个调价方案",
    "做个调价方案",
    "来一版调价方案",
    "做一版调价方案",
  ],
};

const EXACT_PRICING_COMMANDS = Object.values(PRICING_COMMAND_ALIASES).flat();

const PRICING_FILLER_WORDS = [
  "小丽",
  "你好",
  "您好",
  "麻烦",
  "请",
];

const PRICING_COMMAND_PATTERNS = [
  /(生成|帮我生成|给我生成|做个|做一版|帮我做个|来个|来一版).*(收益分析)/,
  /(生成|帮我生成|给我生成|做个|做一版|帮我做个|来个|来一版).*(昨日复盘)/,
  /(生成|帮我生成|给我生成|做个|做一版|帮我做个|来个|来一版).*(调价方案)/,
];

const HARD_BACKEND_PREEMPT_KEYWORDS = [
  "早餐",
  "停车",
  "车位",
  "停哪",
  "停哪儿",
  "收钱",
  "停车费",
  "进车口",
  "辅路",
  "发票",
  "开票",
  "抬头",
  "税号",
  "入住",
  "退房",
  "晚到",
  "半夜到",
  "续住",
  "房型",
  "路线",
  "怎么走",
  "导航",
  "店名",
  "楼层",
  "会议室",
  "开会地方",
  "洗衣房",
  "健身房",
  "营业时间",
  "收费",
  "政策",
  "几点",
  "在哪",
  "位置",
  "高铁",
  "机场",
  "剃须刀",
  "用品",
  "前台",
];

const INTERRUPT_PRIORITY = {
  NONE: 0,
  HIGH: 1,
  MEDIUM: 2,
  LOW: 3,
};

const state = {
  bootstrap: null,
  sessionId: null,
  rtc: null,
  rtcModule: null,
  eventSource: null,
  joined: false,
  voiceChatStarted: false,
  activeRequestId: 0,
  activeTurnId: 0,
  activeTurnToken: "",
  activeTurnOwner: "backend",
  activeTurnPhase: "idle",
  lastParagraphKey: "",
  interrupting: false,
  uiState: "Idle",
  currentOwner: "backend",
  lastBinaryEvents: [],
  lastSubtitleEvents: [],
  backendPreempt: {
    active: false,
    reason: "",
  },
  micPermission: "unknown",
  autoGreetingTriggered: false,
  lastInterruptAt: 0,
  revenueTurnPending: false,
  revenuePendingTurnId: null,
  revenueBusyUntil: 0,
  revenueBusyReleaseTimer: null,
  liveAiComposite: "",
  interruptGate: {
    active: false,
    turnId: 0,
    turnToken: "",
    status: "idle",
  },
};

function revenueTurnIsBusy() {
  return state.revenueTurnPending || Date.now() < state.revenueBusyUntil;
}

function clearRevenueBusyLatch() {
  state.revenueTurnPending = false;
  state.revenuePendingTurnId = null;
  state.revenueBusyUntil = 0;
  if (state.revenueBusyReleaseTimer) {
    window.clearTimeout(state.revenueBusyReleaseTimer);
    state.revenueBusyReleaseTimer = null;
  }
}

function holdRevenueBusyForSpeak(speakText = "") {
  const text = String(speakText || "").trim();
  const chars = text.length;
  const holdMs = Math.min(12000, Math.max(4000, 1800 + chars * 120));
  state.revenueBusyUntil = Date.now() + holdMs;
  if (state.revenueBusyReleaseTimer) {
    window.clearTimeout(state.revenueBusyReleaseTimer);
  }
  state.revenueBusyReleaseTimer = window.setTimeout(() => {
    state.revenueBusyUntil = 0;
    state.revenueBusyReleaseTimer = null;
    if (!state.revenueTurnPending) {
      setPricingState("收益链待机中，等待调价或复盘指令。");
    }
  }, holdMs);
}

function pushDebugEvent(key, payload) {
  const target = state[key];
  if (!Array.isArray(target)) return;
  target.push({
    ts: new Date().toISOString(),
    ...payload,
  });
  if (target.length > 20) {
    target.shift();
  }
}

function setStatus(stateLabel, detail = "", speak = "") {
  state.uiState = stateLabel;
  dom.statusChip.textContent = stateLabel;
  if (detail) dom.thinkingText.textContent = detail;
  if (speak) dom.speakText.textContent = speak;
}

function setConnection(text) {
  dom.connectionChip.textContent = text;
}

function setMetric(text) {
  dom.metricText.textContent = text;
}

function setPricingState(text) {
  if (dom.pricingStateText) {
    dom.pricingStateText.textContent = text;
  }
}

function setWarning(text) {
  dom.warningText.textContent = text;
}

function setCallback(text) {
  dom.callbackText.textContent = text;
}

function setLiveTranscript(text = "") {
  if (!dom.liveCaptionText) return;
  const normalized = String(text || "").trim();
  dom.liveCaptionText.textContent = normalized ? `实时听写：${normalized}` : "实时听写：";
}

function clearLiveTranscript() {
  setLiveTranscript("");
}

function mergeCaptionChunk(previousText = "", nextText = "") {
  const prev = String(previousText || "").trim();
  const next = String(nextText || "").trim();
  if (!next) return prev;
  if (!prev) return next;
  if (next.includes(prev)) return next;
  if (prev.includes(next)) return prev;
  const maxOverlap = Math.min(prev.length, next.length);
  for (let size = maxOverlap; size > 0; size -= 1) {
    if (prev.slice(-size) === next.slice(0, size)) {
      return `${prev}${next.slice(size)}`;
    }
  }
  return `${prev}${next}`;
}

function setRtcSubtitleDebug(payload = {}) {
  if (!dom.rtcSubtitleDebugText) return;
  const source = String(payload.source || "unknown");
  const role = String(payload.role || "unknown");
  const userId = String(payload.userId || "-");
  const text = String(payload.text || "").trim();
  const flags = [payload.paragraph ? "paragraph" : "", payload.definite ? "definite" : ""]
    .filter(Boolean)
    .join("/");
  dom.rtcSubtitleDebugText.textContent = text
    ? `RTC 字幕调试：${role} · ${source} · ${userId}${flags ? ` · ${flags}` : ""} · ${text}`
    : `RTC 字幕调试：${role} · ${source} · ${userId}${flags ? ` · ${flags}` : ""}`;
}

function canSendInterrupt() {
  const now = Date.now();
  if (now - state.lastInterruptAt < 800) {
    return false;
  }
  state.lastInterruptAt = now;
  return true;
}

function setActiveTurn(payload = {}) {
  const turnId = Number(payload.turn_id || 0);
  const turnToken = typeof payload.turn_token === "string" ? payload.turn_token : "";
  if (turnId && turnId >= state.activeTurnId) {
    state.activeTurnId = turnId;
    state.activeTurnToken = turnToken || state.activeTurnToken;
  }
  if (payload.owner) {
    state.activeTurnOwner = payload.owner;
  }
  if (payload.phase) {
    state.activeTurnPhase = payload.phase;
  }
}

function matchesCurrentTurn(payload = {}, allowLiveWithoutToken = false) {
  const turnId = Number(payload.turn_id || 0);
  const turnToken = typeof payload.turn_token === "string" ? payload.turn_token : "";
  if (!turnId) return allowLiveWithoutToken;
  if (turnId < state.activeTurnId) return false;
  if (turnId > state.activeTurnId) {
    setActiveTurn(payload);
    return true;
  }
  if (!state.activeTurnToken) return true;
  if (!turnToken) return allowLiveWithoutToken;
  return turnToken === state.activeTurnToken;
}

function updateInterruptGate(payload = {}) {
  const gate = typeof payload.interrupt_gate === "string" ? payload.interrupt_gate : "";
  if (!gate) return;
  if (gate === "interrupting" || gate === "waiting_interrupt_ack") {
    state.interruptGate = {
      active: true,
      turnId: Number(payload.turn_id || state.activeTurnId || 0),
      turnToken: typeof payload.turn_token === "string" ? payload.turn_token : state.activeTurnToken,
      status: gate,
    };
    return;
  }
  state.interruptGate = {
    active: false,
    turnId: 0,
    turnToken: "",
    status: gate,
  };
}

function shouldRenderAiLiveCaption() {
  return !state.interruptGate.active;
}

function shouldAcceptAiFinalSubtitle(payload = {}) {
  const turnId = Number(payload.turn_id || 0);
  if (!turnId) return true;
  if (payload.owner === "backend") return true;
  return state.activeTurnOwner !== "backend";
}

async function readMicrophonePermissionState() {
  if (!navigator.permissions?.query) {
    return "unknown";
  }
  try {
    const status = await navigator.permissions.query({ name: "microphone" });
    return status.state || "unknown";
  } catch (error) {
    pushDebugEvent("lastBinaryEvents", {
      type: "permission-query",
      error: String(error),
    });
    return "unknown";
  }
}

async function readCameraPermissionState() {
  if (!navigator.permissions?.query) {
    return "unknown";
  }
  try {
    const status = await navigator.permissions.query({ name: "camera" });
    return status.state || "unknown";
  } catch (error) {
    pushDebugEvent("lastBinaryEvents", {
      type: "permission-query-camera",
      error: String(error),
    });
    return "unknown";
  }
}

async function ensureMicrophoneAccess(interactive = true, includeVideo = false) {
  const micPermissionState = await readMicrophonePermissionState();
  const cameraPermissionState = includeVideo ? await readCameraPermissionState() : "granted";
  state.micPermission = micPermissionState;
  if (micPermissionState === "granted" && cameraPermissionState === "granted") {
    setWarning(includeVideo ? "摄像头和麦克风权限已授权。" : "麦克风权限已授权。");
    return true;
  }
  if (micPermissionState === "denied" || (includeVideo && cameraPermissionState === "denied")) {
    setWarning(
      includeVideo
        ? "浏览器已拒绝摄像头或麦克风权限。请点击地址栏旁的站点设置，改成允许后，再点“重新授权”。"
        : "浏览器已拒绝麦克风权限。请点击地址栏旁的站点设置，改成允许后，再点“重新授权麦克风”。"
    );
    return false;
  }
  if (!interactive) {
    setWarning(includeVideo ? "摄像头或麦克风权限尚未确认，请点“重新授权”触发授权。" : "麦克风权限尚未确认，请点“重新授权麦克风”触发授权。");
    return false;
  }
  if (!navigator.mediaDevices?.getUserMedia) {
    setWarning(includeVideo ? "当前浏览器不支持音视频采集，无法启动摄像头和麦克风。" : "当前浏览器不支持 getUserMedia，无法启动麦克风采集。");
    return false;
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: includeVideo });
    stream.getTracks().forEach((track) => track.stop());
    state.micPermission = "granted";
    setWarning(includeVideo ? "摄像头和麦克风权限授权成功，正在继续 RTC 联调。" : "麦克风权限授权成功，正在继续 RTC 联调。");
    return true;
  } catch (error) {
    state.micPermission = "denied";
    setStatus("Error", "麦克风授权失败。", String(error));
    setWarning(`麦克风授权失败，请在浏览器站点权限里允许麦克风后重试：${String(error)}`);
    return false;
  }
}

function normalizeRouteText(text) {
  return (text || "").replace(/[？?！!，,。.\s]+/g, "").toLowerCase();
}

function currentFaqRouteMode() {
  return state.bootstrap?.voice_chat?.faq_route_mode || "hybrid_risk_split";
}

function faqPrefersS2SMemory() {
  return ["s2s_memory", "hybrid_risk_split"].includes(currentFaqRouteMode());
}

function pureS2SEnabled() {
  return Boolean(state.bootstrap?.voice_chat?.pure_s2s_enabled);
}

function matchesPricingPreempt(normalized) {
  const stripped = PRICING_FILLER_WORDS.reduce((acc, filler) => acc.replaceAll(filler, ""), normalized);
  if (EXACT_PRICING_COMMANDS.includes(stripped)) {
    return true;
  }
  if (PRICING_COMMAND_PATTERNS.some((pattern) => pattern.test(stripped))) {
    return true;
  }
  const tokenGroups = [
    ["收益", "分析"],
    ["昨日", "复盘"],
    ["昨天", "复盘"],
    ["调价", "方案"],
  ];
  const actionHints = ["生成", "来个", "来一版", "做个", "做一版", "给我", "帮我"];
  return tokenGroups.some((tokens) =>
    tokens.every((token) => stripped.includes(token)) &&
    stripped.includes("生成") &&
    (actionHints.some((hint) => stripped.includes(hint)) || stripped.includes(tokens.join("")))
  );
}

function shouldPreemptToBackend(text) {
  const normalized = normalizeRouteText(text);
  if (!normalized) return { hit: false, reason: "" };
  if (pureS2SEnabled()) {
    return { hit: false, reason: "" };
  }
  if (currentFaqRouteMode() === "s2s_memory") {
    return { hit: false, reason: "" };
  }
  if (
    matchesPricingPreempt(normalized)
  ) {
    return { hit: true, reason: "pricing-keyword-hit" };
  }
  if (
    HARD_BACKEND_PREEMPT_KEYWORDS.some((keyword) => normalized.includes(keyword)) ||
    /\d|几点|多少|费用|价格|规则|政策/.test(normalized)
  ) {
    return { hit: true, reason: "hard-backend-rule" };
  }
  return { hit: false, reason: "" };
}

function updateAvatarStatus(text) {
  dom.avatarStatus.textContent = text;
}

function stringToTlv(str, type) {
  const typeBuffer = new Uint8Array(4);
  for (let i = 0; i < type.length; i += 1) {
    typeBuffer[i] = type.charCodeAt(i);
  }
  const valueBuffer = new TextEncoder().encode(str);
  const tlvBuffer = new Uint8Array(typeBuffer.length + 4 + valueBuffer.length);
  tlvBuffer.set(typeBuffer, 0);
  tlvBuffer[4] = (valueBuffer.length >> 24) & 0xff;
  tlvBuffer[5] = (valueBuffer.length >> 16) & 0xff;
  tlvBuffer[6] = (valueBuffer.length >> 8) & 0xff;
  tlvBuffer[7] = valueBuffer.length & 0xff;
  tlvBuffer.set(valueBuffer, 8);
  return tlvBuffer.buffer;
}

function tlvToString(buffer) {
  const typeBuffer = new Uint8Array(buffer, 0, 4);
  const lengthBuffer = new Uint8Array(buffer, 4, 4);
  const valueBuffer = new Uint8Array(buffer, 8);
  let type = "";
  for (let i = 0; i < typeBuffer.length; i += 1) {
    type += String.fromCharCode(typeBuffer[i]);
  }
  const length =
    (lengthBuffer[0] << 24) |
    (lengthBuffer[1] << 16) |
    (lengthBuffer[2] << 8) |
    lengthBuffer[3];
  const value = new TextDecoder().decode(valueBuffer.subarray(0, length));
  return { type, value };
}

function decodeBase64ToBytes(base64Text) {
  const normalized = String(base64Text || "").trim();
  if (!normalized) {
    throw new Error("empty base64 payload");
  }
  const binary = window.atob(normalized);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return bytes;
}

function unpackSubtitleMessage(bufferLike) {
  const bytes = bufferLike instanceof Uint8Array ? bufferLike : new Uint8Array(bufferLike);
  if (bytes.length < 8) {
    throw new Error("subtitle payload too short");
  }
  const header = String.fromCharCode(...bytes.subarray(0, 4));
  if (header !== MESSAGE_TYPE.SUBTITLE) {
    throw new Error(`unexpected subtitle header: ${header}`);
  }
  const length =
    (bytes[4] << 24) |
    (bytes[5] << 16) |
    (bytes[6] << 8) |
    bytes[7];
  const payloadBytes = bytes.subarray(8, 8 + length);
  return JSON.parse(new TextDecoder().decode(payloadBytes));
}

async function consumeSubtitlePayload(parsed, source) {
  pushDebugEvent("lastBinaryEvents", {
    type: `${MESSAGE_TYPE.SUBTITLE}:${source}`,
    parsed,
  });
  const entries = Array.isArray(parsed?.data) ? parsed.data : [];
  for (const item of entries) {
    await handleSubtitleEvent(item || {}, source);
  }
}

function bindRtcSubtitleListeners(engine, VERTC) {
  engine.on(VERTC.events.onRoomBinaryMessageReceived, async (event) => {
    try {
      const { type, value } = tlvToString(event.message);
      const parsed = JSON.parse(value);
      pushDebugEvent("lastBinaryEvents", {
        type,
        parsed,
      });
      if (type === MESSAGE_TYPE.SUBTITLE) {
        await consumeSubtitlePayload(parsed, "room_binary");
      }
      if (type === MESSAGE_TYPE.BRIEF) {
        const [label, detail] = mapBriefCode(parsed?.Stage?.Code);
        setStatus(label, detail, dom.speakText.textContent);
      }
    } catch (error) {
      setCallback(`回调日志：解析 room binary message 失败，${String(error)}`);
    }
  });

  engine.on("on_volc_message_data", async (event) => {
    try {
      const parsed = unpackSubtitleMessage(decodeBase64ToBytes(event?.message));
      await consumeSubtitlePayload(parsed, "on_volc_message_data");
    } catch (error) {
      pushDebugEvent("lastBinaryEvents", {
        type: "on_volc_message_data:error",
        error: String(error),
      });
      setCallback(`回调日志：解析 on_volc_message_data 失败，${String(error)}`);
    }
  });
}

async function postJson(url, payload = {}) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`${response.status}: ${text}`);
  }
  return response.json();
}

async function loadBootstrap() {
  state.bootstrap = await postJson("/api/bootstrap", {
    client_id: "lobby-screen",
    transport: "volcengine-rtc",
  });
  state.sessionId = state.bootstrap.session_id;
  dom.sessionText.textContent = `RTC Session：${state.sessionId} / 房间 ${state.bootstrap.rtc.room_id} / FAQ ${state.bootstrap.voice_chat.faq_route_mode}`;
  setMetric(`链路耗时：bootstrap ${state.bootstrap.processing_ms} ms`);
  if (state.bootstrap.warnings.length) {
    setWarning(state.bootstrap.warnings.join(" "));
  } else {
    setWarning("火山 RTC、StartVoiceChat、S2S 与后端接管参数已就绪。");
  }
  const effectiveDialogPath =
    state.bootstrap.voice_chat.effective_dialog_path || state.bootstrap.voice_chat.primary_dialog_path;
  dom.knowledgeText.textContent = effectiveDialogPath === "s2s"
    ? (
      pureS2SEnabled()
        ? "当前是纯 S2S 实验模式，所有问题都直接留在端到端链路，后端不接管。"
        : currentFaqRouteMode() === "s2s_memory"
        ? "主链为 S2S(2024-12-01)，酒店 FAQ 正在走原生 MemoryConfig 全量实验线，调价与确认类问题仍切后端。"
        : currentFaqRouteMode() === "hybrid_risk_split"
        ? "主链为 S2S(2024-12-01)，低风险自然交流走实时对话 AI，高风险酒店事实由本地 FAQ 语义匹配后端接管。"
        : "主链为 S2S(2024-12-01)，酒店知识与强规则问题命中后会切到后端知识链。"
    )
    : "当前主链为 ASR -> LLM -> TTS，RTC 负责音频传输；酒店事实题优先走本地 FAQ 语义匹配与标准句播报。";
  setPricingState(
    state.bootstrap.pricing?.revenue_mcp_enabled
      ? "收益链已启用，调价/复盘/执行请求将切到后端收益 MCP。"
      : "收益链未启用。"
  );
  updateAvatarStatus(
    state.bootstrap.avatar.official_avatar_enabled
      ? "已启用火山官方数字人，远端视频流将覆盖备用层。"
      : `自研 3D 容器已预留，挂载点 #${state.bootstrap.avatar.self_avatar_mount_id}。`
  );
}

function bindSse() {
  if (!state.sessionId) return;
  state.eventSource = new EventSource(`/api/rtc/sessions/${state.sessionId}/events`);
  state.eventSource.onmessage = (event) => {
    if (!event.data) return;
    const packet = JSON.parse(event.data);
    handleServerEvent(packet);
  };
  state.eventSource.onerror = () => {
    setCallback("回调日志：SSE 断开，等待浏览器自动重连。");
  };
}

function handleServerEvent(packet) {
  const { kind, payload } = packet;
  if (kind === "state") {
    setActiveTurn(payload);
    updateInterruptGate(payload);
    if (!matchesCurrentTurn(payload, true) && payload.state !== "interrupted") {
      return;
    }
    const label = payload.state || "Idle";
    if (payload.state === "interrupted") {
      state.lastParagraphKey = "";
      state.backendPreempt = { active: false, reason: "" };
      clearRevenueBusyLatch();
      clearLiveTranscript();
      state.liveAiComposite = "";
    }
    dom.thinkingText.textContent = payload.detail || "等待新的 RTC 事件。";
    if (payload.action_state && payload.action_state !== "none") {
      setPricingState(`收益链状态：${payload.action_state}`);
    }
    setStatus(label.charAt(0).toUpperCase() + label.slice(1), payload.detail || dom.aiSubtitleText.textContent);
    return;
  }
  if (kind === "connection") {
    setConnection(
      payload.voice_chat_started
        ? "RTC 已连接 / VoiceChat 已启动"
        : payload.rtc_connected
          ? "RTC 已连接 / VoiceChat 未启动"
          : "RTC 未连接"
    );
    return;
  }
  if (kind === "presence") {
    if (payload.should_greet) {
      setStatus("Greeting", "检测到来宾进入展厅区域。", state.bootstrap.voice_chat.greeting_text);
    }
    return;
  }
  if (kind === "subtitle") {
    if (!matchesCurrentTurn(payload, payload.kind !== "final")) {
      return;
    }
    const text = String(payload.text || "").trim();
    if (!text) {
      return;
    }
    if (payload.speaker === "user") {
      if (payload.kind === "final") {
        dom.userSubtitleText.textContent = text;
        clearLiveTranscript();
      } else {
        setLiveTranscript(text);
      }
    } else {
      if (payload.kind !== "final" && !shouldRenderAiLiveCaption()) {
        return;
      }
      if (payload.kind === "final") {
        if (!shouldAcceptAiFinalSubtitle(payload)) {
          return;
        }
        clearLiveTranscript();
        state.liveAiComposite = "";
        dom.aiSubtitleText.textContent = text;
        dom.speakText.textContent = text;
      } else {
        state.liveAiComposite = mergeCaptionChunk(state.liveAiComposite, text);
        dom.aiSubtitleText.textContent = state.liveAiComposite;
        dom.speakText.textContent = state.liveAiComposite;
        setLiveTranscript(text);
      }
    }
    return;
  }
  if (kind === "turn_result") {
    setActiveTurn(payload);
    updateInterruptGate(payload);
    if (!matchesCurrentTurn(payload)) {
      return;
    }
    state.backendPreempt = { active: false, reason: "" };
    state.currentOwner = "backend";
    clearLiveTranscript();
    state.liveAiComposite = "";
    if (state.revenueTurnPending && payload.turn_id === state.revenuePendingTurnId) {
      state.revenueTurnPending = false;
      state.revenuePendingTurnId = null;
      holdRevenueBusyForSpeak(payload.speak_text || payload.display_text || "");
    }
    const spokenText = String(payload.speak_text || payload.display_text || "").trim();
    dom.aiSubtitleText.textContent = spokenText || payload.display_text;
    dom.speakText.textContent = spokenText || payload.display_text;
    if (payload.action_state && payload.action_state !== "none") {
      setPricingState(`收益链状态：${payload.action_state}`);
    } else {
      setPricingState("收益链待机中，等待调价或复盘指令。");
    }
    setMetric(`链路耗时：后端 ${payload.processing_ms} ms / turn ${payload.turn_id}`);
    return;
  }
  if (kind === "turn_started") {
    setActiveTurn(payload);
    updateInterruptGate(payload);
    if (payload.owner === "backend" && (payload.intent === "pricing" || payload.intent === "pricing_confirm")) {
      state.revenueTurnPending = true;
      state.revenuePendingTurnId = payload.turn_id ?? null;
    }
    if (payload.owner !== "backend") {
      state.backendPreempt = { active: false, reason: "" };
    } else {
      clearLiveTranscript();
      state.liveAiComposite = "";
    }
    state.currentOwner = payload.owner || state.currentOwner;
    return;
  }
  if (kind === "agent_command") {
    dispatchAgentCommand(payload).catch((error) => {
      setCallback(`回调日志：发送 AI 指令失败，${String(error)}`);
    });
    return;
  }
  if (kind === "callback") {
    if (payload.callback_type === "agent_command_ack" && payload.command === "interrupt" && payload.applies_to_current_turn) {
      updateInterruptGate({ ...payload, interrupt_gate: payload.ok ? "acked" : "ack_error" });
    }
    if (payload.callback_type === "agent_command_ack") {
      setCallback(
        `回调日志：${payload.command} ${payload.ok ? "发送成功" : "发送失败"}，${payload.detail || "无明细"}。`
      );
    } else {
      setCallback(`回调日志：收到 ${payload.callback_type} 回调。`);
    }
    return;
  }
  if (kind === "voice_chat") {
    setCallback(`回调日志：${payload.action === "start" ? "已启动" : "已停止"} VoiceChat。`);
  }
}

async function dispatchAgentCommand(payload) {
  if (!state.rtc || !state.bootstrap) {
    if (payload.message) {
      dom.speakText.textContent = payload.message;
    }
    return;
  }
  const message = JSON.stringify({
    Command: payload.command,
    InterruptMode: payload.interrupt_mode ?? INTERRUPT_PRIORITY.NONE,
    Message: payload.message || "",
  });
  const sender = state.rtc.room && typeof state.rtc.room.sendUserBinaryMessage === "function"
    ? state.rtc.room
    : state.rtc.engine;
  const reliableOrdered =
    state.rtcModule?.MessageConfig?.RELIABLE_ORDERED ??
    state.rtcModule?.MessageConfig?.MESSAGE_CONFIG_RELIABLE_ORDERED;
  const args = [
    state.bootstrap.rtc.ai_user_id,
    stringToTlv(message, "ctrl"),
  ];
  if (reliableOrdered !== undefined) {
    args.push(reliableOrdered);
  }
  try {
    await sender.sendUserBinaryMessage(...args);
    await postJson(`/api/rtc/sessions/${state.sessionId}/agent-command-acks`, {
      command: payload.command,
      ok: true,
      detail: `sent via ${sender === state.rtc.room ? "room" : "engine"}${reliableOrdered !== undefined ? " / reliable_ordered" : ""}`,
      turn_id: payload.turn_id ?? null,
      turn_token: payload.turn_token ?? null,
    });
    setCallback(`回调日志：已发送 ${payload.command} 指令给 ${state.bootstrap.rtc.ai_user_id}。`);
    if (payload.message) {
      dom.speakText.textContent = payload.message;
    }
  } catch (error) {
    await postJson(`/api/rtc/sessions/${state.sessionId}/agent-command-acks`, {
      command: payload.command,
      ok: false,
      detail: String(error),
      turn_id: payload.turn_id ?? null,
      turn_token: payload.turn_token ?? null,
    }).catch(() => {});
    throw error;
  }
}

async function sendTextToAgent(text) {
  if (!text || !text.trim()) return;
  if (!state.rtc || !state.voiceChatStarted) {
    throw new Error("RTC / VoiceChat 尚未就绪，无法向火山原生 VoiceChat 主链发送文本。");
  }
  state.currentOwner = "native";
  dom.userSubtitleText.textContent = text;
  clearLiveTranscript();
  setPricingState("收益链待机中，当前为火山原生 VoiceChat 主链文本直发测试。");
  setStatus("Listening", `已向火山原生 VoiceChat 主链发送文本：${text}`, dom.speakText.textContent);
  await dispatchAgentCommand({
    command: COMMAND.EXTERNAL_TEXT_TO_LLM,
    message: text,
    interrupt_mode: INTERRUPT_PRIORITY.HIGH,
  });
}

function mapBriefCode(code) {
  switch (code) {
    case AGENT_BRIEF.LISTENING:
      return ["Listening", "AI 正在聆听用户输入。"];
    case AGENT_BRIEF.THINKING:
      return ["Thinking", "AI 正在识别并等待后端知识编排。"];
    case AGENT_BRIEF.SPEAKING:
      return ["Speaking", "AI 正在播报答案。"];
    case AGENT_BRIEF.INTERRUPTED:
      return ["Interrupted", "当前播报已被用户打断。"];
    case AGENT_BRIEF.FINISHED:
      return ["Idle", "本轮播报结束，等待下一轮提问。"];
    default:
      return ["Idle", "等待新的 RTC 事件。"];
  }
}

async function handleSubtitleEvent(data, source = "unknown") {
  if (!data || !data.text) return;
  const isUser = data.userId === state.bootstrap.rtc.user_id;
  const isAi = data.userId === state.bootstrap.rtc.ai_user_id;
  pushDebugEvent("lastSubtitleEvents", {
    text: data.text,
    userId: data.userId,
    paragraph: Boolean(data.paragraph),
    definite: Boolean(data.definite),
    isUser,
    isAi,
    source,
  });
  setRtcSubtitleDebug({
    source,
    role: isUser ? "user" : isAi ? "ai" : "unknown",
    userId: data.userId,
    text: data.text,
    paragraph: Boolean(data.paragraph),
    definite: Boolean(data.definite),
  });
  if (isUser) {
    if (revenueTurnIsBusy()) {
      if (data.paragraph && data.definite) {
        setStatus("Thinking", "收益链处理中，请先等这一轮结果返回。");
      }
      return;
    }
    const preempt = shouldPreemptToBackend(data.text);
    if (
      preempt.hit &&
      !state.backendPreempt.active &&
      state.currentOwner !== "backend" &&
      !state.interrupting
    ) {
      state.backendPreempt = {
        active: true,
        reason: preempt.reason,
      };
      state.currentOwner = "backend";
      setStatus("Thinking", `已提前切到后端：${preempt.reason}`);
      if (preempt.reason === "pricing-keyword-hit") {
        setPricingState("收益链接管中：pricing-keyword-hit");
      }
      if (canSendInterrupt()) {
        state.interrupting = true;
        try {
          await postJson(`/api/rtc/sessions/${state.sessionId}/interrupt`, { reason: "early-backend-preempt" });
        } finally {
          state.interrupting = false;
        }
      }
    }
    if ((state.uiState === "Greeting" || state.uiState === "Speaking") && !state.interrupting && !revenueTurnIsBusy()) {
      if (canSendInterrupt()) {
        state.interrupting = true;
        try {
          await postJson(`/api/rtc/sessions/${state.sessionId}/interrupt`, { reason: "user-speech" });
        } finally {
          state.interrupting = false;
        }
      }
    }
    if (data.paragraph && data.definite) {
      const paragraphKey = `${data.userId}:${data.text}`;
      if (paragraphKey !== state.lastParagraphKey) {
        state.lastParagraphKey = paragraphKey;
        dom.userSubtitleText.textContent = data.text;
        clearLiveTranscript();
        const source = state.backendPreempt.active ? "rtc-paragraph-preempted" : "rtc-paragraph";
        await submitTurn(data.text, source);
        state.backendPreempt = { active: false, reason: "" };
      }
    } else {
      setLiveTranscript(data.text);
    }
  } else {
    if (shouldRenderAiLiveCaption()) {
      state.liveAiComposite = mergeCaptionChunk(state.liveAiComposite, data.text);
      dom.aiSubtitleText.textContent = state.liveAiComposite;
      dom.speakText.textContent = state.liveAiComposite;
      setLiveTranscript(data.text);
    }
  }
}

function attachRtcListeners(VERTC) {
  const engine = state.rtc.engine;
  engine.on(VERTC.events.onUserJoined, (event) => {
    if (event.userInfo.userId === state.bootstrap.rtc.ai_user_id) {
      updateAvatarStatus("火山 AI 备用视频用户已加入房间，等待是否发布流。");
    }
  });
  engine.on(VERTC.events.onUserPublishStream, (event) => {
    if (event.userId === state.bootstrap.rtc.ai_user_id) {
      updateAvatarStatus("火山备用视频流已发布，可与自研 3D 舞台并行联调。");
      state.rtc.setRemoteVideoPlayer(
        event.userId,
        dom.rtcStreamMount,
        state.rtcModule.VideoRenderMode.RENDER_MODE_HIDDEN
      );
    }
  });
  engine.on(VERTC.events.onUserUnpublishStream, (event) => {
    if (event.userId === state.bootstrap.rtc.ai_user_id) {
      updateAvatarStatus("火山备用视频流已取消，自研 3D 舞台继续保留。");
    }
  });
  bindRtcSubtitleListeners(engine, VERTC);
  engine.on(VERTC.events.onError, (event) => {
    setStatus("Error", `RTC 错误：${event.errorCode || "unknown"}`);
  });
}

async function initRtc() {
  if (state.joined && state.voiceChatStarted) {
    return;
  }
  if (!state.bootstrap.rtc.app_id || !state.bootstrap.rtc.token) {
    setConnection("RTC 参数未配置");
    updateAvatarStatus("当前未提供 AppId / Token，RTC 不会真正进房，但自研 3D 舞台容器仍可调试。");
    return;
  }
  const rtcModule = await import(state.bootstrap.sdk.esm_url);
  const VERTC = rtcModule.default;
  state.rtcModule = rtcModule;
  const engine = VERTC.createEngine(state.bootstrap.rtc.app_id);
  state.rtc = {
    engine,
    room: null,
    setRemoteVideoPlayer(userId, renderDom, renderMode) {
      return engine.setRemoteVideoPlayer(rtcModule.StreamIndex.STREAM_INDEX_MAIN, {
        renderDom,
        userId,
        renderMode,
      });
    },
  };

  attachRtcListeners(VERTC);
  const cameraVisionEnabled = Boolean(state.bootstrap?.voice_chat?.camera_vision_enabled);
  const micReady = await ensureMicrophoneAccess(true, cameraVisionEnabled);
  if (!micReady) {
    setConnection("等待麦克风授权");
    updateAvatarStatus("麦克风权限未就绪，RTC/VoiceChat 未启动。");
    return;
  }
  try {
    await VERTC.enableDevices({ audio: true, video: cameraVisionEnabled });
  } catch (error) {
    setWarning(`麦克风设备启用失败：${String(error)}`);
  }
  if (typeof engine.setAudioCaptureConfig === "function") {
    try {
      await engine.setAudioCaptureConfig({
        noiseSuppression: true,
        echoCancellation: true,
        autoGainControl: true,
      });
      setCallback("回调日志：已按官方建议配置音频采集参数。");
    } catch (error) {
      setWarning(`音频采集参数设置失败：${String(error)}`);
    }
  }
  try {
    await engine.startAudioCapture();
    setCallback("回调日志：本地麦克风采集已启动。");
  } catch (error) {
    setConnection("RTC 连接前校验失败");
    setStatus("Error", `音频采集启动失败：${String(error)}`);
    setWarning(`音频采集未启动，已阻止 VoiceChat 启动，避免云端出现 feed audio slice error：${String(error)}`);
    return;
  }
  if (cameraVisionEnabled && typeof engine.startVideoCapture === "function") {
    try {
      await engine.startVideoCapture();
      setCallback("回调日志：已启动本地摄像头采集，供火山官方视觉链使用。");
    } catch (error) {
      setWarning(`摄像头启动失败，官方视觉链将无法看到实时画面：${String(error)}`);
    }
  }

  const joinedRoom = await engine.joinRoom(
    state.bootstrap.rtc.token,
    state.bootstrap.rtc.room_id,
    {
      userId: state.bootstrap.rtc.user_id,
      extraInfo: JSON.stringify({
        call_scene: "RTC-AIGC",
        user_name: state.bootstrap.rtc.user_id,
        user_id: state.bootstrap.rtc.user_id,
      }),
    },
    {
      isAutoPublish: false,
      isAutoSubscribeAudio: true,
      roomProfileType: rtcModule.RoomProfileType.chat,
    }
  );
  if (joinedRoom && typeof joinedRoom.sendUserBinaryMessage === "function") {
    state.rtc.room = joinedRoom;
  }
  state.joined = true;
  setConnection("RTC 已连接，正在启动 VoiceChat");
  updateAvatarStatus("RTC 已进房，自研 3D 舞台可用，等待 S2S / 备用视频流联调。");
  if (typeof engine.publishStream === "function" && state.rtcModule?.MediaType?.AUDIO) {
    try {
      await engine.publishStream(state.rtcModule.MediaType.AUDIO);
      setCallback("回调日志：已显式发布本地音频流。");
      setWarning("本地麦克风采集与 RTC 音频发布已完成，正在启动 VoiceChat。");
    } catch (error) {
      setWarning(`本地音频流显式发布失败：${String(error)}`);
    }
  }
  if (cameraVisionEnabled && typeof engine.publishStream === "function" && state.rtcModule?.MediaType?.VIDEO) {
    try {
      await engine.publishStream(state.rtcModule.MediaType.VIDEO);
      setCallback("回调日志：已发布本地视频流，供火山官方视觉链使用。");
    } catch (error) {
      setWarning(`本地视频流发布失败，官方视觉链将无法使用实时画面：${String(error)}`);
    }
  }
  await postJson(`/api/rtc/sessions/${state.sessionId}/connected`);
  const startPayload = await postJson(`/api/rtc/sessions/${state.sessionId}/start`, {});
  if (startPayload.started) {
    state.voiceChatStarted = true;
    const effectiveDialogPath =
      startPayload.effective_dialog_path || state.bootstrap.voice_chat.effective_dialog_path || state.bootstrap.voice_chat.primary_dialog_path;
    setConnection(`RTC 已连接 / VoiceChat 已启动 / ${String(effectiveDialogPath).toUpperCase()} 主链`);
    setStatus("Idle", "VoiceChat 已启动，等待迎宾触发。", dom.speakText.textContent);
    if (!state.autoGreetingTriggered) {
      state.autoGreetingTriggered = true;
      window.setTimeout(() => {
        handlePresence().catch((error) => {
          setWarning(`自动迎宾触发失败：${String(error)}`);
        });
      }, 120);
    }
  } else {
    setWarning((startPayload.warnings || []).join(" "));
    setConnection("RTC 已连接 / VoiceChat 未启动");
  }
}

async function submitTurn(userText, source = "manual") {
  if (revenueTurnIsBusy()) {
    setStatus("Thinking", "当前操作还在处理中，请先等这一轮结果返回。");
    setPricingState("收益链处理中，请先等当前操作完成。");
    return;
  }
  const requestId = ++state.activeRequestId;
  dom.userSubtitleText.textContent = userText;
  setStatus("Listening", `正在判断本轮由 S2S 还是后端接管：${userText}`, dom.speakText.textContent);
  try {
    const payload = await postJson(`/api/rtc/sessions/${state.sessionId}/utterances`, {
      user_text: userText,
      source,
    });
    if (requestId !== state.activeRequestId) return;
    setActiveTurn(payload);
    updateInterruptGate(payload.owner === "backend" ? { ...payload, interrupt_gate: "interrupting" } : payload);
    state.currentOwner = payload.owner;
    if (payload.owner === "backend") {
      if (payload.intent === "pricing" || payload.intent === "pricing_confirm") {
        state.revenueTurnPending = true;
        state.revenuePendingTurnId = payload.turn_id ?? null;
      }
      const detail = payload.intent === "pricing" || payload.intent === "pricing_confirm"
        ? `收益链接管：${payload.route_reason}`
        : `后端接管：${payload.route_reason}`;
      if (payload.intent === "pricing" || payload.intent === "pricing_confirm") {
        setPricingState(`收益链接管中：${payload.route_reason}`);
      }
      setStatus("Thinking", detail, payload.transition_text || "");
    } else {
      setStatus("Listening", `火山原生 VoiceChat 主链继续作答：${payload.route_reason}`, dom.speakText.textContent);
    }
    setMetric(
      `链路耗时：utterance ${payload.processing_ms} ms / turn ${payload.turn_id} / owner ${payload.owner} / 阈值 ${payload.transition_after_ms} ms`
    );
    if (
      payload.owner !== "backend" &&
      !["rtc-paragraph", "rtc-paragraph-preempted"].includes(source)
    ) {
      await sendTextToAgent(userText);
    }
  } catch (error) {
    if (requestId !== state.activeRequestId) return;
    state.revenueTurnPending = false;
    state.revenuePendingTurnId = null;
    setStatus("Error", "提交用户话术失败。", String(error));
  }
}

async function handlePresence() {
  const payload = await postJson(`/api/rtc/sessions/${state.sessionId}/presence`, {
    source: "manual-button",
  });
  if (payload.should_greet) {
    setStatus("Greeting", payload.greeting_text, payload.greeting_text);
  }
}

async function handleInterrupt() {
  if (!canSendInterrupt()) {
    setCallback("回调日志：已忽略过于频繁的打断指令。");
    return;
  }
  state.lastParagraphKey = "";
  dom.aiSubtitleText.textContent = "";
  await postJson(`/api/rtc/sessions/${state.sessionId}/interrupt`, {
    reason: "manual-button",
  });
}

async function start() {
  try {
    await loadBootstrap();
    bindSse();
    dom.micBtn.addEventListener("click", async () => {
      const ok = await ensureMicrophoneAccess(true, Boolean(state.bootstrap?.voice_chat?.camera_vision_enabled));
      if (!ok) return;
      if (!state.joined || !state.voiceChatStarted) {
        await initRtc();
      } else {
        setWarning("麦克风权限已刷新，RTC/VoiceChat 已在运行。");
      }
    });
    await initRtc();
    dom.presenceBtn.addEventListener("click", () => {
      handlePresence().catch((error) => setStatus("Error", "迎宾触发失败。", String(error)));
    });
    dom.interruptBtn.addEventListener("click", () => {
      handleInterrupt().catch((error) => setStatus("Error", "打断失败。", String(error)));
    });
    document.querySelectorAll("[data-query]").forEach((button) => {
      button.addEventListener("click", () => {
        submitTurn(button.getAttribute("data-query"), "manual-chip");
      });
    });
    window.hotelLobby = {
      presence: () => handlePresence(),
      interrupt: () => handleInterrupt(),
      submitTurn: (text) => submitTurn(text, "external"),
      sendTextToAgent: (text) => sendTextToAgent(text),
      retryRtc: () => initRtc(),
      debugState: state,
      mountSelfAvatar(node) {
        if (!node || !dom.selfAvatarMount) return;
        dom.selfAvatarMount.replaceChildren(node);
        updateAvatarStatus("已挂载自研 3D 人物组件，RTC 备用层继续可用。");
      },
    };
  } catch (error) {
    setStatus("Error", "页面初始化失败。", String(error));
  }
}

window.addEventListener("beforeunload", () => {
  if (state.eventSource) {
    state.eventSource.close();
  }
  if (state.sessionId) {
    navigator.sendBeacon(
      `/api/rtc/sessions/${state.sessionId}/stop`,
      new Blob([JSON.stringify({})], { type: "application/json" })
    );
  }
});

start();
