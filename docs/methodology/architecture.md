---
tags: [agent, architecture, context-window, tool-schema, parallel-execution, mcp, multi-server, llm-knowledge-stability, ground-truth]
domain: ai-engineering
type: best-practices
updated: 2026-05-13
---

# Agent 架构最佳实践

## 2026-04-20: 上下文腐烂的原因与缓解策略

**问题/背景**: Agent 长对话中上下文质量持续退化，导致绕圈、状态混乱、指令漂移。
**原因/分析**: 五大原因——窗口溢出（硬截断）、Lost in the Middle（注意力对中间部分偏弱）、信噪比下降（工具返回值/失败尝试堆积）、状态不一致（新旧版本共存）、指令漂移（system prompt 影响力被稀释）。
**解决方案/结论**: 六种缓解策略组合使用——上下文压缩（定期摘要替换原始历史）、工具返回值裁剪、滑动窗口+关键帧、结构化外部状态管理（不依赖上下文维护状态）、指令重注入、子 Agent 分治（每个子任务用干净上下文）。其中子 Agent 分治效果最好但复杂度最高。

## 2026-04-20: Tool Schema 的 description 直接决定模型工具调用准确率

**问题/背景**: 在 my-cli-agent 中做 Tool Schema 对比实验，修改工具的 description 后观察模型调用行为变化。
**原因/分析**: 模型选择调用哪个工具的唯一依据就是 description。描述模糊或不准确时，模型无法正确匹配用户意图到对应工具，导致调错工具或无法输出结果。
**解决方案/结论**: Tool description 要明确写清工具的用途、适用场景和输入含义。这是 Agent 工程中投入产出比最高的优化点——不需要改代码，只改描述就能显著提升调用准确率。

## 2026-04-20: Python 中并行执行工具调用的方案选型

**问题/背景**: Python 版 Agent 的工具调用是顺序执行，需要改成并行以对应 TS 版的 Promise.all。
**原因/分析**: 两种方案——ThreadPoolExecutor（适合同步函数+IO密集）和 asyncio.gather（适合已有 async 链路）。如果 execute_tool 是同步的，用 asyncio.gather 需要把整个调用链改成 async（execute_tool/run_agent/main + input 替换），改动量大。
**解决方案/结论**: 当 execute_tool 是同步函数且包含网络 I/O 时，优先用 `concurrent.futures.ThreadPoolExecutor`，只需替换循环部分，其他代码不动。等整个项目迁移到 async 架构时再考虑 asyncio.gather。

## 2026-04-21: 个人知识库 RAG 离线阶段技术方案选型

**问题/背景**: 要把 ai/memory/ 和 ai/learning/ 下的 md 文件接入 RAG，实现自然语言问答。
**原因/分析**: 数据量小（几十个 md 文件），不需要重型基础设施。分块策略需区分结构化文件（memory 下按 ## 标题切块）和大文件（learning 下按固定 token+重叠切块）。Embedding 优先用内部服务（如支持），否则本地 BGE-small-zh。
**解决方案/结论**: 向量库选 Chroma（纯 Python、本地存储、支持元数据过滤、pip install 即用）。frontmatter 的 tags/domain/type 作为元数据过滤维度。混合分块策略：结构化文件按标题切、大文件按 token 切。

## 2026-04-30: Reranker 接入 RAG 的前置条件与通用陷阱

**背景**: 在 second-brain-rag 项目接入 bge-reranker-base 期望 Hit@1 提升，反而倒退。归纳出对任何项目都成立的规律。

**Reranker 不是无脑收益，前置条件**:
1. **候选池要先净化**: 软加权（intent-based source boost、metadata 过滤）必须在 reranker 之前生效。candidate_n 越大噪声越多，reranker 不会自动剔除噪声，反而可能放大噪声。
2. **语料要避免自指**: 评估用 query 的字面文本绝不能出现在语料正文里。CrossEncoder 对"chunk 包含 query 子串"极度敏感，会把"讨论 query 的元文档"判为最相关，挤掉真答案。BM25+RRF 因 IDF + 长度归一对此不敏感，所以**vector+BM25 阶段没事，到 reranker 才爆**。
3. **chunk 粒度要适合 reranker**: CrossEncoder 看的是 (query, chunk) 文本对，chunk 太长被截断（默认 max_length=512 token），太短信号不足。喂之前可以拼上 heading_path 作为 prefix，让短 chunk 也有上下文。

**Reranker 调参的次序（成本由低到高）**:
1. `rerank_candidate_n` 减半（30→10）— 一行配置改动，能挽回 10~15pp Hit@1
2. 启用软加权 + reranker 串联（rules 模式）— 比纯 baseline+rerank 强
3. 喂给 reranker 的文本前置 heading_path / metadata 摘要
4. 换更强模型（bge-reranker-v2-m3, ~600MB）
5. 清洗语料的自指引用 / 重切 chunk

