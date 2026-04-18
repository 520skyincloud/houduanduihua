const els = {
  scene: document.getElementById("scene"),
  modelStage: document.getElementById("model-stage"),
  particleField: document.getElementById("particle-field"),
  captionStack: document.getElementById("caption-stack"),
  captionLines: [
    document.getElementById("caption-line-0"),
    document.getElementById("caption-line-1"),
    document.getElementById("caption-line-2"),
  ],
  processLabel: document.getElementById("process-label"),
  processMain: document.getElementById("process-main"),
  processDetail: document.getElementById("process-detail"),
  rtcSubtitleDebug: document.getElementById("rtc-subtitle-debug"),
  statusChip: document.getElementById("status-chip"),
  connectionChip: document.getElementById("connection-chip"),
  sessionMeta: document.getElementById("session-meta"),
  warningText: document.getElementById("warning-text"),
  micBtn: document.getElementById("mic-btn"),
  presenceBtn: document.getElementById("presence-btn"),
  interruptBtn: document.getElementById("interrupt-btn"),
  queryButtons: Array.from(document.querySelectorAll("[data-query]")),
};

const AGENT_BRIEF = {
  UNKNOWN: 0,
  LISTENING: 1,
  THINKING: 2,
  SPEAKING: 3,
  INTERRUPTED: 4,
  FINISHED: 5,
};

const INTERRUPT_PRIORITY = {
  NONE: 0,
  HIGH: 1,
  MEDIUM: 2,
  LOW: 3,
};

const COMMAND = {
  INTERRUPT: "interrupt",
  EXTERNAL_TEXT_TO_LLM: "ExternalTextToLLM",
};

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
  "洗衣房",
  "投屏",
  "空调",
  "早餐券",
  "停车场",
];

const VISION_CAPTURE_KEYWORDS = [
  "看看",
  "看下",
  "看一下",
  "看得见我吗",
  "看见我吗",
  "能看见我吗",
  "看得到我吗",
  "看到我吗",
  "能看到我吗",
  "识别",
  "图片",
  "照片",
  "截图",
  "图上",
  "图里",
  "手上拿的",
  "这是什么",
  "写了什么",
  "看到了什么",
  "画面里",
  "摄像头",
];

const EXTERNAL_INFO_PREEMPT_KEYWORDS = [
  "天气",
  "下雨",
  "气温",
  "温度",
  "空气质量",
  "新闻",
  "路况",
  "实时路况",
  "多少号",
  "今天几号",
  "几号",
  "几月几号",
  "几月几日",
  "星期几",
  "礼拜几",
  "周几",
  "现在几点",
  "现在时间",
  "日期",
  "年份",
  "哪一年",
  "什么年份",
];

const PRICING_COMMAND_ALIASES = {
  "收益分析": [
    "生成收益分析",
    "给我生成收益分析",
    "帮我生成收益分析",
    "来个收益分析",
    "来一个收益分析",
    "做个收益分析",
    "来一版收益分析",
    "做一版收益分析",
  ],
  "昨日复盘": [
    "生成昨日复盘",
    "给我生成昨日复盘",
    "帮我生成昨日复盘",
    "来个昨日复盘",
    "来一个昨日复盘",
    "做个昨日复盘",
    "来一版昨日复盘",
    "做一版昨日复盘",
  ],
  "调价方案": [
    "生成调价方案",
    "给我生成调价方案",
    "帮我生成调价方案",
    "来个调价方案",
    "来一个调价方案",
    "来一个调教方案",
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
  /(生成|帮我生成|给我生成|做个|做一版|帮我做个|来个|来一个|来一版).*(收益分析)/,
  /(生成|帮我生成|给我生成|做个|做一版|帮我做个|来个|来一个|来一版).*(昨日复盘)/,
  /(生成|帮我生成|给我生成|做个|做一版|帮我做个|来个|来一个|来一版).*(调价方案)/,
];

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
  committedUserCaption: "",
  committedAiCaption: "",
  liveCaption: "",
  liveCaptionOwner: "",
  liveAiComposite: "",
  latestCommittedTurnId: 0,
  latestCommittedTurnToken: "",
  latestCommittedOwner: "",
  interruptGate: {
    active: false,
    turnId: 0,
    turnToken: "",
    status: "idle",
  },
};

const visualState = {
  targetTiltX: 0,
  targetTiltY: 0,
  targetDriftX: 0,
  targetDriftY: 0,
  tiltX: 0,
  tiltY: 0,
  driftX: 0,
  driftY: 0,
  bob: 0,
  floatX: 0,
  floatRotate: 0,
  energy: 0.32,
};

const processState = {
  label: "runtime.status",
  main: "boot.init",
  detail: "准备建立会话与实时链路",
  steps: [],
};

const siriOrbState = {
  canvas: null,
  context: null,
  width: 0,
  height: 0,
  lastCaptionSignature: "",
  ripples: [],
};

const particles = [];
let particleContext = null;
let particleWidth = 0;
let particleHeight = 0;

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function sanitizeCaptionLine(text) {
  return typeof text === "string" ? text.trim() : "";
}

function hasRenderableCaptionBody(text) {
  return sanitizeCaptionLine(text).replace(/^(访客|小丽)：\s*/u, "").trim().length > 0;
}

function normalizeRouteText(text) {
  return (text || "").replace(/[？?！!，,。.\s]+/g, "").toLowerCase();
}

function currentFaqRouteMode() {
  return state.bootstrap?.voice_chat?.faq_route_mode || "hybrid_risk_split";
}

function pureS2SEnabled() {
  return Boolean(state.bootstrap?.voice_chat?.pure_s2s_enabled);
}

function backendVisionEnabled() {
  return Boolean(state.bootstrap?.voice_chat?.backend_vision_enabled);
}

function looksLikeVisionCaptureRequest(text) {
  const normalized = normalizeRouteText(text);
  if (!normalized) return false;
  return VISION_CAPTURE_KEYWORDS.some((keyword) => normalized.includes(normalizeRouteText(keyword)));
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
  if (looksLikeVisionCaptureRequest(text)) {
    return { hit: true, reason: "vision-keyword-hit" };
  }
  if (EXTERNAL_INFO_PREEMPT_KEYWORDS.some((keyword) => normalized.includes(normalizeRouteText(keyword)))) {
    return { hit: true, reason: "external-info-keyword-hit" };
  }
  if (
    HARD_BACKEND_PREEMPT_KEYWORDS.some((keyword) => normalized.includes(keyword)) ||
    /\d|几点|多少|费用|价格|规则|政策/.test(normalized)
  ) {
    return { hit: true, reason: "hard-backend-rule" };
  }
  return { hit: false, reason: "" };
}

function getCaptionSignature(lines) {
  return (Array.isArray(lines) ? lines : []).map(sanitizeCaptionLine).filter(Boolean).join("|");
}

function setStatusChip(text) {
  if (els.statusChip) els.statusChip.textContent = text;
}

function setConnectionChip(text) {
  if (els.connectionChip) els.connectionChip.textContent = text;
}

function setSessionMeta(text) {
  if (els.sessionMeta) els.sessionMeta.textContent = text;
}

function setWarning(text) {
  if (els.warningText) els.warningText.textContent = text;
}

