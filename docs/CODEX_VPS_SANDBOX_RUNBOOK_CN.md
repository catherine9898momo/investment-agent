# Codex VPS 沙箱问题处理经验

## 背景

在当前 VPS/容器环境中，部分普通只读命令可能在真正执行前失败，典型报错是：

```text
bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted
```

这通常不是仓库文件、Git 状态或 Python 项目的问题，而是 Codex 的 Linux 沙箱在初始化网络命名空间/loopback 时，被 VPS 或容器运行时限制拦截。

## 识别方式

如果命令输出里出现 `bwrap: loopback`、`RTM_NEWADDR`、`Operation not permitted`，应判断为沙箱初始化失败。

这类失败发生在命令执行前，所以即使是 `sed`、`git status`、`cat` 这类只读命令也可能失败。

## 推荐处理策略

1. 优先使用已经验证可工作的命令前缀，例如：

   ```bash
   rg --files
   python3 -m src.agents.research_demo
   sed -n '1,260p' src/research/evaluator.py
   sed -n '1,240p' docs/RESEARCH_CASE_EVAL.md
   sed -n '1,240p' src/eval/research_case_runner.py
   ```

2. 如果普通命令因为 `bwrap: loopback` 失败，并且该命令对任务必要，应直接用 `require_escalated` 重新执行同一个只读命令。

3. 请求授权时说明这是为了绕过 VPS 沙箱初始化失败，而不是因为命令本身需要联网或修改系统。

4. 对于仓库内文件读取，优先使用 `rg --files` 找文件，再用已批准或可授权的 `sed -n` 读取具体文件片段。

5. 不要把该问题误判为：

   - 仓库损坏
   - `.git` 损坏
   - 文件不存在
   - Python 环境错误
   - 网络访问失败

## 给新会话的建议

如果用户提到“继续 investment-agent 项目”或“按上次规划继续”，新会话应先读取本文件，然后按以下顺序启动：

1. 用 `rg --files` 获取仓库结构。
2. 读取用户提供的交接说明或 `docs/0607.progress.md` 等进度文件。
3. 若遇到 `bwrap: loopback`，直接按本 runbook 的策略请求只读授权重跑。
4. 不要长篇解释该问题，除非用户主动询问。

## 一句话版本

当前 VPS 的 Codex 沙箱偶尔无法初始化 loopback；遇到 `bwrap: loopback` 时，把它当作环境限制，必要只读命令直接授权重跑即可。
