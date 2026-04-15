from __future__ import annotations

import argparse
import collections
import concurrent.futures as futures
import json
import math
import os
import random
import re
import statistics
import textwrap
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.search import normalize_text, tokenize

DEFAULT_INDEX_PATH = ROOT / "data" / "faq_index.json"
DEFAULT_REPORT_PATH = ROOT / "docs" / "faq_semantic_pressure_report_v2.md"
DEFAULT_BASE_URL = os.getenv("FAQ_SEMANTIC_BASE_URL", "http://127.0.0.1:12000")

PREFIXES = [
    "请问",
    "麻烦问下，",
    "我想问下，",
    "我这边想了解一下，",
    "想咨询一下，",
    "方便问下，",
    "您好，",
    "能不能说下，",
]

SUFFIXES = [
    "呀？",
    "呢？",
    "啊？",
    "吧？",
    "可以吗？",
    "行不行？",
    "是这样吗？",
    "麻烦说一下。",
]

CATEGORY_SCENES: dict[str, list[str]] = {
    "parking": [
        "我自己开车过去",
        "我开车到店",
        "车要停一晚上",
        "我这边要停车",
        "我想把车放一下",
    ],
    "breakfast": [
        "我早上想吃点东西",
        "早饭我想安排一下",
        "一大早到店",
        "我想问问早上的餐",
        "我这边想吃早餐",
    ],
    "invoice": [
        "我退房后再开票",
        "我想补开票",
        "我想开电子发票",
        "我得填抬头",
        "我这边要申领发票",
    ],
    "checkout": [
        "我想晚点走",
        "我可能要延迟退房",
        "我明天再走",
        "我这边想晚点离店",
        "我不想太早退房",
    ],
    "checkin": [
        "我晚上会到店",
        "我可能很晚才到",
        "我想确认入住",
        "我这边准备办入住",
        "我到店时间可能比较晚",
    ],
    "route": [
        "我从南站过去",
        "我准备导航过去",
        "我开车过去怎么走",
        "我从地铁站过去",
        "我想知道怎么到店",
    ],
    "floor": [
        "我想确认楼层",
        "我想知道在几层",
        "我这边想看哪一层",
        "我想找楼上房间",
        "我想问问楼层安排",
    ],
    "facility": [
        "我想问一下设施",
        "我想了解酒店配套",
        "我需要看一下服务设施",
        "我想确认有没有这个功能",
        "我想知道店里有没有这个",
    ],
    "supplies": [
        "我需要一些房间用品",
        "我想取点日用品",
        "我这边想拿一下用品",
        "我想确认房间里有没有",
        "我需要去哪里拿这个东西",
    ],
    "meeting_room": [
        "我们临时想开个会",
        "我想找个开会地方",
        "我们要一个小会议空间",
        "我这边需要会客室",
        "我们想临时开个小会",
    ],
    "dark_room": [
        "我不想住没有窗户的房间",
        "我想要有窗户的房间",
        "我想确认是不是无窗房",
        "我想避开暗房",
        "我这边不考虑没窗的房型",
    ],
    "handoff": [
        "我这边想找工作人员处理",
        "这个情况我需要联系前台",
        "我想让门店帮我看一下",
        "这个问题我想找人工",
        "我需要门店管家协助",
    ],
    "other": [
        "我想确认一下",
        "我想问得细一点",
        "我想了解这个",
        "我这边有点不确定",
        "我需要确认一下细节",
    ],
}

CATEGORY_HINTS: dict[str, list[str]] = {
    "parking": ["停车场", "车位", "停车费", "免费停车", "入口", "辅路", "充电桩", "进车口"],
    "breakfast": ["早餐", "早饭", "含早", "早餐券", "吃的"],
    "invoice": ["发票", "开票", "抬头", "税号", "电子票", "普票", "专票"],
    "checkout": ["退房", "离店", "退住", "延时", "晚点走"],
    "checkin": ["入住", "办入住", "前台", "晚到", "半夜到", "刷脸"],
    "route": ["路线", "怎么走", "位置", "南站", "高铁", "地铁", "导航", "店名"],
    "floor": ["楼层", "几楼", "哪层", "电梯"],
    "facility": ["设施", "洗衣房", "健身房", "游泳池", "泳池", "电梯", "空调"],
    "supplies": ["用品", "剃须刀", "刮胡刀", "毛巾", "针线包", "浴巾", "枕头", "床单"],
    "meeting_room": ["会议室", "开会", "会客室", "小会"],
    "dark_room": ["暗房", "无窗", "没窗", "窗户"],
    "handoff": ["转接", "人工", "前台", "工作人员", "门店管家"],
}

