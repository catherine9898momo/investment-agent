# W5 上下文工程实验 · 技术方案(评审稿)

> **文档目的**:把当前 W5 实验的设计、决策、未决项整理成自包含文档,交另一个 Agent 评审"是否完全合理"。
> **当前日期**:2026-05-25
> **方案状态**:S0 baseline 准备就绪,即将跑 30 轮产出实验语料

---

## 1. 背景与目标

### 1.1 我是谁 / 这事在干嘛

- 个人学习 sprint W5,主题"上下文工程量化能力"
- 实验载体:`investment-agent`(MCP 投资助理玩具,有 4 个 MCP server + 持仓 ground truth)
- 实验**不是做产品**,是产**简历杀招的可复现实验数据**

### 1.2 终点(简历那一句)

> "在 30 轮 Agent 对话场景下,我对比了 4 种上下文压缩策略——baseline / 滑动窗口 / LLM 摘要 / PreCompact hook——分别测出 token 节省 X% 和关键持仓信息保留率 Y%"

要求:
- 4 个数字都站得住脚,**面试官追问每个数怎么来的都能答**
- 全程**个人 API 凭证 / 个人付费**,不与公司基建发生任何交互(物理隔离红线)
- 4 策略对比**输入完全一致**(科学性)
- 全部代码 + 数据可复现,放 GitHub

---

## 2. 核心实验设计

### 2.1 4 策略

| 策略 | 干啥 | 期望表现 |
|---|---|---|
| **S0 baseline** | 不压缩,放任 ctx 涨 | token 最贵 / 信息保留 100%(对照组) |
| **S_A 滑动窗口** | 只保留最近 N 轮 messages | token 省最多 / 早期信息丢失 |
| **S_B LLM 摘要** | 用 LLM 压缩老消息 | token 中等省 / 信息有损但语义保留 |
| **S_C PreCompact hook** | 压缩时注入领域指令(强制保留持仓事实) | token 省 + 关键持仓事实定向保留 |

### 2.2 控变量设计(关键)

**停止条件:固定 N=30 轮**(候选 A,非"同 ctx 压力即停")。
- 理由:简历杀招是 efficiency 维度("同样工作量下省多少"),不是 capacity 维度
- "同 ctx 压力即停"会导致 S0/S_A 处理的问题数差几倍,**关键信息保留率分母都不一样,没法对比**
- 选 A 的代价:S_A 压缩猛的话,30 轮 ctx 占用可能很低,触发不到 auto-compact——但 token 节省 % 仍可测,这是主要指标

**同输入保障:首跑落盘 + 重放**(方式 2,非"预生成 dummy assistant + replay")。
- S0 baseline 跑 live 模式时,**每轮的 user_question 落 JSONL**
- S_A/B/C 跑 replay 模式时,从这份 JSONL 按 round_idx 读 user_question
- 4 策略消费**完全相同的 30 个 user_question 序列**
- 已知代价:S_A 因为压缩了 context 回答与 S0 不同,但 user_question 是基于 **S0 助手回答**产的 → 中后段可能"问答错位"——为控变量必须付的代价,**简历讲法里要诚实标注这条 limitation**

### 2.3 量化指标

| 指标 | 怎么算 | 数据源 |
|---|---|---|
| **token 节省 %** | `(tokens_S0 - tokens_Sx) / tokens_S0`,按 30 轮总和算 | `ResultMessage.usage` |
| **关键信息保留率** | 用 SQLite 持仓 ground truth 做"问答事实核对":S_x 在 R20 时被问 "TSLA 复权后成本",答 $80 = 保留;答 $1200 / 答不知道 = 丢失。**不用 LLM-as-judge**,纯字符串/数值匹配 + ground truth 表 | `memory.db` portfolio 表 + 助手回答文本 |
| **cost USD** | SDK 累计值 | `ResultMessage.total_cost_usd` |
| **ctx 占用曲线** | 每轮快照 | `client.get_context_usage()` |

### 2.4 模型选择