function setProcessStatus(nextState = {}) {
  processState.label = sanitizeCaptionLine(nextState.label) || processState.label;
  processState.main = sanitizeCaptionLine(nextState.main) || processState.main;
  processState.detail = sanitizeCaptionLine(nextState.detail) || processState.detail;
  if (nextState.pushStep) {
    processState.steps = [sanitizeCaptionLine(nextState.pushStep), ...processState.steps]
      .filter(Boolean)
      .slice(0, 4);
  }
  if (els.processLabel) els.processLabel.textContent = processState.label;
  if (els.processMain) els.processMain.textContent = processState.main;
  if (els.processDetail) {
    const lines = [processState.detail, ...processState.steps].filter(Boolean).slice(0, 4);
    els.processDetail.textContent = lines.join("\n");
    els.processDetail.style.whiteSpace = "pre-line";
  }
}

function setRtcSubtitleDebug(payload = {}) {
  if (!els.rtcSubtitleDebug) return;
  const source = sanitizeCaptionLine(payload.source || "unknown");
  const role = sanitizeCaptionLine(payload.role || "unknown");
  const userId = sanitizeCaptionLine(payload.userId || "-");
  const text = sanitizeCaptionLine(payload.text || "");
  const flags = [payload.paragraph ? "paragraph" : "", payload.definite ? "definite" : ""]
    .filter(Boolean)
    .join("/");
  els.rtcSubtitleDebug.textContent = text
    ? `RTC 字幕调试：${role} · ${source} · ${userId}${flags ? ` · ${flags}` : ""} · ${text}`
    : `RTC 字幕调试：${role} · ${source} · ${userId}${flags ? ` · ${flags}` : ""}`;
}

function toCodeLabel(text, fallback = "runtime.status") {
  const normalized = sanitizeCaptionLine(text)
    .toLowerCase()
    .replace(/[\u4e00-\u9fa5]/g, "")
    .replace(/[^a-z0-9._-]+/g, ".");
  return normalized.replace(/^\.+|\.+$/g, "") || fallback;
}

function formatProcessLine(domain, action, extra = "") {
  return [domain, action, extra].filter(Boolean).join(".");
}

function restartCaptionAnimation(element, animationClass) {
  if (!element) return;
  element.classList.remove("caption-line--fresh", "caption-line--settle");
  void element.offsetWidth;
  element.classList.add(animationClass);
}

function triggerCaptionFreshAnimation(element) {
  restartCaptionAnimation(element, "caption-line--fresh");
}

function triggerCaptionSettleAnimation(element) {
  restartCaptionAnimation(element, "caption-line--settle");
}

function spawnCaptionGhost(sourceElement, { kind = "oldest" } = {}) {
  const currentText = sanitizeCaptionLine(sourceElement?.textContent);
  if (!currentText || !els.captionStack || !sourceElement) return;
  const stackRect = els.captionStack.getBoundingClientRect();
  const lineRect = sourceElement.getBoundingClientRect();
  if (!lineRect.width || !lineRect.height) return;
  const computedStyle = window.getComputedStyle(sourceElement);
  const ghost = document.createElement("p");
  const startOpacity = Number.parseFloat(computedStyle.opacity) || 0.42;
  const isOldest = kind === "oldest";

  if (isOldest) {
    els.captionStack.querySelectorAll(".caption-ghost").forEach((node) => node.remove());
  }

  ghost.className = sourceElement.className;
  ghost.classList.remove("caption-line--fresh", "caption-line--settle");
  ghost.classList.add("caption-ghost");
  ghost.textContent = currentText;
  ghost.style.left = `${lineRect.left - stackRect.left}px`;
  ghost.style.top = `${lineRect.top - stackRect.top}px`;
  ghost.style.width = `${lineRect.width}px`;
  ghost.style.minHeight = `${lineRect.height}px`;
  ghost.style.opacity = `${startOpacity}`;
  ghost.style.filter = computedStyle.filter;
  els.captionStack.appendChild(ghost);

  const animation = ghost.animate(
    isOldest
      ? [
          { opacity: startOpacity, transform: "translateY(0px) scale(1)", filter: computedStyle.filter },
          { offset: 0.22, opacity: Math.min(startOpacity + 0.06, 0.5), transform: "translateY(-1px) scale(0.998)", filter: "blur(0.8px)" },
          { offset: 0.7, opacity: Math.max(startOpacity * 0.34, 0.12), transform: "translateY(-9px) scale(0.988)", filter: "blur(5px)" },
          { opacity: 0, transform: "translateY(-15px) scale(0.978)", filter: "blur(10px)" },
        ]
      : [
          { opacity: startOpacity, transform: "translateY(0px) scale(1)", filter: computedStyle.filter },
          { opacity: 0, transform: "translateY(-8px) scale(0.986)", filter: "blur(8px)" },
        ],
    {
      duration: isOldest ? 2200 : 1000,
      easing: isOldest ? "cubic-bezier(0.16, 0.74, 0.2, 1)" : "cubic-bezier(0.18, 0.74, 0.2, 1)",
      fill: "forwards",
    }
  );

  animation.onfinish = () => ghost.remove();
}

function triggerSiriOrbPulse(text = "") {
  const normalized = sanitizeCaptionLine(text);
  if (!normalized) return;
  siriOrbState.ripples.push({ bornAt: performance.now(), strength: 0.7 });
  if (siriOrbState.ripples.length > 6) {
    siriOrbState.ripples.shift();
  }
}

function getRenderedCaptionLines() {
  const aiLine = state.liveCaptionOwner === "ai" && state.liveCaption ? state.liveCaption : state.committedAiCaption;
  return [
    "",
    aiLine,
    "",
  ];
}

function renderCaptions({ animateLatest = true } = {}) {
  const paddedLines = getRenderedCaptionLines();
  let latestCaptionChanged = false;
  let latestCaptionText = "";

  els.captionLines.forEach((element, index) => {
    if (!element) return;
    const previousText = sanitizeCaptionLine(element.textContent);
    const nextText = paddedLines[index] || "";
    if (previousText && previousText !== nextText && index === 1) {
      spawnCaptionGhost(element, { kind: "oldest" });
    }
    element.textContent = nextText;
    if (!nextText) {
      element.classList.remove("caption-line--fresh", "caption-line--settle");
      return;
    }
    if (animateLatest && previousText !== nextText) {
      if (index === 1) {
        latestCaptionChanged = true;
        latestCaptionText = nextText;
        triggerCaptionFreshAnimation(element);
      } else {
        triggerCaptionSettleAnimation(element);
      }
    } else {
      element.classList.remove("caption-line--fresh", "caption-line--settle");
    }
    if (index === 1) {
      element.classList.toggle("caption-line--speaking", Boolean(nextText));
    }
  });

  els.captionStack?.classList.toggle("caption-stack--active", Boolean(paddedLines[1]));

  const nextSignature = getCaptionSignature(paddedLines);
  if (animateLatest && latestCaptionChanged && nextSignature !== siriOrbState.lastCaptionSignature) {
    siriOrbState.lastCaptionSignature = nextSignature;
    triggerSiriOrbPulse(latestCaptionText);
  } else if (!animateLatest) {
    siriOrbState.lastCaptionSignature = nextSignature;
  }
}

function setLiveCaption(text, owner = "ai") {
  const normalized = sanitizeCaptionLine(text);
  if (!normalized) {
    state.liveCaption = "";
    state.liveCaptionOwner = "";
    renderCaptions({ animateLatest: false });
    return;
  }
  if (normalized === state.committedUserCaption || normalized === state.committedAiCaption) {
    state.liveCaption = "";
    state.liveCaptionOwner = "";
    renderCaptions({ animateLatest: false });
    return;
  }
  state.liveCaption = hasRenderableCaptionBody(normalized) ? normalized : "";
  state.liveCaptionOwner = state.liveCaption ? owner : "";
  renderCaptions({ animateLatest: true });
}