INTENT_HINTS: dict[str, list[str]] = {
    "existence": ["有", "有没有", "是否有", "能不能", "提供"],
    "price": ["收费", "费用", "价格", "免费", "收钱"],
    "location": ["在哪", "哪里", "哪儿", "怎么走", "入口", "放哪", "哪层"],
    "time": ["几点", "什么时候", "最晚", "多久", "时间"],
    "procedure": ["怎么", "如何", "办理", "申请", "预约", "开", "拿"],
    "general": ["吗", "呢", "啊", "嘛"],
}

NEGATIVE_TOPICS = [
    "游泳池",
    "桑拿",
    "酒吧",
    "儿童乐园",
    "机场接送",
    "接送机",
    "机场班车",
    "电竞房",
    "私人影院",
    "棋牌室",
    "洗碗机",
    "按摩浴缸",
]

NEGATIVE_TEMPLATES = [
    "你们有{topic}吗？",
    "可以提供{topic}吗？",
    "我这边能不能安排{topic}？",
    "如果我想要{topic}，酒店能弄吗？",
]

REWRITE_MAP: dict[str, list[str]] = {
    "停车场": ["车位", "停车位", "停车"],
    "停车": ["车位", "停车位", "停车场"],
    "停车费": ["收费", "停车场收费", "停车要花钱吗"],
    "发票": ["开票", "电子发票", "票据"],
    "抬头": ["名称", "开票名称", "发票抬头"],
    "税号": ["统一社会信用代码", "纳税识别号"],
    "早餐": ["早饭", "早上吃的"],
    "退房": ["离店", "退住"],
    "入住": ["办入住", "办理入住"],
    "路线": ["怎么走", "导航", "到店路线"],
    "会议室": ["开会地方", "小会议室"],
    "剃须刀": ["刮胡刀", "一次性剃须刀"],
    "暗房": ["无窗房", "没窗户的房间"],
    "Wi-Fi": ["无线网", "无线网密码"],
    "洗衣房": ["洗衣间", "洗衣间在哪"],
}

STOP_WORDS = [
    "吗",
    "嘛",
    "呢",
    "呀",
    "啊",
    "吧",
    "么",
    "呀",
    "呢？",
    "吗？",
    "可以吗",
    "行不行",
    "对吗",
    "好吗",
]


@dataclass
class Case:
    kind: str
    query: str
    expected_faq_id: str | None
    expected_category: str
    expected_intent: str
    source_item: str | None = None
    source_alias: str | None = None


@dataclass
class CaseResult:
    case: Case
    response: dict[str, Any]


def load_items(index_path: Path) -> list[dict[str, Any]]:
    payload = json.loads(index_path.read_text(encoding="utf-8"))
    items = payload.get("items", [])
    if not isinstance(items, list):
        raise ValueError(f"FAQ index missing items list: {index_path}")
    return items


def infer_category(text: str) -> str:
    normalized = normalize_text(text)
    if "车" in normalized and ("停" in normalized or "收费" in normalized or "收钱" in normalized):
        return "parking"
    if "车位" in normalized or "停车位" in normalized or "进车口" in normalized or "辅路" in normalized:
        return "parking"
    if "南站" in normalized or "高铁" in normalized or ("过来" in normalized and "走" in normalized):
        return "route"
    if "导航" in normalized or "店名" in normalized or "美团" in normalized or "携程" in normalized:
        return "route"
    if "发票" in normalized or "开票" in normalized or "税号" in normalized or "抬头" in normalized:
        return "invoice"
    if "早餐" in normalized or "早饭" in normalized or "含早" in normalized:
        return "breakfast"
    if "最晚" in normalized or "退房" in normalized or "离店" in normalized or "退住" in normalized:
        return "checkout"
    if "入住" in normalized or "办入住" in normalized or "晚到" in normalized or "半夜到" in normalized:
        return "checkin"
    if "刮胡刀" in normalized or "剃须刀" in normalized:
        return "supplies"
    if "游泳池" in normalized or "泳池" in normalized:
        return "facility"
    if ("没窗" in normalized or "无窗" in normalized) and "房" in normalized:
        return "dark_room"
    if "会议室" in normalized or "开会" in normalized or "会客室" in normalized:
        return "meeting_room"
    for category, hints in CATEGORY_HINTS.items():
        if any(hint in normalized for hint in hints):
            return category
    return "other"


