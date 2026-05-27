# S_A 滑动窗口 · 实施骨架(5/26 D-day-3 早动手用)

> **状态**:伪代码 + 决策点 + SDK 接口调研结果。5/26 早 0 思考成本接手。
> **前置依赖**:`S0_baseline_final_001.jsonl` 已就位(R10/R20/R30 是 probe 轮,assistant_text_full 有 baseline 答案)。

---

## 0. 一句话定义 S_A

> 在 stateful 多轮对话中,**只保留最近 N 轮 user-assistant 对**当作上下文,丢弃更早的全部 messages(不摘要,直接丢)。

参数:**N = 8 轮**(初值,可后续调参)

---

## 1. SDK 接口选项对比

| 路径 | 实现方式 | 优点 | 缺点 |
|---|---|---|---|
| **A. PreCompact hook + custom_instructions** | hook 拦截 SDK 自动压缩,custom_instructions 写"只保留最近 8 轮,不摘要直接丢" | 用 SDK 官方接口,讲得清楚 | hook 只在**ctx 触发阈值时**才 fire——本次实验 ctx 可能撑不到 auto-compact 阈值 |
| **B. 手动 trim messages** | 抛弃 ClaudeSDKClient,改用 bare `query()` + 手动维护 messages list | 完全控制,稳定可预测 | 失去 SDK 内部其他特性(session 状态、工具结果缓存等);跟 stateful_assistant.py 当前架构不一致 |
| **C. ClaudeSDKClient + session 截断** | 每 N 轮 close 当前 client,开新 client,把最近 N 轮 messages 喂进新 client 启动 | 仍走 stateful 路径 | 不优雅,每次重启有开销 |

**决策**:**A 优先尝试**,失败 fallback 到 C。

A 失败的标准:跑 5 轮试运行,如果 PreCompact hook 一次都没 fire(因为 ctx 没到阈值),说明这路径不适合 S_A,转 C。

---

## 2. 骨架代码(直接复用 long_dialogue_runner)

新文件:`src/agents/sa_sliding_window.py`,**不动 long_dialogue_runner**——只覆盖 build_options 和注入 hook。

```python
"""
sa_sliding_window.py — W5 S_A · 滑动窗口压缩策略

【策略】只保留最近 N=8 轮 user-assistant 对,更早 messages 直接丢弃(不摘要)
【入口】PreCompact hook + custom_instructions
【数据流】读 S0_baseline_final_001.jsonl 作为 replay 输入 + 同一份 eval_probes.json
"""

import asyncio
import logging
from pathlib import Path

from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions, HookMatcher
from claude_agent_sdk.types import PreCompactHookInput

from src.agents.long_dialogue_runner import (
    RunConfig, run_dialogue, load_probes, PROJECT_ROOT
)

SLIDING_WINDOW_N = 8  # 保留最近 8 轮

log = logging.getLogger("sa_sliding_window")


# ---------------------------------------------------------------------------
# PreCompact hook · 注入滑动窗口指令
# ---------------------------------------------------------------------------

async def sliding_window_hook(input_data: PreCompactHookInput, tool_use_id, context):
    """SDK 触发自动压缩时,这个 hook 先于 LLM 摘要执行,通过 custom_instructions 告诉 SDK
    用滑动窗口方式压缩(只保留最近 N 轮,不做摘要)。

    【已知不确定性】
    - PreCompactHookInput.custom_instructions 是 hook 输入还是输出?
      看 types.py:它在 input 里,可能是 SDK 传给 hook 的"用户预设指令",hook 可以修改并 return?
      需要 5/26 实跑验证:打印 input_data,确认是否可以 return 一个新 custom_instructions
    - hook return 值的 schema 是什么?HookOutput? 需查 SDK 文档
    """
    log.info("PreCompact hook fired: trigger=%s", input_data.trigger)

    # 滑动窗口指令(自然语言,SDK 内部 LLM 会按这个压)
    instructions = f"""
COMPRESSION STRATEGY: SLIDING WINDOW (NO SUMMARIZATION)

只保留最近 {SLIDING_WINDOW_N} 轮 user-assistant 完整原文消息。
所有更早的消息(包括其中的工具调用 / 工具结果 / 助手分析)直接丢弃,不做摘要。

输出格式:返回 "<keep>" 后接最近 {SLIDING_WINDOW_N} 轮的原文,不要做任何重写或总结。
"""

    # TODO 5/26:确认 hook 返回值结构 + 落 before/after 快照到当前轮的 RoundRecord
    return {"custom_instructions": instructions}


# ---------------------------------------------------------------------------
# build_options · 在 stateful_assistant.build_options 基础上加 hook
# ---------------------------------------------------------------------------

def build_options_sa() -> ClaudeAgentOptions:
    """跟 stateful_assistant.build_options 几乎一样,只额外注册 PreCompact hook"""
    from src.agents.stateful_assistant import build_options
    options = build_options()
    # 注入 hook(覆盖 hooks 字段)
    options.hooks = {
        "PreCompact": [HookMatcher(matcher="*", hooks=[sliding_window_hook])]
    }
    return options


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------

async def main():
    baseline_jsonl = PROJECT_ROOT / "experiments" / "w5_compression" / "S0_baseline_final_001.jsonl"
    probes_json = PROJECT_ROOT / "experiments" / "w5_compression" / "eval_probes.json"

    cfg = RunConfig(
        strategy="S_A_sliding_window",
        total_rounds=30,
        run_tag="001",
        replay_from=baseline_jsonl,                 # 同输入:用 S0 的 user_question 序列
        probe_at_rounds=load_probes(probes_json),   # 同评估:同一份 probe
        seed=42,
    )

    # ⚠️ 关键改动:在跑前 monkey-patch 或新写一个 run_dialogue 变体,把 build_options 换成 build_options_sa
    # 当前 long_dialogue_runner.run_dialogue 是写死 build_options() 的——5/26 早第一步先解耦这里
    # 推荐改法:run_dialogue 接受 build_options 函数作为参数,默认 build_options
    # await run_dialogue(cfg, build_options_fn=build_options_sa)
    raise NotImplementedError("5/26: 先解耦 run_dialogue 的 build_options")


if __name__ == "__main__":
    asyncio.run(main())
```