function clearLiveCaption() {
  state.liveCaption = "";
  state.liveCaptionOwner = "";
  state.liveAiComposite = "";
  renderCaptions({ animateLatest: false });
}

function mergeCaptionChunk(previousText = "", nextText = "") {
  const prev = sanitizeCaptionLine(previousText);
  const next = sanitizeCaptionLine(nextText);
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

function commitCaption(text, options = {}) {
  const normalized = sanitizeCaptionLine(text);
  if (!normalized || !hasRenderableCaptionBody(normalized)) return;
  const speaker = options.owner === "user" || options.speaker === "user" ? "user" : "ai";
  if (options.turnId && options.turnId < state.latestCommittedTurnId) {
    return;
  }
  if (options.turnId) {
    state.latestCommittedTurnId = options.turnId;
  }
  if (options.turnToken) {
    state.latestCommittedTurnToken = options.turnToken;
  }
  if (options.owner) {
    state.latestCommittedOwner = options.owner;
  }
  const targetKey = speaker === "user" ? "committedUserCaption" : "committedAiCaption";
  if (state[targetKey] === normalized) {
    state.liveCaption = "";
    renderCaptions({ animateLatest: false });
    return;
  }
  state[targetKey] = normalized;
  state.liveCaption = "";
  renderCaptions({ animateLatest: true });
}

function clearCaptions() {
  state.committedUserCaption = "";
  state.committedAiCaption = "";
  state.liveCaption = "";
  state.latestCommittedTurnId = 0;
  state.latestCommittedTurnToken = "";
  state.latestCommittedOwner = "";
  renderCaptions({ animateLatest: false });
}

function beginCommittedUserTurn(text, options = {}) {
  state.committedAiCaption = "";
  state.committedUserCaption = "";
  state.liveAiComposite = "";
  if (state.liveCaptionOwner === "ai") {
    state.liveCaption = "";
    state.liveCaptionOwner = "";
  }
  commitCaption(text, {
    ...options,
    owner: "user",
    speaker: "user",
  });
}

function setActiveTurn(payload = {}) {
  const turnId = Number(payload.turn_id || 0);
  const turnToken = sanitizeCaptionLine(payload.turn_token || "");
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

function isCurrentTurnPayload(payload = {}, { allowLiveWithoutToken = false } = {}) {
  const turnId = Number(payload.turn_id || 0);
  const turnToken = sanitizeCaptionLine(payload.turn_token || "");
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

function shouldRenderAiLiveCaption() {
  return !state.interruptGate.active;
}

function shouldAcceptAiFinalSubtitle(payload = {}) {
  const turnId = Number(payload.turn_id || 0);
  if (!turnId) return true;
  if (payload.owner === "backend") return true;
  return state.activeTurnOwner !== "backend";
}

function updateInterruptGate(payload = {}) {
  const status = sanitizeCaptionLine(payload.interrupt_gate || "");
  if (!status) return;
  if (status === "interrupting" || status === "waiting_interrupt_ack") {
    state.interruptGate = {
      active: true,
      turnId: Number(payload.turn_id || state.activeTurnId || 0),
      turnToken: sanitizeCaptionLine(payload.turn_token || state.activeTurnToken || ""),
      status,
    };
    return;
  }
  state.interruptGate = {
    active: false,
    turnId: 0,
    turnToken: "",
    status,
  };
}

function buildHotelMissText() {
  return "这个我这边暂时没查到准确信息，您也可以直接联系前台确认一下。";
}

function initSiriOrb() {
  if (!els.modelStage) return;
  const orb = document.createElement("div");
  orb.className = "siri-orb";
  orb.setAttribute("aria-hidden", "true");
  const haloOuter = document.createElement("div");
  haloOuter.className = "siri-orb__halo siri-orb__halo--outer";
  const haloInner = document.createElement("div");
  haloInner.className = "siri-orb__halo siri-orb__halo--inner";
  const shell = document.createElement("div");
  shell.className = "siri-orb__shell";
  const core = document.createElement("div");
  core.className = "siri-orb__core";
  const specular = document.createElement("div");
  specular.className = "siri-orb__specular";
  const canvas = document.createElement("canvas");
  canvas.className = "siri-orb-canvas";
  orb.append(haloOuter, haloInner, shell, core, specular, canvas);
  els.modelStage.replaceChildren(orb);
  siriOrbState.canvas = canvas;
  siriOrbState.context = canvas.getContext("2d");

  const resize = () => {
    if (!siriOrbState.canvas || !els.modelStage) return;
    const width = Math.max(1, els.modelStage.clientWidth);
    const height = Math.max(1, els.modelStage.clientHeight);
    const pixelRatio = Math.min(window.devicePixelRatio || 1, 2);
    siriOrbState.width = width;
    siriOrbState.height = height;
    siriOrbState.canvas.width = Math.round(width * pixelRatio);
    siriOrbState.canvas.height = Math.round(height * pixelRatio);
    siriOrbState.canvas.style.width = `${width}px`;
    siriOrbState.canvas.style.height = `${height}px`;
    if (siriOrbState.context) {
      siriOrbState.context.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
    }
  };

  resize();
  if ("ResizeObserver" in window) {
    new ResizeObserver(() => resize()).observe(els.modelStage);
  } else {
    window.addEventListener("resize", resize);
  }
}

function drawOrganicBlob(context, cx, cy, radius, options = {}) {
  const { wobble = 0.06, angleOffset = 0, phase = 0, lobes = 6, driftX = 1, driftY = 1 } = options;
  const steps = 40;
  context.beginPath();
  for (let index = 0; index <= steps; index += 1) {
    const t = (index / steps) * Math.PI * 2;
    const waveA = Math.sin(t * lobes + phase) * wobble;
    const waveB = Math.cos(t * (lobes - 1) - phase * 0.7) * wobble * 0.46;
    const irregularRadius = radius * (1 + waveA + waveB);
    const x = cx + Math.cos(t + angleOffset) * irregularRadius * driftX;
    const y = cy + Math.sin(t + angleOffset) * irregularRadius * driftY;
    if (index === 0) context.moveTo(x, y);
    else context.lineTo(x, y);
  }
  context.closePath();
}

function drawSiriOrb(time) {
  const context = siriOrbState.context;
  if (!context || !siriOrbState.width || !siriOrbState.height) return;
  const width = siriOrbState.width;
  const height = siriOrbState.height;
  const cx = width * 0.5;
  const cy = height * 0.49;
  const baseRadius = Math.min(width, height) * 0.06;
  const ripples = siriOrbState.ripples.filter((ripple) => time - ripple.bornAt < 2200);
  siriOrbState.ripples = ripples;
  const rippleBoost = ripples.reduce((acc, ripple) => {
    const progress = clamp((time - ripple.bornAt) / 1200, 0, 1);
    return acc + ripple.strength * (1 - progress);
  }, 0);
  const radius = baseRadius * (1 + rippleBoost * 0.05);
  const auraRadius = radius * 1.28;
  context.clearRect(0, 0, width, height);

  const backdrop = context.createRadialGradient(cx, cy, radius * 0.08, cx, cy, auraRadius * 1.4);
  backdrop.addColorStop(0, "rgba(255,255,255,0.34)");
  backdrop.addColorStop(0.24, "rgba(215,248,255,0.2)");
  backdrop.addColorStop(0.46, "rgba(151,224,255,0.14)");
  backdrop.addColorStop(0.72, "rgba(233,149,210,0.08)");
  backdrop.addColorStop(1, "rgba(255,255,255,0)");
  context.fillStyle = backdrop;
  drawOrganicBlob(context, cx, cy, auraRadius * 1.08, { wobble: 0, phase: 0, lobes: 6 });
  context.fill();

  context.save();
  drawOrganicBlob(context, cx, cy, radius, { wobble: 0, phase: 0, lobes: 6 });
  context.clip();
  const shell = context.createRadialGradient(cx - radius * 0.18, cy - radius * 0.28, radius * 0.12, cx, cy, radius);
  shell.addColorStop(0, "rgba(255,255,255,0.98)");
  shell.addColorStop(0.18, "rgba(215,252,255,0.92)");
  shell.addColorStop(0.42, "rgba(120,201,255,0.44)");
  shell.addColorStop(0.68, "rgba(198,146,255,0.24)");
  shell.addColorStop(0.84, "rgba(247,168,212,0.22)");
  shell.addColorStop(1, "rgba(255,255,255,0.04)");
  context.fillStyle = shell;
  drawOrganicBlob(context, cx, cy, radius * 0.98, { wobble: 0, phase: 0, lobes: 6 });
  context.fill();

  const coreGradient = context.createRadialGradient(cx - radius * 0.12, cy - radius * 0.16, radius * 0.02, cx, cy, radius * 0.52);
  coreGradient.addColorStop(0, "rgba(255,255,255,0.98)");
  coreGradient.addColorStop(0.26, "rgba(230,247,255,0.86)");
  coreGradient.addColorStop(0.58, "rgba(170,224,255,0.34)");
  coreGradient.addColorStop(1, "rgba(255,255,255,0)");
  context.fillStyle = coreGradient;
  drawOrganicBlob(context, cx, cy, radius * 0.42, { wobble: 0, phase: 0, lobes: 5 });
  context.fill();
  context.restore();
}

function resizeParticleField() {
  if (!els.particleField) return;
  const { devicePixelRatio = 1 } = window;
  particleWidth = window.innerWidth;
  particleHeight = window.innerHeight;
  els.particleField.width = Math.round(particleWidth * devicePixelRatio);
  els.particleField.height = Math.round(particleHeight * devicePixelRatio);
  els.particleField.style.width = `${particleWidth}px`;
  els.particleField.style.height = `${particleHeight}px`;
  particleContext = els.particleField.getContext("2d");
  if (particleContext) {
    particleContext.setTransform(devicePixelRatio, 0, 0, devicePixelRatio, 0, 0);
  }
}

function seedParticles() {
  particles.length = 0;
  const count = Math.max(70, Math.round(window.innerWidth / 20));
  for (let index = 0; index < count; index += 1) {
    particles.push({
      x: Math.random() * particleWidth,
      y: Math.random() * particleHeight,
      radius: 0.8 + Math.random() * 3.8,
      drift: 0.2 + Math.random() * 0.7,
      sway: 0.3 + Math.random() * 1.2,
      alpha: 0.08 + Math.random() * 0.34,
      hue: Math.random() > 0.5 ? "cyan" : "pink",
      phase: Math.random() * Math.PI * 2,
      offset: Math.random() * Math.PI * 2,
      trail: 8 + Math.random() * 22,
    });
  }
}

function drawCenterGlow(time) {
  if (!particleContext) return;
  const cx = particleWidth * 0.5;
  const cy = particleHeight * 0.46;
  const pulse = 0.92 + Math.sin(time * 0.0015) * 0.06;
  const radius = Math.min(particleWidth, particleHeight) * 0.22 * pulse;
  const gradient = particleContext.createRadialGradient(cx, cy, radius * 0.14, cx, cy, radius);
  gradient.addColorStop(0, "rgba(255,255,255,0.34)");
  gradient.addColorStop(0.42, "rgba(247,214,232,0.14)");
  gradient.addColorStop(0.72, "rgba(194,239,248,0.12)");
  gradient.addColorStop(1, "rgba(255,255,255,0)");
  particleContext.fillStyle = gradient;
  particleContext.beginPath();
  particleContext.arc(cx, cy, radius, 0, Math.PI * 2);
  particleContext.fill();
}

function drawParticles(time) {
  if (!particleContext) return;
  particleContext.clearRect(0, 0, particleWidth, particleHeight);
  drawCenterGlow(time);
  particles.forEach((particle) => {
    particle.y -= particle.drift * 0.45;
    particle.x += Math.sin(time * 0.0007 * particle.sway + particle.offset) * 0.28;
    if (particle.y < -40) {
      particle.y = particleHeight + 40;
      particle.x = Math.random() * particleWidth;
    }
    const pulse = (Math.sin(time * 0.002 + particle.phase) + 1) * 0.5;
    const radius = particle.radius + pulse * 2.4;
    const alpha = particle.alpha * (0.66 + pulse * 0.72);
    const color = particle.hue === "cyan" ? `rgba(99, 202, 223, ${alpha.toFixed(3)})` : `rgba(235, 159, 199, ${alpha.toFixed(3)})`;
    particleContext.beginPath();
    particleContext.strokeStyle = color;
    particleContext.lineWidth = Math.max(0.8, radius * 0.34);
    particleContext.globalAlpha = alpha * 0.74;
    particleContext.moveTo(particle.x, particle.y);
    particleContext.lineTo(particle.x, particle.y + particle.trail);
    particleContext.stroke();
    particleContext.beginPath();
    particleContext.fillStyle = color;
    particleContext.shadowBlur = 18;
    particleContext.shadowColor = color;
    particleContext.globalAlpha = 1;
    particleContext.arc(particle.x, particle.y, radius, 0, Math.PI * 2);
    particleContext.fill();
  });
  particleContext.shadowBlur = 0;
  particleContext.globalAlpha = 1;
}

function bindPointer() {
  if (!els.scene) return;
  els.scene.addEventListener("pointermove", (event) => {
    const rect = els.scene.getBoundingClientRect();
    const x = (event.clientX - rect.left) / rect.width;
    const y = (event.clientY - rect.top) / rect.height;
    const nx = x * 2 - 1;
    const ny = y * 2 - 1;
    visualState.targetTiltY = clamp(nx * 18, -18, 18);
    visualState.targetTiltX = clamp(-ny * 12, -12, 12);
    visualState.targetDriftX = clamp(nx * 26, -26, 26);
    visualState.targetDriftY = clamp(ny * 18, -18, 18);
  });
  els.scene.addEventListener("pointerleave", () => {
    visualState.targetTiltX = 0;
    visualState.targetTiltY = 0;
    visualState.targetDriftX = 0;
    visualState.targetDriftY = 0;
  });
}

function animate(time) {
  visualState.tiltX += (visualState.targetTiltX - visualState.tiltX) * 0.09;
  visualState.tiltY += (visualState.targetTiltY - visualState.tiltY) * 0.09;
  visualState.driftX += (visualState.targetDriftX - visualState.driftX) * 0.1;
  visualState.driftY += (visualState.targetDriftY - visualState.driftY) * 0.1;
  const ambientTiltX = Math.cos(time * 0.0011) * 2.6;
  const ambientTiltY = Math.sin(time * 0.0014) * 4.2;
  visualState.bob = Math.sin(time * 0.002) * 18 + Math.cos(time * 0.0012) * 7;
  visualState.floatX = Math.sin(time * 0.0014) * 16;
  visualState.floatRotate = Math.sin(time * 0.0015) * 1.6;
  document.documentElement.style.setProperty("--tilt-x", `${(visualState.tiltX + ambientTiltX).toFixed(2)}deg`);
  document.documentElement.style.setProperty("--tilt-y", `${(visualState.tiltY + ambientTiltY).toFixed(2)}deg`);
  document.documentElement.style.setProperty("--drift-x", `${visualState.driftX.toFixed(2)}px`);
  document.documentElement.style.setProperty("--drift-y", `${visualState.driftY.toFixed(2)}px`);
  document.documentElement.style.setProperty("--bob-y", `${visualState.bob.toFixed(2)}px`);
  document.documentElement.style.setProperty("--float-x", `${visualState.floatX.toFixed(2)}px`);
  document.documentElement.style.setProperty("--float-rotate", `${visualState.floatRotate.toFixed(2)}deg`);
  drawParticles(time);
  drawSiriOrb(time);
  window.requestAnimationFrame(animate);
}

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
      setProcessStatus({
        label: "pipeline.idle",
        main: "pricing.idle",
        detail: "awaiting next pricing command",
      });
    }
  }, holdMs);
}

