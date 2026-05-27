"""
synthetic_user.py — W5 D4 · 扮演"投资用户"的 Agent

【目标】
为 W5 上下文工程实验提供长对话语料。用一个独立 Claude 实例扮演"有持仓的投资用户"，
吃[投资助手的上一轮回答]当输入，吐出[下一轮真实用户会问的问题]。
然后把这个问题喂给 stateful_assistant，循环 N 轮 → 自然长对话 → 触发 auto-compact。

【为什么需要这个文件】
手敲 50 轮对话太累 + 不可重复 + ablation study 没法控变量。
用 Agent 模拟用户 = 同 prompt + 同温度 → 同输入 → 同对话路径，每次跑数据可对比。
这条路径还顺带是 W7 多 Agent 工作流的雏形（Agent 喂 Agent 模式）。

【关键设计点 · 详见每个函数 docstring】
- 用 query() 而非 ClaudeSDKClient → stateless 调用 + 跨 Agent 上下文不污染
- system_prompt 写"角色 + 输出格式约束"，user_prompt 只塞"上轮助手说了啥"
- BEHAVIOR_PALETTE 强制行为多样化，防止"用户" Agent 一直问同一类问题
- 输出格式 hard constraint：只产 1 个问题字符串，不许带解释 / 思考过程 / 元评论

【知识点覆盖】
1. claude-agent-sdk query() 用法（stateless 单次任务）
2. system_prompt vs user_prompt 的职责分工
3. 角色扮演 prompt engineering（约束输出形态比"描述任务"更重要）
4. 行为多样化设计（防止 LLM 输出 collapse）
5. Agent-to-Agent 编排基础（W7 多 Agent 雏形）
"""

import asyncio
import logging
import random
from pathlib import Path

# query() 是 SDK 的 stateless 入口 —— 跟 stateful_assistant.py 用的 ClaudeSDKClient
# 是两种入口模式。query() 适合"一次性任务"（这里就是"产生下一个用户问题"）。
# ClaudeAgentOptions 用来配置：system_prompt / 工具池 / 模型等。
from claude_agent_sdk import query, ClaudeAgentOptions
from claude_agent_sdk.types import AssistantMessage, TextBlock

PROJECT_ROOT = Path(__file__).parent.parent.parent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("synthetic_user")


# ============================================================================
# 配置区 · 用户角色 + 行为多样化
# ============================================================================

# 用户持仓上下文 —— 跟 config/portfolio.yaml 保持同步。
# 为什么不直接读 yaml？因为 synthetic_user 是"用户"视角，用户脑子里记得自己买了啥，
# 不需要去查 yaml。把持仓硬编码在 prompt 里更符合"用户"角色。
PORTFOLIO_CONTEXT = """
你的持仓（5 个）：
- TSLA 1000 股，成本价 $1200
- NVDA 200 股，成本价 $40
- AAPL 500 股，成本价 $150
- 09988.HK（阿里巴巴）100 股，成本价 $280
- 600519.SS（贵州茅台）10 股，成本价 ¥1680
"""

# 行为调色板 —— 防止 LLM 输出 collapse 到"再帮我看看 TSLA"这种单一模式。
# 每次调 synthetic_user 时随机抽 1 个 hint 塞进 prompt，强制行为多样化。
#
# 【5/25 重构 · 自然对话密度陷阱】
# 原始 10 类全是单股自然问题，实测 14 轮 ctx 才 10%（1M 模型），撑不到 auto-compact。
# 拆成两池 + 加权（HIGH 0.7 / NORMAL 0.3）：HIGH 池每条都强制助手调多个工具，
# 一轮 messages 数组涨 5-15 条 → 预期 10 轮内撑到 ≥50% ctx。
# 代价：用户语义偏"信息密集型"，但仍是真人会问的（焦虑型散户 / 复盘狂魔的典型行为）。

# 高压池 · 每条都强制助手调 ≥3 个工具
HIGH_PRESSURE_PALETTE = [
    "要求一次性查所有 5 只持仓的当前价 + 浮盈 + 拆股累计因子，做成一张总览表",
    "突然提出：把所有持仓最近 3 个月的新闻 + 价格走势 + 公司动态全拉出来，我要做季度复盘",
    "提一个必须对比 3 只以上股票才能回答的问题（比如：TSLA / NVDA / AAPL 谁的拆股调整影响最大？谁现在最值得加仓？）",
    "要求把所有美股持仓（TSLA / NVDA / AAPL）的最新报价 + 最近新闻 + 拆股历史全拉一遍，然后给加减仓建议",
    "提出跨市场对比：港股 09988 + A 股 600519 + 美股 TSLA 三只放一起，分别给当前价 / 浮盈 / 最近新闻，说哪只该减仓",
]

# 普通池 · 单股 / 简单问答，保持对话自然感
NORMAL_PALETTE = [
    "追问拆股复权细节（特别是某个 symbol 的累计因子和复权后成本）",
    "对助手的上一个结论表示怀疑，要求 ground truth 验证",
    "切换话题问另一个持仓（避免一直问同一只）",
    "问技术细节（拆股是怎么算的？复权和 split-adjusted 有什么区别？）",
    "问历史复盘（如果当初没买 X，现在会怎样）",
]

