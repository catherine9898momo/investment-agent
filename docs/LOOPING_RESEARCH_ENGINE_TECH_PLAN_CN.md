# Looping Research Engineer 技术方案

## 1. 方案目标

本文档承接 `docs/LOOPING_RESEARCH_ENGINE_PRD_CN.md`，描述如何实现第一版 `Looping Research Engineer`。

第一版的准确定位是：**Bounded Evidence Repair Loop**。

它不是开放式 autonomous loop，而是一个受控的补证据闭环：先生成初稿 `run_0`，审计质量问题，执行一轮白名单补证据任务，将补证据结果合并进 `enhanced_bundle_1`，再通过现有 report generation pipeline 重新生成 `run_1`。

核心约束：

```text
补证据任务的结果不能只贴到报告底部。
补证据结果必须回到 ToolResultBundle 层。
最终报告必须来自重新生成的 run_1。
```

这段约束的含义：

- `不能只贴到底部`：loop summary 只能解释过程，不能替代重新生成报告正文。
- `回到 ToolResultBundle 层`：新增证据要作为工具结果进入 normalizer、fact verifier、attribution evaluator 和 renderer。
- `最终报告来自 run_1`：用户最终看到的是重新构建后的报告，而不是 `run_0.final_output` 的文本 patch。

## 2. 当前代码基线

关键入口：

- `src/agents/research_demo.py`
  - `build_research_run()`：从用户 query 拉取工具数据并构建单轮 run。
  - `build_research_run_from_bundle()`：从给定 `ToolResultBundle` 构建完整 run，是本方案重建 `run_1` 的核心入口。
- `src/research/tool_provider.py`
  - 定义 `ToolResultBundle`、fixture provider 和 live provider。
- `src/research/normalizers.py`
  - 将 raw tool result 转成 `Source` / `Fact`。
- `src/research/fact_verifier.py`
  - 将 facts 转成 `VerifiedFact` / `MissingFact`。
- `src/research/attribution_evaluator.py`
  - 根据事实覆盖和方向一致性输出 attribution cause。
- `src/research/claim_verifier.py`
  - 检查候选 claims 的证据绑定和安全边界。
- `src/research/memo_renderer.py`
  - 渲染最终 memo。
- `src/research/trace.py`
  - 写入 JSONL trace。

当前缺口：

```text
没有质量审计器。
没有 issue -> task 的白名单映射。
没有 task result -> enhanced bundle 的合并层。
没有 run_0 -> run_1 的 loop controller。
没有 loop summary 和 loop trace events。
```

## 3. 总体架构

第一版采用方案 A：**Enhanced ToolResultBundle Rebuild**。

```text
build run_0
  -> audit run_0
  -> plan evidence_tasks_1
  -> execute evidence_tasks_1
  -> merge task_results_1 into enhanced_bundle_1
  -> build run_1 from enhanced_bundle_1
  -> audit run_1
  -> render final memo from run_1
  -> attach loop summary
```

节点说明：

- `build run_0`：调用现有 `build_research_run()` 或 provider + `build_research_run_from_bundle()` 生成初稿。
- `audit run_0`：调用 `ReportQualityAuditor` 生成 `QualityIssue`。
- `plan evidence_tasks_1`：调用 `EvidenceTaskPlanner` 只从白名单生成补证据任务。
- `execute evidence_tasks_1`：执行任务，产出 `EvidenceTaskResult`。失败也结构化返回。
- `merge task_results_1 into enhanced_bundle_1`：将 task 结果合并进初始 `ToolResultBundle`。
- `build run_1 from enhanced_bundle_1`：调用 `build_research_run_from_bundle()` 完整重跑 normalizer、verifier、evaluator、synthesis、renderer、guardrail。
- `audit run_1`：对最终 run 再审计，生成最终质量状态。
- `render final memo from run_1`：最终正文来自 `run_1`。
- `attach loop summary`：附加本轮 loop 做了什么、仍缺什么、为什么停止。

## 4. 为什么选择 Enhanced Bundle Rebuild

不采用 run patch：

```text
run_0.facts += new_facts
run_0.verified_facts = rebuild_verified_fact_table(...)
run_0.final_output = rerender(...)
```

原因：

- patch 容易漏掉 derived state，例如 `research_context`、`claim_verification`、`attribution_causes`。
- patch 后 trace 难以证明报告正文来自完整 pipeline。
- patch 容易让新增证据没有经过完整 guardrail。

