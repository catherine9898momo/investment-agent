"""
test_probe_scorer.py — probe_scorer 的快速 sanity test

【目的】
在真 baseline 数据出来之前,用手工伪造的"完美答案" / "糟糕答案" / "部分对答案"
喂进 scorer,验证 3 种评分方法的判定逻辑都对。

【运行】
    python -m src.eval.test_probe_scorer
"""

import json
import tempfile
from pathlib import Path

from src.eval.probe_scorer import (
    score_strategy, extract_numbers, find_number_near, print_report,
)

PROJECT_ROOT = Path(__file__).parent.parent.parent
PROBES_PATH = PROJECT_ROOT / "experiments" / "w5_compression" / "eval_probes.json"


# ---------------------------------------------------------------------------
# 手工伪造 3 种答案场景:perfect / partial / awful
# ---------------------------------------------------------------------------

PERFECT_R10 = "TSLA 复权后单股成本是 $80。"
PARTIAL_R10 = "大概是 $75 左右吧。"     # 偏离 5,超出 ±$2 容差 → 应失败
AWFUL_R10 = "不太清楚,看具体哪一年。"   # 没数字 → 失败

PERFECT_R20 = """
你的 5 只持仓复权后成本和数量:
| Symbol | 复权后成本 | 数量 |
|--------|-----------|------|
| TSLA   | $80       | 1000 |
| NVDA   | $1        | 200  |
| AAPL   | $150      | 500  |
| 09988.HK | $280    | 100  |
| 600519.SS | ¥1680  | 10   |
"""
# partial: 缺 09988 和 600519,且 NVDA 算错
PARTIAL_R20 = """
- TSLA $80 复权后,1000 股
- NVDA $40 (没算拆股) 200 股
- AAPL $150 500 股
"""

PERFECT_R30 = """
回顾你的全部持仓:
- TSLA 1000 股,2020-08 拆 5:1 + 2022-08 拆 3:1,累计 15:1,复权后 $80
- NVDA 200 股,累计 40:1 拆股,复权后 $1
- AAPL 500 股,$150 成本
- 09988.HK 100 股,$280
- 600519.SS 10 股,¥1680

建议减仓 TSLA,理由:浮盈最大(+421% 当前价 $417),风险回吐风险高。
"""
# hallucination 版:AAPL 拆股编错(说成 10:1)
HALLU_R30 = """
- TSLA 1000 股,拆股 15:1
- NVDA 200 股,拆股 40:1
- AAPL 500 股,经历 10:1 拆股 (←编造!实际是 4:1 + 7:1)
- 09988.HK 100 股
- 建议减 TSLA
"""


# ---------------------------------------------------------------------------
# 构造伪 JSONL,跑 scorer
# ---------------------------------------------------------------------------

def make_fake_jsonl(scenario_name: str, r10_text: str, r20_text: str, r30_text: str) -> Path:
    """造一份只有 3 个 probe 轮的 JSONL。"""
    tmpdir = tempfile.mkdtemp(prefix="probe_test_")
    path = Path(tmpdir) / f"{scenario_name}.jsonl"
    rounds = [
        (10, "R10_probe", r10_text),
        (20, "R20_probe", r20_text),
        (30, "R30_probe", r30_text),
    ]
    with path.open("w") as f:
        for round_idx, probe_id, text in rounds:
            rec = {
                "round_idx": round_idx,
                "user_question": "(test)",
                "assistant_text_preview": text[:200],
                "num_turns": 1,
                "cost_usd": 0.0,
                "ctx_total_tokens": 0,
                "ctx_percentage": 0.0,
                "ctx_max_tokens": 0,
                "ctx_auto_compact_enabled": True,
                "ctx_categories": {},
                "timestamp": "2026-05-25T17:00:00",
                "is_probe": True,
                "probe_id": probe_id,
                "assistant_text_full": text,
            }
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return path


def test_helpers() -> None:
    """工具函数单元测试。"""
    print("\n=== Helper unit tests ===")
    nums = extract_numbers("TSLA $80,当前 $417,浮盈 +421%")
    assert 80.0 in nums and 417.0 in nums and 421.0 in nums, f"got {nums}"
    print(f"  ✅ extract_numbers: {nums}")

    n = find_number_near("TSLA 复权 $80 当前 $417", "TSLA")
    assert n == 80.0, f"got {n}"
    print(f"  ✅ find_number_near('TSLA'): {n}")

    nums2 = extract_numbers("1,000 股")
    assert 1000.0 in nums2, f"got {nums2}"
    print(f"  ✅ extract_numbers with comma: {nums2}")

    nums3 = extract_numbers("成本 ¥1680")
    assert 1680.0 in nums3, f"got {nums3}"
    print(f"  ✅ extract_numbers with ¥ prefix: {nums3}")

    print("Helper tests PASS")


def test_perfect() -> None:
    print("\n=== Scenario: PERFECT (期望 ~100%) ===")
    jsonl = make_fake_jsonl("perfect", PERFECT_R10, PERFECT_R20, PERFECT_R30)
    score = score_strategy(jsonl, PROBES_PATH)
    print_report(score)
    assert score.overall_pass_rate >= 0.85, (
        f"Perfect 场景应该 ≥ 85%,实际 {score.overall_pass_rate*100:.0f}% — scorer 太严"
    )
    print("✅ Perfect scenario passed")


def test_partial() -> None:
    print("\n=== Scenario: PARTIAL (R10 偏离 / R20 漏 2 行 / R30 完整) ===")
    jsonl = make_fake_jsonl("partial", PARTIAL_R10, PARTIAL_R20, PERFECT_R30)
    score = score_strategy(jsonl, PROBES_PATH)
    print_report(score)
    r10 = next(r for r in score.probe_results if r.round_idx == 10)
    r20 = next(r for r in score.probe_results if r.round_idx == 20)
    assert r10.pass_rate < 0.5, f"R10 偏离 5 美元应该 fail,实际 {r10.pass_rate}"
    assert r20.pass_rate <= 0.6, f"R20 漏 2 行应该 ≤60%,实际 {r20.pass_rate}"
    print("✅ Partial scenario judged correctly")


def test_awful() -> None:
    print("\n=== Scenario: AWFUL (R10 无数 / R20 半对 / R30 hallu) ===")
    jsonl = make_fake_jsonl("awful", AWFUL_R10, PARTIAL_R20, HALLU_R30)
    score = score_strategy(jsonl, PROBES_PATH)
    print_report(score)
    r10 = next(r for r in score.probe_results if r.round_idx == 10)
    r30 = next(r for r in score.probe_results if r.round_idx == 30)
    assert r10.pass_rate == 0.0, f"R10 无数字应该 0,实际 {r10.pass_rate}"
    assert r30.details.get("hallucinations"), "R30 应检测出 hallucination"
    print("✅ Awful scenario judged correctly")


if __name__ == "__main__":
    print(">>> probe_scorer sanity test")
    test_helpers()
    test_perfect()
    test_partial()
    test_awful()
    print("\n🎉 ALL TESTS PASSED")