---

## 3. 5/26 早实施步骤(顺序固定,不要乱)

### Step 1(15 分钟):**解耦 long_dialogue_runner.run_dialogue 的 build_options**
`run_dialogue(cfg, build_options_fn=build_options)` 接受 callable 参数,默认 `stateful_assistant.build_options`。所有 S_A/S_B/S_C 共享这个改动。

### Step 2(20 分钟):**实测 PreCompact hook 触发情况**
写个最小测试 `tests/test_precompact_hook.py`:跑 3 轮高压对话 + autoCompactThreshold 设很低(如果可设),看 hook 是否 fire,打印 input_data 完整结构。
**这一步决定走 A 还是 C 路径。**

### Step 3(30 分钟,取决于 Step 2):
- 如果 A 可行:把骨架补完,跑 30 轮 S_A
- 如果 A 不可行:转 C 路径,每 N 轮主动 close + reopen client,把最近 N 轮 messages 喂回去

### Step 4(15 分钟):
跑评分脚本(eval_scorer.py,5/26 当天也要写),对 S_A 的 R10/R20/R30 probe 答案打分,对比 S0 baseline。

### 总预算:1.5 小时 + $5

---

## 4. 落 RoundRecord 压缩快照字段

S_A 在 PreCompact hook 内能拿到 messages 数组,可以填:
```python
before_messages_count = len(input_data.messages)  # 待确认字段名
after_messages_count = SLIDING_WINDOW_N * 2       # N 轮 × 2 条 / 轮
before_tokens = ?  # 需要 SDK 暴露
after_tokens = ?
compression_action = f"sliding_window_keep_recent_{SLIDING_WINDOW_N}_turns"
dropped_message_indices = list(range(0, before_messages_count - SLIDING_WINDOW_N * 2))
retained_facts_count = 0  # 滑动窗口策略不做"事实提取",此字段对 S_A 无意义,留 None
```
快照怎么从 hook 里落到当前轮的 RoundRecord:**5/26 实施时考虑,可能要在 hook 里 set 一个 module-level 状态变量,主循环写 JSONL 时读出来填。**

---

## 5. 待澄清的开放问题(5/26 跑前必须答完)

| # | 问题 | 怎么答 |
|---|---|---|
| Q1 | `PreCompactHookInput.custom_instructions` 是 input 字段还是 output 字段? | 看 SDK 示例 / 直接打印 hook 收到的 input_data |
| Q2 | hook return 的 schema 是什么?是 dict 还是 HookOutput dataclass? | `grep -rn "HookOutput\|return.*hook" venv/lib/python3.11/site-packages/claude_agent_sdk/` |
| Q3 | `autoCompactThreshold` 在 ClaudeAgentOptions 里是否可写? | grep options 看有没有对应字段 |
| Q4 | 如果 ctx 撑不到 auto-compact 阈值,hook 还能 manual 触发吗? | 看 SDK 有没有 `client.compact()` 或类似方法 |
| Q5 | hook 拿到的 messages 数组怎么修改才能让 SDK 应用?直接改 input_data?return 新 messages? | 同 Q1 验证 |

---

## 6. S_B / S_C 顺势规划

S_A 跑通后,S_B (LLM 摘要) 和 S_C (PreCompact hook + 领域指令) 都复用同一个 PreCompact hook 框架,差别只在 `custom_instructions` 内容:

| 策略 | custom_instructions |
|---|---|
| S_A 滑动窗口 | "只保留最近 8 轮原文,不要摘要" |
| S_B LLM 摘要 | "把所有 messages 摘成 500 字以内,保留所有数字事实" |
| S_C PreCompact + 领域指令 | "摘要时**必须保留**:所有持仓 symbol/cost/shares、拆股因子、复权后成本;其他可省" |

**S_B 和 S_C 的差异 = 是否注入领域知识**。这是 W5 最有论证价值的对比——证明"通用摘要"和"领域感知摘要"在事实保留率上的差异。
