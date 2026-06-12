# 归因分析质量与 Trace 可追溯性技术方案

## 1. 方案目标

本文档承接 `docs/ATTRIBUTION_QUALITY_AND_TRACEABILITY_PRD_CN.md`，描述如何在当前项目中落地数据可信度 gate、归因证据补齐、措辞降级和 trace/report 联动。

核心原则：

```text
价格异常检测不是为了否定官方数据，而是为了触发 provenance/口径复核。
如果官方行情源、新闻、历史序列一致，则接受新价格，并更新先验。
如果 quote/history/公司行动口径不一致，才降级或提示风险。
```

## 2. 当前代码基线

关键模块：

- `src/research/tool_provider.py`
  - `LiveToolResultProvider` 当前拉取 preferences、quote、history、news、corporate actions。
- `src/research/normalizers.py`
  - 将 raw tool result 归一化为 `Source` / `Fact`。
  - 当前已有 `normalize_data_quality()`，但覆盖有限。
- `src/research/fact_verifier.py`
  - 将 `Fact.metric` 映射为 `VerifiedFact.fact_type`。
- `src/research/attribution_planner.py`
  - 对 price_drop 问题生成 `sector_move`、`peer_moves` 等需求，但当前还没有实际工具结果填充。
- `src/research/context_builder.py`
  - 将 verified facts 和 missing facts 组装成 research context。
- `src/research/claim_verifier.py`
  - 当前能拦截直接交易建议、缺失 evidence、价格单独因果推断等。
- `src/research/memo_renderer.py`
  - 渲染用户报告。
- `src/research/trace_viewer.py`
  - 生成 HTML trace 预览。
- `src/agents/research_demo.py`
  - 串联完整 research run。

## 3. 总体架构

新增质量与归因链路：

```text
Live/Fixture Tool Results
  -> normalize_*()
  -> data_quality_gate
  -> Source / Fact
  -> VerifiedFact / MissingFact
  -> AttributionEvidence Matrix
  -> Synthesis / Claim Verification
  -> Memo Renderer with attribution levels
  -> Guardrail
  -> Trace Viewer Quality Panel
```

建议采用渐进式改造：

1. P0 先在 `normalizers.py` 和 `memo_renderer.py` 落地数据质量 gate，不改变 provider API。
2. P1 扩展 `ToolResultBundle`，加入 sector/peer tool results。
3. P2 增加 attribution level 和 renderer 降级规则。
4. P3 增强 trace viewer 和 CLI。

## 4. 数据结构设计

### 4.1 新增 DataQualityIssue

建议在 `src/research/models.py` 增加：

```python
@dataclass
class DataQualityIssue:
    """/**
     * 单个数据质量问题或 provenance 复核结果。
     *
     * @property issue_type - invalid_number、insufficient_history、price_provenance_uncertain 等。
     * @property severity - info/warning/error。
     * @property metric - 影响的 fact metric。
     * @property message - 用户/trace 可读说明。
     * @property fields - 涉及的原始字段路径。
     * @property provenance_status - confirmed/uncertain/conflicting/not_checked。
     */
    """

    issue_type: str
    severity: Literal["info", "warning", "error"]
    metric: str
    message: str
    fields: list[str] = field(default_factory=list)
    provenance_status: Literal["confirmed", "uncertain", "conflicting", "not_checked"] = "not_checked"
```

MVP 可先不挂到 `ResearchRunState`，而是以 `Fact(metric="data_quality_warning")` 形式落库；后续再结构化。

### 4.2 新增 AttributionCause

建议在 `models.py` 增加：

```python
@dataclass
class AttributionCause:
    label: str
    level: Literal[
        "confirmed_cause",
        "likely_factor",
        "candidate_factor",
        "background_context",
        "unsupported",
    ]
    support_fact_ids: list[str]
    counter_fact_ids: list[str] = field(default_factory=list)
    missing_fact_types: list[str] = field(default_factory=list)
    confidence: Literal["high", "medium", "low"] = "low"
    rationale: str = ""
    next_checks: list[str] = field(default_factory=list)
```

MVP 可先由 renderer 内部 dict 生成；P2 再提升为稳定模型字段。

