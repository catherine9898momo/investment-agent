# 归因分析质量与 Trace 可追溯性 PRD

## 1. 背景

当前 investment-agent 已经能把用户问题解析成研究路由，拉取价格、历史行情、新闻、公司行动和用户偏好，并在报告中输出证据、缺口和护栏结果。最近一次真实数据运行暴露出三个关键问题：

1. 报告难以直接反查本次输出对应的 trace log 文件。
2. 数据质量信号没有进入足够强的决策门控，例如 `nan` 收盘价、历史行情有效点不足、quote/history/company action 口径不明。
3. 归因措辞偏强：在缺少板块 ETF、同行涨跌和宏观/财报证据时，报告仍可能写出“某因素主导”一类强结论。

同时需要纠正一个重要原则：价格异常检测不是为了否定官方数据，而是为了触发 provenance 和口径复核。如果官方行情源、新闻、历史序列一致，则接受新价格并更新先验；如果 quote/history/company actions 口径不一致，才降级或提示风险。

## 2. 产品目标

### 2.1 总目标

把当前“可审计初稿”升级为“不会轻易误导的研究草稿”：

- 明显脏数据不能进入结论。
- 可疑但被权威来源交叉支持的数据可以进入结论，但必须保留 provenance 和口径说明。
- 缺少归因关键证据时，只能输出候选原因，不能输出主导原因。
- 每份报告都能直接定位对应 trace log 和 trace HTML 预览。

### 2.2 非目标

- 不在本阶段直接提供交易建议。
- 不要求一次性接入完整财务数据库。
- 不把新闻标题直接当作因果证明。
- 不用模型历史印象覆盖官方行情数据。
- 不在 P0 阶段实现复杂机器学习异常检测；先用确定性规则和来源一致性检查。

## 3. 用户场景

### 场景 A：用户询问“为什么大跌”

用户问：

```text
帮我看 MU 最近为什么大跌？
```

系统应：

1. 识别为 `news_explanation` / price attribution 问题。
2. 拉取 quote/history/news/corporate actions/preferences。
3. 对 quote/history 做有限数字、有效点数量和口径一致性检查。
4. 拉取板块 ETF 和同行涨跌，或明确暴露缺口。
5. 如果证据不足，只输出候选因素和下一步核验，不输出“主导因素”。
6. 报告底部展示 trace log 路径和 trace 预览入口。

### 场景 B：官方行情价格高于历史先验

如果 MU 返回 `935.89`、历史行情出现 `1079.57` 这类与旧先验冲突的价格，系统不应直接判错。

系统应：

- 检查 quote/history 是否同源或时间窗口一致。
- 检查新闻是否有相近价格描述或目标价语境。
- 检查公司行动是否存在窗口内拆股/复权影响。
- 若多源一致，则接受价格，并把“旧先验冲突”视为已解决。
- 若口径不一致，则生成 data quality warning，并降级归因结论。

## 4. 功能需求

## FR1. 数据可信度 Gate

### FR1.1 有限数字检查

检查字段：

```text
quote.price
quote.previous_close
quote.change_pct
history.bars[].close
```

规则：

- `nan`、`inf`、`-inf`、`null`、非数字字符串不得进入价格区间和结论。
- `history.close` 过滤后若无有效值，历史行情 fact 应降级为 data quality fact。
- 若 quote 核心字段缺失，价格归因不能升级。

验收：

- 报告中不出现 `nan` / `inf`。
- trace 中记录被过滤的无效字段数量。
- 数据质量问题进入 `missing_facts` 或 `data_quality_warning`。

### FR1.2 历史行情有效性

规则：

- 至少 2 个有效 close 才能输出“区间”。
- 至少 3 个有效 close 才能输出“最近走势”。
- 不足 5 个有效 close 时，报告应提示历史窗口不完整。

验收：

- 只有 1 个有效 close 时，报告不能写“近 5 个交易日收盘价区间”。
- 有 2 个有效 close 时，可写区间，但不能写趋势判断。
- 有 3-5 个有效 close 时，可写趋势，但需说明样本窗口。

### FR1.3 复权/拆股口径检查

公司行动不能只展示“拆股记录数量”和“累计因子”。需要判断：

- 是否存在 `actions.date` 落在研究窗口内。
- quote 与 history 是否标明 adjusted/unadjusted 口径。
- 如果口径缺失，是否能通过价格连续性和公司行动时间做弱推断。

验收：

- 若窗口内存在 split/dividend 且 history/quote 口径不明，归因结论必须降级。
- 报告应显示“公司行动未落在本轮窗口内”或“公司行动口径不明，需要复核”。
- trace 中记录 corporate action window check 结果。

### FR1.4 异常价格 provenance 复核

异常价格检测不是否定官方数据，而是触发复核。

触发条件：

- 当前价格相对最近有效历史均值偏离超过阈值。
- quote 与 history 最新 close 偏离超过阈值。
- 价格与已知旧先验或上次本地缓存差异极大。
- 新闻中存在明显不同价格口径。

复核动作：

