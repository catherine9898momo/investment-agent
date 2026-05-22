# 架构图集

> 4 张图按"系统总览 → 设计模式 → 真实调用 → 时间叙事"递进，覆盖所有简历素材场景。

| # | 图名 | 类型 | 主用途 |
|---|---|---|---|
| [A](./01-overview.md) | 系统总览（3 客户端 → 4 Server → 数据源） | flowchart | README 首图 / 录屏开场 |
| [B](./02-knowledge-layering.md) | 知识分层设计模式（触发器 / 事实 / 建议） | flowchart | ADR-004 主图 / 博客封面 |
| [C](./03-case-d-sequence.md) | Case D' 7 次工具调用时序 | sequenceDiagram | Case Study 配图 / 录屏第 3 段 |
| [D](./04-closed-loop-timeline.md) | 反例闭环 24h 时间线 | timeline | 终面 / 录屏第 4 段升华 |

---

## 使用建议

### 投递场景速查

| 场景 | 用哪张 |
|---|---|
| GitHub README 首图 | A |
| 技术博客《LLM 训练知识不稳定》封面 | B |
| Case Study PDF 配图 | A → B → C → D 全用 |
| 5 分钟录屏 | 开场 A · 设计段 B · 实跑段 C · 升华 D |
| 简历附件最后一页 | D（视觉收尾） |
| 面试现场白板 | A 简化版（3 个框 + 3 条线） |

### 面试答题速查

| 面试官问题 | 拿哪张图答 |
|---|---|
| "整个系统什么样？" | A |
| "你怎么解决幻觉 / LLM 出错？" | B |
| "Agent 真的能自主串调用？" | C |
| "你能主导技术决策吗？" | D |
| "为什么不让 LLM 联网搜？" | B（"web_search hop=1，关键事实必须 hop=0"） |
| "涌现行为是 LLM 随机吗？" | C（涌现 3 行为表） |

---

## 渲染方式

所有图都是 Mermaid 源码：

- **GitHub** 原生支持，push 后直接渲染
- **VS Code** 装 "Markdown Preview Mermaid Support" 扩展
- **在线预览**：[mermaid.live](https://mermaid.live) 粘贴源码
- **导出 PNG**：`mmdc -i 01-overview.md -o 01-overview.png`（需 `npm i -g @mermaid-js/mermaid-cli`）
- **嵌入 PDF**：Typora / Marp / pandoc 都能识别

---

## 设计统一性

四张图共享一套配色，让面试官在 4 张图之间切换不会出戏：

| 颜色 | 含义 |
|---|---|
| 🟢 绿色（粗边） | corporate_actions / 具体事实层 / Case D' 修复后 |
| 🔵 蓝色 | Client / 决策建议层 |
| 🟠 橙色 | MCP Server / 触发器层 |
| ⚪ 灰色虚线 | 外部数据源 / IO 边界 |
| 🔴 红色 | 反例失败模式（仅 02 反例对比 / 04 5/13 节点） |