### 4.3 ToolResultBundle 扩展

P1 扩展：

```python
@dataclass
class ToolResultBundle:
    data_source: Literal["fixture", "live"]
    preferences: dict[str, Any]
    quote: dict[str, Any]
    history: dict[str, Any]
    news: dict[str, Any]
    corporate_actions: dict[str, Any]
    sector_history: dict[str, Any] | None = None
    peer_history: dict[str, Any] | None = None
```

`sector_history` 建议 shape：

```json
{
  "window": {"start_date": "...", "end_date": "..."},
  "items": [
    {"symbol": "SMH", "change_pct": -2.1, "bars": [...]},
    {"symbol": "SOXX", "change_pct": -2.4, "bars": [...]},
    {"symbol": "QQQ", "change_pct": -1.0, "bars": [...]}
  ]
}
```

`peer_history` 同理。

## 5. P0 技术实现

### 5.1 有限数字工具函数

新增模块：

```text
src/research/data_quality.py
```

接口：

```python
from math import isfinite


def is_finite_number(value: object) -> bool:
    return isinstance(value, (int, float)) and isfinite(float(value))


def finite_closes(bars: list[dict]) -> list[float]:
    """过滤 nan/inf/null/non-number close。"""
```

迁移当前 `normalizers.py` / `memo_renderer.py` 内部重复的 `_finite_closes()` 到该模块。

### 5.2 normalize_history 强化

修改 `src/research/normalizers.py`：

- `summarize_history_fact()` 使用 `finite_closes()`。
- `_valid_history()` 至少要求 2 个有效 close 才标记为 `five_day_close_range`。
- 少于 2 个有效 close 时 metric 改为 `unknown_history` 或 `data_quality_history_insufficient`。
- 少于 5 个有效 close 时新增 warning fact。

伪代码：

```python
closes = finite_closes(bars)
if len(closes) == 0:
    metric = "failure_five_day_close_range"
elif len(closes) == 1:
    metric = "data_quality_history_insufficient"
elif len(closes) < requested_days:
    add_quality_fact("history_window_incomplete")
else:
    metric = "five_day_close_range"
```

### 5.3 quote sanity check

在 `normalize_data_quality()` 增加：

- `invalid_quote_price`
- `invalid_previous_close`
- `invalid_change_pct`
- `quote_change_mismatch`

`quote_change_mismatch`：

```python
computed = (price - previous_close) / previous_close * 100
abs(computed - change_pct) > tolerance
```

### 5.4 公司行动窗口检查

新增函数：

```python
def corporate_actions_in_window(actions: dict, time_window: TimeWindow | None) -> list[dict]: ...
def has_adjustment_metadata(history: dict, quote: dict) -> bool: ...
```

落点选择：

- MVP：在 `normalize_data_quality()` 里只检查 actions/date 是否在窗口内，需要传入 `time_window`。
- 如果不想改函数签名，可在 `build_research_run_from_bundle()` 中调用新 `build_data_quality_facts(bundle, run.time_window, symbol)`。

推荐第二种，避免 `normalize_tool_result_bundle()` 参数继续膨胀。

### 5.5 provenance 状态

新增 data quality fact metric：

```text
price_provenance_confirmed
price_provenance_uncertain
conflicting_price_sources
```

初期规则：

- quote/history 都有有效价格，且偏离在合理阈值内：`price_provenance_confirmed`。
- quote/history 有效但时间戳/adjustment metadata 缺失：`price_provenance_uncertain` warning。
- quote 与 history 最新 close 偏离超过阈值，且无盘中/时间差解释：`conflicting_price_sources` error/warning。

注意：`935.89` 这类价格高低本身不作为错误，只作为复核触发条件。

## 6. P1 技术实现

### 6.1 Tool provider 扩展

修改 `src/research/tool_provider.py`：

- 增加 `fetch_history_many(symbols: list[str], days: int)` helper。
- Live provider 对 `SMH/SOXX/QQQ` 和 peer symbols 调用 `_fetch_history()`。
- Fixture provider 增加确定性 sector/peer fixture。

默认 symbols：