- 检查 quote/history 时间戳。
- 检查 quote/history 来源和复权字段。
- 检查公司行动窗口。
- 检查新闻是否支持该价格区间。

结论规则：

- 多源一致：接受价格，记录 provenance_confirmed。
- 口径不明：接受数据但降级归因强度，记录 provenance_uncertain。
- 多源冲突：阻断强结论，记录 conflicting_price_sources。

验收：

- 报告不能因为“看起来贵/高”直接判定官方行情错误。
- 可疑价格必须有 `data_quality_warning` 或 `provenance_confirmed` 之一。

## FR2. 归因证据补齐

### FR2.1 板块/指数对照

同窗口拉取：

```text
SMH
SOXX
QQQ
```

输出：

- 标的涨跌幅。
- 板块 ETF/指数涨跌幅。
- 标的相对板块超额涨跌。

验收：

- `sector_move` fact 进入 verified fact table。
- 如果 sector 数据缺失，报告只能说“待核验板块因素”。

### FR2.2 同行对照

默认同行：

```text
NVDA
AMD
AVGO
WDC
STX
SNDK
```

输出：

- 同行同窗口涨跌幅。
- 同步下跌比例。
- 标的是行业共振还是个股异常。

验收：

- `peer_moves` fact 进入 verified fact table。
- 如果同行缺失，不能把板块/同行因素写成主导原因。

### FR2.3 新闻分类

新闻不再只列标题。需要分类为：

```text
company_specific
sector
macro
analyst
earnings_or_guidance
corporate_action
insider
```

验收：

- 每条新闻至少有一个分类。
- 归因报告按分类聚合新闻，而不是把标题直接当因果证据。
- 标题只能作为线索，不能单独支撑 confirmed cause。

### FR2.4 归因证据矩阵

每个候选原因都要输出：

```text
支持证据
反证/缺口
置信度
下一步验证
```

验收：

- 报告中原因排序从“原因列表”升级为“候选原因矩阵”。
- 每个原因都能追溯到 fact/source。
- 缺失关键证据时置信度最高只能到 `candidate_factor`。

## FR3. 归因措辞制度化

建立归因等级：

```text
confirmed_cause      已确认原因
likely_factor        较可能因素
candidate_factor     候选因素
background_context   背景信息
unsupported          不支持
```

规则：

- 缺少 `sector_move` 和 `peer_moves` 时，板块因素最多为 `candidate_factor`。
- 只有新闻标题时，最多为 `background_context` 或 `candidate_factor`。
- 有 quote/history 但无新闻或对照数据时，只能写价格现象，不能写原因。
- 有多源一致证据时才允许 `likely_factor`。
- `confirmed_cause` 需要直接公司公告、财报/指引、重大公司行动或高质量多源一致证据。

验收：

- 缺少 sector/peer 数据时，报告不能出现“主导”“主要原因已确认”等表达。
- trace 中记录每个原因的 attribution_level 和降级理由。

## FR4. Trace 与报告联动

### FR4.1 报告输出 trace 信息

报告底部固定输出：

```text
Trace 日志：logs/research_traces/xxx.jsonl
Trace 预览：生成后的 html/http 链接（如果可用）
```

验收：

- 每份 CLI 报告都能定位对应 JSONL。
- 如果未启动预览 server，也要输出可生成预览的命令。

### FR4.2 Trace viewer 质量面板

trace viewer 增加：

```text
数据质量问题
缺失证据
被降级的归因
通过/未通过的声明
```

验收：

- 打开 HTML 后无需展开所有事件，就能看到分析质量摘要。
- 点击质量问题能跳转到对应 trace 事件。

### FR4.3 一键运行与预览

新增命令能力：

```bash
python3 -m src.agents.research_demo --query "..." --data-source live --trace-view
```

输出：

- Markdown 报告。
- Trace JSONL 路径。
- Trace HTML 预览链接。

验收：

- 在 Codex 浏览器中点击预览链接可直接打开 HTML。
- 如果端口被占用，自动选择可用端口。

## 5. 优先级

### P0：数据可信度先过关

- 有限数字检查。
- 历史有效点数量检查。
- 复权/拆股窗口检查。
- 异常价格 provenance 复核。
- 报告 trace log 路径输出。

### P1：补齐归因证据

- 板块/指数对照。
- 同行对照。
- 新闻分类。
- 归因证据矩阵。

### P2：归因措辞制度化

- attribution level。
- 措辞降级规则。
- claim verifier / renderer 集成。

### P3：Trace 产品化

- trace viewer 质量面板。
- 一键运行并预览。
- 报告输出 trace preview link。

## 6. 成功指标

- 报告中 `nan/inf/null` 价格输出次数为 0。
- 缺少 sector/peer 数据时，“主导原因”误用次数为 0。
- 每份报告 100% 带 trace log 路径。
- 归因结论 100% 带 attribution level。
- 对价格异常的处理 100% 有 provenance 状态，而不是直接判错。
- trace viewer 首屏能看到数据质量和证据缺口摘要。
