from __future__ import annotations

import re
from typing import Optional, Tuple

from app.models import FAQItem, ResolvedAnswer, SearchResult, TurnIntent, TurnRouteDecision


PRICING_COMMAND_ALIASES = {
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
}
EXACT_PRICING_COMMANDS = [
    alias for aliases in PRICING_COMMAND_ALIASES.values() for alias in aliases
]
PRICING_FILLER_WORDS = [
    "小丽",
    "你好",
    "您好",
    "麻烦",
    "请",
]
PRICING_COMMAND_PATTERNS = [
    r"(生成|帮我生成|给我生成|做个|做一版|帮我做个|来个|来一个|来一版).*(收益分析)",
    r"(生成|帮我生成|给我生成|做个|做一版|帮我做个|来个|来一个|来一版).*(昨日复盘)",
    r"(生成|帮我生成|给我生成|做个|做一版|帮我做个|来个|来一个|来一版).*(调价方案)",
]
PRICING_COMMAND_FAMILY_PATTERNS = [
    ("收益分析", r"(生成|帮我生成|给我生成|做个|做一版|帮我做个|来个|来一个|来一版).*(收益分析)"),
    ("昨日复盘", r"(生成|帮我生成|给我生成|做个|做一版|帮我做个|来个|来一个|来一版).*(昨日复盘)"),
    ("昨日复盘", r"(生成|帮我生成|给我生成|做个|做一版|帮我做个|来个|来一个|来一版).*(昨天复盘)"),
    ("调价方案", r"(生成|帮我生成|给我生成|做个|做一版|帮我做个|来个|来一个|来一版).*(调价方案)"),
]
CHITCHAT_KEYWORDS = ["你好", "您好", "嗨", "介绍一下你", "你是谁", "你能做什么"]
VISION_KEYWORDS = [
    "看看",
    "看下",
    "看一下",
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
]
EXTERNAL_INFO_KEYWORDS = [
    "天气",
    "下雨",
    "气温",
    "温度",
    "周边",
    "附近",
    "商场",
    "地铁",
    "公交",
    "机场",
    "高铁站",
    "火车站",
    "路线规划",
    "路况",
    "新闻",
]
FAQ_KEYWORDS = [
    "酒店",
    "早餐",
    "停车",
    "发票",
    "路线",
    "楼层",
    "设施",
    "用品",
    "会议室",
    "退房",
    "入住",
    "位置",
    "怎么走",
    "剃须刀",
    "洗衣房",
    "门口",
    "房间",
    "高铁",
    "护发素",
    "漱口水",
    "矿泉水",
    "卷纸",
    "纸巾",
    "被套",
    "被子",
    "枕头",
    "枕套",
    "床单",
    "梳子",
    "拖鞋",
    "牙刷",
    "牙膏",
    "洗发水",
    "沐浴露",
    "吹风机",
    "投影仪",
    "投屏",
    "门锁密码",
    "洗衣机",
    "空调",
    "遥控器",
    "小爱同学",
    "美团",
    "抖音",
]
HARD_BACKEND_KEYWORDS = [
    "早餐",
    "停车",
    "发票",
    "入住",
    "退房",
    "续住",
    "房型",
    "路线",
    "怎么走",
    "楼层",
    "会议室",
    "设施",
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
    "护发素",
    "漱口水",
    "矿泉水",
    "卷纸",
    "纸巾",
    "被套",
    "被子",
    "枕头",
    "枕套",
    "床单",
    "梳子",
    "拖鞋",
    "牙刷",
    "牙膏",
    "洗发水",
    "沐浴露",
    "吹风机",
    "投影仪",
    "投屏",
    "门锁密码",
    "洗衣机",
    "空调",
    "遥控器",
    "小爱同学",
    "美团",
    "抖音",
]
HOTEL_FACT_VISUAL_KEYWORDS = [
    "早餐券",
    "房卡",
    "发票",
    "订单",
    "入住",
    "停车票",
]
FAQ_REQUEST_VERBS = [
    "想用",
    "想要",
    "想拿",
    "想问",
    "需要",
    "有没有",
    "有没",
    "能给",
    "能不能",
    "可以给",
    "能提供",
    "能用",
    "用一下",
]
HOTEL_SUPPLY_KEYWORDS = [
    "护发素",
    "漱口水",
    "矿泉水",
    "卷纸",
    "纸巾",
    "被套",
    "被子",
    "枕头",
    "枕套",
    "床单",
    "梳子",
    "拖鞋",
    "牙刷",
    "牙膏",
    "洗发水",
    "沐浴露",
    "吹风机",
    "剃须刀",
    "投影仪",
    "投屏",
    "门锁密码",
    "洗衣机",
    "空调",
    "遥控器",
    "小爱同学",
]
CONFIRM_KEYWORDS = ["确认", "执行", "通过", "批准", "按这个", "就按", "可以", "行", "ok", "好的"]
REJECT_KEYWORDS = ["拒绝", "不要", "取消", "算了", "驳回", "不执行"]
FAQ_TOPIC_GROUPS = [
    ("早餐", ["早餐"]),
    ("停车", ["停车", "停车场"]),
    ("发票", ["发票", "水单"]),
    ("入住退房", ["入住", "退房", "续住"]),
    ("路线", ["路线", "怎么走", "位置", "高铁", "机场", "南站"]),
    ("楼层", ["楼层", "几楼", "哪层"]),
    ("设施", ["设施", "洗衣房", "健身房", "空调", "投影", "wifi"]),
    ("用品", ["用品", "剃须刀", "护手霜", "洗漱"]),
    ("会议室", ["会议室", "开会"]),
]
FAST_FAQ_PATTERNS = [
    (["早餐"], ["早餐"]),
    (["停车", "收费"], ["收费", "免费", "停车场收费"]),
    (["停车", "免费"], ["免费停车", "停车免费", "免费"]),
    (["停车", "有"], ["停车场有吗", "有停车场", "有免费停车场"]),
    (["停车", "哪"], ["停车场入口", "停车场怎么走", "车停在哪里", "哪条路进"]),
    (["停车"], ["停车", "停车场"]),
    (["发票"], ["发票", "开票"]),
    (["退房", "几点"], ["退房时间", "退房", "几点", "时间"]),
    (["退房", "时间"], ["退房时间", "退房", "几点", "时间"]),
    (["入住"], ["入住", "办理入住"]),
    (["路线"], ["路线", "怎么走", "位置", "在哪", "南站", "机场", "高铁"]),
    (["楼层"], ["楼层", "几楼", "哪层"]),
    (["会议室"], ["会议室", "开会"]),
    (["用品"], ["用品", "剃须刀", "护手霜", "洗漱"]),
    (["设施"], ["设施", "洗衣房", "健身房"]),
]