- sector/index: `SMH`, `SOXX`, `QQQ`
- peers: `NVDA`, `AMD`, `AVGO`, `WDC`, `STX`, `SNDK`

这些默认值应来自 `AttributionPlan.index_symbols` 和 `AttributionPlan.peer_symbols`，不要在 provider 内写死。

### 6.2 normalize_sector_peer

新增 normalizers：

```python
def normalize_sector_history(sector_history: dict, data_source: str, symbol: str) -> NormalizedToolResult: ...
def normalize_peer_history(peer_history: dict, data_source: str, symbol: str) -> NormalizedToolResult: ...
```

输出 metric：

```text
sector_move
peer_moves
```

fact value：

```json
{
  "target_symbol": "MU",
  "target_change_pct": -2.0,
  "items": [
    {"symbol": "SMH", "change_pct": -2.3, "valid_points": 5},
    {"symbol": "SOXX", "change_pct": -2.5, "valid_points": 5}
  ],
  "relative_move_pct": 0.3,
  "synchronous_decline_count": 2
}
```

### 6.3 fact_verifier mapping

在 `src/research/fact_verifier.py` 增加：

```python
"sector_move": "sector_move"
"peer_moves": "peer_moves"
"news_category_summary": "news_events"
```

## 7. P1 新闻分类

新增模块：

```text
src/research/news_classifier.py
```

MVP 使用规则：

```python
CATEGORY_KEYWORDS = {
    "sector": ["chip", "semiconductor", "memory", "AI trade", "sector"],
    "analyst": ["analyst", "rating", "price target", "upgrade", "downgrade"],
    "earnings_or_guidance": ["earnings", "revenue guidance", "forecast", "outlook"],
    "corporate_action": ["split", "dividend", "buyback"],
    "insider": ["CEO", "insider", "sold", "bought"],
    "macro": ["rates", "Nasdaq", "S&P", "yield", "macro"],
    "company_specific": ["Micron", "MU", "HBM", "DRAM", "NAND"],
}
```

输出：

```python
def classify_news_items(news: dict) -> dict:
    return {
        "items": [... item + categories ...],
        "category_counts": {...},
    }
```

`normalize_news()` 可新增 `news_category_summary` fact，保留原 `news_tone`。

## 8. P2 归因等级与措辞降级

新增模块：

```text
src/research/attribution_evaluator.py
```

核心接口：

```python
def build_attribution_causes(run: ResearchRunState) -> list[AttributionCause]: ...
def attribution_level_for_cause(cause, run) -> str: ...
def downgrade_reason(cause, run) -> str | None: ...
```

规则：

- 缺 `sector_move` / `peer_moves` 时，sector cause 最大 `candidate_factor`。
- 只有 news 标题，无 sector/peer/price 支撑时，最大 `background_context`。
- 有 sector + peer 同步下跌，且 target 与 sector 同向，最大 `likely_factor`。
- 有公司公告/财报/指引直接命中，且价格同向，才可能 `confirmed_cause`。
- 有 data quality error 时，所有 cause 最大 `background_context`。

修改 `memo_renderer.py`：

- `cause_ranking_lines()` 改为读取 `AttributionCause`。
- 文案显示等级：`候选因素`、`较可能因素` 等。
- 禁止在低等级中使用“主导”“确认”“直接导致”。

## 9. P3 Trace 产品化

### 9.1 research_demo CLI

修改 `src/agents/research_demo.py`：

新增参数：

```text
--trace-view
--trace-view-host
--trace-view-port
```

行为：

1. 正常生成 run 和报告。
2. 调用 `src.research.trace_viewer.write_view(run.trace_path)`。
3. 如果 `--trace-view`，启动 preview server 或打印可复用命令。

注意：CLI 中长期运行 server 会阻塞。建议 MVP 输出命令和 HTML 路径；Codex 场景可另起命令启动。

### 9.2 报告 trace preview link

`ResearchRunState` 可新增：

```python
trace_preview_url: str | None = None
```

`memo_renderer.source_summary_lines()` 输出：

```text
Trace 日志：...
Trace 预览：...
```

如果没有 URL，输出：

```text
Trace 预览：运行 python3 -m src.research.trace_viewer <trace_path> --serve 生成。
```