采用 rebuild：

```text
base_bundle + task_results = enhanced_bundle
build_research_run_from_bundle(enhanced_bundle) = run_1
```

优点：

- 所有新增证据重新经过 normalizer。
- verified facts 和 missing facts 重新计算。
- attribution causes 重新评估。
- synthesis 和 claim verification 重新执行。
- memo 和 guardrail 与现有单轮逻辑保持一致。
- 单测可以直接比较 `run_0` 和 `run_1`。

## 5. 新增模块

```text
src/research/quality_auditor.py
src/research/evidence_tasks.py
src/research/loop_engine.py
src/research/test_quality_auditor.py
src/research/test_evidence_tasks.py
src/research/test_loop_engine.py
```

模块说明：

- `quality_auditor.py`：发现质量问题，只读，不执行工具。
- `evidence_tasks.py`：定义 EvidenceTask、EvidenceTaskResult，以及 issue-to-task 映射。
- `loop_engine.py`：控制 run_0、task execution、enhanced bundle、run_1、停止条件和 trace。
- `test_quality_auditor.py`：每条质量规则都有单测。
- `test_evidence_tasks.py`：每个 issue 到 task 的映射都有单测。
- `test_loop_engine.py`：证明 run_1 是从 enhanced bundle 重新生成的。

## 6. 数据结构设计

### 6.1 QualityIssue

```python
@dataclass(frozen=True)
class QualityIssue:
    issue_type: str
    severity: Literal["info", "warning", "error"]
    message: str
    affected_fact_types: list[str] = field(default_factory=list)
    affected_fact_ids: list[str] = field(default_factory=list)
    retrieval_needed: bool = False
    suggested_task_type: str | None = None
```

字段说明：

- `issue_type`：稳定问题类型，例如 `missing_peer_moves`。
- `severity`：问题严重程度。
- `message`：trace 和 debug 可读说明。
- `affected_fact_types`：受影响事实类别。
- `affected_fact_ids`：受影响 fact id。
- `retrieval_needed`：是否需要补证据。
- `suggested_task_type`：建议任务类型，但最终由 planner 决定。

### 6.2 EvidenceTask

```python
@dataclass(frozen=True)
class EvidenceTask:
    task_type: Literal[
        "retry_news_zh",
        "fetch_sector_history",
        "fetch_peer_history",
        "rerender_with_downgrade",
    ]
    reason: str
    target_symbol: str
    required_fact_type: str | None = None
    max_attempts: int = 1
```

字段说明：

- `task_type`：白名单任务类型。
- `reason`：为什么执行该任务。
- `target_symbol`：主标的。
- `required_fact_type`：期望补齐的 fact type。
- `max_attempts`：最大尝试次数，V1 固定为 1。

### 6.3 EvidenceTaskResult

```python
@dataclass(frozen=True)
class EvidenceTaskResult:
    task_type: str
    status: Literal["completed", "failed", "skipped"]
    tool_result_slot: Literal["news", "sector_history", "peer_history"] | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
```

字段说明：

- `task_type`：对应哪个 EvidenceTask。
- `status`：任务执行状态。
- `tool_result_slot`：结果应该合并到 `ToolResultBundle` 的哪个槽位。
- `payload`：工具结果 payload，形态应与 provider 返回值兼容。
- `error`：失败原因。失败不能让整个 loop crash。

### 6.4 LoopIteration

```python
@dataclass(frozen=True)
class LoopIteration:
    index: int
    quality_issues_before: list[QualityIssue]
    evidence_tasks: list[EvidenceTask]
    task_results: list[EvidenceTaskResult]
    quality_issues_after: list[QualityIssue] = field(default_factory=list)
    stop_reason: str | None = None
```

字段说明：

- `index`：第几次补证据 iteration，从 1 开始。
- `quality_issues_before`：执行任务前的审计问题。
- `evidence_tasks`：本轮计划执行的任务。
- `task_results`：任务结果。
- `quality_issues_after`：重建 `run_1` 后的再审计问题。
- `stop_reason`：本轮后停止的原因。

### 6.5 LoopResult

```python
@dataclass(frozen=True)
class LoopResult:
    initial_run: ResearchRunState
    final_run: ResearchRunState
    iterations: list[LoopIteration]
    stop_reason: Literal[
        "quality_passed",
        "no_actionable_tasks",
        "max_loops_reached",
        "all_tasks_failed",
        "guardrail_blocked",
        "no_quality_improvement",
    ]
    quality_delta: dict[str, Any] = field(default_factory=dict)
```

