"""
regression_runner.py — description 行为回归测试

每次修改任意 MCP Server 的 description 后运行此脚本，
自动验证每个 fixture case 的工具触发行为是否符合预期。

用法：
  python -m src.agents.regression_runner

为什么用 query() 而不是 ClaudeSDKClient：
  回归测试要求每个 case 独立上下文，防止前一条 case 的信息污染后一条。
  query() 每次调用都是全新 session，天然满足这个要求。
  ClaudeSDKClient 适合多轮交互场景（保持 session 状态），不适合隔离测试。
"""

import asyncio
import textwrap
from dataclasses import dataclass, field

from claude_agent_sdk import query, ClaudeAgentOptions
from claude_agent_sdk.types import (
    PreToolUseHookInput,
    HookContext,
    HookMatcher,
    PreToolUseHookSpecificOutput,
    ResultMessage,
)

# ============================================================
# Fixture 定义
# ============================================================

@dataclass
class Case:
    id: str
    prompt: str
    must_call: list[str]    # 必须触发的工具（全部命中才 pass）
    must_not_call: list[str] = field(default_factory=list)  # 不能触发的工具


# fixture 来源：cross-server-cases.md 实测 case 集
CASES: list[Case] = [
    Case(
        id="A · 单 Server 新闻召回",
        prompt="NVIDIA 最近一周有什么重要新闻？",
        must_call=["mcp__investment-news__get_news"],
        must_not_call=["mcp__investment-finance__get_quote"],
    ),
    Case(
        id="B · 中文新闻召回",
        prompt="贵州茅台最近一周有什么新闻？",
        must_call=["mcp__investment-news__get_news"],
    ),
    Case(
        id="C · 因果推理跨 Server",
        prompt="腾讯最近为什么跌？",
        must_call=[
            "mcp__investment-finance__get_quote",
            "mcp__investment-finance__get_history",
            "mcp__investment-news__get_news",
        ],
    ),
    Case(
        id="Case-3 · 拆股提醒应触发 NVDA",
        prompt="我的 NVDA 持仓浮盈多少？",
        must_call=[
            "mcp__investment-memory__list_portfolio",
            "mcp__investment-finance__get_quote",
        ],
    ),
    Case(
        id="Case-4 · 拆股提醒不应误触 AAPL",
        prompt="我的 AAPL 持仓浮盈多少？",
        must_call=[
            "mcp__investment-memory__list_portfolio",
            "mcp__investment-finance__get_quote",
        ],
        # AAPL $150 是正常 post-split 价位，不应触发 corporate_actions 查询
        must_not_call=["mcp__investment-corporate-actions__get_corporate_actions"],
    ),
    Case(
        id="Case-6 · 真实下跌不误触 09988.HK",
        prompt="我的 09988.HK 持仓浮盈多少？",
        must_call=[
            "mcp__investment-memory__list_portfolio",
            "mcp__investment-finance__get_quote",
        ],
        # 阿里港股无拆股，-52% 是真实下跌，不应触发
        must_not_call=["mcp__investment-corporate-actions__get_corporate_actions"],
    ),
    Case(
        id="D' · 完整周报 + 拆股兜底 TSLA",
        prompt="持仓里的 TSLA：拉新闻 + 当前价 + 我的成本，给个建议",
        must_call=[
            "mcp__investment-memory__list_portfolio",
            "mcp__investment-finance__get_quote",
            "mcp__investment-news__get_news",
            "mcp__investment-corporate-actions__get_corporate_actions",
        ],
    ),
    Case(
        id="NEG-1 · 负样本：行业趋势",
        prompt="帮我分析一下 AI 行业的发展趋势",
        must_call=[],
        # 不涉及持仓或行情，不应触发任何 MCP 投资工具
        must_not_call=[
            "mcp__investment-memory__list_portfolio",
            "mcp__investment-finance__get_quote",
            "mcp__investment-news__get_news",
        ],
    ),
    Case(
        id="NEG-2 · 负样本：概念解释",
        prompt="什么是量化投资？",
        must_call=[],
        must_not_call=[
            "mcp__investment-memory__list_portfolio",
            "mcp__investment-finance__get_quote",
        ],
    ),
]

# ============================================================
# 单 case 运行
# ============================================================

async def run_case(case: Case, options: ClaudeAgentOptions) -> dict:
    """运行一个 case，返回 {passed, actual_tools, missing, unexpected}。"""
    actual_tools: list[str] = []

    async def pre_hook(
        inp: PreToolUseHookInput, session_id: str | None, ctx: HookContext
    ) -> PreToolUseHookSpecificOutput:
        actual_tools.append(inp["tool_name"])
        return PreToolUseHookSpecificOutput(hookEventName="PreToolUse")

    case_options = ClaudeAgentOptions(
        **{k: v for k, v in vars(options).items() if k != "hooks"},
        hooks={"PreToolUse": [HookMatcher(hooks=[pre_hook])]},
    )

    async for message in query(prompt=case.prompt, options=case_options):
        pass  # 只关心工具调用，不收集文本

    # 过滤掉平台层 ToolSearch，它不是业务工具
    business_tools = [t for t in actual_tools if t != "ToolSearch"]

    missing = [t for t in case.must_call if t not in business_tools]
    unexpected = [t for t in case.must_not_call if t in business_tools]
    passed = not missing and not unexpected

    return {
        "passed": passed,
        "actual": business_tools,
        "missing": missing,
        "unexpected": unexpected,
    }


# ============================================================
# 主入口
# ============================================================

async def main() -> None:
    base_options = ClaudeAgentOptions(
        setting_sources=["project", "local"],
        cwd="/Users/mtdp/ai/projects/investment-agent",
        permission_mode="bypassPermissions",
        allowed_tools=[
            "mcp__investment-memory__list_portfolio",
            "mcp__investment-memory__get_preferences",
            "mcp__investment-finance__get_quote",
            "mcp__investment-finance__get_history",
            "mcp__investment-news__get_news",
            "mcp__investment-corporate-actions__get_corporate_actions",
        ],
    )

    results = []
    for case in CASES:
        print(f"  running [{case.id}] …", end="", flush=True)
        result = await run_case(case, base_options)
        results.append((case, result))
        print(" ✅ PASS" if result["passed"] else " ❌ FAIL")

    # 汇总
    passed = sum(1 for _, r in results if r["passed"])
    total = len(results)
    print(f"\n{'='*60}")
    print(f"结果：{passed}/{total} passed")
    print(f"{'='*60}")

    for case, result in results:
        if not result["passed"]:
            print(f"\n❌ {case.id}")
            print(f"   实际触发：{result['actual']}")
            if result["missing"]:
                print(f"   缺少：    {result['missing']}")
            if result["unexpected"]:
                print(f"   多余：    {result['unexpected']}")

    if passed < total:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