function canSendInterrupt() {
  const now = Date.now();
  if (now - state.lastInterruptAt < 800) {
    return false;
  }
  state.lastInterruptAt = now;
  return true;
}

async function readMicrophonePermissionState() {
  if (!navigator.permissions?.query) return "unknown";
  try {
    const status = await navigator.permissions.query({ name: "microphone" });
    return status.state || "unknown";
  } catch {
    return "unknown";
  }
}

async function readCameraPermissionState() {
  if (!navigator.permissions?.query) return "unknown";
  try {
    const status = await navigator.permissions.query({ name: "camera" });
    return status.state || "unknown";
  } catch {
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
        ? "浏览器已拒绝摄像头或麦克风权限，请在站点设置中改成允许后，再点重新授权。"
        : "浏览器已拒绝麦克风权限，请在站点设置中改成允许后，再点重新授权。"
    );
    return false;
  }
  if (!interactive) {
    setWarning(includeVideo ? "摄像头或麦克风权限尚未确认，请点重新授权。" : "麦克风权限尚未确认，请点重新授权麦克风。");
    return false;
  }
  if (!navigator.mediaDevices?.getUserMedia) {
    setWarning(includeVideo ? "当前浏览器不支持音视频采集。" : "当前浏览器不支持麦克风采集。");
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
    setStatus("Error", `麦克风授权失败：${String(error)}`);
    return false;
  }
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
  const length = (lengthBuffer[0] << 24) | (lengthBuffer[1] << 16) | (lengthBuffer[2] << 8) | lengthBuffer[3];
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
  if (header !== "subv") {
    throw new Error(`unexpected subtitle header: ${header}`);
  }
  const length = (bytes[4] << 24) | (bytes[5] << 16) | (bytes[6] << 8) | bytes[7];
  const payloadBytes = bytes.subarray(8, 8 + length);
  return JSON.parse(new TextDecoder().decode(payloadBytes));
}

