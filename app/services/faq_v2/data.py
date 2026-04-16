from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from .types import FaqEntry


BASE_DIR = Path(__file__).resolve().parents[3]
DATA_DIR = BASE_DIR / "data" / "faq_v2"
CLUSTERS_PATH = DATA_DIR / "hotel-faq.clusters.json"
MANUAL_PATH = DATA_DIR / "hotel-faq.manual.json"

HANDOFF_ANSWERS: dict[str, str] = {
    "handoff_door_lock": "这个需要为您转给门店管家协助处理门锁或入门问题，请稍等。",
    "handoff_room_info": "这个需要为您转给门店管家核对房间信息，请稍等。",
    "handoff_checkin_issue": "这个需要为您转给门店管家协助处理入住登记问题，请稍等。",
    "handoff_laundry_issue": "这个需要为您转给门店管家协助处理洗衣设备问题，请稍等。",
    "handoff_aircon": "这个需要为您转给门店管家协助处理空调问题，请稍等。",
    "handoff_projector": "这个需要为您转给门店管家协助处理投屏或投影问题，请稍等。",
    "handoff_cleanliness": "这个需要为您转给门店管家协助处理卫生或异味问题，请稍等。",
    "handoff_refund_change": "这个需要为您转给门店管家协助处理退款或订单变更，请稍等。",
    "handoff_change_room": "这个需要为您转给门店管家协助处理换房需求，请稍等。",
    "handoff_noise": "这个需要为您转给门店管家协助处理噪音问题，请稍等。",
    "handoff_lost_found": "这个需要为您转给门店管家协助处理失物或代寄问题，请稍等。",
    "handoff_cleaning_contact": "这个需要为您转给门店管家协助联系保洁或管家，请稍等。",
    "handoff_vehicle_exit": "这个需要为您转给门店管家协助处理出车问题，请稍等。",
    "handoff_equipment": "这个需要为您转给门店管家协助处理设备故障，请稍等。",
    "handoff_amenity_request": "这个需要为您转给门店管家协助处理物品补给或取送需求，请稍等。",
    "handoff_transfer_generic": "这个需要为您转给门店管家继续处理，请稍等。",
}

CLARIFY_GROUP_BY_INTENT: dict[str, str | None] = {
    "parking": "parking",
    "invoice": "invoice",
    "checkout": "checkout",
    "breakfast": "breakfast",
    "location": "location",
    "service": "service",
    "handoff": "service",
}


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if not item:
            continue
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _build_negative_keywords(intent: str, sub_intent: str) -> list[str]:
    negatives: list[str] = []
    if intent == "parking":
        if sub_intent != "parking_fee":
            negatives.extend(["收费", "免费", "费用", "多少钱"])
        if sub_intent != "parking_entrance":
            negatives.extend(["入口", "怎么进", "从哪", "辅路"])
        if sub_intent != "parking_duration":
            negatives.extend(["多久", "多长", "最久", "最长"])
        if sub_intent != "parking_charging_pile":
            negatives.extend(["充电", "充电桩", "新能源"])
        if sub_intent != "parking_reservation":
            negatives.extend(["预约", "报备"])
    if intent == "invoice":
        if sub_intent != "invoice_special":
            negatives.extend(["专票", "增值税专票"])
        if sub_intent != "invoice_normal":
            negatives.extend(["普票", "增值税普票"])
        if sub_intent != "invoice_title":
            negatives.extend(["抬头", "税号", "名称"])
        if sub_intent != "invoice_time":
            negatives.extend(["多久", "几天", "时间", "何时"])
    if intent == "location":
        if sub_intent != "location_station_distance":
            negatives.extend(["南站", "高铁南站", "远吗", "多久", "打车"])
        if sub_intent != "location_navigation_name":
            negatives.extend(["导航", "搜什么", "店名", "地图"])
        if sub_intent != "location_nearby_recommendation":
            negatives.extend(["附近", "游玩", "攻略", "商场"])
    if intent == "service":
        if sub_intent != "microwave":
            negatives.extend(["微波炉", "加热"])
        if sub_intent != "laundry_room":
            negatives.extend(["洗衣房", "洗衣机", "烘干机"])
        if sub_intent != "laundry_access":
            negatives.extend(["洗衣房门", "刷脸开门", "密码"])
        if sub_intent != "amenity_shaving_razor":
            negatives.extend(["剃须刀", "刮胡刀"])
        if sub_intent != "meeting_room":
            negatives.extend(["会议室", "开会"])
        if sub_intent != "gym_info":
            negatives.extend(["健身房", "健身"])
    if intent == "handoff":
        if sub_intent != "handoff_lost_found":
            negatives.extend(["失物", "落在", "落房间", "忘在"])
        if sub_intent != "handoff_change_room":
            negatives.extend(["换房", "换房型", "换个房间"])
        if sub_intent != "handoff_noise":
            negatives.extend(["噪音", "太吵", "施工", "睡不着"])
        if sub_intent != "handoff_aircon":
            negatives.extend(["空调", "制热", "制冷"])
        if sub_intent != "handoff_room_info":
            negatives.extend(["房间号", "房号"])
        if sub_intent != "handoff_checkin_issue":
            negatives.extend(["登记异常", "登记失败", "人脸识别失败"])
        if sub_intent == "handoff_transfer_generic":
            negatives.extend(
                [
                    "停车",
                    "停车场",
                    "收费",
                    "发票",
                    "早餐",
                    "高铁南站",
                    "南站",
                    "导航",
                    "地图",
                    "剃须刀",
                    "洗衣房",
                    "微波炉",
                    "健身房",
                    "会议室",
                    "床单",
                    "污渍",
                ]
            )
    return _unique(negatives)