**两个 Agent 都锁 `claude-sonnet-4-6`**(5/25 决定,之前默认走 Opus 4.7 一天烧 $17)。
- 对比实验科学性要求**只是"同模型"**,不要求"最强"
- Sonnet 4.6 比 Opus 4.7 便宜 ~5x,且智能足够做 multi-tool reasoning
- 简历讲法里明确标注"Sonnet 4.6"反而更专业

---

## 3. 架构

### 3.1 两个 Agent 的不对称设计

```
synthetic_user (扮演用户)         stateful_assistant (投资助手)
─────────────────────             ────────────────────────────
SDK 入口: query()                  SDK 入口: ClaudeSDKClient
状态:    stateless                 状态:    stateful (跨轮记忆)
工具:    [] (用户不查股票)         工具:    4 个 MCP server
模型:    Sonnet 4.6                模型:    Sonnet 4.6
作用:    基于上轮助手回答产 1 个   作用:    投资问答 + 工具调用 +
         真用户会问的问题(≤50字)    复权计算 + 跨轮持仓累积
```

**为什么不对称**:
- 投资助手必须 stateful——压缩策略实验的对象就是"如何管理这个跨轮 messages 数组"
- 用户 Agent 每轮"基于上轮助手回答产 1 个问题",跨轮上下文从外部喂(`last_assistant_response` 参数),自己不需要记忆 → stateless 更轻

### 3.2 关键文件

| 文件 | 行数 | 职责 |
|---|---|---|
| `src/agents/stateful_assistant.py` | ~100 | 投资助手 Agent;`build_options()` 锁 Sonnet 4.6;含 `log_context_usage()` 观测 |
| `src/agents/synthetic_user.py` | ~290 | 用户 Agent;`next_question()` 单次产问题;含 HIGH_PRESSURE_PALETTE(0.7 权重) + NORMAL_PALETTE(0.3) 双池 |
| `src/agents/long_dialogue_runner.py` | ~260 | 主驱动;`RunConfig` / `RoundRecord` / `QuestionSource` / `run_dialogue()`;**4 策略共用此 runner**,通过 `--replay-from` 切换 live/replay |

### 3.3 数据流

```
S0 baseline 跑(live 模式):
  synthetic_user × stateful_assistant × 30 轮
  → experiments/w5_compression/S0_baseline_*.jsonl (每轮 1 行,30 行)
  字段: round_idx, user_question, assistant_text_preview, num_turns,
        cost_usd(SDK 累计), ctx_total_tokens, ctx_percentage,
        ctx_categories(分类 token 占用), timestamp

S_A/B/C 跑(replay 模式):
  for round_idx in 1..30:
    user_question = JSONL[round_idx - 1].user_question   # 从 S0 读
    assistant 接 user_question (各自策略压缩)
    落新 JSONL: S_A_*.jsonl / S_B_*.jsonl / S_C_*.jsonl

后处理:
  4 份 JSONL → 计算 token 节省 % / 关键信息保留率 → 出 README + 图
```

---

## 4. 关键设计决策表(已敲定)