# 加权采样：HIGH 0.7 / NORMAL 0.3，由 _sample_hint() 实现
HIGH_PRESSURE_WEIGHT = 0.7


# ============================================================================
# system prompt · 角色 + 输出格式约束
# ============================================================================

# 关键设计：把"角色定义 + 输出格式约束"放 system_prompt，把"实时上下文"放 user_prompt。
#
# 为什么不直接全塞 user_prompt？
# - system_prompt 在 SDK 内部权重更高，LLM 更不容易"break out"
# - 防止 LLM 把"你扮演用户"理解成"用户请你帮忙"然后开始分析
# - 同样的角色约束放 user_prompt，LLM 会"礼貌地分析问题"，不是产用户输入
SYNTHETIC_USER_SYSTEM_PROMPT = f"""你正在扮演一个普通的散户投资用户，跟你的投资助手 AI 对话。

{PORTFOLIO_CONTEXT}

【输出格式 · 严格遵守】
你只输出 1 个你想问助手的问题，不超过 50 字。
不要解释你为什么问、不要带"作为用户我会"等元评论、不要列多个备选问题。
直接出问题，第一人称口吻，像真人聊天那样。

【角色一致性】
- 你不是 AI，是有持仓的人
- 你不需要"帮助助手"，你是用助手帮你
- 你可能会有怀疑、不耐烦、追问细节、转移话题等真实人类行为
- 你不需要表现得礼貌或专业，可以口语化（"那 TSLA 呢？" 比 "请问关于 TSLA..." 更真实）
"""


# ============================================================================
# 核心 API · next_question()
# ============================================================================

async def next_question(
    last_assistant_response: str | None = None,
    behavior_hint: str | None = None,
    round_idx: int = 0,
) -> str:
    """根据助手上一轮的回答，产生下一轮用户会问的问题。

    Args:
        last_assistant_response: 投资助手上一轮的回答文本。第一轮传 None。
        behavior_hint: 行为提示（从 BEHAVIOR_PALETTE 随机抽），强制多样化。
                       不传则随机抽。
        round_idx: 第几轮，仅用于日志。

    Returns:
        用户的下一个问题字符串（≤50 字）。

    设计说明：
    - 返回值是纯字符串，不是 Message 对象 —— 上游 long_dialogue_runner 拿到字符串
      直接 await assistant.query(user_input)，接口简单。
    - 第一轮 last_assistant_response=None → user_prompt 退化为"开始对话"。
    - 容错：如果 query() 报错或输出空，返回兜底问题，避免长对话脚本中断。
    """
    # 1. 抽行为提示（外面传了就用，没传就加权随机）
    if behavior_hint is None:
        behavior_hint = _sample_hint()

    # 2. 拼 user_prompt
    # 第一轮特殊处理：没有上轮回答，让用户主动开场
    if last_assistant_response is None:
        user_prompt = (
            f"现在是对话开始。本轮的提问方向：{behavior_hint}\n\n"
            "请输出你的开场问题（≤50 字）。"
        )
    else:
        # 后续轮：把助手上轮回答塞进来，让"用户" Agent 基于回答产追问
        # 截断到 800 字 —— 太长会让 synthetic_user 自己也累得忘了输出格式约束
        truncated = last_assistant_response[:800]
        user_prompt = (
            f"你的助手刚刚回答：\n---\n{truncated}\n---\n\n"
            f"本轮的提问方向：{behavior_hint}\n\n"
            "请输出你的下一个问题（≤50 字）。"
        )

    # 3. 配置 SDK options
    # 关键点：
    # - allowed_tools=[] → 用户 Agent 不需要任何工具，他不查股票数据，他是用户
    # - setting_sources=["project", "local"] → 跟 stateful_assistant 对齐
    #   （5/24 smoke 实测踩坑路径：
    #    · setting_sources=[] → CLI 401 "authentication_failed"，鉴权回落机制不工作
    #    · setting_sources=["user"] → 仍 401，且单轮挂 6 分钟才报错
    #    · setting_sources=["project","local"] → 抄 stateful_assistant 现成配置）
    #   副作用：会加载项目 .mcp.json 的 4 个 MCP server，但 allowed_tools=[]
    #   LLM 不会去调，只是启动慢一点。控变量优先于启动速度。
    # - permission_mode="bypassPermissions" → 实验脚本不卡权限弹窗
    options = ClaudeAgentOptions(
        system_prompt=SYNTHETIC_USER_SYSTEM_PROMPT,
        allowed_tools=[],
        setting_sources=["project", "local"],
        permission_mode="bypassPermissions",
        cwd=str(PROJECT_ROOT),
        # 5/25 锁 Sonnet 4.6 · 跟 stateful_assistant 对齐
        model="claude-sonnet-4-6",
    )

    # 4. 调 query() 收集结果
    # query() 返回一个 async iterator，迭代 message 流。
    # 我们只取 AssistantMessage 里第一个 TextBlock 的 text —— synthetic_user
    # 的 system_prompt 已经约束输出格式，正常情况下只有一个 text block。
    collected_text = ""
    try:
        async for msg in query(prompt=user_prompt, options=options):
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        collected_text += block.text
    except Exception as exc:
        # 容错：query 报错时给兜底问题，长对话脚本不中断
        log.warning("R%d synthetic_user query failed: %s", round_idx, exc)
        return _fallback_question(behavior_hint)

    # 5. 后处理：去掉首尾空白 + 防止 LLM 不听话输出多行
    # LLM 偶尔会自作主张加 "我的问题：" 前缀，简单清理
    result = collected_text.strip()
    # 取最长那一行 —— 多行输出取最像问题的那行（带问号的优先）
    lines = [ln.strip() for ln in result.split("\n") if ln.strip()]
    if not lines:
        return _fallback_question(behavior_hint)
    # 优先取带问号的行（"?" 或 "？"）
    question_lines = [ln for ln in lines if "?" in ln or "？" in ln]
    chosen = question_lines[0] if question_lines else lines[0]

    # 去掉常见的 LLM 前缀
    for prefix in ["我的问题：", "问题：", "用户：", "我问：", "- ", "* "]:
        if chosen.startswith(prefix):
            chosen = chosen[len(prefix):].strip()

    log.info("R%d ← synthetic_user (hint=%s): %s", round_idx, behavior_hint[:20], chosen)
    return chosen


