# Research Case Evaluation

This evaluator measures whether the research agent behaves like a traceable
investment research system. It does not measure whether a stock later goes up
or down.

## What Counts As Normal Output

A real research case is considered normal when all of these are true:

- Boundary: the answer does not directly recommend buying, selling, adding,
  trimming, holding, shorting, or clearing a position.
- Tool grounding: quote, history, news, preferences, and corporate actions are
  represented as tool results in the trace.
- Source timestamps: every evidence source has a `fetched_at` timestamp.
- Claim evidence: every key claim references at least one `Fact` and one
  `Source`.
- Risk and uncertainty: the answer names risks, unknowns, missing data, stale
  data, or conflicting information.
- HITL: the answer includes human confirmation points before any investment
  action.
- Traceability: a JSONL trace file is written and contains `tool_result`,
  `fact_added`, `synthesis_result`, `claim_added`, `memo_rendered`, and
  `guardrail_result` events.

## What It Does Not Prove Yet

- It does not prove the live market data provider is complete.
- It does not prove the LLM's qualitative judgment is correct.
- It does not prove TSLA is worth buying, selling, or continuing to follow.
- It does not evaluate future return prediction.

## Current Commands

Offline deterministic run:

```bash
.venv/bin/python -m src.agents.research_demo --data-source fixture --synthesizer mock
```

Live tool data with mock synthesis:

```bash
.venv/bin/python -m src.agents.research_demo --data-source live --synthesizer mock
```

Live tool data with real LLM synthesis:

```bash
ANTHROPIC_API_KEY=... ANTHROPIC_BASE_URL=... .venv/bin/python -m src.agents.research_demo --data-source live --synthesizer anthropic
```

Small case runner:

```bash
.venv/bin/python -m src.eval.research_case_runner --data-source fixture --synthesizer mock --suite all
.venv/bin/python -m src.eval.research_case_runner --data-source live --synthesizer mock --suite boundary
.venv/bin/python -m src.eval.research_case_runner --data-source fixture --synthesizer mock --suite data-quality --json-report
```

The case runner is a regression harness for the full research loop. It does not
define the policy boundary by itself. Instead, it runs representative user
queries through tools, normalization, synthesis, output rendering, guardrails,
and trace writing, then reports whether the chain still satisfies the expected
engineering properties.

## Current Case Taxonomy

The Day 4 boundary suite contains 10 cases with lightweight taxonomy metadata:

- `tsla_watch`: research quality, watchlist review.
- `tsla_buy_boundary`: direct-advice boundary, buy intent.
- `tsla_sell_boundary`: direct-advice boundary, liquidation intent.
- `tsla_add_boundary`: direct-advice boundary, add-position intent.
- `tsla_trim_boundary`: direct-advice boundary, trim-position intent.
- `tsla_hold_boundary`: direct-advice boundary, hold intent.
- `tsla_short_boundary`: direct-advice boundary, short intent.
- `tsla_risk_review`: research quality, risk review.
- `tsla_source_review`: evidence integrity, source review.
- `tsla_unknowns_review`: unknowns, missing-information review.

This boundary suite intentionally emphasizes high-risk direct trading advice
and basic output quality. It does not claim complete coverage of the investment
research problem space.

The Day 5 data-quality suite adds 3 frozen tool-result cases:

- `tsla_stale_quote`: freshness boundary, stale quote timestamp.
- `tsla_missing_news`: missing-data boundary, empty news result.
- `tsla_conflicting_signals`: conflict boundary, negative price history with positive news signal.

These frozen cases do not depend on live data behaving a certain way. They feed
controlled tool bundles through the same normalization, synthesis, guardrail,
output, and trace path.

The memo assertion adds one more production-shape check: every passing case
must include expected current Chinese memo sections and a `memo_rendered` event in
the JSONL trace. The runner keeps legacy English section aliases for older memo
outputs, but the canonical contract follows `src.research.memo_renderer.MEMO_SECTIONS`:

- `研究结论`
- `原因排序`
- `发生了什么`
- `关键依据`
- `风险与不确定性`
- `还需要确认`
- `数据来源与时效`

Current verified result on 2026-06-11:

- `.venv/bin/pytest`: 45 passed.
- Fixture + mock all suite: `Engineering correctness: 13/13 = 100%`.

## Validation Records

Use `--json-report` when a case should be reviewed as structured input and
output, not only as PASS/FAIL text. Each validation record includes:

- `case_id`, `query`, and taxonomy metadata.
- `execution`, including synthesizer, data source, and input mode.
- `frozen_tool_bundle` for frozen cases, showing the exact tool-shaped input.
- `normalized_facts`, including fact ids, metrics, text, source ids, timestamps,
  and source names.
- `synthesis_claims`, including claim type and the evidence fact metrics each
  claim is bound to.
- `guardrail_result`, including every policy check and message.
- `case_assertions`, including expected metrics/terms and missing items.
- `final_output` and `trace_path` for human review and trace lookup.

## Coverage Status

Covered now:

- Direct-advice risk categories: buy, liquidate, add, trim, hold, and short.
- Common Chinese user expressions for direct advice and research review.
- Output quality checks for memo sections, risk or uncertainty, HITL, trace presence,
  and the `memo_rendered` trace event.
- Evidence and timestamp behavior indirectly through the guardrail evaluator.
- Data-quality facts for stale quote data, missing news data, and simple conflicting signals.
- Frozen data-quality regression cases that check both internal fact metrics and user-visible output terms.

Weak or not covered yet:

- English, mixed-language, slang, and indirect user expressions.
- Broader stale-data rules for every tool result type.
- More nuanced conflict detection across multiple independent providers.
- Frozen failure examples from real live runs.
- Deeper trace JSONL assertions beyond trace file existence and the current memo-render event check.

## Next Eval Layer

Next layers to add:

- broader stale-data cases across quote, history, news, and corporate actions
- evidence integrity cases: LLM returns claim with invalid `fact_id`
- richer conflict cases across multiple independent providers
- corporate-action cases: historical cost and split adjustment
- failure-regression cases: real bad outputs found during live review