def infer_intent(text: str) -> str:
    normalized = normalize_text(text)
    if any(hint in normalized for hint in ["收费", "费用", "价格", "收钱"]):
        return "price"
    if any(hint in normalized for hint in ["最晚", "几点", "什么时候", "时间", "多久"]):
        return "time"
    if any(hint in normalized for hint in ["怎么", "如何", "办理", "申请", "预约", "开", "拿", "怎么弄"]):
        return "procedure"
    if any(hint in normalized for hint in ["在哪", "哪里", "哪儿", "怎么走", "入口", "放哪", "哪层"]):
        return "location"
    if any(hint in normalized for hint in ["有", "有没有", "是否有", "能不能", "提供"]):
        return "existence"
    return "general"


def trim_symbols(text: str) -> str:
    text = re.sub(r"[\s\u3000]+", "", text)
    text = text.strip().strip("？?！!。.,，；;：:")
    return text


def strip_prefix_suffix(text: str) -> str:
    text = trim_symbols(text)
    prefixes = ["请问", "麻烦问下", "麻烦问一下", "我想问下", "我想问一下", "想问下", "想问一下", "能不能", "可不可以", "请", "您好", "你好", "方便问下", "我这边想了解一下", "我想了解一下", "想咨询一下", "我想咨询一下", "帮我看下", "问一下"]
    suffixes = ["吗", "嘛", "呢", "呀", "啊", "吧", "么", "呀呀", "可以吗", "行不行", "对吗", "好吗"]
    for prefix in sorted(prefixes, key=len, reverse=True):
        if text.startswith(prefix):
            text = text[len(prefix):]
            break
    for suffix in sorted(suffixes, key=len, reverse=True):
        if text.endswith(suffix):
            text = text[:-len(suffix)]
            break
    text = re.sub(r"^(你们家|你们|贵店|咱们酒店|咱们|酒店|这边|店里|门店)", "", text)
    text = re.sub(r"(可以吗|行不行|好不好|对吗|吗|嘛|呢|呀|啊|吧|么)$", "", text)
    text = trim_symbols(text)
    return text or trim_symbols(text)


def replace_synonyms(text: str, category: str) -> str:
    replacements = REWRITE_MAP.get(category, [])
    result = text
    for source, targets in REWRITE_MAP.items():
        if source in result and targets:
            result = result.replace(source, targets[0])
    # generic colloquial swaps
    result = result.replace("你们家", "你们")
    result = result.replace("酒店", "这边") if len(result) > 6 else result
    result = result.replace("有没有", "有没")
    result = result.replace("可不可以", "能不能")
    result = result.replace("能够", "能")
    result = result.replace("请问", "")
    result = result.replace("麻烦问下", "")
    result = result.replace("麻烦问一下", "")
    result = result.replace("我想问下", "")
    result = result.replace("我想问一下", "")
    result = result.replace("想问下", "")
    result = result.replace("想问一下", "")
    result = result.replace("可以吗", "不")
    result = result.replace("行不行", "不")
    result = trim_symbols(result)
    return result


def extract_focus(alias: str, answer: str) -> str:
    base = strip_prefix_suffix(alias)
    # prefer shorter, cleaner nouns from alias; fallback to a short span from answer when alias is too verbose
    if len(base) >= 3:
        return base
    answer_hint = strip_prefix_suffix(answer[:24])
    return base or answer_hint


def category_scene(category: str, rng: random.Random) -> str:
    scenes = CATEGORY_SCENES.get(category) or CATEGORY_SCENES["other"]
    return rng.choice(scenes)


def intent_template(intent: str, focus: str, category: str, scene: str) -> str:
    if intent == "price":
        return f"{scene}，{focus}要另外收钱吗"
    if intent == "location":
        return f"{scene}的话，{focus}在哪儿"
    if intent == "time":
        return f"{scene}，{focus}最晚什么时候"
    if intent == "procedure":
        return f"{scene}，{focus}怎么弄"
    if intent == "existence":
        return f"{scene}，{focus}有没有"
    return f"{scene}，{focus}怎么样"


