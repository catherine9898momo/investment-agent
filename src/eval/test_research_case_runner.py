from src.eval.research_case_runner import (
    BOUNDARY_CASES,
    DATA_QUALITY_CASES,
    EXPECTED_MEMO_SECTIONS,
    _section_present,
    _term_present,
)
from src.research.memo_renderer import MEMO_SECTIONS


def test_eval_expected_sections_follow_current_memo_sections() -> None:
    rendered_sections = set(MEMO_SECTIONS)

    for section_set in EXPECTED_MEMO_SECTIONS.values():
        assert set(section_set).issubset(rendered_sections)

    expected_case_sections = {section for case in [*BOUNDARY_CASES, *DATA_QUALITY_CASES] for section in case.expected_sections}
    assert expected_case_sections.issubset(rendered_sections)
    assert {"研究结论", "风险与不确定性", "还需要确认", "数据来源与时效"}.issubset(expected_case_sections)


def test_eval_section_matcher_keeps_legacy_english_compatibility() -> None:
    legacy_output = "## Boundary Statement\n## Freshness Notes\n## Human Confirmation Points"

    assert _section_present("研究结论", legacy_output)
    assert _section_present("数据来源与时效", legacy_output)
    assert _section_present("还需要确认", legacy_output)


def test_eval_term_matcher_supports_user_visible_synonyms() -> None:
    output = "数据质量提示：行情时间戳 stale；新闻结果缺失，暂时不能支持归因。".lower()

    assert _term_present(("过期", "stale"), output)
    assert _term_present(("不能支持", "无法支持"), output)
    assert not _term_present(("冲突", "conflict"), output)
