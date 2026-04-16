from __future__ import annotations

import re

from .lexicon import get_clarify_question
from .normalize import normalize_faq_text
from .retrieve import RetrievedFaqCandidate, detect_faq_signals
from .types import FaqMatch


BROAD_QUERY_PATTERN = re.compile(r"怎么|如何|怎么办|怎样|能否|可以吗|能吗|行吗|要不要|是否")


def clamp_score(value: float) -> float:
    return max(0.0, min(1.0, round(value, 3)))


def contains_any(text: str, keywords: list[str]) -> bool:
    normalized = normalize_faq_text(text)
    return any(normalize_faq_text(keyword) in normalized for keyword in keywords)


def rerank_faq_candidates(query: str, candidates: list[RetrievedFaqCandidate]) -> list[FaqMatch]:
    normalized_query = normalize_faq_text(query)
    query_signals = detect_faq_signals(query)
    concrete_signals = [signal for signal in query_signals if signal != "generic_question"]
    has_generic_question = bool(BROAD_QUERY_PATTERN.search(normalized_query))

    results: list[FaqMatch] = []
    for candidate in candidates:
        score = candidate.score
        reasons = list(candidate.reasons)
        entry = candidate.entry

        matched_intent_signal = entry.intent in query_signals
        matched_sub_intent_signal = entry.subIntent in query_signals

        if matched_intent_signal:
            score += 0.05
            reasons.append(f"intent:{entry.intent}")
        if matched_sub_intent_signal:
            score += 0.15
            reasons.append(f"subIntent:{entry.subIntent}")
        if entry.clarifyGroup and has_generic_question and not matched_sub_intent_signal:
            score -= 0.04
            reasons.append("generic_question_penalty")
        if not concrete_signals and not candidate.matchedKeywords and not candidate.matchedSignals:
            score -= 0.16
            reasons.append("no_domain_signal_penalty")
        if entry.negativeKeywords and contains_any(normalized_query, entry.negativeKeywords):
            score -= min(0.22, len(entry.negativeKeywords) * 0.06)
            reasons.append(f"negative:{','.join(entry.negativeKeywords[:4])}")
        if "pet" in query_signals and entry.intent != "pet":
            score -= 0.35
            reasons.append("pet_mismatch")
        if "pool" in query_signals and entry.intent != "pool":
            score -= 0.4
            reasons.append("pool_mismatch")
        if "parking_reservation" in query_signals and entry.intent == "parking" and entry.subIntent != "parking_reservation":
            score -= 0.32
            reasons.append("parking_reservation_mismatch")
        if "parking_exists" in query_signals and entry.intent == "parking" and entry.subIntent == "parking_exists":
            score += 0.08
            reasons.append("bonus:parking_exists")
        if "invoice_apply" in query_signals and entry.intent == "invoice" and entry.subIntent == "invoice_apply":
            score += 0.08
            reasons.append("bonus:invoice_apply")
        if "invoice_special" in query_signals and entry.intent == "invoice" and entry.subIntent != "invoice_special":
            score -= 0.08
        if "location_station_distance" in query_signals and entry.intent == "location" and entry.subIntent != "location_station_distance":
            score -= 0.12
        if "location_navigation_name" in query_signals and entry.intent == "location" and entry.subIntent != "location_navigation_name":
            score -= 0.12
        if "location_navigation_name" in query_signals and entry.subIntent == "location_navigation_name":
            score += 0.12
            reasons.append("bonus:location_navigation_name")
        if "location_nearby_recommendation" in query_signals and entry.intent == "location" and entry.subIntent == "location_nearby_recommendation":
            score += 0.1
        if "breakfast" in query_signals and entry.intent == "breakfast" and not matched_sub_intent_signal:
            score += 0.03
        if "breakfast_exists" in query_signals and entry.intent == "breakfast" and entry.subIntent == "breakfast_exists":
            score += 0.12
            reasons.append("bonus:breakfast_exists")
        if "parking_fee" in query_signals and entry.intent == "parking" and entry.subIntent == "parking_fee":
            score += 0.08
        if "parking_entrance" in query_signals and entry.intent == "parking" and entry.subIntent == "parking_entrance":
            score += 0.08
        if "invoice_title" in query_signals and entry.intent == "invoice" and entry.subIntent == "invoice_title":
            score += 0.08
        if "invoice_time" in query_signals and entry.intent == "invoice" and entry.subIntent == "invoice_time":
            score += 0.08
        if "checkout_time" in query_signals and entry.intent == "checkout" and entry.subIntent == "checkout_time":
            score += 0.12
            reasons.append("bonus:checkout_time")
        if "voice_control_aircon" in query_signals and entry.subIntent == "voice_control_aircon":
            score += 0.12
            reasons.append("bonus:voice_control_aircon")
        if "voice_control_aircon" in query_signals and entry.subIntent == "handoff_aircon":
            score -= 0.24
            reasons.append("aircon_howto_not_handoff")
        if "handoff_aircon" in query_signals and entry.subIntent == "voice_control_aircon":
            score -= 0.18
            reasons.append("aircon_fault_not_service")
        if "projector_info" in query_signals and entry.subIntent == "projector_info":
            score += 0.18
            reasons.append("bonus:projector_info")
        if "projector_info" in query_signals and entry.subIntent == "handoff_projector":
            score -= 0.28
            reasons.append("projector_howto_not_handoff")
        if "handoff_projector" in query_signals and entry.subIntent == "projector_info":
            score -= 0.14
            reasons.append("projector_fault_not_service")
        if any(signal.startswith("handoff_") for signal in query_signals):
            if entry.subIntent and entry.subIntent in query_signals:
                score += 0.18
                reasons.append(f"handoff:{entry.subIntent}")
            elif entry.handoff:
                score -= 0.06
                reasons.append("handoff_other_penalty")
            elif not entry.handoff:
                score -= 0.22
                reasons.append("handoff_penalty")
        if "handoff_room_info" in query_signals and entry.subIntent == "handoff_room_info":
            score += 0.12
        if "handoff_checkin_issue" in query_signals and entry.subIntent == "handoff_checkin_issue":
            score += 0.12
        if "handoff_laundry_issue" in query_signals and entry.subIntent == "handoff_laundry_issue":
            score += 0.12
        if "handoff_equipment" in query_signals and entry.subIntent == "handoff_equipment":
            score += 0.08
        if "handoff_cleanliness" in query_signals and entry.subIntent == "handoff_cleanliness":
            score += 0.08
        if "handoff_lost_found" in query_signals and entry.subIntent == "handoff_lost_found":
            score += 0.08
        if "handoff_cleaning_contact" in query_signals and entry.subIntent == "handoff_cleaning_contact":
            score += 0.16
        if "handoff_transfer_generic" in query_signals and entry.subIntent == "handoff_transfer_generic":
            score += 0.18
        if "handoff_transfer_generic" in query_signals and entry.subIntent == "handoff_lost_found":
            score -= 0.12
            reasons.append("transfer_generic_not_lost_found")
        if "handoff_cleaning_contact" in query_signals and entry.subIntent == "handoff_lost_found":
            score -= 0.18
            reasons.append("cleaning_contact_not_lost_found")
        if "laundry_access" in query_signals and entry.subIntent == "laundry_access":
            score += 0.1
        if "luggage" in query_signals and entry.subIntent == "luggage_storage":
            score += 0.05

        score = clamp_score(score)
        results.append(
            FaqMatch(
                id=entry.id,
                canonicalQuestion=entry.canonicalQuestion,
                answer=entry.answer,
                intent=entry.intent,
                subIntent=entry.subIntent,
                score=score,
                reasons=reasons,
            )
        )

    return sorted(results, key=lambda item: item.score, reverse=True)


def get_clarify_message(intent: str) -> str:
    return get_clarify_question(intent) or "请问您是想了解酒店哪一方面的信息？"