async function consumeSubtitlePayload(parsed, source) {
  const entries = Array.isArray(parsed?.data) ? parsed.data : [];
  setProcessStatus({
    label: "rtc.subtitle",
    main: `subtitle.${source}`,
    detail: `received ${entries.length} subtitle chunk(s)`,
    pushStep: `rtc.${source} -> subv`,
  });
  for (const item of entries) {
    await handleSubtitleEvent(item || {}, source);
  }
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

async function postForm(url, formData) {
  const response = await fetch(url, {
    method: "POST",
    body: formData,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`${response.status}: ${text}`);
  }
  return response.json();
}

async function captureCameraFrameFile() {
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new Error("当前浏览器不支持摄像头图像采集。");
  }
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: false,
    video: {
      facingMode: "user",
      width: { ideal: 1280 },
      height: { ideal: 720 },
    },
  });
  const video = document.createElement("video");
  video.playsInline = true;
  video.muted = true;
  video.srcObject = stream;
  try {
    await new Promise((resolve, reject) => {
      video.onloadedmetadata = () => resolve();
      video.onerror = () => reject(new Error("摄像头画面初始化失败。"));
    });
    await video.play().catch(() => {});
    await new Promise((resolve) => window.setTimeout(resolve, 180));
    const width = video.videoWidth || 1280;
    const height = video.videoHeight || 720;
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const context = canvas.getContext("2d");
    if (!context) {
      throw new Error("摄像头画面渲染上下文不可用。");
    }
    context.drawImage(video, 0, 0, width, height);
    const blob = await new Promise((resolve, reject) => {
      canvas.toBlob((value) => (value ? resolve(value) : reject(new Error("摄像头图像导出失败。"))), "image/jpeg", 0.9);
    });
    return new File([blob], "camera-frame.jpg", { type: "image/jpeg" });
  } finally {
    stream.getTracks().forEach((track) => track.stop());
    video.srcObject = null;
  }
}

function setStatus(label, detail = "") {
  state.uiState = label;
  setStatusChip(label);
  setProcessStatus({
    label: "voice.state",
    main: formatProcessLine("voice", String(label || "idle").toLowerCase()),
    detail: detail || "等待新的语音事件",
  });
}

function mapBriefCode(code) {
  switch (code) {
    case AGENT_BRIEF.LISTENING:
      return ["Listening", "AI 正在聆听用户输入。"];
    case AGENT_BRIEF.THINKING:
      return ["Thinking", "AI 正在整理问题并等待链路处理。"];
    case AGENT_BRIEF.SPEAKING:
      return ["Speaking", "AI 正在播报答案。"];
    case AGENT_BRIEF.INTERRUPTED:
      return ["Interrupted", "当前播报已被打断。"];
    case AGENT_BRIEF.FINISHED:
      return ["Idle", "本轮播报结束，等待下一轮提问。"];
    default:
      return ["Idle", "等待新的 RTC 事件。"];
  }
}

function processRouteDetail(intent, reason) {
  if (intent === "pricing" || intent === "pricing_confirm") {
    return `route=pricing · ${reason || "pricing-route"}`;
  }
  if (intent === "faq") {
    return `route=hotel_knowledge · ${reason || "faq-route"}`;
  }
  return reason || "waiting-route-response";
}

function summarizeTurnResult(payload) {
  const source = payload?.metadata?.source || "backend";
  if (payload.action_state && payload.action_state !== "none") {
    return `action=${payload.action_state} · ${payload.processing_ms} ms`;
  }
  if (source === "fastgpt") {
    return `source=fastgpt · ${payload.processing_ms} ms`;
  }
  if (source === "memory") {
    return `source=memory · ${payload.processing_ms} ms`;
  }
  if (source === "ragflow") {
    return `source=ragflow · ${payload.processing_ms} ms`;
  }
  return `source=${source} · ${payload.processing_ms} ms`;
}