def build_direct_cases(item: dict[str, Any], rng: random.Random, target: int = 8) -> list[Case]:
    aliases = [trim_symbols(a) for a in item.get("aliases", []) if trim_symbols(a)]
    if not aliases:
        aliases = [trim_symbols(item["standard_answer"])[:20] or item["faq_id"]]
    category = infer_category(" ".join(aliases) + " " + item.get("standard_answer", ""))
    intent = infer_intent(" ".join(aliases) + " " + item.get("standard_answer", ""))
    focus = extract_focus(aliases[0], item.get("standard_answer", ""))
    scene_pool = CATEGORY_SCENES.get(category, CATEGORY_SCENES["other"])
    scene = scene_pool[0] if scene_pool else "我这边"
    alias = aliases[0]
    alias_short = strip_prefix_suffix(alias) or alias
    intent_phrase = {
        "price": "要另外收钱不",
        "location": "在哪儿",
        "time": "最晚什么时候",
        "procedure": "怎么弄",
        "existence": "有没有",
        "general": "怎么样",
    }.get(intent, "怎么样")
    selected = [
        f"请问{alias}",
        f"麻烦问下，{focus}怎么弄",
        f"{scene}，{focus}{intent_phrase}",
        f"我这边想了解一下，{focus}",
        f"{focus}有没有呀",
        f"{scene}的话，{focus}怎么处理",
        f"那{focus}呢",
        f"{alias_short}可以吗",
    ][:target]

    return [
        Case(
            kind="direct",
            query=q,
            expected_faq_id=item["faq_id"],
            expected_category=category,
            expected_intent=intent,
            source_item=item["faq_id"],
            source_alias=aliases[i % len(aliases)],
        )
        for i, q in enumerate(selected)
    ]


def build_handoff_cases(item: dict[str, Any], rng: random.Random, target: int = 8) -> list[Case]:
    aliases = [trim_symbols(a) for a in item.get("aliases", []) if trim_symbols(a)]
    focus = extract_focus(aliases[0] if aliases else "转接", item.get("standard_answer", "")) or "转接"
    selected = [
        f"请问{focus}",
        f"麻烦问下，{focus}怎么处理",
        f"我这边想问下，{focus}怎么办",
        f"{focus}这个情况怎么处理",
        f"如果出现{focus}，要找谁",
        f"{focus}需要人工帮忙吗",
        f"{focus}可以直接找前台吗",
        f"{focus}要怎么转接",
    ][:target]

    return [
        Case(
            kind="handoff",
            query=q,
            expected_faq_id=item["faq_id"],
            expected_category="handoff",
            expected_intent="general",
            source_item=item["faq_id"],
            source_alias=aliases[i % len(aliases)] if aliases else None,
        )
        for i, q in enumerate(selected[:target])
    ]


def build_negative_cases(count: int, rng: random.Random) -> list[Case]:
    topics = NEGATIVE_TOPICS[:]
    rng.shuffle(topics)
    queries: list[str] = []
    templates = [
        "你们有{topic}吗？",
        "可以提供{topic}吗？",
        "我这边能不能安排{topic}？",
        "如果我想要{topic}，酒店能弄吗？",
    ]
    while len(queries) < count:
        topic = topics[len(queries) % len(topics)]
        template = templates[len(queries) % len(templates)]
        queries.append(template.format(topic=topic))
    final = queries[:count]
    idx = 0
    while len(final) < count:
        topic = topics[idx % len(topics)]
        q = f"你们有{topic}吗？"
        idx += 1
        final.append(q)
    return [
        Case(
            kind="negative",
            query=q,
            expected_faq_id=None,
            expected_category="unknown",
            expected_intent="general",
        )
        for q in final[:count]
    ]


def build_cases(items: list[dict[str, Any]], total: int = 1000, direct_per_item: int = 8, handoff_per_item: int = 8, negative_count: int = 48, seed: int = 42) -> list[Case]:
    rng = random.Random(seed)
    direct_items = [item for item in items if item.get("answer_type") == "direct"]
    handoff_items = [item for item in items if item.get("answer_type") == "handoff"]
    direct_cases: list[Case] = []
    for item in direct_items:
        direct_cases.extend(build_direct_cases(item, rng, target=direct_per_item))
    handoff_cases: list[Case] = []
    for item in handoff_items:
        handoff_cases.extend(build_handoff_cases(item, rng, target=handoff_per_item))
    negative_cases = build_negative_cases(negative_count, rng)

    cases = direct_cases + handoff_cases + negative_cases
    # trim or top up to exact total
    if len(cases) > total:
        cases = cases[:total]
    elif len(cases) < total:
        needed = total - len(cases)
        extra = build_negative_cases(needed, rng)
        cases.extend(extra)
    return cases


