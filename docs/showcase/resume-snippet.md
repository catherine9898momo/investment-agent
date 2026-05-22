# 简历素材 — investment-agent

> 5/29 投递倒计时主用资产。**按受众 3 版本**：HR / 一面 / 终面。
> 最后更新：2026-05-22

---

## Part 0 · 完整简历骨架（带占位符，自行替换）

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
姓名 <PLACEHOLDER>                                  手机 <PLACEHOLDER>
                                                    邮箱 <PLACEHOLDER>
GitHub <PLACEHOLDER>                                所在地 <PLACEHOLDER>
博客 / 个人站 <PLACEHOLDER>                          求职状态 <PLACEHOLDER>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

【求职意向】
AI 应用工程师 / Agent 工程师 / LLM 应用开发
期望城市 <PLACEHOLDER>     期望薪资 <PLACEHOLDER>     到岗时间 <PLACEHOLDER>

【一句话定位】
N 年互联网工程师经验（RN / TS 全栈背景），近 1 年深入 LLM 应用 / Agent 工程方向，
独立完成 4 MCP Server 协作的金融垂直 Agent 项目，主导反例闭环与方法论沉淀。

【工作经历】
<公司 PLACEHOLDER>     <职位 PLACEHOLDER>     <起止 PLACEHOLDER>
- <职责 / 业绩 PLACEHOLDER>
- <职责 / 业绩 PLACEHOLDER>
- <职责 / 业绩 PLACEHOLDER>

【项目经历】★ 主投项目
👇 按目标公司 / 岗位类型，从 Part 1/2/3 选对应受众版本贴入

【教育背景】
<学校 PLACEHOLDER>     <学历 + 专业 PLACEHOLDER>     <起止 PLACEHOLDER>

【技能清单】
· 语言：Python / TypeScript / JavaScript
· LLM 应用：Claude API · claude-agent-sdk · OpenAI 兼容 API · Prompt Engineering · Function Calling / Tool Use
· Agent 架构：MCP 协议 · 跨 Server 协作 · Hook 工程化 · 上下文工程（W5 中）· 知识分层设计模式
· RAG：向量检索（Chroma）· BM25 混合检索 · RRF 融合 · 增量索引 · golden query 回归评估
· 数据：SQLite · yfinance · Google News RSS · jieba 中文分词
· 工程化：FastAPI · Streamlit · React + Vite · SSE 流式
· 前端基础：React Native · React

【开源 / 内容】
· GitHub: <PLACEHOLDER — investment-agent / second-brain-rag>
· 技术博客: <PLACEHOLDER>（发布后回填）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**使用方法**：把上方骨架复制到 Word / 在线简历工具 → 替换 `<PLACEHOLDER>` → 在【项目经历】位置贴入 Part 1/2/3 之一。

---

## Part 1 · HR 版（约 130 字，关键词压满）

**适用场景**：BOSS 直聘沟通话术、LinkedIn headline、HR 10 秒筛、ATS 关键词扫描、邮件自我介绍开场段。

**取舍**：放弃叙事深度，纯堆量化数字和 JD 关键词。

---

**investment-agent — 金融垂直 MCP Agent**（个人项目，2026-04 至今）
Python · claude-agent-sdk · MCP 协议 · SQLite · yfinance

独立设计与实施 **4 个 MCP Server 协作架构**（持仓记忆 / 行情 / 新闻 / 公司行动事件），Claude Desktop / Claude Code / 自研 Agent **三客户端零修改复用**。跨 Server **拆股事件判别 4/4**，description A/B 在 **10 类语义陷阱 case 行为正确率 10/10**，claude-agent-sdk 编排回归测试 **9/9 通过**。发现 LLM 训练知识不稳定反例，**24 小时**闭环 `corporate_actions_server` ground truth 兜底架构，复权计算 **$400→$80**、浮盈方向反转。抽象"**触发器 / 具体事实 / 决策建议**"三层知识分层设计模式。

---

## Part 2 · 一面版（约 260 字 / 4 bullet，量化为主 + 反例钩子）

**适用场景**：简历项目栏主投、技术一面（30-60 min）开场介绍、PDF 简历正文。

**取舍**：平衡叙事与量化，反例只 1 句钩子（等被问到再展开）。

---

**investment-agent — 金融垂直 MCP Agent**（个人项目，2026-04 至今）
**技术栈**：Python · claude-agent-sdk · MCP 协议 · SQLite · yfinance · Google News RSS
**角色**：独立设计与实施

- **架构落地**：设计并实现 4 个 MCP Server（持仓记忆 / 行情 / 新闻 / 公司行动事件）协作架构，Claude Desktop / Claude Code / 自研 Agent **三客户端零修改复用**；跨 Server 工具路由由 LLM 自主完成，**无需 orchestrator**。
- **量化能力**：跨 Server **拆股事件判别 4/4**（NVDA / TSLA / AAPL / 09988.HK，覆盖近期拆股 / 真实下跌 / 港股代码归一化等边界）；description A/B 实验在 **10 类语义陷阱 case 行为正确率 10/10**；claude-agent-sdk 编排 + Hook 工程化回归测试 **9/9 通过**。
- **反例闭环**：发现 LLM 训练知识在不同 session 输出不一致（同一持仓 **15:1 vs 3:1** 拆股精度），**24 小时**内设计并落地 `corporate_actions_server` ground truth 兜底，复权后成本 **$400 → $80**、浮盈方向 **-64% → +457%**。
- **方法论沉淀**：抽象"**触发器 / 具体事实 / 决策建议**"三层知识分层设计模式与 **LLM hop 最小化**原则，已沉淀为可复用工程方法。