字段说明：

- `initial_run`：初稿 `run_0`。
- `final_run`：最终报告 run。执行补证据后应为 `run_1`。
- `iterations`：补证据过程记录。
- `stop_reason`：最终停止原因。
- `quality_delta`：质量变化摘要。

## 7. Bundle 合并设计

新增函数：

```python
def merge_task_results_into_bundle(
    base_bundle: ToolResultBundle,
    task_results: list[EvidenceTaskResult],
) -> ToolResultBundle:
    ...
```

行为：

```text
base_bundle.news + retry_news_zh result -> enhanced_bundle.news
base_bundle.sector_history + fetch_sector_history result -> enhanced_bundle.sector_history
base_bundle.peer_history + fetch_peer_history result -> enhanced_bundle.peer_history
failed task -> 不覆盖原 slot，只记录失败 result
```

说明：

- 如果任务成功，按 `tool_result_slot` 覆盖或增强对应 bundle slot。
- 如果任务失败，不应污染 bundle。
- 如果多个 task 写同一 slot，V1 先按任务顺序使用最后一个 completed result。
- merge 函数必须是纯函数：不修改 `base_bundle`。

测试要求：

```text
test_retry_news_zh_result_replaces_empty_news_slot
test_fetch_peer_history_result_adds_peer_history_slot
test_failed_task_result_does_not_mutate_bundle
test_merge_is_pure_function
```

## 8. Loop 控制流程

伪代码：

```python
def build_research_run_with_loop(query, max_loops=1):
    base_bundle = provider.fetch(...)
    run_0 = build_research_run_from_bundle(query, base_bundle, ...)

    current_run = run_0
    current_bundle = base_bundle
    iterations = []

    for index in range(1, max_loops + 1):
        issues_before = auditor.audit(current_run)
        if quality_passed(issues_before):
            return LoopResult(run_0, current_run, iterations, "quality_passed")

        tasks = planner.plan(issues_before, current_run)
        if not tasks:
            return LoopResult(run_0, current_run, iterations, "no_actionable_tasks")

        task_results = executor.execute(tasks, current_run)
        if all_failed(task_results):
            return LoopResult(run_0, current_run, iterations, "all_tasks_failed")

        enhanced_bundle = merge_task_results_into_bundle(current_bundle, task_results)
        next_run = build_research_run_from_bundle(query, enhanced_bundle, ...)
        issues_after = auditor.audit(next_run)

        iteration = LoopIteration(index, issues_before, tasks, task_results, issues_after)
        iterations.append(iteration)

        if next_run.guardrail and not next_run.guardrail.passed:
            return LoopResult(run_0, next_run, iterations, "guardrail_blocked")

        if not quality_improved(current_run, next_run, issues_before, issues_after):
            return LoopResult(run_0, next_run, iterations, "no_quality_improvement")

        current_run = next_run
        current_bundle = enhanced_bundle

    return LoopResult(run_0, current_run, iterations, "max_loops_reached")
```

伪代码说明：

- `base_bundle`：第一轮工具结果。
- `run_0`：初稿。
- `current_bundle`：当前用于重建 run 的 bundle。
- `issues_before`：补证据前质量问题。
- `tasks`：白名单补证据任务。
- `task_results`：任务执行结果。
- `enhanced_bundle`：合并补证据后的 bundle。
- `next_run`：从 enhanced bundle 重新生成的 run。
- `issues_after`：再审计结果。
- `quality_improved()`：检查新增 fact、缺口减少、归因等级改善、issue 数减少等。

## 9. 质量改善判定

新增函数：

```python
def compute_quality_delta(before: ResearchRunState, after: ResearchRunState) -> dict[str, Any]:
    ...
```

建议字段：

```json
{
  "added_fact_types": ["peer_moves"],
  "removed_missing_fact_types": ["peer_moves"],
  "attribution_level_before": "candidate_factor",
  "attribution_level_after": "likely_factor",
  "issue_count_before": 3,
  "issue_count_after": 1
}
```

字段说明：

- `added_fact_types`：final run 新增的 verified fact type。
- `removed_missing_fact_types`：被补掉的 missing fact type。
- `attribution_level_before/after`：归因等级变化。
- `issue_count_before/after`：审计问题数量变化。

`quality_improved()` 至少满足其一：

