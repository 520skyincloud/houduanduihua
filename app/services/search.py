from __future__ import annotations

import re
from typing import Optional, Tuple

from app.models import FAQItem, ResolvedAnswer, SearchResult, TurnIntent, TurnRouteDecision


PRICING_KEYWORDS = [
    "调价",
    "收益",
    "收益分析",
    "经营分析",
    "经营情况",
    "收益情况",
    "复盘",
    "经营摘要",
    "盘面摘要",
    "经营摘要",
    "盘面",
    "飞书",
    "发飞书",
    "发群",
    "推送",
    "策略",
    "调价策略",
    "调价方案",
    "调价建议",
    "价格策略",
    "价格怎么调",
    "怎么定价",
    "定价策略",
    "定价方案",
    "定价",
    "改价",
    "改价方案",
    "执行结果",
    "执行详情",
    "审批",
    "批准",
    "通过",
    "拒绝",
]
CHITCHAT_KEYWORDS = ["你好", "您好", "嗨", "介绍一下你", "你是谁", "你能做什么"]
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

    if any(keyword in normalized for keyword in CHITCHAT_KEYWORDS):
        return "chitchat"

    if any(keyword in normalized for keyword in PRICING_KEYWORDS):
        return "pricing"

    if any(keyword in normalized for keyword in FAQ_KEYWORDS):
        return "faq"

    return "unknown"


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
        )

    intent = classify_intent(query)
    if intent == "chitchat":
        return TurnRouteDecision(
            owner="s2s",
            intent=intent,
            confidence=0.92,
            reason="chitchat-whitelist",
        )

    if has_pending_confirmation and (looks_like_confirmation(query) or looks_like_rejection(query)):
        return TurnRouteDecision(
            owner="backend",
            intent="pricing_confirm",
            confidence=0.98,
            reason="pricing-confirmation-pending",
        )

    if intent == "pricing":
        return TurnRouteDecision(
            owner="backend",
            intent="pricing",
            confidence=0.95,
            reason="pricing-keyword-hit",
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
        )

    faq_result = search_faq(query, items)
    if faq_route_mode == "hybrid_risk_split" and intent == "faq":
        confidence = faq_result.confidence if faq_result.faq_id is not None else 0.72
        return TurnRouteDecision(
            owner="s2s",
            intent="faq",
            confidence=max(confidence, 0.72),
            reason="faq-low-risk-s2s-memory",
        )
    if faq_route_mode == "s2s_memory" and (
        intent == "faq" or hard_faq_hit or (faq_result.faq_id is not None and faq_result.confidence >= 0.45)
    ):
        confidence = faq_result.confidence if faq_result.faq_id is not None else 0.72
        return TurnRouteDecision(
            owner="s2s",
            intent="faq",
            confidence=max(confidence, 0.72),
            reason="faq-s2s-memory-experiment",
        )

    if faq_result.faq_id is not None and faq_result.confidence >= 0.45:
        return TurnRouteDecision(
            owner="backend",
            intent="faq",
            confidence=faq_result.confidence,
            reason="faq-fast-hit",
        )

    return TurnRouteDecision(
        owner="s2s",
        intent="unknown",
        confidence=0.55,
        reason="safe-s2s-fallback",
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
        text = "我暂时没有查到准确结果，您可以换个说法，或者联系现场工作人员。"
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
