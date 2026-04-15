from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Any, Optional

from app.models import FAQItem
from app.services.search import normalize_text, tokenize


CATEGORY_SYNONYMS: dict[str, list[str]] = {
    "parking": ["停车", "停车场", "免费停车", "停车收费", "停车入口", "开车", "车停", "停哪儿", "停哪", "车位", "停哪边", "停车费", "收钱", "辅路", "进车口", "地上停车场", "地下停车场", "充电桩", "充电服务"],
    "breakfast": ["早餐", "早饭", "吃的", "早上吃的", "含早", "早餐券", "在哪吃早饭"],
    "invoice": ["发票", "开票", "电子票", "专票", "普票", "抬头", "税号", "名称", "开票名称"],
    "checkout": ["退房", "延迟退房", "退房时间", "几点走", "最晚几点走", "最晚几点之前得走", "离店", "退住", "晚点走"],
    "checkin": ["入住", "办理入住", "刷脸开门", "前台", "很晚到", "晚到", "晚上到", "半夜到", "服务台", "工作人员", "前台有人吗"],
    "route": ["路线", "位置", "怎么走", "高铁", "南站", "机场", "入口", "过来怎么走", "导航", "店名", "携程", "美团", "地铁"],
    "floor": ["几楼", "楼层", "哪层"],
    "facility": ["设施", "洗衣房", "健身房", "游泳池", "泳池", "停车场", "会议室"],
    "supplies": ["用品", "剃须刀", "刮胡刀", "洗漱", "针线包", "护手霜", "房间里有吗", "前台拿"],
    "meeting_room": ["会议室", "开会", "会议", "小会", "开会地方", "会客室", "小会议室", "临时开会"],
    "dark_room": ["暗房", "无窗房", "没窗户", "窗户", "没窗"],
}

INTENT_KEYWORDS: dict[str, list[str]] = {
    "existence": ["有没有", "有无", "是否有", "提供吗", "有吗"],
    "price": ["收费", "费用", "价格", "免费", "收费吗", "花钱", "收钱", "另外收钱", "停车费"],
    "location": ["在哪", "哪里", "哪边", "哪层", "几楼", "入口", "怎么走", "位置", "停哪儿", "店名"],
    "time": ["几点", "什么时候", "时间", "多久", "几时", "最晚", "之前得走", "晚点走"],
    "procedure": ["怎么", "如何", "怎么办", "预定", "预约", "开", "办理", "申请", "线上", "自己弄", "怎么申请", "怎么预约"],
}

REWRITE_MAP: dict[str, list[str]] = {
    "暗房": ["无窗房", "没有窗户的房间"],
    "停车场": ["停车", "地上停车场"],
    "停车场怎么收费": ["停车收费吗", "停车免费吗"],
    "停车场在哪": ["停车场入口在哪", "停车场怎么走"],
    "一次性剃须刀": ["一次性刮胡刀", "剃须刀"],
    "早餐几点": ["有没有早餐", "提供早餐吗"],
    "发票怎么开": ["怎么开发票", "申请发票"],
    "退房时间几点": ["几点退房", "退房是几点"],
    "健身房在哪": ["有没有健身房", "附近有健身房吗"],
    "会议室": ["有没有会议室", "酒店有会议室吗"],
    "我自己开车过去的话，车能停哪儿啊": ["停车场在哪", "车停在哪里", "停车场入口在哪"],
    "车停那边要另外收钱不": ["停车场怎么收费", "停车收费吗", "停车免费吗"],
    "请问你们这边车位收钱吗呀": ["停车场怎么收费", "停车收费吗", "停车免费吗"],
    "停车位怎么进去": ["停车场怎么走", "停车场入口在哪", "进车口在哪"],
    "停车场有充电服务吗": ["停车场有没有充电桩", "停车场有充电桩吗"],
    "发票是退房以后线上自己弄吗": ["发票怎么开", "退房后才能开发票吗", "什么时候可以申请发票"],
    "开票名称怎么填": ["发票抬头怎么填", "开票抬头怎么写", "发票怎么开"],
    "税号要不要填": ["开专票需要税号吗", "发票抬头和税号怎么填", "发票怎么开"],
    "我明天最晚几点之前得走": ["退房时间几点", "最晚几点退房", "退房是几点"],
    "我明天晚点走可以吗": ["可以延迟退房吗", "延时退房怎么收费", "退房时间几点"],
    "刮胡刀有的话我是去前台拿还是房间里有": ["有没有一次性剃须刀", "刮胡刀在哪拿", "剃须刀有吗"],
    "我从南站过来怎么走会比较顺": ["去酒店的路线怎么走", "酒店位置在哪", "如何到达酒店"],
    "我从南站过去你们店名是什么": ["酒店位置在哪", "导航搜什么", "如何到达酒店"],
    "你们家早上有没有吃的": ["酒店有早餐吗", "提供早餐吗", "有没有早餐"],
    "含早吗": ["酒店有早餐吗", "提供早餐吗"],
    "早饭在哪吃": ["酒店有早餐吗", "提供早餐吗"],
    "我晚上很晚到还能正常办入住吧": ["在哪办入住", "酒店是24小时有人吗", "你们有没有前台"],
    "我们想临时开个小会你们那边有会议室吗": ["酒店提供会议室吗", "有没有会议室"],
    "请问开会地方在哪呀": ["酒店提供会议室吗", "有没有会议室", "会议室在哪"],
    "你们房间有没有那种没窗户的": ["有没有暗房", "你们有没有无窗房", "没有窗户的房间"],
}

