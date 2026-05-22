# Methodology · 工程方法论沉淀

> investment-agent 项目过程中抽象出的可复用工程原则。
> 这些文档由实战踩坑反向推导，每条都有具体 case 支撑。

---

## 文档目录

| 文档 | 主题 | 触发场景 |
|---|---|---|
| [llm-hop-minimization.md](./llm-hop-minimization.md) | **LLM hop 最小化原则** — 关键事实 hop=0，模糊判断 hop>0 OK | 5/14 用户自发推导，注意力机制压缩偏移的工程对策 |
| [architecture.md](./architecture.md) | 跨 Server 协作、知识分层、LLM 训练知识稳定性 | W2 D4 3 Server 协作 + corporate_actions 反例闭环 |
| [cross-server-cases.md](./cross-server-cases.md) | 跨 Server 调用的 5 个真实 case（含反例 + 涌现行为） | W2 D3-D5 实战记录 |
| [experiment-decision-framework.md](./experiment-decision-framework.md) | 推理 vs 实测的 3 维 ROI 评分矩阵 | W1 D3 inputSchema A/B 实验决策时抽象 |

---

## 阅读路径建议

**面试官 / 终面架构师**：直接读 [`architecture.md`](./architecture.md) 第 2-3 节（跨 Server 协作 + 知识分层），是 P6+ 能力评估最直接的证据。

**技术一面**：读 [`cross-server-cases.md`](./cross-server-cases.md) 看 5 个真实 case，每个都有量化数据。

**HR / 项目筛**：跳过本目录，回 [项目 README](../../README.md) 主页即可。

---

## 与 Case Study 的关系

[Case Study](../showcase/case-study-corporate-actions.md) 是**单点反例闭环**（24h 设计+落地）。
本目录是从该闭环及其他踩坑中**提取的可复用原则**。

两者的关系类似论文里 **observation → principle**：Case Study 是 observation，methodology 是 principle。

---

## 维护原则

- 新原则必须有**至少 1 个真实 case 支撑**，不写"理论上应该如何"
- 引用的 case 必须能链回 `experiments/` 或 `showcase/case-study-*.md`
- 每个文档顶部保留 frontmatter（tags / domain / type）便于后续做 RAG 检索