def normalize_text(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[？?！!，,。.\s]+", "", text)
    return text


def tokenize(text: str) -> list[str]:
    normalized = normalize_text(text)
    return [normalized[i : i + 2] for i in range(max(len(normalized) - 1, 1)) if normalized]


def jaccard_score(left: str, right: str) -> float:
    left_tokens = set(tokenize(left))
    right_tokens = set(tokenize(right))
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def classify_intent(text: str) -> TurnIntent:
    normalized = normalize_text(text)
    if not normalized:
        return "unknown"

    if normalized in EXACT_PRICING_COMMANDS:
        return "pricing"

    if looks_like_vision_request(normalized):
        return "vision"

    if looks_like_external_info_request(normalized):
        return "external_info"

    if any(keyword in normalized for keyword in CHITCHAT_KEYWORDS):
        return "chitchat"

    if looks_like_pricing_intent(normalized):
        return "pricing"

    if looks_like_hotel_faq_request(normalized):
        return "faq"

    if any(keyword in normalized for keyword in FAQ_KEYWORDS):
        return "faq"

    return "unknown"


def looks_like_vision_request(normalized: str) -> bool:
    return any(keyword in normalized for keyword in VISION_KEYWORDS)


def looks_like_external_info_request(normalized: str) -> bool:
    if any(keyword in normalized for keyword in EXTERNAL_INFO_KEYWORDS):
        return True
    if "路线" in normalized and not looks_like_hotel_faq_request(normalized):
        return True
    return False


def vision_requires_hotel_facts(normalized: str) -> bool:
    return any(keyword in normalized for keyword in HOTEL_FACT_VISUAL_KEYWORDS) or any(
        keyword in normalized for keyword in HARD_BACKEND_KEYWORDS
    )


def looks_like_pricing_intent(normalized: str) -> bool:
    return canonical_pricing_command(normalized) is not None


def canonical_pricing_command(normalized: str) -> str | None:
    normalized_for_match = strip_pricing_fillers(normalized)
    for family, aliases in PRICING_COMMAND_ALIASES.items():
        if normalized_for_match in aliases:
            return family
    for family, pattern in PRICING_COMMAND_FAMILY_PATTERNS:
        if re.search(pattern, normalized_for_match):
            return family
    return match_pricing_command_tokens(normalized_for_match)


def strip_pricing_fillers(normalized: str) -> str:
    stripped = normalized
    for filler in PRICING_FILLER_WORDS:
        stripped = stripped.replace(filler, "")
    return stripped


def match_pricing_command_tokens(normalized: str) -> str | None:
    token_groups = [
        ("收益分析", ("收益", "分析")),
        ("昨日复盘", ("昨日", "复盘")),
        ("昨日复盘", ("昨天", "复盘")),
        ("调价方案", ("调价", "方案")),
    ]
    action_hints = ("生成", "来个", "来一版", "做个", "做一版", "给我", "帮我")
    for family, required_tokens in token_groups:
        if all(token in normalized for token in required_tokens):
            if "生成" in normalized and any(hint in normalized for hint in action_hints):
                return family
            compact = "".join(required_tokens)
            if compact in normalized and "生成" in normalized:
                return family
    return None


def looks_like_hotel_faq_request(normalized: str) -> bool:
    if any(keyword in normalized for keyword in FAQ_KEYWORDS):
        return True
    if any(keyword in normalized for keyword in HOTEL_SUPPLY_KEYWORDS):
        return True
    return any(verb in normalized for verb in FAQ_REQUEST_VERBS) and any(
        keyword in normalized for keyword in HOTEL_SUPPLY_KEYWORDS
    )


def looks_like_confirmation(query: str) -> bool:
    normalized = normalize_text(query)
    return any(keyword in normalized for keyword in CONFIRM_KEYWORDS)


def looks_like_rejection(query: str) -> bool:
    normalized = normalize_text(query)
    return any(keyword in normalized for keyword in REJECT_KEYWORDS)


def decide_turn_route(
    query: str,
    items: list[FAQItem],
    has_pending_confirmation: bool = False,
    faq_route_mode: str = "hybrid_risk_split",
) -> TurnRouteDecision:
    normalized = normalize_text(query)
    if not normalized:
        return TurnRouteDecision(
            owner="backend",
            intent="unknown",
            confidence=1.0,
            reason="empty-input",
            chain="hotel_fact_chain",
            requires_grounding=False,
            grounding_source="none",
            allow_freeform_answer=False,
        )

    intent = classify_intent(query)
    if intent == "vision":
        return TurnRouteDecision(
            owner="backend",
            intent="vision",
            confidence=0.94,
            reason="vision-keyword-hit",
            chain="vision_chain",
            requires_grounding=True,
            grounding_source="vision",
            allow_freeform_answer=False,
        )

    if intent == "external_info":
        return TurnRouteDecision(
            owner="backend",
            intent="external_info",
            confidence=0.88,
            reason="external-info-keyword-hit",
            chain="hotel_fact_chain",
            requires_grounding=True,
            grounding_source="web",
            allow_freeform_answer=False,
        )

    if intent == "chitchat":
        return TurnRouteDecision(
            owner="native",
            intent=intent,
            confidence=0.92,
            reason="chitchat-whitelist",
            chain="social_chain",
            requires_grounding=False,
            grounding_source="none",
            allow_freeform_answer=True,
        )

    if has_pending_confirmation and (looks_like_confirmation(query) or looks_like_rejection(query)):
        return TurnRouteDecision(
            owner="backend",
            intent="pricing_confirm",
            confidence=0.98,
            reason="pricing-confirmation-pending",
            chain="hotel_fact_chain",
            requires_grounding=True,
            grounding_source="mcp",
            allow_freeform_answer=False,
        )

    if intent == "pricing":
        return TurnRouteDecision(
            owner="backend",
            intent="pricing",
            confidence=0.95,
            reason="pricing-keyword-hit",
            chain="hotel_fact_chain",
            requires_grounding=True,
            grounding_source="mcp",
            allow_freeform_answer=False,
        )

    hard_faq_hit = any(keyword in normalized for keyword in HARD_BACKEND_KEYWORDS) or bool(
        re.search(r"\d|几点|多少|费用|价格|规则|政策", normalized)
    )
    if faq_route_mode in {"backend", "hybrid_risk_split"} and hard_faq_hit:
        return TurnRouteDecision(
            owner="backend",
            intent="faq",
            confidence=0.96,
            reason="hard-backend-rule",
            chain="hotel_fact_chain",
            requires_grounding=True,
            grounding_source="rule",
            allow_freeform_answer=False,
        )

    faq_result = search_faq(query, items)
    if faq_route_mode == "hybrid_risk_split" and intent == "faq":
        confidence = faq_result.confidence if faq_result.faq_id is not None else 0.72
        return TurnRouteDecision(
            owner="native",
            intent="faq",
            confidence=max(confidence, 0.72),
            reason="faq-low-risk-s2s-memory",
            chain="social_chain",
            requires_grounding=False,
            grounding_source="none",
            allow_freeform_answer=True,
        )
    if faq_route_mode == "s2s_memory" and (
        intent == "faq" or hard_faq_hit or (faq_result.faq_id is not None and faq_result.confidence >= 0.45)
    ):
        confidence = faq_result.confidence if faq_result.faq_id is not None else 0.72
        return TurnRouteDecision(
            owner="native",
            intent="faq",
            confidence=max(confidence, 0.72),
            reason="faq-s2s-memory-experiment",
            chain="social_chain",
            requires_grounding=False,
            grounding_source="none",
            allow_freeform_answer=True,
        )

    if faq_result.faq_id is not None and faq_result.confidence >= 0.45:
        return TurnRouteDecision(
            owner="backend",
            intent="faq",
            confidence=faq_result.confidence,
            reason="faq-fast-hit",
            chain="hotel_fact_chain",
            requires_grounding=True,
            grounding_source="faq",
            allow_freeform_answer=False,
        )

    return TurnRouteDecision(
        owner="native",
        intent="unknown",
        confidence=0.55,
        reason="safe-s2s-fallback",
        chain="social_chain",
        requires_grounding=False,
        grounding_source="none",
        allow_freeform_answer=True,
    )


def search_faq(query: str, items: list[FAQItem]) -> SearchResult:
    best: Tuple[Optional[FAQItem], float, Optional[str]] = (None, 0.0, None)
    query_normalized = normalize_text(query)

    for required_terms, alias_terms in FAST_FAQ_PATTERNS:
        if not all(term in query_normalized for term in required_terms):
            continue
        fast_best: Tuple[Optional[FAQItem], float, Optional[str]] = (None, 0.0, None)
        for item in items:
            for alias in item.aliases:
                alias_normalized = normalize_text(alias)
                if not any(term in alias_normalized for term in alias_terms):
                    continue
                score = jaccard_score(query, alias)
                if score > fast_best[1]:
                    fast_best = (item, score, alias)
        if fast_best[0] is not None:
            item, _, matched_alias = fast_best
            return SearchResult(
                faq_id=item.faq_id,
                confidence=0.93,
                answer_type=item.answer_type,
                standard_answer=item.standard_answer,
                matched_alias=matched_alias,
            )

    for item in items:
        for alias in item.aliases:
            alias_normalized = normalize_text(alias)
            score = 1.0 if alias_normalized == query_normalized else jaccard_score(query, alias)
            if query_normalized and query_normalized in alias_normalized:
                score = max(score, 0.92)
            elif alias_normalized and alias_normalized in query_normalized:
                score = max(score, 0.88)
            for _, keywords in FAQ_TOPIC_GROUPS:
                if any(keyword in query_normalized for keyword in keywords) and any(
                    keyword in alias_normalized for keyword in keywords
                ):
                    score = max(score, 0.76)
                    break
            if score > best[1]:
                best = (item, score, alias)

    item, score, matched_alias = best
    if item is None:
        return SearchResult(
            faq_id=None,
            confidence=0.0,
            answer_type="invalid",
            standard_answer="",
            matched_alias=None,
        )

    return SearchResult(
        faq_id=item.faq_id,
        confidence=round(score, 4),
        answer_type=item.answer_type,
        standard_answer=item.standard_answer,
        matched_alias=matched_alias,
    )


def to_speak_text(answer: str) -> str:
    cleaned = answer.replace("您好，", "").replace("您好", "")
    cleaned = cleaned.replace("哦。", "。").replace("哈", "")
    cleaned = re.sub(r"\s+", "", cleaned)
    parts = [part.strip() for part in re.split(r"[。！？!?\n]+", cleaned) if part.strip()]
    if not parts:
        return cleaned

    speak = ""
    for part in parts[:2]:
        candidate = f"{speak}{part}。"
        if len(candidate) > 78 and speak:
            break
        speak = candidate

    if not speak:
        speak = cleaned[:78].rstrip("，。； ") + "。"
    cleaned = speak
    return cleaned


def chunk_speak_text(text: str, max_chars: int = 180) -> list[str]:
    cleaned = re.sub(r"\s+", "", text).strip()
    if not cleaned:
        return []
    if len(cleaned) <= max_chars:
        return [cleaned]

    parts = [part.strip() for part in re.split(r"([。！？!?])", cleaned) if part.strip()]
    chunks: list[str] = []
    current = ""
    for part in parts:
        candidate = current + part
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            chunks.append(current)
        current = part
    if current:
        chunks.append(current)
    return chunks or [cleaned[:max_chars]]


def resolve_answer(query: str, items: list[FAQItem]) -> ResolvedAnswer:
    intent = classify_intent(query)
    if intent == "chitchat":
        intro = "您好，我是展厅智能接待助手，可以为您介绍酒店服务并回答常见问题。"
        return ResolvedAnswer(
            status="answered",
            faq_id=None,
            confidence=1.0,
            needs_handoff=False,
            display_text=intro,
            speak_text=intro,
        )

    result = search_faq(query, items)
    if result.faq_id is None or result.confidence < 0.35:
        text = "您可以换个更具体的说法，我再帮您查一下。"
        return ResolvedAnswer(
            status="not_found",
            faq_id=None,
            confidence=result.confidence,
            needs_handoff=False,
            display_text=text,
            speak_text=text,
        )

    if result.answer_type == "handoff":
        handoff_text = "这个问题需要现场工作人员协助您处理，您可以联系门店管家或前台。"
        return ResolvedAnswer(
            status="handoff",
            faq_id=result.faq_id,
            confidence=result.confidence,
            needs_handoff=True,
            display_text=handoff_text,
            speak_text=handoff_text,
        )

    if result.answer_type == "invalid":
        invalid_text = "这个问题我暂时还没有可用答案，建议您联系现场工作人员。"
        return ResolvedAnswer(
            status="not_found",
            faq_id=result.faq_id,
            confidence=result.confidence,
            needs_handoff=False,
            display_text=invalid_text,
            speak_text=invalid_text,
        )

    return ResolvedAnswer(
        status="answered",
        faq_id=result.faq_id,
        confidence=result.confidence,
        needs_handoff=False,
        display_text=result.standard_answer.strip(),
        speak_text=result.standard_answer.strip(),
    )
