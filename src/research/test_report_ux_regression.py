from src.agents.research_demo import build_research_run


def test_mu_fixture_report_prioritizes_narrative_and_aligned_cause() -> None:
    run = build_research_run("美光 MU 最近为什么大跌？", data_source="fixture")

    assert run.final_output is not None
    output = run.final_output

    assert output.index("## 一句话结论") < output.index("## 归因证据矩阵")
    assert "## 最可能的原因" in output
    assert "这不是交易建议" in output
    assert "fact_" not in output
    assert "source_" not in output