### 9.3 trace_viewer 质量面板

修改 `src/research/trace_viewer.py`：

在前端根据 rows 提取：

- `payload.missing_facts`
- `event_type == "guardrail_result"`
- `event_type == "claim_verification"`
- `fact_added` 中 metric 以 `stale_` / `missing_` / `failure_` / `unknown_` / `conflicting_` / `data_quality_` 开头
- attribution downgrade 事件（P2 新增）

新增顶部面板：

```text
数据质量问题 N
缺失证据 N
被降级归因 N
声明核验问题 N
```

点击卡片后自动筛选或滚动到相关事件。

## 10. Trace 事件扩展

新增事件类型：

```text
data_quality_checked
attribution_causes_built
attribution_downgraded
trace_view_generated
```

payload 示例：

```json
{
  "event_type": "data_quality_checked",
  "payload": {
    "issues": [
      {
        "issue_type": "price_provenance_uncertain",
        "severity": "warning",
        "metric": "latest_price",
        "message": "quote/history adjustment metadata missing; attribution capped at candidate_factor",
        "fields": ["quote.price", "history.bars[-1].close"],
        "provenance_status": "uncertain"
      }
    ]
  }
}
```

## 11. 测试计划

### P0 单元测试

- `test_normalizers_filters_nan_and_inf_close`
- `test_history_with_one_close_becomes_quality_warning`
- `test_quote_change_mismatch_generates_quality_fact`
- `test_price_high_but_consistent_is_not_error`
- `test_corporate_action_in_window_caps_attribution`
- `test_memo_includes_trace_path`

### P1 单元测试

- `test_sector_history_normalizes_to_sector_move`
- `test_peer_history_normalizes_to_peer_moves`
- `test_missing_sector_keeps_sector_cause_candidate_only`
- `test_news_classifier_assigns_categories`

### P2 单元测试

- `test_sector_cause_without_sector_fact_is_candidate`
- `test_sector_and_peer_sync_raise_to_likely_factor`
- `test_data_quality_error_caps_all_causes`
- `test_renderer_avoids_dominant_language_for_candidate_factor`

### P3 单元/快照测试

- `test_trace_viewer_quality_panel_counts_issues`
- `test_trace_view_command_prints_preview_url`
- `test_report_prints_trace_preview_command_when_url_missing`

## 12. 分阶段实施建议

### Milestone 1：P0 数据可信度 Gate

改动范围：

- `src/research/data_quality.py`
- `src/research/normalizers.py`
- `src/research/memo_renderer.py`
- `src/research/test_normalizers.py`
- `src/research/test_memo_renderer.py`

产出：报告不再出现 `nan`，trace/report 有数据质量 warning，trace path 固定输出。

### Milestone 2：P2 措辞降级 MVP

改动范围：

- `src/research/attribution_evaluator.py`
- `src/research/memo_renderer.py`
- `src/research/claim_verifier.py` 可选

产出：缺 sector/peer 时不能写“主导因素”。

### Milestone 3：P1 板块/同行证据

改动范围：

- `src/research/tool_provider.py`
- `src/research/normalizers.py`
- `src/research/fact_verifier.py`
- `src/research/attribution_planner.py`

产出：`sector_move` / `peer_moves` 从 missing fact 变成 verified fact。

### Milestone 4：P3 Trace 产品化

改动范围：

- `src/research/trace_viewer.py`
- `src/agents/research_demo.py`
- `src/research/models.py` 可选新增 `trace_preview_url`

产出：报告 + trace 预览链路一键可用。

## 13. 风险与取舍

- 行情源自身可能有错误，因此不能把“官方数据”视为不可复核真理；但系统也不能用模型先验否定官方数据。
- sector/peer 拉取会增加网络和时间成本，需要可配置开关或超时降级。
- 新闻分类 MVP 用规则足够可控，但覆盖有限；后续可接窄任务 LLM classifier。
- `--trace-view` 启动 server 在 CLI 中可能阻塞，Codex 场景需要单独处理进程生命周期。
- 归因等级太保守会让报告显得“不敢说”；但这是当前阶段更可取的失败模式。