function describeRouteAsRuntime(intent, reason) {
  if (intent === "pricing" || intent === "pricing_confirm") {
    return `POST /api/rtc/.../utterances -> pricing.route (${reason || "pricing-route"})`;
  }
  if (intent === "faq") {
    return `POST /api/rtc/.../utterances -> hotel.query (${reason || "hotel-knowledge"})`;
  }
  return `POST /api/rtc/.../utterances -> ${reason || "route.pending"}`;
}

function describeToolExecution(payload) {
  const source = payload?.metadata?.source || "";
  const action = payload?.action_state || "";
  if (source === "fastgpt") {
    return "POST /api/core/dataset/searchTest -> fastgpt.hit";
  }
  if (action === "pricing_preview") {
    return "tool.generate_current_pricing_strategy() -> preview.ready";
  }
  if (action === "pricing_executed") {
    return "tool.run_pms_reprice() -> execution.applied";
  }
  if (action === "pricing_confirm_pending") {
    return "tool.generate_current_pricing_strategy() -> pending.confirm";
  }
  if (action === "pricing_rejected") {
    return "pricing.guard -> rejected";
  }
  return `turn.result -> ${source || action || "backend"}`;
}

function describeCallbackStep(payload) {
  if (payload.callback_type === "agent_command_ack") {
    return `${payload.command || "agent.command"} -> ack.${payload.ok ? "ok" : "error"}`;
  }
  return `callback.${payload.callback_type || "event"} -> received`;
}

function describeVoiceChatStep(payload) {
  if (payload.action === "start") {
    return "voicechat.start() -> runtime.online";
  }
  if (payload.action === "stop") {
    return "voicechat.stop() -> runtime.offline";
  }
  return `voicechat.${payload.action || "event"}`;
}

async function loadBootstrap() {
  state.bootstrap = await postJson("/api/bootstrap", {
    client_id: "stage-screen",
    transport: "volcengine-rtc",
  });
  state.sessionId = state.bootstrap.session_id;
  setSessionMeta(`Session ${state.sessionId} · 房间 ${state.bootstrap.rtc.room_id} · FAQ ${state.bootstrap.voice_chat.faq_route_mode}`);
  if (state.bootstrap.warnings.length) {
    setWarning(state.bootstrap.warnings.join(" "));
  } else {
    setWarning("RTC、VoiceChat 与后端知识链已就绪。");
  }
  setProcessStatus({
    label: "runtime.bootstrap",
    main: "bootstrap.ready",
    detail: `session=${state.sessionId} · ${state.bootstrap.processing_ms} ms`,
    pushStep: "POST /api/bootstrap -> 200 ready",
  });
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
    setProcessStatus({
      label: "stream.events",
      main: "sse.reconnecting",
      detail: "event stream dropped · retrying",
      pushStep: `GET /api/rtc/sessions/${state.sessionId}/events -> retry`,
    });
  };
}

function handleServerEvent(packet) {
  const { kind, payload } = packet;
  if (kind === "state") {
    setActiveTurn(payload);
    updateInterruptGate(payload);
    if (!isCurrentTurnPayload(payload, { allowLiveWithoutToken: true }) && payload.state !== "interrupted") {
      return;
    }
    const label = payload.state || "Idle";
    if (payload.state === "interrupted") {
      state.lastParagraphKey = "";
      state.backendPreempt = { active: false, reason: "" };
      clearRevenueBusyLatch();
      clearLiveCaption();
    }
    const detail = payload.detail || (payload.state === "error" ? buildHotelMissText() : "等待新的 RTC 事件。");
    setStatus(label.charAt(0).toUpperCase() + label.slice(1), detail);
    return;
  }
  if (kind === "connection") {
    setConnectionChip(
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
      setStatus("Greeting", "检测到来宾进入展厅区域。");
    }
    return;
  }
  if (kind === "subtitle") {
    if (!isCurrentTurnPayload(payload, { allowLiveWithoutToken: payload.kind !== "final" })) {
      return;
    }
    const text = sanitizeCaptionLine(payload.text);
    const speaker = payload.speaker === "user" ? "user" : "ai";
    if (!text) {
      return;
    }
    if (speaker === "user") {
      if (payload.kind === "final") {
      commitCaption(text, {
          turnId: Number(payload.turn_id || 0),
          turnToken: payload.turn_token,
          owner: "user",
          speaker: "user",
        });
      } else {
        if (hasRenderableCaptionBody(text)) {
          setLiveCaption(text, "user");
        }
      }
      return;
    }
    if (payload.kind === "final") {
      if (!shouldAcceptAiFinalSubtitle(payload)) {
        return;
      }
      state.liveAiComposite = "";
      commitCaption(text, {
        turnId: Number(payload.turn_id || 0),
        turnToken: payload.turn_token,
        owner: payload.owner || "backend",
        speaker: "ai",
      });
      return;
    }
    if (hasRenderableCaptionBody(text) && shouldRenderAiLiveCaption()) {
      setLiveCaption(text, "ai");
    }
    return;
  }
  if (kind === "turn_result") {
    setActiveTurn(payload);
    updateInterruptGate(payload);
    if (!isCurrentTurnPayload(payload)) {
      return;
    }
    state.backendPreempt = { active: false, reason: "" };
    if (state.revenueTurnPending && payload.turn_id === state.revenuePendingTurnId) {
      state.revenueTurnPending = false;
      state.revenuePendingTurnId = null;
      holdRevenueBusyForSpeak(payload.speak_text || payload.display_text || "");
    }
    const spokenText = sanitizeCaptionLine(payload.speak_text) || sanitizeCaptionLine(payload.display_text);
    if (spokenText) {
      commitCaption(spokenText, {
        turnId: Number(payload.turn_id || 0),
        turnToken: payload.turn_token,
        owner: payload.owner || "backend",
        speaker: "ai",
      });
    }
    setProcessStatus({
      label: payload.action_state && payload.action_state !== "none" ? "pipeline.pricing" : "pipeline.answer",
      main: formatProcessLine("turn", payload.state || payload.metadata?.source || "result"),
      detail: summarizeTurnResult(payload),
      pushStep: describeToolExecution(payload),
    });
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
    }
    setProcessStatus({
      label: "pipeline.dispatch",
      main: formatProcessLine(payload.owner || "backend", payload.intent || "unknown"),
      detail: processRouteDetail(payload.intent, payload.route_reason),
      pushStep: describeRouteAsRuntime(payload.intent, payload.route_reason),
    });
    return;
  }
  if (kind === "callback") {
    if (!payload.applies_to_current_turn && payload.callback_type !== "agent_command_ack") {
      return;
    }
    if (payload.callback_type === "agent_command_ack" && payload.command === "interrupt" && payload.applies_to_current_turn) {
      updateInterruptGate({ ...payload, interrupt_gate: payload.ok ? "acked" : "ack_error" });
    }
    if (payload.callback_type === "agent_command_ack") {
      setProcessStatus({
        label: "callback.agent",
        main: toCodeLabel(payload.command || "agent_command_ack", "agent.command"),
        detail: `${payload.ok ? "ack=ok" : "ack=error"} · ${payload.detail || "no-detail"}`,
        pushStep: describeCallbackStep(payload),
      });
    } else {
      setProcessStatus({
        label: "callback.event",
        main: toCodeLabel(payload.callback_type || "callback", "callback.event"),
        detail: "backend callback received",
        pushStep: describeCallbackStep(payload),
      });
    }
    return;
  }
  if (kind === "voice_chat") {
    setProcessStatus({
      label: "voicechat.runtime",
      main: payload.action === "start" ? "voicechat.started" : "voicechat.stopped",
      detail: payload.action === "start" ? "voice engine online" : "voice engine offline",
      pushStep: describeVoiceChatStep(payload),
    });
  }
}

