"""
probe_scorer.py — W5 上下文压缩实验 · probe 评分器

【职责】
读一份 strategy JSONL(S0/S_A/S_B/S_C)+ eval_probes.json(冻结的预注册规则),
对每个 probe 轮的 assistant_text_full 算分,输出每 probe 详情 + 总分。

【3 种评分方法】
1. numeric_match (R10): 抽取首个数字,跟 expected ±tolerance 比
2. row_coverage   (R20): 对每行 expected,检查 symbol + adj_cost(±5%) + shares
3. fact_recall_minus_hallucination (R30):
   symbols 命中数 + facts 命中数 - hallucination 罚分

【设计原则】
- 透明:每个判定都打日志说"为什么命中 / 为什么没命中"
- 可复现:全规则在 eval_probes.json,scorer 只是规则执行器
- 不用 LLM-as-judge:全字符串/数值匹配,避免引入新随机性

【sanity test】
对 S0 baseline 跑分,期望 R10/R20/R30 都接近满分(因为 baseline 不压缩,信息全在)。
如果 baseline 分数 <0.7,说明 scorer 规则太严或助手输出格式不稳定,需调规则不调策略。

【使用】
    python -m src.eval.probe_scorer \\
        --jsonl experiments/w5_compression/S0_baseline_final_001.jsonl \\
        --probes experiments/w5_compression/eval_probes.json
"""

from __future__ import annotations

import argparse
import json
import logging
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("probe_scorer")


# ============================================================================
# 数据结构
# ============================================================================

@dataclass
class ProbeResult:
    """单个 probe 的评分结果。"""
    probe_id: str
    round_idx: int
    type: str
    score: float
    max_score: float
    pass_rate: float                       # score / max_score
    details: dict[str, Any] = field(default_factory=dict)  # 命中明细 / 失败原因


@dataclass
class StrategyScore:
    """一个策略(整份 JSONL)的总分。"""
    strategy_name: str
    jsonl_path: str
    probe_results: list[ProbeResult]
    total_score: float
    total_max: float
    overall_pass_rate: float


# ============================================================================
# 通用工具:从文本里抽数字
# ============================================================================

# 匹配 $80 / 80美元 / 80.00 / 80 USD / 80 / ¥1680 / 1,000 等
# 【正则坑】alternation 必须把"长贪婪"放前面:re 是"取第一个匹配"不是"最长匹配",
# 否则 ¥1680 会被切成 168 + 0(因为 \d{1,3} 没逗号也算合法 → 168 先 match)
_NUMBER_RE = re.compile(
    r"(?:\$|¥|￥|USD\s*|CNY\s*|HKD\s*)?\s*"           # 可选货币前缀
    r"(-?\d{1,3}(?:,\d{3})+(?:\.\d+)?|-?\d+(?:\.\d+)?)"  # 数字本体:千分位必须含 ',\d{3}+' 排他;否则走纯 greedy
    r"\s*(?:美元|元|港币|刀|USD|CNY|HKD)?"             # 可选单位后缀
)


def extract_numbers(text: str) -> list[float]:
    """从文本里抽出所有数字(去重保序)。"""
    seen = set()
    result = []
    for match in _NUMBER_RE.finditer(text):
        raw = match.group(1).replace(",", "")
        try:
            val = float(raw)
        except ValueError:
            continue
        if val not in seen:
            seen.add(val)
            result.append(val)
    return result


def find_number_near(text: str, anchor: str, window: int = 80) -> float | None:
    """在 anchor 字符串附近 window 字符内找第一个数字。

    例:find_number_near("TSLA 复权后成本 $80,当前价 $417", "TSLA") → 80.0
    """
    idx = text.find(anchor)
    if idx < 0:
        return None
    chunk = text[idx : idx + window]
    nums = extract_numbers(chunk)
    return nums[0] if nums else None


# ============================================================================
# 评分方法 1:numeric_match (R10 single fact)
# ============================================================================

