# Codex Project Guide

本文件记录 Codex 在本仓库工作的默认操作约定。新会话开始时应优先阅读本文件，再继续执行用户任务。

## 会话启动流程

1. 先确认当前仓库结构：

   ```bash
   rg --files
   ```

2. 若用户要求“继续上次任务”或“接着 Investment Agent 项目”，优先阅读：

   ```text
   docs/CODEX_VPS_SANDBOX_RUNBOOK_CN.md
   docs/0607.progress.md
   docs/PROJECT_PANORAMA_AND_MILESTONES.md
   docs/PROJECT_PANORAMA_AND_MILESTONES_CN.md
   ```

   如果用户提供了新的交接附件，以用户提供的最新交接为准。

3. 开始实现前，先读相关源码和测试，不要凭文件名猜接口。

4. 工作中遇到用户新增指令时，以最新用户消息为准。

## VPS 沙箱问题

当前 VPS/容器环境中，普通只读命令可能在执行前失败，典型报错：

```text
bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted
```

这不是仓库、Git、Python 或文件路径问题，而是 Codex 底层沙箱初始化 network namespace / loopback 时被 VPS 限制。

处理规则：

1. 看到 `bwrap: loopback`、`RTM_NEWADDR`、`Operation not permitted` 时，直接判定为 VPS 沙箱初始化失败。
2. 如果命令是必要的只读操作，直接用 `require_escalated` 重跑同一个命令，并说明是为了绕过 VPS 沙箱初始化限制。
3. 不要反复把该问题误判为仓库损坏、文件不存在、Git 损坏或 Python 包缺失。
4. `git status`、`git diff`、`sed`、`nl`、`pwd` 等只读命令也可能触发该问题，按同一规则处理。

已知可优先尝试的命令：

```bash
rg --files
.venv/bin/python -m pytest
python3 -m src.agents.research_demo
```

## Python 与测试

本仓库的 dev 依赖安装在项目虚拟环境 `.venv` 中。默认系统 Python 是：

```bash
/usr/bin/python3
```

它不一定包含 pytest。测试应默认使用：

```bash
.venv/bin/python -m pytest
```

例如：

```bash
.venv/bin/python -m pytest src/research/test_context_builder.py
.venv/bin/python -m pytest src/research/test_synthesizer.py src/agents/test_research_demo.py
```

如果 `.venv/bin/python -m pytest --version` 可用，就不要再用 `python3 -m pytest` 反复验证。

如需安装或更新 dev 依赖，优先使用虚拟环境：

```bash
.venv/bin/python -m pip install -e ".[dev]"
```

涉及联网下载依赖时，需要请求用户授权。

## 文件编辑规则

1. 默认使用 `apply_patch` 编辑文件。
2. 如果 `apply_patch` 也因为 `bwrap: loopback` 失败，可以在用户授权后使用精确脚本修改仓库内目标文件。
3. 精确脚本必须范围小、目标明确，不做大范围重写。
4. 不要删除、覆盖或回滚用户已有改动。
5. `git status --short` 中出现不属于本轮任务的未跟踪或修改文件时，只记录并避开。

## 当前项目方向

当前项目是 Investment Agent，从 P0 骨架进入 P1 建设。已完成的主链路包括：

```text
Query Intake
Entity Resolver
Time Window Resolver
Intent Router
Attribution Planner
基础 live data retrieval
Fact Normalizer
Verified/Missing Fact Table
用户可读研究报告
Debug/Guardrail 输出
Context Builder
```

近期 P1 方向：

```text
Evidence-constrained LLM
Claim Verifier
Sector/Peer Attribution Executor
Research Model Router
```

## 交互习惯

1. 开始较长任务时，先用一两句话说明正在读取哪些上下文。
2. 遇到已知环境问题时，直接按本文件处理，不要长篇解释，除非用户主动询问。
3. 文件编辑前说明将改哪些文件、为什么改。
4. 每个阶段结束后运行最小相关测试。
5. 收尾时简要说明：改了什么、如何验证、是否有未解决问题。
6. 面向用户解释流程链路、数据流、架构图、模块调用顺序、类型转换链等内容时，如果使用箭头、列表或代码块展示结构，例如 `A -> B -> C`，必须同步添加中文注释说明每个节点的作用、输入输出含义和链路整体语义。不要只给英文类名/模块名堆叠。

## 常用验证命令

快速验证 Context Builder：

```bash
.venv/bin/python -m pytest src/research/test_context_builder.py
```

验证 synthesis 相关路径：

```bash
.venv/bin/python -m pytest src/research/test_context_builder.py src/research/test_synthesizer.py
```

验证 fixture 主链路：

```bash
python3 -m src.agents.research_demo --data-source fixture --query "美光最近为什么会大跌？"
```

如果普通命令遇到 VPS 沙箱失败，按“VPS 沙箱问题”章节授权重跑。