async function dispatchAgentCommand(payload) {
  if (!state.rtc || !state.bootstrap) return;
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
  const args = [state.bootstrap.rtc.ai_user_id, stringToTlv(message, "ctrl")];
  if (reliableOrdered !== undefined) {
    args.push(reliableOrdered);
  }
  await sender.sendUserBinaryMessage(...args);
  await postJson(`/api/rtc/sessions/${state.sessionId}/agent-command-acks`, {
    command: payload.command,
    ok: true,
    detail: `sent via ${sender === state.rtc.room ? "room" : "engine"}`,
    turn_id: payload.turn_id ?? null,
    turn_token: payload.turn_token ?? null,
  });
}

async function sendTextToAgent(text) {
  if (!text || !text.trim()) return;
  if (!state.rtc || !state.voiceChatStarted) {
    throw new Error("RTC / VoiceChat 尚未就绪。");
  }
  beginCommittedUserTurn(text);
  setProcessStatus({
    label: "pipeline.native",
    main: "native.text",
    detail: `text forwarded · ${text}`,
    pushStep: "rtc.binary.send(ctrl) -> ExternalTextToLLM",
  });
  await dispatchAgentCommand({
    command: COMMAND.EXTERNAL_TEXT_TO_LLM,
    message: text,
    interrupt_mode: INTERRUPT_PRIORITY.HIGH,
  });
}

async function submitVisionTurn(question, source = "manual") {
  beginCommittedUserTurn(question, { source });
  setProcessStatus({
    label: "vision.capture",
    main: "vision.capture.pending",
    detail: "正在抓取摄像头当前画面并发送后端视觉链",
    pushStep: "camera.frame -> pending",
  });
  if (canSendInterrupt()) {
    await postJson(`/api/rtc/sessions/${state.sessionId}/interrupt`, {
      reason: "vision-camera-frame",
    }).catch(() => {});
  }
  const frame = await captureCameraFrameFile();
  const form = new FormData();
  form.append("file", frame, frame.name);
  form.append("question", question);
  const payload = await postForm(`/api/rtc/sessions/${state.sessionId}/vision-turn`, form);
  state.currentOwner = "backend";
  state.activeTurnOwner = "backend";
  clearLiveCaption();
  const spokenText = sanitizeCaptionLine(payload?.result?.speak_text || payload?.result?.display_text || "");
  if (spokenText) {
    commitCaption(spokenText, {
      speaker: "ai",
      source: "vision-camera-frame",
      final: true,
    });
  }
  setProcessStatus({
    label: "vision.backend",
    main: "vision.frame.done",
    detail: payload?.needs_fact_resolution ? "已完成看图并补充酒店事实判断" : "已完成摄像头画面识别",
    pushStep: "POST /api/rtc/.../vision-turn -> ok",
  });
  return payload;
}

