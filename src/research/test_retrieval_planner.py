from src.research.attribution_planner import build_attribution_plan
from src.research.claim_verifier import verify_synthesis_claims
from src.research.context_builder import build_research_context
from src.research.models import (
    Fact,
    IntentRoute,
    MissingFact,
    ResearchRunState,
    ResolvedEntity,
    Source,
    TimeWindow,
    VerifiedFact,
)
from src.research.retrieval_planner import build_retrieval_need_plan
from src.research.synthesizer import CandidateClaim, SynthesisResult


def _run_with_attribution_context() -> ResearchRunState:
    run = ResearchRunState.start("美光最近为什么大跌？")
    run.resolved_entity = ResolvedEntity("美光", "MU", "Micron", "Micron Technology")
    run.intent_route = IntentRoute("news_explanation", "用户询问涨跌原因。")
    run.time_window = TimeWindow("最近", "2026-06-01", "2026-06-07")
    run.attribution_plan = build_attribution_plan(run.intent_route, run.resolved_entity, run.time_window, run.user_query)
    source = Source("src_quote", "tool_result", "quote", "2026-06-07T00:00:00+00:00", tool_name="finance.get_quote")
    run.sources.append(source)
    run.facts.append(
        Fact(
            id="fact_price",
            text="MU declined 4.2% during the latest observed window.",
            source_ids=[source.id],
            observed_at=source.fetched_at,
            metric="latest_price",
            value={"change_pct": -4.2},
            symbol="MU",
        )
    )
    run.verified_facts = [
        VerifiedFact(
            id="vfact_price",
            fact_type="price_move",
            text="MU declined 4.2% during the latest observed window.",
            source_ids=[source.id],
            observed_at=source.fetched_at,
            confidence="medium",
            verification_status="verified",
            raw_fact_id="fact_price",
        )
    ]
    run.missing_facts = [
        MissingFact("sector_move", "需要比较板块走势。", True),
        MissingFact("peer_moves", "需要比较同行走势。", True),
    ]
    run.research_context = build_research_context(run)
    return run


def test_price_only_causal_issue_plans_sector_peer_and_news_tasks() -> None:
    run = _run_with_attribution_context()
    verification = verify_synthesis_claims(
        run,
        SynthesisResult([CandidateClaim("MU 下跌的原因是短期价格走弱。", "supporting_factor", ["fact_price"])]),
    )

    plan = build_retrieval_need_plan(run, verification)

    tasks_by_type = {task.fact_type: task for task in plan.tasks}
    assert plan.issue_count == 1
    assert {"sector_move", "peer_moves", "news_events"}.issubset(tasks_by_type)
    assert tasks_by_type["sector_move"].symbols == ["QQQ", "SMH", "SOXX"]
    assert {"NVDA", "AMD", "AVGO"}.issubset(set(tasks_by_type["peer_moves"].symbols))
    assert {"WDC", "STX", "SNDK"}.issubset(set(tasks_by_type["peer_moves"].symbols))
    assert tasks_by_type["news_events"].symbols == ["MU"]
    assert tasks_by_type["sector_move"].candidate_tools == ["finance.get_price_history"]
    assert run.retrieval_need_plan is plan


def test_unsupported_fact_id_becomes_reliable_source_task() -> None:
    run = _run_with_attribution_context()
    verification = verify_synthesis_claims(
        run,
        SynthesisResult([CandidateClaim("MU declined because guidance disappointed.", "supporting_factor", ["fact_guidance"])]),
    )

    plan = build_retrieval_need_plan(run, verification)

    assert len(plan.tasks) == 1
    task = plan.tasks[0]
    assert task.fact_type == "earnings_or_guidance"
    assert task.fact_ids == ["fact_guidance"]
    assert task.priority == "high"
    assert "official source when available" in task.source_requirements


def test_missing_fact_used_as_support_targets_matching_missing_fact() -> None:
    run = _run_with_attribution_context()
    verification = verify_synthesis_claims(
        run,
        SynthesisResult([CandidateClaim("sector_move 显示这主要是板块拖累。", "supporting_factor", ["fact_price"])]),
    )

    plan = build_retrieval_need_plan(run, verification)

    assert [task.fact_type for task in plan.tasks] == ["sector_move"]
    assert plan.tasks[0].reason == "需要比较板块走势。"


def test_low_confidence_overstated_plans_higher_confidence_same_fact_type() -> None:
    run = _run_with_attribution_context()
    run.verified_facts[0].confidence = "low"
    run.research_context = build_research_context(run)
    verification = verify_synthesis_claims(
        run,
        SynthesisResult([CandidateClaim("MU 显著下跌。", "fact_summary", ["fact_price"])]),
    )

    plan = build_retrieval_need_plan(run, verification)

    assert len(plan.tasks) == 1
    assert plan.tasks[0].fact_type == "price_move"
    assert plan.tasks[0].fact_ids == ["fact_price"]
    assert plan.tasks[0].priority == "medium"
