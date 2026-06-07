from src.agents.research_demo import build_parser, build_research_run


def test_build_research_run_uses_query_understanding_for_entity_and_plan() -> None:
    run = build_research_run("帮我看美光 MU 最近是否还值得研究。", data_source="fixture")

    assert run.resolved_entity is not None
    assert run.resolved_entity.symbol == "MU"
    assert run.intent_route is not None
    assert run.intent_route.route == "company_research_memo"
    assert run.research_plan is not None
    assert run.time_window is not None
    assert run.attribution_plan is not None
    assert run.verified_facts
    assert {"price", "history", "news", "corporate_actions"}.issubset({need.key for need in run.research_plan.fact_needs})
    assert run.final_output is not None
    assert "MU" in run.final_output
    assert "## 研究结论" in run.final_output
    assert "## 原因排序" in run.final_output
    assert "## 证据表" not in run.final_output
    assert "fact_" not in run.final_output


def test_research_demo_parser_defaults_to_interactive_mode() -> None:
    args = build_parser().parse_args([])

    assert args.query is None
    assert args.data_source == "live"
    assert args.synthesizer == "mock"
    assert args.debug is False
    assert args.json is False


def test_research_demo_parser_keeps_one_shot_query_mode() -> None:
    args = build_parser().parse_args(["--query", "帮我看 MU", "--symbol", "MU"])

    assert args.query == "帮我看 MU"
    assert args.symbol == "MU"


def test_research_demo_parser_supports_debug_mode() -> None:
    args = build_parser().parse_args(["--debug"])

    assert args.debug is True