| # | 决策 | 候选项 | 选择 | 理由 | 已知代价 |
|---|---|---|---|---|---|
| 1 | 实验载体 | 新建项目 / 复用 investment-agent | **复用** | W2 知识分层 + W3 回归框架可复用,不重复造 | 持仓只有 5 只,场景窄 |
| 2 | 长会话语料源 | 手敲 30 个问题 / 预生成 / Agent-to-Agent | **A2A(synthetic_user)** | 可复现 + 控变量 + 顺带是 W7 多 Agent 雏形 | synthetic_user 自己也烧 token |
| 3 | 停止条件 | 同 ctx 压力 / 固定 N 轮 / 跑到报错 | **固定 N=30** | efficiency 维度可比,关键信息保留率有同分母 | 部分策略可能 ctx 极低,触发不到 auto-compact |
| 4 | 同输入保障 | 预生成 / 首跑落盘+重放 | **首跑落盘+重放** | 预生成需要 dummy assistant 回答失真;真 S0 回答更自然 | S_A/B/C 中后段"问答错位",limitation 要标注 |
| 5 | 信息保留评估 | LLM-as-judge / 字符串+ground truth | **后者** | LLM-as-judge 引入新随机性,简历讲不清楚;ground truth 表准确可复盘 | 评估场景只能覆盖"事实问答",发挥型回答评不了 |
| 6 | 模型 | Opus / Sonnet / Haiku / 混搭 | **两边都 Sonnet 4.6** | 5x 便宜于 Opus + 智能够用 + 同模型可比 | — |
| 7 | 高压版 BEHAVIOR_PALETTE | 全自然问题 / 全高压 / 加权 | **HIGH 0.7 + NORMAL 0.3** | smoke 实测:全自然 14 轮 ctx 才 10%,密度不够;全高压失真;加权兼顾 | 用户语义偏"焦虑型散户",但仍是真人会问的 |
| 8 | API 配置 | env / 项目级 .env / Claude Code 全局 | **项目级 .env 个人付费** | 物理隔离公司基建;envvar 透明 | 每次跑前要确认 BASE_URL 不污染 |

---

## 5. 当前进度

### 5.1 已完成 ✅

- [x] `stateful_assistant.py` 单跑 3 轮(W5 D1 已沉淀):cost $0.64→$0.70→$0.98,验证 stateful 跨轮工具结果复用
- [x] `synthetic_user.py` 单次产问题:8 秒 / 真 LLM 输出 / 行为多样化生效
- [x] `long_dialogue_runner.py` 主循环:30 轮 + JSONL + ctx 快照全链路通
- [x] 高压版 palette 验证:3 轮 smoke 单轮就推到 25% ctx(老版 14 轮才 10%)
- [x] Sonnet 4.6 锁定:smoke 3 轮 $0.51,折算 30 轮 ~$5-6(老 Opus 7 轮 $2.44,折算 30 轮 $10+)

### 5.2 已踩坑(简历可讲)

1. **SDK 进程模型**:`ClaudeSDKClient` messages 物理上在 CLI **子进程**,不在 Python 脚本进程
2. **stateful 红利本质**:不是"字面记忆",是**跨轮工具结果复用**(R2 turns=1 零工具调用就能给答案)
3. **自然对话密度陷阱**:1M context + Sonnet,14 轮自然对话 ctx 才 10%,撑不到 auto-compact——必须**主动设计高压问题**才能造出有压力的实验语料
4. **`setting_sources=[]` 鉴权回落机制不工作**:CLI 401 静默失败,错误文本被吞("returned an error result: success")
5. **`cost_usd` 是 session 累计不是单轮增量**:差点错算 5x 预算
6. **红线判定标准**:看域名命名空间,不光看错误码/语言(中文 + 402 可能是个人付费网关,不是公司)

### 5.3 待做

- [ ] **S0 baseline 30 轮正式跑**(下一步,即将开跑)
- [ ] S_A 滑动窗口实现(5/26)
- [ ] S_B LLM 摘要实现(5/27)
- [ ] S_C PreCompact hook 实现(5/28)
- [ ] 评估脚本:4 份 JSONL → 节省 % + 保留率 → README + 1 张图
- [ ] daily-lesson 沉淀(5/25 收尾)

---

## 6. 已识别风险与未决项 ⚠️

### 6.1 强风险

| # | 风险 | 触发条件 | 缓解 |
|---|---|---|---|
| R1 | **S_A/B/C replay 失真**:压缩后助手回答变,但 user_question 仍基于 S0 回答 → 后段对话脱节 | 当压缩较狠 / 关键事实丢了 | 简历讲法标注 limitation;评估只看"事实问答轮"不看"对话连贯性" |
| R2 | **ctx 撑不到 auto-compact** | 30 轮 + Sonnet 4.6 + 高压 palette 可能也只到 60-70% | 接受作为发现:"在 1M 模型下,30 轮 + 强工具调用对话也撑不爆 ctx,压缩策略主要价值在 cost 而非 capacity" |
| R3 | **关键信息保留率评估口径模糊** | "保留"的判定标准是字面 / 语义 / 数值匹配? | 在 S0 baseline 跑完后**先建 eval 集**:挑 10 个"事实问答"问题 + 标准答案,4 策略统一过 |
| R4 | **`get_context_usage` 超时** | R1 已观察到 1 次(12 turns 后) | 已有 try/except + 落 -1 标记;30 轮里再频繁出再深查 |