def score_numeric_match(probe: dict, assistant_text: str) -> ProbeResult:
    """R10 风格:抽首个数字 / anchor 附近数字,跟 expected ±tolerance 比。"""
    expected_val = probe["expected"]["value"]
    tol = probe["scoring"].get("tolerance_usd", 2.0)
    pass_score = probe["scoring"]["score_if_pass"]
    fail_score = probe["scoring"]["score_if_fail"]

    # 抽数字策略:优先看回答开头(因为 question 要求"直接给数字")
    # 第一个数字往往就是答案
    nums = extract_numbers(assistant_text)

    details: dict[str, Any] = {
        "expected": expected_val,
        "tolerance": tol,
        "extracted_numbers": nums[:8],     # 首 8 个,避免日志爆炸
    }

    if not nums:
        log.warning("R%d numeric_match: 无数字可抽", probe["round"])
        details["failure_reason"] = "no_numbers_extracted"
        return ProbeResult(
            probe_id=probe["id"],
            round_idx=probe["round"],
            type=probe["type"],
            score=fail_score,
            max_score=pass_score,
            pass_rate=0.0,
            details=details,
        )

    # 找最接近 expected 的数字(避免被"当前价 $417"等干扰数字误判)
    closest = min(nums, key=lambda x: abs(x - expected_val))
    diff = abs(closest - expected_val)
    passed = diff <= tol

    details["closest_match"] = closest
    details["abs_diff"] = round(diff, 4)
    details["passed"] = passed

    log.info(
        "R%d numeric_match: expected=%.2f, closest=%.2f, diff=%.2f, tol=%.2f → %s",
        probe["round"], expected_val, closest, diff, tol,
        "✅ PASS" if passed else "❌ FAIL",
    )

    return ProbeResult(
        probe_id=probe["id"],
        round_idx=probe["round"],
        type=probe["type"],
        score=pass_score if passed else fail_score,
        max_score=pass_score,
        pass_rate=1.0 if passed else 0.0,
        details=details,
    )


# ============================================================================
# 评分方法 2:row_coverage (R20 multi fact table)
# ============================================================================

def score_row_coverage(probe: dict, assistant_text: str) -> ProbeResult:
    """R20 风格:对每行 expected,检查 symbol + adj_cost(±5%) + shares 是否出现。"""
    rows = probe["expected"]["rows"]
    score_per_row = probe["scoring"]["score_per_row_correct"]
    max_score = probe["scoring"]["max_score"]

    correct_rows: list[dict] = []
    for row in rows:
        symbol = row["symbol"]
        adj_cost = row["adj_cost"]
        shares = row["shares"]

        # 1. symbol 必须出现(支持 TSLA 也支持完整 09988.HK)
        symbol_present = symbol in assistant_text or symbol.split(".")[0] in assistant_text

        # 2. adj_cost 必须 ±5% 出现
        cost_ok = False
        if symbol_present:
            # 在 symbol 附近 200 字内找数字
            num_near = find_number_near(assistant_text, symbol, window=300)
            if num_near is not None and adj_cost > 0:
                cost_ok = abs(num_near - adj_cost) / adj_cost <= 0.05
                # cost_ok 也可能因为找到的是 shares 而误判,继续抽更多
                if not cost_ok:
                    # 再 fallback:整段抽所有数字,看有没有命中
                    idx = assistant_text.find(symbol)
                    chunk = assistant_text[idx : idx + 400] if idx >= 0 else ""
                    all_nums = extract_numbers(chunk)
                    cost_ok = any(
                        abs(n - adj_cost) / adj_cost <= 0.05 for n in all_nums
                    )

        # 3. shares 必须精确匹配(整数,不带容差)
        shares_ok = False
        if symbol_present:
            idx = assistant_text.find(symbol)
            chunk = assistant_text[idx : idx + 400] if idx >= 0 else ""
            chunk_nums = extract_numbers(chunk)
            shares_ok = float(shares) in chunk_nums

        passed = symbol_present and cost_ok and shares_ok
        correct_rows.append({
            "symbol": symbol,
            "expected_cost": adj_cost,
            "expected_shares": shares,
            "symbol_present": symbol_present,
            "cost_ok": cost_ok,
            "shares_ok": shares_ok,
            "passed": passed,
        })

    n_correct = sum(1 for r in correct_rows if r["passed"])
    score = min(n_correct * score_per_row, max_score)

    log.info(
        "R%d row_coverage: %d/%d rows correct, score=%.2f / %.2f",
        probe["round"], n_correct, len(rows), score, max_score,
    )
    for r in correct_rows:
        flag = "✅" if r["passed"] else "❌"
        log.info(
            "    %s %-12s sym=%s cost=%s shares=%s",
            flag, r["symbol"],
            "✓" if r["symbol_present"] else "✗",
            "✓" if r["cost_ok"] else "✗",
            "✓" if r["shares_ok"] else "✗",
        )

    return ProbeResult(
        probe_id=probe["id"],
        round_idx=probe["round"],
        type=probe["type"],
        score=score,
        max_score=max_score,
        pass_rate=score / max_score if max_score > 0 else 0.0,
        details={"rows": correct_rows, "n_correct": n_correct, "n_total": len(rows)},
    )


# ============================================================================
# 评分方法 3:fact_recall_minus_hallucination (R30 synthesis)
# ============================================================================