async function handleSubtitleEvent(data, source = "unknown") {
  if (!data || !data.text) return;
  const isUser = data.userId === state.bootstrap.rtc.user_id;
  const isAi = data.userId === state.bootstrap.rtc.ai_user_id;
  setRtcSubtitleDebug({
    source,
    role: isUser ? "user" : isAi ? "ai" : "unknown",
    userId: data.userId,
    text: data.text,
    paragraph: Boolean(data.paragraph),
    definite: Boolean(data.definite),
  });
  if (isUser) {
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
      setProcessStatus({
        label: "pipeline.backend",
        main: "backend.preempt",
        detail: `early handoff · ${preempt.reason}`,
        pushStep: "subtitle.partial -> interrupt -> backend",
      });
      if (canSendInterrupt()) {
        state.interrupting = true;
        try {
          await postJson(`/api/rtc/sessions/${state.sessionId}/interrupt`, { reason: "early-backend-preempt" });
        } finally {
          state.interrupting = false;
        }
      }
    }
    if (data.paragraph && data.definite) {
      const paragraphKey = `${data.userId}:${data.text}`;
      if (paragraphKey !== state.lastParagraphKey) {
        state.lastParagraphKey = paragraphKey;
        beginCommittedUserTurn(data.text, {
          turnId: state.activeTurnId,
          turnToken: state.activeTurnToken,
        });
        const source = state.backendPreempt.active ? "rtc-paragraph-preempted" : "rtc-paragraph";
        await submitTurn(data.text, source);
        state.backendPreempt = { active: false, reason: "" };
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
  } else if (hasRenderableCaptionBody(data.text) && shouldRenderAiLiveCaption()) {
    state.liveAiComposite = mergeCaptionChunk(state.liveAiComposite, data.text);
    setLiveCaption(state.liveAiComposite, "ai");
  }
}

function attachRtcListeners(VERTC) {
  const engine = state.rtc.engine;
  engine.on(VERTC.events.onUserJoined, (event) => {
    if (event.userInfo.userId === state.bootstrap.rtc.ai_user_id) {
      setProcessStatus({
        label: "rtc.event",
        main: "ai-user-joined",
        detail: "fallback AI user joined room",
        pushStep: "rtc.onUserJoined(ai) -> online",
      });
    }
  });
  engine.on(VERTC.events.onRoomBinaryMessageReceived, async (event) => {
    try {
      const { type, value } = tlvToString(event.message);
      const parsed = JSON.parse(value);
      if (type === "subv") {
        await consumeSubtitlePayload(parsed, "room_binary");
      }
      if (type === "conv") {
        const [label, detail] = mapBriefCode(parsed?.Stage?.Code);
        setStatus(label, detail);
      }
    } catch (error) {
      setProcessStatus({
        label: "rtc.decode",
        main: "rtc.binary.decode_error",
        detail: String(error),
        pushStep: "rtc.binary.decode -> error",
      });
    }
  });
  engine.on("on_volc_message_data", async (event) => {
    try {
      const parsed = unpackSubtitleMessage(decodeBase64ToBytes(event?.message));
      await consumeSubtitlePayload(parsed, "on_volc_message_data");
    } catch (error) {
      setProcessStatus({
        label: "rtc.subtitle",
        main: "subtitle.decode_error",
        detail: String(error),
        pushStep: "rtc.on_volc_message_data -> error",
      });
    }
  });
  engine.on(VERTC.events.onError, (event) => {
    setStatus("Error", `RTC 错误：${event.errorCode || "unknown"}`);
  });
}

async function initRtc() {
  if (state.joined && state.voiceChatStarted) return;
  if (!state.bootstrap.rtc.app_id || !state.bootstrap.rtc.token) {
    setConnectionChip("RTC 参数未配置");
    setProcessStatus({
      label: "rtc.status",
      main: "rtc.unconfigured",
      detail: "missing app_id/token",
      pushStep: "rtc.init -> missing_credentials",
    });
    return;
  }
  const rtcModule = await import(state.bootstrap.sdk.esm_url);
  const VERTC = rtcModule.default;
  state.rtcModule = rtcModule;
  const engine = VERTC.createEngine(state.bootstrap.rtc.app_id);
  state.rtc = { engine, room: null };
  attachRtcListeners(VERTC);

  const cameraVisionEnabled = Boolean(state.bootstrap?.voice_chat?.camera_vision_enabled);
  const micReady = await ensureMicrophoneAccess(true, cameraVisionEnabled);
  if (!micReady) {
    setConnectionChip("等待麦克风授权");
    return;
  }
  try {
    await VERTC.enableDevices({ audio: true, video: cameraVisionEnabled });
  } catch {}
  if (typeof engine.setAudioCaptureConfig === "function") {
    try {
      await engine.setAudioCaptureConfig({
        noiseSuppression: true,
        echoCancellation: true,
        autoGainControl: true,
      });
    } catch {}
  }
  try {
    await engine.startAudioCapture();
  } catch (error) {
    setStatus("Error", `音频采集启动失败：${String(error)}`);
    return;
  }
  if (cameraVisionEnabled && typeof engine.startVideoCapture === "function") {
    try {
      await engine.startVideoCapture();
      setProcessStatus({
        label: "rtc.vision",
        main: "camera.capture.started",
        detail: "native vision camera stream enabled",
        pushStep: "rtc.startVideoCapture() -> ok",
      });
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
  setConnectionChip("RTC 已连接，正在启动 VoiceChat");
  if (typeof engine.publishStream === "function" && state.rtcModule?.MediaType?.AUDIO) {
    try {
      await engine.publishStream(state.rtcModule.MediaType.AUDIO);
    } catch {}
  }
  if (cameraVisionEnabled && typeof engine.publishStream === "function" && state.rtcModule?.MediaType?.VIDEO) {
    try {
      await engine.publishStream(state.rtcModule.MediaType.VIDEO);
      setProcessStatus({
        label: "rtc.vision",
        main: "camera.publish.started",
        detail: "rtc video stream published for native vision",
        pushStep: "rtc.publishStream(VIDEO) -> ok",
      });
    } catch (error) {
      setWarning(`摄像头视频发布失败，官方视觉链将无法使用实时画面：${String(error)}`);
    }
  }
  await postJson(`/api/rtc/sessions/${state.sessionId}/connected`);
  const startPayload = await postJson(`/api/rtc/sessions/${state.sessionId}/start`, {});
  if (startPayload.started) {
    state.voiceChatStarted = true;
    const effectiveDialogPath = startPayload.effective_dialog_path || state.bootstrap.voice_chat.effective_dialog_path || state.bootstrap.voice_chat.primary_dialog_path;
    setConnectionChip(`RTC 已连接 / VoiceChat 已启动 / ${String(effectiveDialogPath).toUpperCase()}`);
    setStatus("Idle", "VoiceChat 已启动，等待迎宾与第一轮问答。");
    if (!state.autoGreetingTriggered) {
      state.autoGreetingTriggered = true;
      window.setTimeout(() => {
        handlePresence().catch((error) => {
          setWarning(`自动迎宾触发失败：${String(error)}`);
        });
      }, 120);
    }
  } else {
    setConnectionChip("RTC 已连接 / VoiceChat 未启动");
  }
}

async function submitTurn(userText, source = "manual") {
  if (revenueTurnIsBusy()) {
    setProcessStatus({
      label: "pipeline.guard",
      main: "pricing.busy",
      detail: "previous pricing turn still running",
      pushStep: "pricing.guard -> previous_turn_running",
    });
    return;
  }
  const requestId = ++state.activeRequestId;
  if (backendVisionEnabled() && looksLikeVisionCaptureRequest(userText)) {
    try {
      await submitVisionTurn(userText, source);
    } catch (error) {
      if (requestId === state.activeRequestId) {
        setStatus("Error", `视觉识别失败：${String(error)}`);
        setProcessStatus({
          label: "vision.backend",
          main: "vision.frame.error",
          detail: String(error),
          pushStep: "camera.frame -> error",
        });
      }
    }
    return;
  }
  beginCommittedUserTurn(userText);
  setProcessStatus({
    label: "turn.submit",
    main: "turn.submit",
    detail: `routing text · ${userText}`,
    pushStep: "POST /api/rtc/.../utterances -> pending",
  });
  try {
    const payload = await postJson(`/api/rtc/sessions/${state.sessionId}/utterances`, {
      user_text: userText,
      source,
    });
    if (requestId !== state.activeRequestId) return;
    setActiveTurn(payload);
    updateInterruptGate(payload.owner === "backend" ? { ...payload, interrupt_gate: "interrupting" } : payload);
    if (payload.owner === "backend" && (payload.intent === "pricing" || payload.intent === "pricing_confirm")) {
      state.revenueTurnPending = true;
      state.revenuePendingTurnId = payload.turn_id ?? null;
    }
    setProcessStatus({
      label: payload.owner === "backend" ? "pipeline.backend" : "pipeline.s2s",
      main: formatProcessLine(payload.owner, payload.intent),
      detail: `${payload.route_reason} · ${payload.processing_ms} ms`,
      pushStep: describeRouteAsRuntime(payload.intent, payload.route_reason),
    });
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
    setStatus("Error", `提交用户话术失败：${String(error)}`);
  }
}

async function handlePresence() {
  const payload = await postJson(`/api/rtc/sessions/${state.sessionId}/presence`, {
    source: "stage-button",
  });
  if (payload.should_greet) {
    setStatus("Greeting", payload.greeting_text || "检测到来宾进入展厅区域。");
  }
}

async function handleInterrupt() {
  if (!canSendInterrupt()) {
    setProcessStatus({
      label: "打断控制",
      main: "interrupt.throttled",
      detail: "已忽略过于频繁的打断指令。",
    });
    return;
  }
  state.lastParagraphKey = "";
  clearLiveCaption();
  await postJson(`/api/rtc/sessions/${state.sessionId}/interrupt`, {
    reason: "stage-button",
  });
}

function bindUi() {
  els.micBtn?.addEventListener("click", async () => {
    const ok = await ensureMicrophoneAccess(true, Boolean(state.bootstrap?.voice_chat?.camera_vision_enabled));
    if (!ok) return;
    if (!state.joined || !state.voiceChatStarted) {
      await initRtc();
    } else {
      setWarning("麦克风权限已刷新，RTC/VoiceChat 已在运行。");
    }
  });
  els.presenceBtn?.addEventListener("click", () => {
    handlePresence().catch((error) => setStatus("Error", `迎宾触发失败：${String(error)}`));
  });
  els.interruptBtn?.addEventListener("click", () => {
    handleInterrupt().catch((error) => setStatus("Error", `打断失败：${String(error)}`));
  });
  els.queryButtons.forEach((button) => {
    button.addEventListener("click", () => {
      submitTurn(button.getAttribute("data-query"), "stage-chip");
    });
  });
}

function bootstrapVisuals() {
  document.body.classList.add("real-model-mode");
  initSiriOrb();
  resizeParticleField();
  seedParticles();
  bindPointer();
  renderCaptions({ animateLatest: false });
  setProcessStatus(processState);
  window.addEventListener("resize", () => {
    resizeParticleField();
    seedParticles();
  });
  window.requestAnimationFrame(animate);
}

async function start() {
  try {
    bootstrapVisuals();
    bindUi();
    await loadBootstrap();
    bindSse();
    await initRtc();
    window.hotelStage = {
      presence: () => handlePresence(),
      interrupt: () => handleInterrupt(),
      submitTurn: (text) => submitTurn(text, "external"),
      sendTextToAgent: (text) => sendTextToAgent(text),
      retryRtc: () => initRtc(),
      debugState: state,
      setProcessStatus,
      commitCaption,
      setLiveCaption,
    };
  } catch (error) {
    setStatus("Error", `页面初始化失败：${String(error)}`);
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