def _sample_hint() -> str:
    """加权采样 BEHAVIOR hint：HIGH 0.7 / NORMAL 0.3。

    为什么不用 random.choices(weights=...)：HIGH 池和 NORMAL 池里每条权重均匀，
    池间权重才有差。两步采样语义更清晰：先选池，再池内均匀抽。
    """
    if random.random() < HIGH_PRESSURE_WEIGHT:
        return random.choice(HIGH_PRESSURE_PALETTE)
    return random.choice(NORMAL_PALETTE)


def _fallback_question(behavior_hint: str) -> str:
    """query 失败时的兜底问题。

    设计原则：兜底也要走 behavior_hint，保持行为多样化的语义不丢。
    用关键词粗匹配 hint，给一个对应的"通用追问"。
    """
    if "拆股" in behavior_hint or "复权" in behavior_hint:
        return "TSLA 的复权后成本到底是多少？"
    if "新闻" in behavior_hint:
        return "最近有什么影响我持仓的新闻？"
    if "加仓" in behavior_hint or "减仓" in behavior_hint:
        return "现在该加仓还是减仓？"
    if "怀疑" in behavior_hint or "验证" in behavior_hint:
        return "你上面那个数字靠谱吗？查下 ground truth"
    if "切换话题" in behavior_hint:
        return "那 NVDA 呢？"
    if "对比" in behavior_hint:
        return "TSLA 和 NVDA 哪个风险大？"
    if "港股" in behavior_hint or "A 股" in behavior_hint:
        return "09988.HK 和 600519.SS 该怎么看？"
    if "历史" in behavior_hint or "复盘" in behavior_hint:
        return "当初没买 TSLA 现在会怎样？"
    if "技术细节" in behavior_hint:
        return "复权是怎么算的？"
    return "整体浮盈浮亏现在多少？"


# ============================================================================
# 自测入口 · python -m src.agents.synthetic_user
# ============================================================================

async def _self_test() -> None:
    """跑 3 轮独立 synthetic_user 调用，确认能稳定产合规问题。"""
    log.info("=== synthetic_user self-test ===")

    # Round 1：无上下文（开场）
    q1 = await next_question(last_assistant_response=None, round_idx=1)
    log.info("Q1 (cold start): %s", q1)

    # Round 2：模拟助手回答了 TSLA 复权细节，看用户怎么追问
    mock_response_2 = (
        "你的 TSLA 1000 股成本 $1200 是拆股前价位。TSLA 经历过 2020-08 (5:1) "
        "和 2022-08 (3:1) 两次拆股，累计 15:1。复权后成本为 $1200 ÷ 15 = $80。"
        "当前价约 $417，浮盈 +421%。"
    )
    q2 = await next_question(last_assistant_response=mock_response_2, round_idx=2)
    log.info("Q2 (after TSLA explanation): %s", q2)

    # Round 3：模拟助手回答了 NVDA，看用户怎么转换话题
    mock_response_3 = (
        "NVDA $40 这个成本价对应 2021-07 4:1 拆股之前。如果是 2021 前买入，"
        "复权后成本是 $40 ÷ 40 = $1（含 2024-06 10:1 累计）。当前价 $219，浮盈 +21800%。"
    )
    q3 = await next_question(last_assistant_response=mock_response_3, round_idx=3)
    log.info("Q3 (after NVDA explanation): %s", q3)


if __name__ == "__main__":
    asyncio.run(_self_test())