**RAG eval 设计的独立性原则**: golden_queries 字面与语料正文要双向独立，否则你评估的是"reranker 找元目录的能力"而不是"找答案的能力"。dogfooding 项目（用项目自己的踩坑文档评估项目的检索）尤其要警惕这点。

**指标解读经验**: Hit@K 倒退但 KeywordCoverage 反而涨满 → 经典 reranker fooled 信号（选了关键词更密的"讨论文档"而非"答案文档"）。这种背离比单纯下降更值得告警。

## 2026-05-13: 多 MCP Server 协作的工程模式（"不需要 orchestrator"）

**背景**: investment-agent 项目同时挂载 3 个 MCP Server（memory / finance / news），观察 Claude 在跨 Server 任务上的工具编排行为。

**原因/分析**: 实验观察到的 3 个关键现象：
1. **跨 Server 顺序自动选对**：用户问"我的 NVDA 浮盈多少"，Claude 自动先调 memory.list_portfolio 拿成本，再调 finance.get_quote 拿现价。没有任何 prompt 引导
2. **因果问题自主多源并取**：用户问"腾讯为什么跌"，Claude 自己决定三路并取（finance.get_quote 确认跌幅 + finance.get_history 看趋势 + news.get_news 找原因）
3. **3 Server 并存无 description 干扰**：每个 Server 各自写好"我管什么"，工具池 8+ 也不会互相误触发

**解决方案/结论**: 多 MCP Server 协作的最小工程模式是"**每个 Server 各管一摊 + description 写清边界 + 名字空间区分**"，**不需要 orchestrator 程序**。Agent 是 LLM 本身，不是另一个调度器。这跟"传统微服务必须有网关/编排器"的直觉相反——LLM 的工具调用规划能力在足够好的 description 下已经胜任简单调度。

**反向风险**: 工具池规模上去后（10+ Server）是否仍成立未验证；description 互相干扰的临界点未知。生产环境可能仍需要在 LLM 前加一个轻量 retrieval 层（Claude Desktop 的 ToolSearch 就是这个角色）。

## 2026-05-13: LLM 训练知识的"不稳定性"——知识分层设计模式

**背景**: investment-agent 在拆股提醒 case 上发现 LLM 训练知识不稳定——对同一份 TSLA 持仓（$1200 成本），同一天两次给出不同精度的复权答案：早上正确识别 2020 + 2022 两次拆股（15:1），晚上漏算 2020 那次（只给 3:1）。

**原因/分析**: LLM 训练知识有"召回稳定性"问题——同一事实在不同 session 可能输出不同精度，受多因素叠加：
- **上下文压力**：长输出 / 多焦点任务下，对次要信息精度下降
- **任务焦点**：同一事实是"主角"还是"sub-point"影响召回质量
- **训练数据分布**：近 5 年事件比 5+ 年事件召回更稳
- **采样随机性**：temperature 引入的固有不确定性

**解决方案/结论**: 设计垂直 Agent 时遵循"LLM 知识分层"原则：

| 决策类别 | 用什么 | 例子 |
|---|---|---|
| **触发器**（"可能有问题"信号） | LLM 训练知识 | "成本远高于现价，可能拆股" |
| **具体事实**（日期/比例/数字） | 外部 ground truth（工具/数据库） | "TSLA 2020-08 5:1 + 2022-08 3:1" |
| **决策建议** | 两者结合 + LLM 综合 | "复权浮盈 + 利好/利空 → 持有" |

**核心原则**: **LLM 提示要存在感、不要权威感**——它该说"可能"、"建议核对"触发用户检查，不该直接给具体数字让用户当真。
- ✅ "**可能**是拆股前价位，**建议核对**"
- ❌ "复权后 $80 USD，浮盈 +361%"

**工程修复路径**: 投资 Agent 场景下，建 `corporate_actions_server`（yfinance + SQLite 缓存）提供历史拆股 / 股息 / 合并的结构化数据；description 引导"涉及历史价位判断时先调本工具拿 ground truth"。这是"识别 LLM 失败模式 + 主动设计 ground truth 兜底"的范式，**比单纯"用 LLM 多智能"高一个工程认知档次**。

**机制层归因 + 判断标准**: 详见 [`llm-hop-minimization.md`](./llm-hop-minimization.md)。本节是模式描述（"分三层"），那里是**为什么要分层**（注意力机制 → 处理偏移）+ **怎么判断哪一层**（保真度 + LLM hop 次数）。2026-05-14 由用户从反例闭环实测后自发推导产出。