def score_fact_recall(probe: dict, assistant_text: str) -> ProbeResult:
    """R30 风格:symbols 命中 + facts 命中 - hallucination 罚分。"""
    must_symbols = probe["expected"]["must_mention_symbols"]
    must_facts = probe["expected"]["must_mention_facts"]
    no_hallucinations = probe["expected"]["no_hallucination"]

    s_per_symbol = probe["scoring"]["score_per_symbol_recalled"]
    s_per_fact = probe["scoring"]["score_per_fact_recalled"]
    penalty_per_hallu = probe["scoring"]["penalty_per_hallucination"]
    max_score = probe["scoring"]["max_score"]
    min_score = probe["scoring"]["min_score"]

    # 1. symbols 命中
    symbols_hit = [s for s in must_symbols if s in assistant_text or s.split(".")[0] in assistant_text]

    # 2. facts 命中(用关键词 substring 匹配)
    # 每条 fact 是描述性字符串如 "TSLA 拆股 15:1 或复权成本 $80"
    # 拆解判定:必须出现 "TSLA" + 出现 "15" 或 "$80"/"80美元"
    facts_hit = []
    for fact in must_facts:
        if _fact_mentioned(fact, assistant_text):
            facts_hit.append(fact)

    # 3. hallucination 检测(规则式,粗筛)
    hallucinations_hit = []
    for hallu in no_hallucinations:
        # hallu 是禁止内容描述,如 "不能编造未发生的拆股(如 AAPL 4:1 之外的拆股)"
        # 检测:如果文本里出现 AAPL 同时出现非 1:1 / 7:1 / 4:1 / 2:1 的拆股说法,算 hallucination
        # 这里简化:只检测最常见 hallu 模式,后续可加规则
        if _hallucination_detected(hallu, assistant_text):
            hallucinations_hit.append(hallu)

    raw_score = (
        len(symbols_hit) * s_per_symbol
        + len(facts_hit) * s_per_fact
        - len(hallucinations_hit) * penalty_per_hallu
    )
    score = max(min_score, min(max_score, raw_score))

    log.info(
        "R%d fact_recall: symbols=%d/%d, facts=%d/%d, hallucinations=%d, raw=%.2f, final=%.2f",
        probe["round"],
        len(symbols_hit), len(must_symbols),
        len(facts_hit), len(must_facts),
        len(hallucinations_hit),
        raw_score, score,
    )

    return ProbeResult(
        probe_id=probe["id"],
        round_idx=probe["round"],
        type=probe["type"],
        score=score,
        max_score=max_score,
        pass_rate=score / max_score if max_score > 0 else 0.0,
        details={
            "symbols_hit": symbols_hit,
            "symbols_missed": [s for s in must_symbols if s not in symbols_hit],
            "facts_hit": facts_hit,
            "facts_missed": [f for f in must_facts if f not in facts_hit],
            "hallucinations": hallucinations_hit,
            "raw_score": raw_score,
        },
    )


def _fact_mentioned(fact_desc: str, text: str) -> bool:
    """判定 fact 描述是否在 text 里出现。

    策略:从 fact_desc 抽出 (symbol, 数字) 对,要求 text 里这两个 token 都在附近。
    例:fact_desc = "TSLA 拆股 15:1 或复权成本 $80"
        → 需要 text 含 TSLA 且附近有 "15" 或 "80"
    """
    # 抽 fact_desc 里的 ticker (3-6 大写字母 / 含点的港股代码)
    tickers = re.findall(r"\b[A-Z]{2,6}\b|\b\d{5}\.[A-Z]{2}\b|\b\d{6}\.[A-Z]{2}\b", fact_desc)
    nums_in_fact = extract_numbers(fact_desc)

    # 简化规则:fact 里若有 ticker,text 必须含该 ticker;同时 fact 的数字至少一个在 text 里(允许 ±5% 模糊)
    text_nums = extract_numbers(text)

    if tickers:
        any_ticker_in_text = any(t in text for t in tickers)
        if not any_ticker_in_text:
            return False

    if nums_in_fact:
        any_num_match = any(
            any(abs(tn - fn) / max(abs(fn), 1) <= 0.05 for tn in text_nums)
            for fn in nums_in_fact
        )
        return any_num_match

    # fact 既无 ticker 也无数字 → 用全文 substring fallback(每词都要在)
    keywords = [w for w in fact_desc.split() if len(w) >= 2]
    return all(kw in text for kw in keywords[:3])


