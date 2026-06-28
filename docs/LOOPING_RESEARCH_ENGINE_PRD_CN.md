# Looping Research Engineer PRD

## 1. 背景

当前 investment-agent 已经具备单轮研究报告能力：用户提出问题后，系统会完成 query intake、工具数据获取、Source/Fact 归一化、事实核验、归因等级评估、claim verification、memo 渲染和 guardrail 检查。

但单轮报告仍有一个产品缺口：系统已经能暴露缺失证据和质量问题，却还不能自动把这些问题转化为一次受控的补证据和重新生成报告流程。用户看到的仍然可能是“初稿 + 缺口提示”，而不是“初稿经过一次审稿和补证据修复后的版本”。

本 PRD 定义第一版 `Looping Research Engineer`。它不是开放式 autonomous agent loop，而是一个 **Bounded Evidence Repair Loop**：系统先生成初稿，再审计初稿，再按白名单任务补一轮证据，然后必须回到报告生成 pipeline 重新生成最终报告。

## 2. 产品目标

第一版目标：

- 把“报告审计 -> 补证据 -> 重新生成报告 -> 再审计”的闭环跑起来。
- 明确 `max_loops=1` 的含义：最多执行一次 evidence improvement iteration，但会构建 `run_0` 和 `run_1` 两份报告状态。
- 补证据结果不能只贴到报告底部，必须回到 report generation pipeline。
- 每一轮是否继续、补了什么、为什么停止，都必须可 trace。
- 所有 loop 行为必须可通过单测或 fixture regression 验证。

非目标：

- 不做开放式多轮 autonomous research。
- 不允许 LLM 自由提出新工具调用。
- 不允许 LLM 把自己的判断写入 facts。
- 不直接实现 LLM judge 语义支撑评估。
- 不实现完整多轮对话；多轮对话建立在本 loop 稳定之后。
- 不提供交易建议。

## 3. Loop 定义

V1 是 **Bounded Evidence Repair Loop**。

标准流程：

```text
run_0 = 生成初稿
  -> audit_0 = 审计初稿
  -> tasks_1 = 生成补证据任务
  -> evidence_1 = 执行补证据任务
  -> enhanced_bundle_1 = 合并原始工具结果和补证据结果
  -> run_1 = 用 enhanced_bundle_1 重新生成报告
  -> audit_1 = 再审计最终报告
  -> final = 输出 run_1 + loop summary
```

流程说明：

- `run_0`：第一次常规报告构建结果。
- `audit_0`：对 `run_0` 做质量审计，发现缺证据、partial evidence、归因过强、guardrail 风险等问题。
- `tasks_1`：把可处理的质量问题映射成白名单补证据任务。
- `evidence_1`：执行补证据任务得到的结构化工具结果或失败信息。
- `enhanced_bundle_1`：把原始 `ToolResultBundle` 与补证据结果合并后的增强数据包。
- `run_1`：必须通过 `build_research_run_from_bundle(enhanced_bundle_1)` 重新生成，而不是 patch 原报告文本。
- `audit_1`：对 `run_1` 再审计，确认质量是否改善以及还剩哪些缺口。
- `final`：最终用户看到的是 `run_1` 的报告正文，加上 loop summary。

`max_loops=1` 的产品含义：

```text
最多执行 1 次 evidence improvement iteration。
这不是“不补证据”，也不是“只审计一次”。
它包含 initial run 和 final run 两次报告构建。
```

## 4. 用户场景

### 场景 A：新闻缺失后中文重试

用户问：

```text
茅台最近表现怎么样？
```

第一轮可能出现：

```text
news_events = partial
missing_news = true
```

系统应：

- 审计出 `partial_news_events`。
- 生成 `retry_news_zh` 任务。
- 用中文公司名重试新闻。
- 把新闻结果合并进 enhanced bundle。
- 重新生成 `run_1`。
- 最终报告正文使用 `run_1`，底部说明本轮补过新闻或新闻仍缺失。

### 场景 B：同行缺失后补同行

用户问：

```text
美光 MU 最近为什么大跌？
```

第一轮如果缺 `peer_moves`，系统应：

- 审计出 `missing_peer_moves`。
- 生成 `fetch_peer_history`。
- 拉取 attribution plan 里的同行历史行情。
- 合并成 enhanced bundle。
- 重新跑 normalizer、fact verifier、attribution evaluator、synthesis、memo renderer 和 guardrail。

### 场景 C：没有可执行任务

如果审计发现“claim 与 evidence 语义关联弱”，但 V1 尚未实现 semantic support checker 或 LLM judge，则系统应：

- 记录质量问题。
- 不自由发明工具。
- 停止于 `no_actionable_tasks`。
- 在 loop summary 说明这个限制。

## 5. 功能需求

### FR1. 初稿质量审计

系统必须对 `run_0` 输出结构化质量问题。

至少支持：

