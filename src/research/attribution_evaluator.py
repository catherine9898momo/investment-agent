"""Deterministic attribution level evaluator."""

from __future__ import annotations

from src.research.models import AttributionCause, ResearchRunState, VerifiedFact


def evaluate_attribution_causes(run: ResearchRunState) -> list[AttributionCause]:
    price = _fact(run, "price_move")
    news = _fact(run, "news_events")
    sector = _fact(run, "sector_move")
    peers = _fact(run, "peer_moves")
    missing = [fact.fact_type for fact in run.missing_facts if fact.fact_type in {"sector_move", "peer_moves"}]

    support_ids = [fact.raw_fact_id or fact.id for fact in (price, news, sector, peers) if fact]
    if not support_ids:
        return [AttributionCause(
            label="当前证据不足以形成归因",
            level="unsupported",
            support_fact_ids=[],
            confidence="low",
            rationale="No citable price, news, sector, or peer facts are available.",
            next_checks=["补齐价格、新闻、板块和同行事实"],
        )]

    sector_success, sector_failure = _coverage(sector)
    peer_success, peer_failure = _coverage(peers)
    sector_peer_available = sector_success >= 2 and peer_success >= 2
    all_comparison_failed = (sector is not None or peers is not None) and sector_success == 0 and peer_success == 0

    if sector_peer_available and _directions_consistent(price, sector, peers):
        rationale = "Sector and peer coverage supports a likely factor."
        confidence = "medium"
        if sector_failure or peer_failure:
            rationale += " Partial symbol failures remain."
        return [AttributionCause(
            label="板块/同行同步波动",
            level="likely_factor",
            support_fact_ids=support_ids,
            missing_fact_types=missing,
            confidence=confidence,
            rationale=rationale,
            next_checks=_partial_next_checks(sector, peers),
        )]

    rationale = "Comparison coverage is insufficient for a likely factor." if all_comparison_failed else "Price/news evidence is present but sector/peer confirmation is incomplete."
    return [AttributionCause(
        label="短期价格与新闻线索",
        level="candidate_factor",
        support_fact_ids=support_ids,
        missing_fact_types=missing or _missing_from_absence(sector, peers),
        confidence="low",
        rationale=rationale,
        next_checks=["补齐 sector_move 和 peer_moves 后再升级归因等级"],
    )]


def _fact(run: ResearchRunState, fact_type: str) -> VerifiedFact | None:
    return next((fact for fact in run.verified_facts if fact.fact_type == fact_type), None)


def _coverage(fact: VerifiedFact | None) -> tuple[int, int]:
    value = fact.value if fact else None
    if not isinstance(value, dict):
        return 0, 0
    return int(value.get("success_count") or 0), int(value.get("failure_count") or 0)


def _directions_consistent(price: VerifiedFact | None, sector: VerifiedFact | None, peers: VerifiedFact | None) -> bool:
    price_change = _change_from_value(price.value if price else None)
    if price_change is None:
        return True
    sector_direction = _average_direction(sector)
    peer_direction = _average_direction(peers)
    if price_change < 0:
        return sector_direction <= 0 and peer_direction <= 0
    if price_change > 0:
        return sector_direction >= 0 and peer_direction >= 0
    return True


def _change_from_value(value: object) -> float | None:
    if isinstance(value, dict) and isinstance(value.get("change_pct"), (int, float)):
        return float(value["change_pct"])
    return None


def _average_direction(fact: VerifiedFact | None) -> float:
    value = fact.value if fact else None
    if not isinstance(value, dict):
        return 0.0
    changes = [float(item["change_pct"]) for item in value.get("items") or [] if isinstance(item, dict) and isinstance(item.get("change_pct"), (int, float))]
    if not changes:
        return 0.0
    return sum(changes) / len(changes)


def _partial_next_checks(sector: VerifiedFact | None, peers: VerifiedFact | None) -> list[str]:
    checks: list[str] = []
    for fact in (sector, peers):
        value = fact.value if fact else None
        if not isinstance(value, dict):
            continue
        for failure in value.get("partial_failures") or []:
            if isinstance(failure, dict) and failure.get("symbol"):
                checks.append(f"复核 {failure['symbol']} 的同窗口涨跌")
    return checks or ["继续核验板块、同行与新闻是否同窗口一致"]


def _missing_from_absence(sector: VerifiedFact | None, peers: VerifiedFact | None) -> list[str]:
    missing: list[str] = []
    if sector is None:
        missing.append("sector_move")
    if peers is None:
        missing.append("peer_moves")
    return missing