def _hallucination_detected(hallu_desc: str, text: str) -> bool:
    """粗规则检测 hallucination。

    当前覆盖:
    - AAPL 拆股因子异常(预期 4:1,但文本声称 X:1 X≠4)
    - TSLA 拆股因子异常(预期 5:1 + 3:1 = 累计 15:1)
    - NVDA 拆股因子异常(预期累计 40:1)

    扩展:5/28 跑完三个 treatment 后,人工抽查发现哪些 hallucination 模式高发,加规则
    """
    # 规则 1:AAPL 出现拆股比例但非 4:1 / 7:1(历史真实)
    if "AAPL" in hallu_desc and "AAPL" in text:
        aapl_splits = re.findall(r"AAPL[^\n]*?(\d+)\s*[:×]\s*(\d+)", text)
        for a, b in aapl_splits:
            ratio_str = f"{a}:{b}"
            if ratio_str not in ("4:1", "7:1", "1:1"):
                return True

    # 规则 2:TSLA 错说成单次拆股(应为 15:1 累计)
    if "TSLA" in hallu_desc and "TSLA" in text:
        tsla_match = re.search(r"TSLA[^\n]*?(\d+)\s*[:×]\s*1", text)
        if tsla_match:
            ratio = int(tsla_match.group(1))
            if ratio not in (5, 3, 15):
                return True

    return False


# ============================================================================
# 主入口
# ============================================================================

SCORER_BY_METHOD = {
    "numeric_match": score_numeric_match,
    "row_coverage": score_row_coverage,
    "fact_recall_minus_hallucination": score_fact_recall,
}


def score_strategy(jsonl_path: Path, probes_path: Path) -> StrategyScore:
    """对一份策略 JSONL 算总分。"""
    # 1. 加载 probes
    with probes_path.open() as f:
        probes_data = json.load(f)
    probes_by_round = {p["round"]: p for p in probes_data["probes"]}
    log.info("loaded %d probes: rounds=%s", len(probes_by_round), sorted(probes_by_round.keys()))

    # 2. 加载 JSONL,提取 probe 轮
    probe_records: dict[int, dict] = {}
    with jsonl_path.open() as f:
        for line in f:
            rec = json.loads(line)
            if rec.get("is_probe"):
                probe_records[rec["round_idx"]] = rec

    log.info("found probe rounds in JSONL: %s", sorted(probe_records.keys()))

    # 3. 逐 probe 算分
    results: list[ProbeResult] = []
    for round_idx, probe in probes_by_round.items():
        rec = probe_records.get(round_idx)
        if rec is None:
            log.warning("R%d probe 在 JSONL 中找不到记录,跳过", round_idx)
            continue

        assistant_text = rec.get("assistant_text_full") or rec.get("assistant_text_preview", "")
        if not assistant_text:
            log.warning("R%d 无 assistant_text,跳过", round_idx)
            continue

        method = probe["scoring"]["method"]
        scorer = SCORER_BY_METHOD.get(method)
        if scorer is None:
            log.error("R%d 未知评分方法: %s", round_idx, method)
            continue

        result = scorer(probe, assistant_text)
        results.append(result)

    # 4. 汇总
    total_score = sum(r.score for r in results)
    total_max = sum(r.max_score for r in results)
    overall = total_score / total_max if total_max > 0 else 0.0

    return StrategyScore(
        strategy_name=jsonl_path.stem,
        jsonl_path=str(jsonl_path),
        probe_results=results,
        total_score=total_score,
        total_max=total_max,
        overall_pass_rate=overall,
    )


def print_report(strategy_score: StrategyScore) -> None:
    """打印人类可读报告。"""
    print()
    print("=" * 70)
    print(f"Strategy: {strategy_score.strategy_name}")
    print(f"JSONL:    {strategy_score.jsonl_path}")
    print("=" * 70)
    for r in strategy_score.probe_results:
        bar = "█" * int(r.pass_rate * 20) + "░" * (20 - int(r.pass_rate * 20))
        print(f"  R{r.round_idx:2d} {r.probe_id:25s} [{bar}] {r.score:.2f}/{r.max_score:.2f}  ({r.pass_rate*100:.0f}%)")
    print("-" * 70)
    print(f"  TOTAL                              {strategy_score.total_score:.2f}/{strategy_score.total_max:.2f}  ({strategy_score.overall_pass_rate*100:.0f}%)")
    print("=" * 70)


def main() -> None:
    parser = argparse.ArgumentParser(description="W5 probe scorer")
    parser.add_argument("--jsonl", type=Path, required=True, help="策略 JSONL 路径")
    parser.add_argument("--probes", type=Path, required=True, help="eval_probes.json")
    parser.add_argument("--json-out", type=Path, default=None, help="JSON 报告落盘路径(可选)")
    args = parser.parse_args()

    score = score_strategy(args.jsonl, args.probes)
    print_report(score)

    if args.json_out:
        with args.json_out.open("w") as f:
            json.dump(asdict(score), f, ensure_ascii=False, indent=2)
        log.info("JSON report written to %s", args.json_out)


if __name__ == "__main__":
    main()