---

## Part 3 · 终面版（约 350 字 / 3 bullet，反例叙事 + 方法论压脚）

**适用场景**：终面 / 架构师 / 主导能力评估、邮件附 Case Study 阅读材料、大厂跳板线投递。

**取舍**：砍掉部分量化数字密度（9/9 不出现），腾出空间讲"为什么这么做 + 抽象出什么模式"。**P6+ 信号埋点**：归因深度 + 备选方案显式 + 反例叙事 + 可复用模式。

---

**investment-agent — 金融垂直 MCP Agent**（个人项目，2026-04 至今）
**技术栈**：Python · claude-agent-sdk · MCP 协议 · SQLite · yfinance
**角色**：独立设计 / 主导技术决策 / 全栈实施

- **架构主导**：4 个 MCP Server 协作架构。选 MCP 而非 LangChain 的关键判别是**跨客户端复用**——同一 Server 被 Claude Desktop / Claude Code / 自研 Agent 零修改消费，已三客户端验证。跨 Server 协作**无 orchestrator** —— LLM 即编排器，依赖 description 边界写好；3 Server 协作（memory + finance + news）在因果问题（"腾讯为什么跌"）下自主三路并取（决策记录见 ADR-001 / ADR-002）。
- **反例驱动设计**：跑通 3 Server 协作后，发现同一 TSLA 持仓在不同 session 给出 **15:1 vs 3:1** 不同拆股精度。归因不是"训练数据过时"，是 **LLM 注意力机制在长 session 下的压缩偏移** —— 同一模型同一天可输出不同精度。**24 小时内**落地 `corporate_actions_server` ground truth 兜底（yfinance + SQLite 24h TTL + stale fallback），Case 复现复权 **$400→$80**、浮盈方向 **-64%→+457%**，且 Claude 自发涌现"先查历史拆股再判断"的金句和主动澄清持仓时点行为。
- **方法论抽象**：从该闭环抽象出"**触发器（LLM 训练知识）/ 具体事实（外部 ground truth）/ 决策建议（LLM 综合）**"三层知识分层设计模式，与 **LLM hop 最小化**原则 —— 关键事实 hop=0（结构化工具直给），模糊判断可 hop>0。原则可复用于任何"领域常识不稳定"的垂直 Agent 场景。

---

## Part 4 · 一句话版（约 50 字 / LinkedIn headline、自我介绍开场、推荐信）

> 设计 4 MCP Server 协作的金融垂直 Agent，24 小时闭环 LLM 训练知识不稳定反例，提出知识分层设计模式。

---

## 投递配套素材链接（替换为真实 URL）

- GitHub: `<PLACEHOLDER — github.com/.../investment-agent>`
- Case Study: [case-study-corporate-actions.md](./case-study-corporate-actions.md)（仓库 README 可直链）
- 技术博客《LLM 训练知识不稳定 — 24h 兜底架构》: `<PLACEHOLDER — 发布后回填>`

---

## 关键词清单（确保 ATS / 人工筛简历能命中 JD）

> 对应 BOSS 直聘锁定 JD 的关键词：

- ✅ Agent / Agent 架构 / Agent 工程
- ✅ MCP 协议 / Function Calling / Tool Use
- ✅ Prompt Engineering / description A/B
- ✅ claude-agent-sdk / Hook 工程化 / 回归测试
- ⚠️ 上下文工程 / 上下文压缩（W5 推进中，5/29 投递后补强）
- ⚠️ 记忆系统 / 长短期记忆（W6 推进中）/ ✅ 知识分层（已有）
- ✅ 金融垂直 / 垂直领域 Agent
- ✅ Python / SQLite
- ⚠️ LangGraph / 多 Agent 工作流（W7 加分项，未来补）
- ⚠️ RAGAs / 量化评估（W7 加分项）

---

## 受众-版本对照速查

| 你要投 / 用在哪里 | 选哪版 |
|---|---|
| BOSS 直聘开场话术 / LinkedIn / HR 邮件 | **Part 1 HR 版** |
| PDF 简历项目栏（主投） | **Part 2 一面版** |
| 大厂终面 / 邮件附 Case Study / 架构师面 | **Part 3 终面版** |
| 一句话自我介绍 | **Part 4 一句话版** |

---

## 打磨备注

- **量化数据三处必出现**（Part 1/2）：4/4 拆股判别、10/10 description A/B、$400→$80 复权反转
- **金句两处必出现**（全版本）：24 小时反例闭环、知识分层设计模式
- **避免弱动词**："使用 / 学习 / 尝试" → 全部换 "设计 / 落地 / 抽象 / 主导 / 实施"
- **Part 2 bullet 顺序**：架构 → 量化 → 反例 → 方法论（从工程到能力升华）
- **Part 3 取舍**：终面版数字密度低于一面版是有意——P6+ 评估看的是归因和抽象，不是数字堆叠
- **W5 / W6 完成后回灌**：Part 1/2/3 的"反例闭环"段后补 1 句 "上下文压缩 X% / 关键信息保留率 Y%"
