"""Rule-based output evaluator for investment research answers."""

from __future__ import annotations

import re

from src.research.models import GuardrailResult, PolicyCheck, ResearchRunState


DIRECT_ADVICE_PATTERNS = [
    r"(建议|应该|可以|适合|立刻|现在)\s*(买入|卖出|加仓|减仓|清仓|满仓|重仓|做空|持有)",
    r"(买入|卖出|加仓|减仓|清仓|满仓|重仓|做空|持有)\s*(吧|即可|就行|是更好选择)",
    r"\b(you should|should|recommend|recommendation:|do)\s+(buy|sell|add|trim|liquidate|short|hold)\b",
    r"\b(buy|sell|add|trim|liquidate|short|hold)\s+(now|immediately|this stock|the stock)\b",
]

RISK_KEYWORDS = ["风险", "risk", "不确定", "uncertain", "unknown", "未知", "缺失", "冲突"]
SOURCE_KEYWORDS = ["来源", "source", "证据", "evidence"]
HUMAN_CONFIRMATION_KEYWORDS = ["人工确认", "human confirmation", "确认", "问题"]
TIMESTAMP_RE = re.compile(r"\d{4}-\d{2}-\d{2}|timestamp|时间|fetched_at|observed_at", re.I)


def _check_no_direct_trading_advice(output: str) -> PolicyCheck:
    for pattern in DIRECT_ADVICE_PATTERNS:
        if re.search(pattern, output, flags=re.I):
            return PolicyCheck(
                name="no_direct_trading_advice",
                passed=False,
                message=f"Output contains direct trading advice pattern: {pattern}",
            )
    return PolicyCheck(
        name="no_direct_trading_advice",
        passed=True,
        message="No direct buy/sell/add/trim instruction detected.",
    )


def _check_key_claim_evidence(run: ResearchRunState) -> PolicyCheck:
    missing = [claim.id for claim in run.claims if claim.is_key and not claim.evidence]
    if missing:
        return PolicyCheck(
            name="key_claims_have_evidence",
            passed=False,
            message=f"Key claims missing evidence: {', '.join(missing)}",
        )
    return PolicyCheck(
        name="key_claims_have_evidence",
        passed=True,
        message="Every key claim has at least one evidence link.",
    )


def _check_evidence_sources_have_timestamps(run: ResearchRunState) -> PolicyCheck:
    source_ids = {
        evidence.source_id
        for claim in run.claims
        for evidence in claim.evidence
    }
    missing = [
        source_id
        for source_id in source_ids
        if (source := run.source_by_id(source_id)) is None or not source.fetched_at
    ]
    if missing:
        return PolicyCheck(
            name="evidence_sources_have_timestamps",
            passed=False,
            message=f"Evidence sources missing timestamps: {', '.join(missing)}",
        )
    return PolicyCheck(
        name="evidence_sources_have_timestamps",
        passed=True,
        message="Every evidence source has fetched_at timestamp.",
    )


def _check_output_mentions_sources(output: str) -> PolicyCheck:
    passed = any(keyword.lower() in output.lower() for keyword in SOURCE_KEYWORDS)
    return PolicyCheck(
        name="output_mentions_sources",
        passed=passed,
        message="Output mentions source/evidence." if passed else "Output does not mention source/evidence.",
    )


def _check_output_mentions_timestamps(output: str) -> PolicyCheck:
    passed = bool(TIMESTAMP_RE.search(output))
    return PolicyCheck(
        name="output_mentions_timestamps",
        passed=passed,
        message="Output includes a date or timestamp." if passed else "Output does not include a date/timestamp.",
    )


def _check_output_mentions_risk_or_uncertainty(output: str) -> PolicyCheck:
    passed = any(keyword.lower() in output.lower() for keyword in RISK_KEYWORDS)
    return PolicyCheck(
        name="output_mentions_risk_or_uncertainty",
        passed=passed,
        message="Output includes risk/uncertainty language." if passed else "Output lacks risk/uncertainty language.",
    )


def _check_output_has_human_confirmation_points(run: ResearchRunState, output: str) -> PolicyCheck:
    has_state_points = bool(run.human_confirmation_points)
    has_output_points = any(keyword.lower() in output.lower() for keyword in HUMAN_CONFIRMATION_KEYWORDS)
    passed = has_state_points and has_output_points
    return PolicyCheck(
        name="output_has_human_confirmation_points",
        passed=passed,
        message=(
            "Output includes human confirmation points."
            if passed
            else "Output is missing human confirmation points."
        ),
    )


def evaluate_research_output(run: ResearchRunState, output: str) -> GuardrailResult:
    checks = [
        _check_no_direct_trading_advice(output),
        _check_key_claim_evidence(run),
        _check_evidence_sources_have_timestamps(run),
        _check_output_mentions_sources(output),
        _check_output_mentions_timestamps(output),
        _check_output_mentions_risk_or_uncertainty(output),
        _check_output_has_human_confirmation_points(run, output),
    ]
    return GuardrailResult(
        passed=all(check.passed for check in checks),
        checks=checks,
    )
