from src.research.models import (
    AttributionCause,
    AttributionNeed,
    AttributionPlan,
    ClaimVerificationIssue,
    ClaimVerificationResult,
    GuardrailResult,
    MissingFact,
    PolicyCheck,
    ResearchRunState,
    VerifiedFact,
)
from src.research.quality_auditor import ReportQualityAuditor


def _run() -> ResearchRunState:
    run = ResearchRunState.start("美光 MU 最近为什么大跌？")
    run.attribution_plan = AttributionPlan(
        question_type="price_drop",
        needs=[
            AttributionNeed("price_move", "核验价格波动。"),
            AttributionNeed("news_events", "核验新闻事件。"),
            AttributionNeed("sector_move", "核验板块波动。"),
            AttributionNeed("peer_moves", "核验同行波动。"),
        ],
        peer_symbols=["NVDA", "AMD"],
        index_symbols=["QQQ"],
    )
    return run


def _fact(fact_type: str, *, confidence: str = "medium", status: str = "verified", raw_id: str | None = None) -> VerifiedFact:
    fact_id = raw_id or f"fact_{fact_type}"
    return VerifiedFact(
        id=f"v_{fact_id}",
        fact_type=fact_type,
        text=f"{fact_type} fact",
        source_ids=["src"],
        observed_at="2026-06-28T00:00:00+00:00",
        confidence=confidence,  # type: ignore[arg-type]
        verification_status=status,  # type: ignore[arg-type]
        raw_fact_id=fact_id,
        value={},
    )


def _issue_types(run: ResearchRunState) -> set[str]:
    return {issue.issue_type for issue in ReportQualityAuditor().audit(run)}


def test_auditor_flags_missing_price_move_as_error() -> None:
    run = _run()
    run.verified_facts = [_fact("news_events")]

    issues = ReportQualityAuditor().audit(run)

    issue = next(issue for issue in issues if issue.issue_type == "missing_price_move")
    assert issue.severity == "error"
    assert issue.affected_fact_types == ["price_move"]
    assert issue.retrieval_needed is True


def test_auditor_flags_partial_news_as_retryable_warning() -> None:
    run = _run()
    run.verified_facts = [_fact("price_move"), _fact("news_events", confidence="low", status="partial")]

    issues = ReportQualityAuditor().audit(run)

    issue = next(issue for issue in issues if issue.issue_type == "partial_news_events")
    assert issue.severity == "warning"
    assert issue.retrieval_needed is True
    assert issue.suggested_task_type == "retry_news_zh"


def test_auditor_flags_missing_peer_moves_when_plan_requires_peers() -> None:
    run = _run()
    run.verified_facts = [_fact("price_move"), _fact("news_events"), _fact("sector_move")]
    run.missing_facts = [MissingFact("peer_moves", "缺少同行对照。")]

    issues = ReportQualityAuditor().audit(run)

    issue = next(issue for issue in issues if issue.issue_type == "missing_peer_moves")
    assert issue.severity == "warning"
    assert issue.affected_fact_types == ["peer_moves"]
    assert issue.retrieval_needed is True
    assert issue.suggested_task_type == "fetch_peer_history"


def test_auditor_flags_likely_factor_with_partial_comparison() -> None:
    run = _run()
    run.verified_facts = [
        _fact("price_move"),
        _fact("news_events"),
        _fact("sector_move", status="partial", raw_id="fact_sector"),
        _fact("peer_moves"),
    ]
    run.attribution_causes = [
        AttributionCause(
            label="板块/同行同步波动",
            level="likely_factor",
            support_fact_ids=["fact_sector"],
            confidence="medium",
        )
    ]

    issues = ReportQualityAuditor().audit(run)

    issue = next(issue for issue in issues if issue.issue_type == "partial_comparison_supports_likely_factor")
    assert issue.severity == "warning"
    assert issue.retrieval_needed is False
    assert issue.suggested_task_type == "rerender_with_downgrade"


def test_auditor_flags_direct_advice_claim_verification_error() -> None:
    run = _run()
    run.verified_facts = [_fact("price_move"), _fact("news_events")]
    run.claim_verification = ClaimVerificationResult(
        passed=False,
        issues=[
            ClaimVerificationIssue(
                claim_text="建议现在买入 MU。",
                issue_type="direct_trading_advice",
                message="direct advice",
                severity="error",
            )
        ],
    )

    issues = ReportQualityAuditor().audit(run)

    issue = next(issue for issue in issues if issue.issue_type == "direct_trading_advice")
    assert issue.severity == "error"
    assert issue.retrieval_needed is False


def test_auditor_flags_failed_guardrail_as_error() -> None:
    run = _run()
    run.verified_facts = [_fact("price_move"), _fact("news_events")]
    run.guardrail = GuardrailResult(
        passed=False,
        checks=[PolicyCheck("no_direct_trading_advice", False, "direct advice detected")],
    )

    assert "guardrail_failed" in _issue_types(run)