```text
missing_price_move
missing_news_events
partial_news_events
missing_sector_move
missing_peer_moves
partial_comparison_supports_likely_factor
direct_trading_advice
guardrail_failed
```

说明：

- 这些 issue 是稳定枚举，用于测试、trace 和 task planning。
- 审计器只读 `ResearchRunState`，不得拉数据，不得改报告。
- 每个 issue 都必须能通过 fixture run 单测复现。

### FR2. 白名单补证据任务

系统只能从白名单生成任务。

第一版白名单：

```text
retry_news_zh
fetch_sector_history
fetch_peer_history
rerender_with_downgrade
```

说明：

- `retry_news_zh`：新闻缺失时，用中文 query 重试。
- `fetch_sector_history`：补 sector/index history。
- `fetch_peer_history`：补 peer history。
- `rerender_with_downgrade`：不补数据，只要求最终报告保守措辞。

禁止：

```text
LLM 自由提出新 task
LLM 自由新增工具
LLM 自由新增数据源
```

### FR3. 补证据后必须重建报告

补证据结果必须进入 enhanced bundle，然后重建 `run_1`。

硬约束：

```text
不得只把补充证据追加到 final memo 底部。
不得只 patch run_0.final_output。
不得绕过 normalizer / fact verifier / attribution evaluator / guardrail。
```

验收：

- `result.initial_run.run_id != result.final_run.run_id`。
- `final_run` 的 facts/verified facts 里能看到新增 fact type。
- `final_run.final_output` 来自 `run_1`，不是 `run_0` 文本拼接。

### FR4. 再审计和停止

重建 `run_1` 后必须再次审计。

停止原因必须稳定枚举：

```text
quality_passed
no_actionable_tasks
max_loops_reached
all_tasks_failed
guardrail_blocked
no_quality_improvement
```

说明：

- `quality_passed`：再审计没有发现需要继续处理的问题。
- `no_actionable_tasks`：有问题，但 V1 没有白名单任务能处理。
- `max_loops_reached`：达到最大补证据轮数。
- `all_tasks_failed`：本轮所有补证据任务失败。
- `guardrail_blocked`：最终报告触发 guardrail 阻断。
- `no_quality_improvement`：执行任务后质量没有任何改善。

### FR5. Loop Summary

最终报告必须说明 loop 做了什么。

示例：

```text
## 本轮质量改进
- Loop 状态：已执行 1 次补证据；停止原因：max_loops_reached。
- 新增证据：peer_moves, sector_move。
- 仍缺证据：news_events。
- 归因等级变化：candidate_factor -> likely_factor。
- Trace 日志：/path/to/trace.jsonl
```

说明：

- loop summary 只是解释过程，不替代报告正文。
- 报告正文必须来自 `run_1`。
- 如果没有新增证据，也必须解释为什么停止。

### FR6. Trace 可回放

每个 loop 事件必须写入 trace。

至少包含：

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

验收：

- 可以从 trace 看出 `run_0`、`tasks_1`、`run_1` 的关系。
- 可以看到每个 task 成功或失败。
- 可以看到停止原因。

## 6. 验收标准

第一版完成时必须满足：

- 有 PRD 和技术方案。
- 有 `QualityAuditor`、`EvidenceTaskPlanner`、`LoopEngine`。
- 所有新增模块都有单测。
- fixture case 能证明 `run_0 -> enhanced_bundle_1 -> run_1`。
- loop 后 final run 的 fact types 有可观察变化，或明确停止原因。
- CLI 支持 `--loop --max-loops 1`。
- 默认不启用 loop，不破坏现有单轮行为。
- live smoke 覆盖 MU、腾讯、茅台。
- 全量测试通过。

## 7. 风险与边界

### 7.1 名不副实的 loop

风险：如果只审计和 patch 文本，会变成单流程。

约束：必须重建 `run_1`，并在测试中断言 `initial_run.run_id != final_run.run_id`。

### 7.2 成本失控

风险：live 模式重复拉数据。

约束：默认 `max_loops=1`，每个 task `max_attempts=1`。

### 7.3 LLM 自由发挥

风险：LLM 自己发明工具或结论。

约束：V1 不接 LLM judge；所有 task 来自白名单。

### 7.4 质量无改善

风险：补证据执行了，但最终报告没有变好。

约束：计算 quality delta；如果无新增 fact、无缺口减少、无归因改善，则停止为 `no_quality_improvement`。

## 8. 后续演进

V1：Bounded Evidence Repair Loop

```text
规则审计 -> 白名单补证据 -> enhanced bundle -> run_1 -> 再审计
```

V2：Iterative Evidence Improvement Loop

```text
max_loops 可提升到 2/3，引入 quality_score 和 no_quality_improvement gate。
```

V3：Rule-based semantic hints

```text
用规则发现明显语义弱支撑，比如“利润率结论必须引用利润率/财报/指引类事实”。
```

V4：Hybrid LLM judge

```text
规则先筛高风险 claim -> LLM judge 只做 schema verdict -> verdict 进入 quality audit。
```