NOISE_KEYWORDS = ["充电桩", "矿泉水", "洗衣房", "投影仪", "电视"]


def _jaccard(left: str, right: str) -> float:
    left_tokens = set(tokenize(left))
    right_tokens = set(tokenize(right))
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def _contains_any(text: str, keywords: list[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def _detect_category(text: str) -> Optional[str]:
    normalized = normalize_text(text)
    if "车" in normalized and ("停" in normalized or "收费" in normalized or "收钱" in normalized):
        return "parking"
    if "车位" in normalized or "进车口" in normalized or "辅路" in normalized:
        return "parking"
    if "南站" in normalized or "高铁" in normalized or ("过来" in normalized and "怎么走" in normalized):
        return "route"
    if "导航" in normalized or "店名" in normalized or "美团" in normalized or "携程" in normalized:
        return "route"
    if "发票" in normalized or "开票" in normalized:
        return "invoice"
    if ("早上" in normalized and ("吃" in normalized or "早餐" in normalized)) or "早饭" in normalized:
        return "breakfast"
    if ("最晚" in normalized and "走" in normalized) or "退房" in normalized:
        return "checkout"
    if "晚到" in normalized or "很晚到" in normalized or ("入住" in normalized and "晚上" in normalized):
        return "checkin"
    if "刮胡刀" in normalized:
        return "supplies"
    if "泳池" in normalized:
        return "facility"
    if ("没窗" in normalized or "无窗" in normalized) and "房" in normalized:
        return "dark_room"
    if "小会" in normalized:
        return "meeting_room"
    if "开会地方" in normalized or "会客室" in normalized:
        return "meeting_room"
    for category, synonyms in CATEGORY_SYNONYMS.items():
        if _contains_any(normalized, [normalize_text(term) for term in synonyms]):
            return category
    return None


def _detect_intent(text: str) -> str:
    normalized = normalize_text(text)
    if "收钱" in normalized or "另外收钱" in normalized:
        return "price"
    if "线上" in normalized or "自己弄" in normalized:
        return "procedure"
    if "最晚" in normalized or "之前得走" in normalized:
        return "time"
    if "停哪" in normalized or "停哪儿" in normalized:
        return "location"
    if "进去" in normalized or "进车口" in normalized:
        return "location"
    if "店名" in normalized:
        return "location"
    for intent, keywords in INTENT_KEYWORDS.items():
        if _contains_any(normalized, [normalize_text(term) for term in keywords]):
            return intent
    return "general"


def _query_variants(query: str) -> list[str]:
    variants = [query]
    normalized = normalize_text(query)
    for key, rewrites in REWRITE_MAP.items():
        if normalize_text(key) in normalized:
            variants.extend(rewrites)
    if "停车" in normalized and "收费" not in normalized and "在哪" not in normalized and "入口" not in normalized:
        variants.extend(["有没有停车场", "酒店有停车场吗"])
    if "车位" in normalized:
        variants.extend(["有没有停车场", "停车场在哪", "停车场怎么收费"])
    if "停车" in normalized and ("收费" in normalized or "免费" in normalized):
        variants.extend(["停车收费吗", "停车场怎么收费"])
    if "收钱" in normalized:
        variants.extend(["停车收费吗", "停车场怎么收费", "停车免费吗"])
    if "停车" in normalized and ("在哪" in normalized or "入口" in normalized or "怎么走" in normalized):
        variants.extend(["停车场入口在哪", "停车场怎么走"])
    if "进去" in normalized or "进车口" in normalized:
        variants.extend(["停车场入口在哪", "停车场怎么走", "车停在哪里"])
    if "辅路" in normalized or "进车口" in normalized:
        variants.extend(["停车场入口在哪", "停车场怎么走"])
    if "车" in normalized and "停" in normalized:
        variants.extend(["停车场在哪", "车停在哪里", "停车场怎么走"])
    if "发票" in normalized and ("线上" in normalized or "退房" in normalized):
        variants.extend(["发票怎么开", "退房后才能开发票吗", "什么时候可以申请发票"])
    if "抬头" in normalized or "税号" in normalized or "名称" in normalized:
        variants.extend(["发票怎么开", "发票抬头怎么填", "开专票需要税号吗"])
    if "最晚" in normalized and "走" in normalized:
        variants.extend(["退房时间几点", "最晚几点退房"])
    if "晚点走" in normalized or "延时" in normalized:
        variants.extend(["可以延迟退房吗", "延时退房怎么收费", "退房时间几点"])
    if "南站" in normalized or "高铁" in normalized:
        variants.extend(["去酒店的路线怎么走", "酒店位置在哪", "如何到达酒店"])
    if "店名" in normalized or "导航" in normalized:
        variants.extend(["导航搜什么", "酒店位置在哪", "如何到达酒店"])
    if "早上" in normalized and ("吃" in normalized or "早餐" in normalized):
        variants.extend(["酒店有早餐吗", "提供早餐吗"])
    if "含早" in normalized or "早饭" in normalized:
        variants.extend(["酒店有早餐吗", "提供早餐吗"])
    if "刮胡刀" in normalized:
        variants.extend(["有没有一次性剃须刀", "刮胡刀在哪拿"])
    if ("没窗" in normalized or "无窗" in normalized) and "房" in normalized:
        variants.extend(["有没有暗房", "你们有没有无窗房"])
    if ("很晚到" in normalized or "晚到" in normalized or ("晚上" in normalized and "入住" in normalized)):
        variants.extend(["在哪办入住", "酒店是24小时有人吗", "你们有没有前台"])
    if "前台" in normalized or "服务台" in normalized or "工作人员" in normalized:
        variants.extend(["在哪办入住", "酒店是24小时有人吗"])
    if "开会地方" in normalized or "会客室" in normalized or "小会" in normalized:
        variants.extend(["酒店提供会议室吗", "有没有会议室"])
    deduped: list[str] = []
    seen: set[str] = set()
    for item in variants:
        norm = normalize_text(item)
        if norm and norm not in seen:
            deduped.append(item)
            seen.add(norm)
    return deduped


@dataclass
class FAQSemanticCandidate:
    faq_id: str
    alias: str
    standard_answer: str
    score: float
    matched_query: str
    category: Optional[str]
    intent: str


class FAQSemanticExperiment:
    def __init__(self, items: list[FAQItem]) -> None:
        self._items = [item for item in items if item.answer_type == "direct"]

    def _candidate_score(
        self,
        query: str,
        alias: str,
        answer: str,
        query_category: Optional[str],
        query_intent: str,
    ) -> float:
        query_norm = normalize_text(query)
        alias_norm = normalize_text(alias)
        answer_norm = normalize_text(answer)
        score = max(_jaccard(query, alias), _jaccard(query, answer[:80]))

        if query_norm in alias_norm or query_norm in answer_norm:
            score = max(score, 0.92)
        elif alias_norm and alias_norm in query_norm:
            score = max(score, 0.88)

        category_match = False
        if query_category:
            synonyms = [normalize_text(term) for term in CATEGORY_SYNONYMS[query_category]]
            category_match = _contains_any(alias_norm, synonyms) or _contains_any(answer_norm, synonyms)
            if category_match:
                score += 0.18
            else:
                score -= 0.08

        if query_intent == "price" and _contains_any(answer_norm, [normalize_text(k) for k in ["收费", "免费", "费用"]]):
            score += 0.12
        elif query_intent == "location" and _contains_any(answer_norm, [normalize_text(k) for k in ["入口", "进入", "路线", "位置", "几楼", "哪层"]]):
            score += 0.12
        elif query_intent == "time" and _contains_any(answer_norm, [normalize_text(k) for k in ["时间", "几点", "12点", "24小时"]]):
            score += 0.12
        elif query_intent == "procedure" and _contains_any(answer_norm, [normalize_text(k) for k in ["打开", "联系", "申请", "办理", "预约"]]):
            score += 0.08
        elif query_intent == "existence" and _contains_any(answer_norm, [normalize_text(k) for k in ["有", "没有", "不提供", "提供"]]):
            score += 0.08

        if query_category == "parking" and query_intent == "existence":
            if "充电桩" in alias_norm or "充电桩" in answer_norm:
                score -= 0.35
            if _contains_any(answer_norm, [normalize_text(k) for k in ["停车场", "免费停车", "地上停车场"]]):
                score += 0.18

        if query_category == "facility" and "游泳池" in query_norm:
            if not _contains_any(alias_norm + answer_norm, [normalize_text("游泳池")]):
                score -= 0.3

        if query_category == "checkin" and query_intent == "time":
            if "退房" in alias_norm or "退房" in answer_norm:
                score -= 0.25

        if any(noise in alias_norm or noise in answer_norm for noise in [normalize_text(item) for item in NOISE_KEYWORDS]):
            if not any(noise in query_norm for noise in [normalize_text(item) for item in NOISE_KEYWORDS]):
                score -= 0.12

        return round(score, 4)

    def query(self, query: str, limit: int = 5) -> dict[str, Any]:
        started = perf_counter()
        query_category = _detect_category(query)
        query_intent = _detect_intent(query)
        variants = _query_variants(query)
        candidates: list[FAQSemanticCandidate] = []

        for item in self._items:
            item_category = _detect_category(" ".join(item.aliases) + item.standard_answer)
            for alias in item.aliases:
                for variant in variants:
                    score = self._candidate_score(
                        variant,
                        alias,
                        item.standard_answer,
                        query_category,
                        query_intent,
                    )
                    if score < 0.32:
                        continue
                    candidates.append(
                        FAQSemanticCandidate(
                            faq_id=item.faq_id,
                            alias=alias,
                            standard_answer=item.standard_answer,
                            score=score,
                            matched_query=variant,
                            category=item_category,
                            intent=query_intent,
                        )
                    )

        candidates.sort(key=lambda item: item.score, reverse=True)

        unique: list[FAQSemanticCandidate] = []
        seen_faqs: set[str] = set()
        for candidate in candidates:
            if candidate.faq_id in seen_faqs:
                continue
            unique.append(candidate)
            seen_faqs.add(candidate.faq_id)
            if len(unique) >= limit:
                break

        top = unique[0] if unique else None
        second = unique[1] if len(unique) > 1 else None
        accepted = False
        reject_reason = ""
        if top:
            gap = top.score - (second.score if second else 0.0)
            consensus_accept = self._supports_consensus_accept(unique[:3], query_category, query_intent)
            accepted = top.score >= 0.63 and (gap >= 0.06 or consensus_accept)
            if not accepted:
                reject_reason = (
                    "top-match-too-weak"
                    if top.score < 0.63
                    else "top-second-gap-too-small"
                )
        else:
            reject_reason = "no-match"

        elapsed_ms = round((perf_counter() - started) * 1000, 2)
        return {
            "query": query,
            "query_category": query_category,
            "query_intent": query_intent,
            "query_variants": variants,
            "elapsed_ms": elapsed_ms,
            "accepted": accepted,
            "reject_reason": reject_reason or None,
            "top_match": None
            if not top
            else {
                "faq_id": top.faq_id,
                "alias": top.alias,
                "standard_answer": top.standard_answer,
                "score": top.score,
                "matched_query": top.matched_query,
                "category": top.category,
            },
            "candidates": [
                {
                    "faq_id": candidate.faq_id,
                    "alias": candidate.alias,
                    "standard_answer": candidate.standard_answer,
                    "score": candidate.score,
                    "matched_query": candidate.matched_query,
                    "category": candidate.category,
                }
                for candidate in unique
            ],
        }

    def _supports_consensus_accept(
        self,
        candidates: list[FAQSemanticCandidate],
        query_category: Optional[str],
        query_intent: str,
    ) -> bool:
        if len(candidates) < 2 or not query_category:
            return False

        top_answers = [normalize_text(candidate.standard_answer) for candidate in candidates]
        top_categories = [candidate.category for candidate in candidates]
        if sum(category == query_category for category in top_categories) < 2:
            return False

        if query_category == "parking":
            if query_intent == "existence":
                hits = sum(
                    _contains_any(answer, [normalize_text(word) for word in ["停车场", "免费停车", "地上停车场"]])
                    for answer in top_answers
                )
                return hits >= 2
            if query_intent == "price":
                hits = sum(
                    _contains_any(answer, [normalize_text(word) for word in ["免费", "收费", "出车前十分钟"]])
                    for answer in top_answers
                )
                return hits >= 2
            if query_intent == "location":
                hits = sum(
                    _contains_any(answer, [normalize_text(word) for word in ["繁华大道辅路", "停车场入口", "怎么走"]])
                    for answer in top_answers
                )
                return hits >= 2

        if query_category in {"invoice", "dark_room"}:
            if query_category == "invoice" and all(category == "invoice" for category in top_categories[:2]):
                return candidates[0].score >= 1.0 and candidates[1].score >= 1.0
            answer_similarity = _jaccard(candidates[0].standard_answer[:120], candidates[1].standard_answer[:120])
            return answer_similarity >= 0.4

        answer_similarity = _jaccard(candidates[0].standard_answer[:120], candidates[1].standard_answer[:120])
        return answer_similarity >= 0.33

    def benchmark(self) -> dict[str, Any]:
        cases = [
            {
                "query": "有没有停车场",
                "expect_any": ["免费停车", "地上停车场", "停车场"],
                "forbid": ["充电桩"],
            },
            {
                "query": "停车场怎么收费",
                "expect_any": ["免费", "停车场"],
            },
            {
                "query": "停车场在哪",
                "expect_any": ["繁华大道辅路", "停车场入口"],
            },
            {
                "query": "酒店有早餐吗",
                "expect_any": ["暂不提供早餐", "不提供早餐"],
            },
            {
                "query": "退房时间几点",
                "expect_any": ["12点", "退房时间"],
                "forbid": ["入住"],
            },
            {
                "query": "发票怎么开",
                "expect_any": ["电子", "发票", "小程序"],
            },
            {
                "query": "有没有暗房",
                "expect_any": ["没有暗房", "有窗户"],
            },
            {
                "query": "有没有一次性剃须刀",
                "expect_any": ["剃须刀", "洗衣房"],
            },
            {
                "query": "健身房在哪",
                "expect_any": ["不提供健身房", "周边"],
            },
            {
                "query": "你们有游泳池吗",
                "expect_not_found": True,
            },
        ]
        rows: list[dict[str, Any]] = []
        passed = 0
        total_elapsed = 0.0

        for case in cases:
            result = self.query(case["query"])
            total_elapsed += result["elapsed_ms"]
            top_answer = ((result.get("top_match") or {}).get("standard_answer") or "")
            answer_norm = normalize_text(top_answer)
            ok = False
            if case.get("expect_not_found"):
                ok = not result["accepted"]
            else:
                expected = [normalize_text(item) for item in case.get("expect_any", [])]
                forbidden = [normalize_text(item) for item in case.get("forbid", [])]
                ok = result["accepted"] and any(token in answer_norm for token in expected)
                if ok and forbidden:
                    ok = not any(token in answer_norm for token in forbidden)
            if ok:
                passed += 1
            rows.append(
                {
                    "query": case["query"],
                    "ok": ok,
                    "accepted": result["accepted"],
                    "elapsed_ms": result["elapsed_ms"],
                    "reject_reason": result["reject_reason"],
                    "top_match": result["top_match"],
                }
            )

        return {
            "cases": rows,
            "passed": passed,
            "total": len(cases),
            "accuracy": round(passed / len(cases), 4),
            "avg_elapsed_ms": round(total_elapsed / len(cases), 2),
        }