def _build_entry(cluster: dict[str, Any], overrides: dict[str, Any]) -> FaqEntry:
    override = overrides.get(cluster["sub_intent"], {})
    aliases = _unique(
        [
            override.get("canonicalQuestion"),
            cluster["sample_questions"][0] if cluster.get("sample_questions") else None,
            *cluster.get("sample_questions", []),
            *[item.get("question", "") for item in cluster.get("source_questions", [])],
            *override.get("aliases", []),
        ]
    )
    answer = override.get("answer") or (
        HANDOFF_ANSWERS.get(cluster["sub_intent"], HANDOFF_ANSWERS["handoff_transfer_generic"])
        if cluster.get("status") == "transfer" or cluster["sub_intent"].startswith("handoff_")
        else cluster["canonical_answer"]
    )
    keywords = _unique(
        [
            cluster["intent"],
            cluster["sub_intent"],
            *aliases,
            cluster["canonical_answer"],
            *override.get("keywords", []),
        ]
    )
    return FaqEntry(
        id=cluster["cluster_id"],
        canonicalQuestion=override.get("canonicalQuestion") or aliases[0] or cluster["cluster_id"],
        aliases=aliases,
        answer=answer,
        intent=cluster["intent"],
        subIntent=cluster["sub_intent"],
        keywords=keywords,
        negativeKeywords=_unique(_build_negative_keywords(cluster["intent"], cluster["sub_intent"]) + override.get("negativeKeywords", [])),
        handoff=bool(cluster.get("status") == "transfer" or cluster["sub_intent"].startswith("handoff_")),
        clarifyGroup=override.get("clarifyGroup") or CLARIFY_GROUP_BY_INTENT.get(cluster["intent"]),
    )


def _build_manual_entry(entry: dict[str, Any]) -> FaqEntry:
    return FaqEntry(
        id=entry["id"],
        canonicalQuestion=entry["canonicalQuestion"],
        aliases=_unique([entry["canonicalQuestion"], *entry.get("aliases", [])]),
        answer=entry["answer"],
        intent=entry["intent"],
        subIntent=entry["subIntent"],
        keywords=_unique(
            [
                entry["intent"],
                entry["subIntent"],
                entry["canonicalQuestion"],
                *entry.get("aliases", []),
                *entry.get("keywords", []),
            ]
        ),
        negativeKeywords=_unique(entry.get("negativeKeywords", [])),
        handoff=entry.get("handoff", False),
        clarifyGroup=entry.get("clarifyGroup") or CLARIFY_GROUP_BY_INTENT.get(entry["intent"]),
    )


@lru_cache(maxsize=1)
def load_faq_v2_entries() -> list[FaqEntry]:
    clusters = _load_json(CLUSTERS_PATH)
    manual = _load_json(MANUAL_PATH) if MANUAL_PATH.exists() else {}
    overrides = manual.get("subIntentOverrides", {})
    entries = [_build_entry(cluster, overrides) for cluster in clusters]
    entries.extend(_build_manual_entry(entry) for entry in manual.get("manualEntries", []))
    return entries
