# ADR-006：Showcase 资产走纯文本 + HTML 静态站点路线

- **状态**：Accepted
- **日期**：2026-05-19
- **决策者**：项目作者

---

## Context（背景）

Investment-agent 项目作为求职 portfolio 资产已完成 18 个 Markdown 文档沉淀（简历段落 / Case Study / ADR / Mermaid 架构图 / 博客大纲 / 讲稿）。W2 D6 沉淀时遗留 3 个媒体类 TODO：

- 补 7 张操作截图（`screenshots/CHECKLIST.md`）
- Case Study 转 PDF
- 5 分钟项目演示录屏

进入 W4 demo 打磨阶段前，需要决定这些 TODO 是执行还是废除。

---

## Decision（决策）

**Showcase 资产只走两类载体**：

1. **Markdown 文档**——所有原始内容（简历段落 / Case Study / ADR / 博客 / 讲稿 / Mermaid 源码）
2. **HTML 静态站点**——从 Markdown 渲染产出的可投递公开 URL（MkDocs Material + GitHub Pages）

**废除**：录屏 / 截图 / PDF 三类媒体资产。

**例外**：讲稿类 Markdown（如 `elevator-pitch-and-3min-script.md`）**保留作面试自我讲述用**——不录像，但可背、可口述。

---

## 设计原则

### 单一真理源（Single Source of Truth）

- 每个内容点**只在一处 Markdown 维护**
- HTML 站点是渲染产物，不是新内容载体
- 投递、面试官分享、简历链接全部指向同一 URL

### 自动同步

- Markdown 变更 → `mkdocs build` → 站点更新
- 无需手动重录视频、重截图片、重导 PDF

### 按受众分页，不按资产类型分页

7 页结构面向"看的人"，不是"产物种类"：

| 页面 | 受众 |
|---|---|
| Home（30 秒） | HR 第一眼 |
| Project Overview（5 分钟） | HR / 一面开场 |
| Case Study | 一面深入 / 终面 |
| 架构设计 | 一面 / 终面 |
| 技术决策（ADR） | 终面深问 |
| 技术博客 | 公域 / 自我品牌 |
| About | 投递便利 |

量化数字（4/4 / 10/10 / 9/9 / 24h）**必须在 Home 横幅可见**，不藏深页。

---

## Consequences（结果）

### 正面

- ✅ **可维护性**：内容变更 push 即更新，无需重录/重截
- ✅ **工程化程度**：Markdown → HTML 是自动 pipeline，零人工渲染步骤
- ✅ **投递载体统一**：一个 URL 走天下（简历链接、邮件签名、GitHub README）
- ✅ **面试官访问门槛低**：点一下 vs 下载附件/跳转网盘
- ✅ **资产一致性**：单一真理源，杜绝"截图旧版 vs Markdown 新版"脱节
- ✅ **零内容重写工作量**：现有 13 个 Markdown 直接复用为站点输入

### 负面

- ⚠️ **缺少视觉冲击力**：录屏 / 截图对部分受众（非技术 HR）的直观感更强
  - **缓解**：用 Mermaid 图 + 量化数字横幅替代——架构图直观、数字醒目
- ⚠️ **依赖面试官点链接**：如果面试官只看 PDF 简历不点链接，深度内容无法触达
  - **缓解**：简历里把核心量化数字放在最显眼位置，URL 是"延伸阅读"而非主战场
- ⚠️ **`elevator-pitch-and-3min-script.md` 的口述能力是必须的**：因为没录屏，面试自我介绍必须自己讲——倒逼口述训练

---

## Alternatives Considered（备选方案）

| 方案 | 问题 |
|---|---|
| 全做（Markdown + HTML + 录屏 + 截图 + PDF） | 维护成本爆炸，资产间易脱节；ROI 低 |
| 录屏 + Markdown 不做 HTML | 录屏一次性人工，无法应对内容迭代；面试官无法 deep-link 到具体章节 |
| PDF + 简历 | PDF 不是可交互资产，无法导航、不能搜索、改一处要重导出 |
| Docusaurus / VitePress 替代 MkDocs | 功能过剩，工作量 4-8 小时 vs MkDocs < 2 小时；Markdown 直渲染是核心需求 |
| 手写 React/Next 站点 | 重复造轮子，开发时间 2-3 天，性价比极低 |
| **Markdown + MkDocs Material HTML ★** | 单一真理源 + 自动同步 + < 2 小时部署 + 黑色技术风主题 |

---

## 实施

### 选型：MkDocs Material

| 维度 | 评价 |
|---|---|
| Markdown 直渲染 | ✅ 原生 |
| Mermaid 支持 | ✅ 插件 `mkdocs-mermaid2-plugin` 成熟 |
| 主题 | Material Dark / Slate（黑色技术风） |
| 部署 | `mkdocs gh-deploy` 一键到 GitHub Pages |
| 内置能力 | 搜索 / 目录 / 面包屑 / 暗色模式 / 代码高亮 |
| 工作量 | < 2 小时（含部署） |

### 实施步骤

```bash
# 1. 安装
pip install mkdocs-material mkdocs-mermaid2-plugin

# 2. 在 docs/showcase/ 写 mkdocs.yml
#    - theme: material（带 dark scheme）
#    - plugins: [mermaid2, search]
#    - nav: 按 7 页结构组织

# 3. 现有 13 个 Markdown 软链或 cp 到 docs/ 根

# 4. 本地预览
mkdocs serve  # http://127.0.0.1:8000

# 5. 部署到 GitHub Pages
mkdocs gh-deploy

# 6. 拿到 URL：username.github.io/investment-agent
#    加到简历顶端、GitHub README、邮件签名
```

---

## 清理动作

| 资产 | 处理 |
|---|---|
| `screenshots/CHECKLIST.md` | 建议删除（已废除 TODO） |
| `screenshots/` 目录 | 建议删除（空目录） |
| `elevator-pitch-and-3min-script.md` | 保留（作面试讲稿） |
| 现有 13 个 Markdown | 全部保留，作站点输入 |

---

## 关联

- 协议沉淀：`learning/daily-lesson/2026-05-19b-showcase-html-route.md`
- 用户偏好 memory：`feedback_showcase_no_media.md`
- 资产总入口：`docs/showcase/index.md`
- 关联 ADR-005（description 设计）：同样体现"一次写好、多处复用"的工程美学