### 6.2 未决项

1. **S_A 滑动窗口的"N"取多少?** —— 保留最近 5 轮 / 10 轮 / 15 轮?对节省 % 影响很大,需先实验调参
2. **S_B LLM 摘要用什么模型?** —— Haiku 摘要 Sonnet 输出?成本极低但摘要质量差?
3. **S_C PreCompact hook 怎么写"领域指令"?** —— hook 注入 prompt 模板还没设计,只有"必须保留所有持仓的拆股因子和复权后成本"这条粗规则
4. **回归测试**:W3 跑的 9/9 回归是 stateless `query()` 版,W5 改 stateful 后**没跑回归**——可能 stateful 改动引入回归
5. **simulated user 是否引入实验偏置?** —— synthetic_user 自己用 Sonnet,可能产出"对 Sonnet 助手最有利"的问题,跟真人用户问的分布不同。但简历讲法里 explicit 标注 "Agent-to-Agent 模拟"已经诚实

---

## 7. 请求评审的具体维度

请评审 Agent 重点判定以下几条:

### 7.1 实验设计科学性
- **决策 #3(固定 N 轮)是否真的优于"同 ctx 压力即停"?** 有没有第三条更好的停止条件我没想到?
- **决策 #4(首跑落盘+重放)的"问答错位"limitation 在简历讲法里怎么处理最不掉链子?**
- **关键信息保留率不用 LLM-as-judge 是否过于保守?** 现在 LLM-as-judge 在 ML 论文里已经是常规做法

### 7.2 工程合理性
- 两 Agent 一个 stateful 一个 stateless 的不对称设计是否合理?有没有更干净的写法?
- `QuestionSource` 抽象层是否过度工程?(就为切 live/replay 写了 30 行)
- S_A/B/C 三个策略都跑同一份 `long_dialogue_runner` 但用 hook/options 注入压缩——这个扩展点设计够不够灵活?

### 7.3 风险评估
- R1(replay 失真)的缓解措施够吗?有没有更好的方案我漏了?
- R3(评估口径)的"先建 eval 集"做法是否足以让面试官信服?
- **未决项 #5(simulated user 偏置)** 是否需要做对照(真人 vs synthetic)?投递截止 5/29,时间不够。

### 7.4 简历讲法
- 终点那一句话(§1.2)在 P6 面试官面前能不能扛住"具体问每个数字怎么来的"?
- 还有什么 "P6+ 加分点"在我当前设计里没显化但其实做了的?(例:Agent-to-Agent 是 W7 多 Agent 雏形)
- 哪些 limitation 必须在简历 README 里 explicit 写出来,不写就有伪造嫌疑?

---

## 8. 附录:文件清单

- 主代码:
  - `/Users/mtdp/ai/projects/investment-agent/src/agents/stateful_assistant.py`
  - `/Users/mtdp/ai/projects/investment-agent/src/agents/synthetic_user.py`
  - `/Users/mtdp/ai/projects/investment-agent/src/agents/long_dialogue_runner.py`
- 实验产物目录:
  - `/Users/mtdp/ai/projects/investment-agent/experiments/w5_compression/`
- 已有 W5 D1 沉淀:
  - `/Users/mtdp/ai/learning/daily-lesson/2026-05-21-w5-d1-stateful-skeleton.md`
- W5 启动笔记:
  - `/Users/mtdp/ai/learning/daily-lesson/2026-05-20-w5-kickoff.md`

---

**评审请按 §7 的四个维度逐条出意见,每条标注:✅ 合理 / ⚠️ 有顾虑+建议 / ❌ 不合理+替代方案。**