```text
新增 fact type
missing fact 减少
error issue 减少
warning issue 减少
归因等级从 unsupported/candidate 升级
```

否则停止为 `no_quality_improvement`。

## 10. Trace 设计

新增 trace event：

```text
loop_started
audit_completed
evidence_tasks_planned
evidence_task_completed
evidence_task_failed
enhanced_bundle_built
run_rebuilt_from_enhanced_bundle
loop_stopped
```

示例：

```json
{
  "event_type": "run_rebuilt_from_enhanced_bundle",
  "payload": {
    "iteration_index": 1,
    "previous_run_id": "rrun_000",
    "next_run_id": "rrun_111",
    "added_tool_result_slots": ["peer_history"],
    "added_fact_types": ["peer_moves"]
  }
}
```

字段说明：

- `iteration_index`：第几轮补证据。
- `previous_run_id`：重建前 run id。
- `next_run_id`：重建后 run id。
- `added_tool_result_slots`：哪些 bundle slot 被补充。
- `added_fact_types`：重建后新增了哪些 verified fact type。

## 11. Memo 输出设计

最终 memo 正文来自 `final_run.final_output`，然后附加 loop summary。

示例：

```text
## 本轮质量改进
- Loop 状态：已执行 1 次补证据；停止原因：max_loops_reached。
- 初稿 run：rrun_000；最终 run：rrun_111。
- 新增证据：peer_moves。
- 仍缺证据：news_events。
- 归因等级变化：candidate_factor -> likely_factor。
- Trace 日志：/path/to/trace.jsonl
```

说明：

- `Loop 状态`：说明是否真的执行了补证据。
- `初稿 run / 最终 run`：证明最终报告来自重建 run。
- `新增证据`：展示 loop 的实际收益。
- `仍缺证据`：保留风险边界。
- `归因等级变化`：展示质量改善或无改善。
- `Trace 日志`：方便 review 和调试。

## 12. CLI 设计

新增参数：

```bash
.venv/bin/python -m src.agents.research_demo \
  --query "美光 MU 最近为什么大跌？" \
  --data-source live \
  --synthesizer mock \
  --loop \
  --max-loops 1 \
  --quality-threshold normal \
  --debug
```

参数说明：

- `--loop`：启用 bounded evidence repair loop。
- `--max-loops`：最大 evidence improvement iteration 数。V1 默认 1。
- `--quality-threshold`：质量阈值。V1 先实现 `normal`，预留 `strict`。
- `--debug`：打印 loop 和 guardrail debug 信息。

## 13. TDD 与验收测试

实现顺序必须遵守：

```text
写失败测试
  -> 跑测试确认红灯
  -> 最小实现
  -> 跑目标测试确认绿灯
  -> 跑全量测试
```

关键测试：

```text
test_auditor_flags_missing_peer_moves
test_task_planner_maps_missing_peer_to_fetch_peer_history
test_task_result_merges_into_enhanced_bundle
test_loop_rebuilds_final_run_from_enhanced_bundle
test_final_run_id_differs_from_initial_run_id
test_failed_task_keeps_initial_run_and_records_failure
test_loop_summary_reports_added_fact_types
```

最关键验收断言：

```python
assert result.initial_run.run_id != result.final_run.run_id
assert "peer_moves" not in initial_fact_types
assert "peer_moves" in final_fact_types
```

断言说明：

- 第一行证明不是 patch 原 run。
- 第二行证明初稿确实缺证据。
- 第三行证明补证据结果进入了 final run。

## 14. 实现阶段

### Phase 1: QualityAuditor

只做审计，不补证据。

### Phase 2: EvidenceTaskPlanner

把 issue 映射到白名单任务。

### Phase 3: EvidenceTaskResult 和 bundle merge

实现 task result 到 enhanced bundle 的纯函数合并。

### Phase 4: LoopEngine fixture rebuild

用 fixture 证明 run_0 -> enhanced_bundle_1 -> run_1。

### Phase 5: Trace 和 memo summary

展示 loop 做了什么、为何停止。

### Phase 6: CLI 和 live smoke

支持 `--loop --max-loops 1`，跑 MU、腾讯、茅台。

## 15. 后续演进

V1：Bounded Evidence Repair Loop。

V2：提高 `max_loops`，加入 quality score。

V3：加入 rule-based semantic hints。

V4：加入 hybrid LLM judge：规则先筛高风险 claim，再让 LLM judge 输出 schema verdict。