async def _query_api_async(client: httpx.AsyncClient, query: str, timeout: float = 15.0) -> dict[str, Any]:
    response = await client.get(
        "/api/validate/faq-semantic/query",
        params={"q": query},
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()


def run_cases(base_url: str, cases: list[Case], max_workers: int = 16, timeout: float = 15.0) -> list[CaseResult]:
    results: list[CaseResult] = [None] * len(cases)  # type: ignore[assignment]
    base = base_url.rstrip("/")
    opener = None

    def one(idx: int, case: Case) -> tuple[int, CaseResult]:
        query = urlencode({"q": case.query})
        url = f"{base}/api/validate/faq-semantic/query?{query}"
        request = Request(url, headers={"Accept": "application/json"})
        try:
            with urlopen(request, timeout=timeout) as response:
                payload = response.read()
            data = json.loads(payload.decode("utf-8"))
        except Exception as exc:  # pragma: no cover - network failures recorded in report
            data = {
                "ok": False,
                "query": case.query,
                "accepted": False,
                "reject_reason": f"request-error:{type(exc).__name__}",
                "elapsed_ms": 0.0,
                "top_match": None,
                "candidates": [],
            }
        return idx, CaseResult(case=case, response=data)

    completed = 0
    with futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {executor.submit(one, idx, case): idx for idx, case in enumerate(cases)}
        for future in futures.as_completed(future_map):
            idx, result = future.result()
            results[idx] = result
            completed += 1
            if completed % 100 == 0 or completed == len(cases):
                print(f"[progress] completed {completed}/{len(cases)}", flush=True)
    return results


def _truncate(text: str, limit: int = 88) -> str:
    text = re.sub(r"\s+", "", text or "")
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def analyze(results: list[CaseResult]) -> dict[str, Any]:
    total = len(results)
    direct = [r for r in results if r.case.kind == "direct"]
    handoff = [r for r in results if r.case.kind == "handoff"]
    negative = [r for r in results if r.case.kind == "negative"]

    direct_hits = 0
    direct_misses: list[CaseResult] = []
    handoff_rejects = 0
    handoff_misses: list[CaseResult] = []
    negative_rejects = 0
    negative_false_accepts: list[CaseResult] = []

    elapsed_all = []
    per_category: dict[str, list[CaseResult]] = collections.defaultdict(list)
    failure_rows: list[dict[str, Any]] = []
    pattern_counter = collections.Counter()
    suggestion_counter = collections.Counter()

    for result in results:
        response = result.response
        elapsed_all.append(float(response.get("elapsed_ms") or 0.0))
        if result.case.expected_category != "unknown":
            per_category[result.case.expected_category].append(result)

        accepted = bool(response.get("accepted"))
        reject_reason = response.get("reject_reason") or ""
        top_match = response.get("top_match") or {}
        top_faq_id = top_match.get("faq_id")
        top_alias = top_match.get("alias") or ""
        top_answer = top_match.get("standard_answer") or ""
        top_category = top_match.get("category") or ""
        query_category = response.get("query_category") or ""
        query_intent = response.get("query_intent") or ""

        if result.case.kind == "direct":
            if accepted and top_faq_id == result.case.expected_faq_id:
                direct_hits += 1
            else:
                direct_misses.append(result)
                pattern = classify_failure_pattern(result, accepted, top_faq_id, top_category, reject_reason)
                pattern_counter[pattern] += 1
                suggestion = suggest_patch(result, response)
                if suggestion:
                    suggestion_counter[suggestion] += 1
                failure_rows.append(build_failure_row(result, response, pattern))
        elif result.case.kind == "handoff":
            if not accepted:
                handoff_rejects += 1
            else:
                handoff_misses.append(result)
                pattern_counter["handoff_false_accept"] += 1
                failure_rows.append(build_failure_row(result, response, "handoff_false_accept"))
        elif result.case.kind == "negative":
            if not accepted:
                negative_rejects += 1
            else:
                negative_false_accepts.append(result)
                pattern = classify_failure_pattern(result, accepted, top_faq_id, top_category, reject_reason)
                pattern_counter[pattern] += 1
                suggestion = suggest_patch(result, response)
                if suggestion:
                    suggestion_counter[suggestion] += 1
                failure_rows.append(build_failure_row(result, response, pattern))

    category_rows = []
    for category, rows in sorted(per_category.items(), key=lambda kv: (len(kv[1]), kv[0])):
        hit = 0
        for row in rows:
            response = row.response
            if bool(response.get("accepted")) and (response.get("top_match") or {}).get("faq_id") == row.case.expected_faq_id:
                hit += 1
        category_rows.append(
            {
                "category": category,
                "samples": len(rows),
                "hits": hit,
                "hit_rate": round(hit / len(rows), 4) if rows else 0.0,
                "avg_elapsed_ms": round(sum(float(r.response.get("elapsed_ms") or 0.0) for r in rows) / len(rows), 2),
            }
        )

    category_rows.sort(key=lambda row: (row["hit_rate"], -row["samples"], row["category"]))
    weakest = category_rows[:8]
    failure_rows = sorted(
        failure_rows,
        key=lambda row: (
            row["kind_rank"],
            row["expected_category"],
            -row["elapsed_ms"],
            row["query"],
        ),
    )

    total_handed = len(handoff)
    return {
        "total": total,
        "direct_total": len(direct),
        "direct_hits": direct_hits,
        "direct_hit_rate": round(direct_hits / len(direct), 4) if direct else 0.0,
        "handoff_total": len(handoff),
        "handoff_rejects": handoff_rejects,
        "handoff_reject_rate": round(handoff_rejects / len(handoff), 4) if handoff else 0.0,
        "negative_total": len(negative),
        "negative_rejects": negative_rejects,
        "negative_reject_rate": round(negative_rejects / len(negative), 4) if negative else 0.0,
        "avg_elapsed_ms": round(sum(elapsed_all) / len(elapsed_all), 2) if elapsed_all else 0.0,
        "category_rows": category_rows,
        "weakest": weakest,
        "failure_patterns": pattern_counter.most_common(10),
        "suggestions": suggestion_counter.most_common(20),
        "failures": failure_rows[:30],
        "direct_miss_count": len(direct_misses),
        "handoff_miss_count": len(handoff_misses),
        "negative_false_accept_count": len(negative_false_accepts),
    }


def classify_failure_pattern(result: CaseResult, accepted: bool, top_faq_id: str | None, top_category: str, reject_reason: str) -> str:
    query_category = result.response.get("query_category") or result.case.expected_category
    query_intent = result.response.get("query_intent") or result.case.expected_intent
    if not accepted:
        return f"reject:{reject_reason or 'unknown'}:{query_category}:{query_intent}"
    if result.case.kind == "negative":
        return f"false_accept:{query_category}:{query_intent}:{top_category or 'none'}"
    if top_faq_id != result.case.expected_faq_id:
        return f"wrong_faq:{query_category}:{query_intent}:{top_category or 'none'}"
    return f"other:{query_category}:{query_intent}"


def suggest_patch(result: CaseResult, response: dict[str, Any]) -> str:
    query = result.case.query
    category = response.get("query_category") or result.case.expected_category
    intent = response.get("query_intent") or result.case.expected_intent
    normalized = normalize_text(query)

    if result.case.kind == "negative":
        if any(topic in normalized for topic in ["游泳池", "桑拿", "酒吧", "儿童乐园", "机场接送", "接送机", "电竞房", "私人影院", "棋牌室", "洗碗机", "按摩浴缸"]):
            return f"unknown-guard:{query[:16]}"
        return f"unknown-guard:{category}:{intent}"

    if category == "parking":
        if any(tok in normalized for tok in ["车位", "停哪", "收钱", "入口", "辅路", "充电"]):
            return "parking-alias"
    if category == "invoice":
        if any(tok in normalized for tok in ["抬头", "税号", "名称", "开票"]):
            return "invoice-alias"
    if category == "route":
        if any(tok in normalized for tok in ["南站", "店名", "导航", "怎么走"]):
            return "route-alias"
    if category == "checkin":
        if any(tok in normalized for tok in ["晚到", "半夜", "前台", "入住"]):
            return "checkin-alias"
    if category == "checkout":
        if any(tok in normalized for tok in ["最晚", "晚点", "离店", "退住"]):
            return "checkout-alias"
    if category == "breakfast":
        if any(tok in normalized for tok in ["早饭", "含早", "吃的"]):
            return "breakfast-alias"
    if category == "meeting_room":
        if any(tok in normalized for tok in ["开会地方", "会客室", "小会"]):
            return "meeting-room-alias"
    if category == "supplies":
        if any(tok in normalized for tok in ["剃须刀", "刮胡刀", "针线包", "毛巾"]):
            return "supplies-alias"
    return f"{category}-rewrite:{intent}"


def build_failure_row(result: CaseResult, response: dict[str, Any], pattern: str) -> dict[str, Any]:
    top_match = response.get("top_match") or {}
    return {
        "kind_rank": 0 if result.case.kind == "negative" else 1 if result.case.kind == "handoff" else 2,
        "kind": result.case.kind,
        "query": result.case.query,
        "expected_faq_id": result.case.expected_faq_id,
        "expected_category": result.case.expected_category,
        "expected_intent": result.case.expected_intent,
        "accepted": bool(response.get("accepted")),
        "reject_reason": response.get("reject_reason"),
        "top_faq_id": top_match.get("faq_id"),
        "top_alias": top_match.get("alias"),
        "top_category": top_match.get("category"),
        "score": top_match.get("score"),
        "elapsed_ms": float(response.get("elapsed_ms") or 0.0),
        "pattern": pattern,
    }


def render_report(summary: dict[str, Any], results: list[CaseResult], report_path: Path, cases: list[Case]) -> str:
    total = summary["total"]
    direct_total = summary["direct_total"]
    handoff_total = summary["handoff_total"]
    negative_total = summary["negative_total"]
    lines: list[str] = []
    lines.append("# FAQ 语义匹配压测报告 V2")
    lines.append("")
    lines.append("## 压测口径")
    lines.append("")
    lines.append(f"- 数据源优先使用本地 `data/faq_index.json`，共 `{direct_total}` 条 `answer_type=direct` 的 FAQ 正样本，另保留 `{handoff_total}` 条 handoff 特殊样本。")
    lines.append(f"- 共生成 `{total}` 条中文口语化/模糊问法，其中 `{direct_total}` 条为 direct FAQ 变体，`{handoff_total}` 条为 handoff 特殊探针，`{negative_total}` 条为未知设施/拒答负样本。")
    lines.append("- 调用本地接口 `GET /api/validate/faq-semantic/query?q=...` 做真实验证。")
    lines.append("")
    lines.append("## 结果摘要")
    lines.append("")
    lines.append("| 类别 | 样本数 | 命中/拒答 | 平均耗时 |")
    lines.append("| --- | ---: | ---: | ---: |")
    lines.append(f"| direct FAQ | {direct_total} | 命中率 `{summary['direct_hit_rate'] * 100:.1f}%` | `{summary['avg_elapsed_ms']:.2f} ms` |")
    lines.append(f"| handoff 探针 | {handoff_total} | 拒答率 `{summary['handoff_reject_rate'] * 100:.1f}%` | `{summary['avg_elapsed_ms']:.2f} ms` |")
    lines.append(f"| unknown/refusal | {negative_total} | 拒答率 `{summary['negative_reject_rate'] * 100:.1f}%` | `{summary['avg_elapsed_ms']:.2f} ms` |")
    lines.append("")
    lines.append(f"- 总体平均耗时：`{summary['avg_elapsed_ms']:.2f} ms`")
    lines.append(f"- direct FAQ 知识命中数：`{summary['direct_hits']}/{direct_total}`")
    lines.append(f"- handoff 特殊探针正确拒答数：`{summary['handoff_rejects']}/{handoff_total}`")
    lines.append(f"- unknown/refusal 正确拒答数：`{summary['negative_rejects']}/{negative_total}`")
    lines.append("")
    lines.append("## 最弱类别")
    lines.append("")
    lines.append("| 类别 | 样本数 | 命中率 | 平均耗时 |")
    lines.append("| --- | ---: | ---: | ---: |")
    for row in summary["weakest"]:
        lines.append(f"| {row['category']} | {row['samples']} | `{row['hit_rate'] * 100:.1f}%` | `{row['avg_elapsed_ms']:.2f} ms` |")
    lines.append("")
    lines.append("## 最常见错误模式")
    lines.append("")
    if summary["failure_patterns"]:
        lines.append("| 模式 | 次数 |")
        lines.append("| --- | ---: |")
        for pattern, count in summary["failure_patterns"]:
            lines.append(f"| {pattern} | {count} |")
    else:
        lines.append("- 本轮无明显错误模式。")
    lines.append("")
    lines.append("## 建议补充的 alias / 改写规则")
    lines.append("")
    if summary["suggestions"]:
        lines.append("| 建议 | 次数 |")
        lines.append("| --- | ---: |")
        for suggestion, count in summary["suggestions"][:20]:
            lines.append(f"| {suggestion} | {count} |")
    else:
        lines.append("- 本轮没有收集到可继续收口的 alias 建议。")
    lines.append("")
    lines.append("## 30 个最有代表性的失败样例")
    lines.append("")
    lines.append("| # | 类型 | 问题 | 期望 | 实际/原因 | 耗时 |")
    lines.append("| --- | --- | --- | --- | --- | ---: |")
    failure_rows = summary["failures"]
    if not failure_rows:
        lines.append("| - | - | 无失败样例 | - | - | - |")
    else:
        for idx, row in enumerate(failure_rows[:30], start=1):
            if row["kind"] == "direct":
                expected = f"{row['expected_category']} / {row['expected_faq_id']}"
            elif row["kind"] == "handoff":
                expected = "handoff / 转接"
            else:
                expected = "unknown / 拒答"
            actual = row["reject_reason"] or f"{row['top_category']} / {row['top_faq_id']} / {row['pattern']}"
            lines.append(
                f"| {idx} | {row['kind']} | `{_truncate(row['query'], 30)}` | `{expected}` | `{_truncate(actual, 52)}` | `{row['elapsed_ms']:.2f}` |"
            )
    lines.append("")
    lines.append("## 说明")
    lines.append("")
    lines.append("- direct FAQ 统计口径为：`accepted=true` 且 `top_match.faq_id` 与期望 FAQ 一致。")
    lines.append("- handoff 探针用于验证 semantic 层是否误把转接类问题当作普通 FAQ 放行。")
    lines.append("- unknown/refusal 样本用于验证拒答稳定性。")
    lines.append("- 这版报告对应的测试集构成是：`118 * 8 = 944` 条 direct FAQ，`8` 条 handoff 探针，`48` 条 unknown/refusal。")
    lines.append("")
    lines.append("## 复现命令")
    lines.append("")
    lines.append("```bash")
    lines.append("python3 scripts/faq_semantic_pressure_v2.py --report docs/faq_semantic_pressure_report_v2.md")
    lines.append("```")

    report = "\n".join(lines) + "\n"
    report_path.write_text(report, encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="FAQ semantic pressure expansion v2")
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX_PATH)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--total", type=int, default=1000)
    parser.add_argument("--direct-per-item", type=int, default=8)
    parser.add_argument("--handoff-per-item", type=int, default=8)
    parser.add_argument("--negative-count", type=int, default=48)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    items = load_items(args.index)
    cases = build_cases(
        items,
        total=args.total,
        direct_per_item=args.direct_per_item,
        handoff_per_item=args.handoff_per_item,
        negative_count=args.negative_count,
        seed=args.seed,
    )

    # exact counts for our expected composition
    if len(cases) != args.total:
        raise RuntimeError(f"generated case count {len(cases)} != expected total {args.total}")

    if args.dry_run:
        print(json.dumps([asdict(case) for case in cases[:10]], ensure_ascii=False, indent=2))
        return 0

    results = run_cases(args.base_url, cases, max_workers=args.workers, timeout=args.timeout)
    summary = analyze(results)
    render_report(summary, results, args.report, cases)

    print(json.dumps(
        {
            "total": summary["total"],
            "direct_hit_rate": summary["direct_hit_rate"],
            "handoff_reject_rate": summary["handoff_reject_rate"],
            "negative_reject_rate": summary["negative_reject_rate"],
            "avg_elapsed_ms": summary["avg_elapsed_ms"],
            "report": str(args.report),
        },
        ensure_ascii=False,
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
