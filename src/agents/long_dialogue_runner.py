"""
long_dialogue_runner.py — W5 · Agent-to-Agent 长对话驱动器（策略 0 baseline）

【目标】
把 synthetic_user.next_question() × stateful_assistant 的 ClaudeSDKClient 串成
N 轮自动对话。每轮记录 ctx token / cost / auto-compact 状态 → 落 JSONL，
观察 token 单调上升曲线 + 何时触发什么行为。

【今天 D 边界】
仅跑策略 0（不压缩）。压缩策略 A/B/C 在 5/26-5/28 接入。
本文件不引入 hook、不做 messages 截断、不做摘要——纯 baseline 观测。

【两 Agent 的不对称：为什么投资助手用 ClaudeSDKClient，用户用 query()】
- 投资助手要"跨轮记忆"→ 必须 stateful → ClaudeSDKClient
- 用户 Agent 每轮"基于上轮助手回答产 1 个问题"，跨轮上下文从外部喂（last_response），
  Agent 自己不需要记忆 → stateless → query() 更轻
这条不对称是 W5 实验的语料生成器设计原则，不是巧合。
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path

from claude_agent_sdk import ClaudeSDKClient
from claude_agent_sdk.types import AssistantMessage, TextBlock, ResultMessage

from src.agents.stateful_assistant import build_options
from src.agents.synthetic_user import next_question

PROJECT_ROOT = Path(__file__).parent.parent.parent
EXPERIMENT_DIR = PROJECT_ROOT / "experiments" / "w5_compression"
EXPERIMENT_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("long_dialogue_runner")


# ============================================================================
# 配置区 · 单次 run 的可调参数
# ============================================================================

@dataclass
class RunConfig:
    """一次 run 的全部可调参数。

    设计抉择（5/24 已定）：
    - 停止条件 = **固定 N 轮**（候选 A）。所有策略跑同一长度，token 量是因变量，
      这样"token 节省 %"和"信息保留率"才有同分母可比。
    - 同输入保障 = **首跑落盘 + 重放**（方式 2）。S0 baseline 把每轮 user_question
      落 JSONL，S_A/B/C 用 replay_from 读这份 JSONL 当固定输入。
    - 重放失真：S_A 因为压缩了 context 回答可能跟 S0 不一样，但 user_question
      还是基于 S0 回答产的 → 中后段可能"问答错位"。为控变量必须付的代价。

    设计抉择（5/25 增强 · 评审反馈）：
    - probe_at_rounds：在指定轮强制注入"评估题"，**绕过 synthetic_user / replay**，
      让 4 策略在 R10/R20/R30 被同一刀切。这是 replay 失真风险（R1）的真正解药：
      自然对话评分会被前轮错位污染，固定 probe 与对话历史无关，所有策略可比。
    - probe 内容从 eval_probes.json 加载（pre-registration / 预注册原则）：
      eval 配置必须在跑 treatment 前 commit，避免"跑完挑题"的 p-hacking。
    """
    strategy: str = "S0_baseline"          # 跟 5/26+ 的 S_A / S_B / S_C 拉齐
    total_rounds: int = 30                 # 固定跑这么多轮，所有策略对齐
    stop_on_error: bool = True             # SDK 报错时是否中止（true=诚实记录极限）
    seed: int | None = 42                  # synthetic_user 行为多样化的随机种子
    replay_from: Path | None = None        # 非 None = 重放模式，从该 JSONL 读 user_question
    run_tag: str = "001"                   # 落盘文件名后缀
    probe_at_rounds: dict[int, str] | None = None  # {round_idx: probe_question}，None 则不注入


# ============================================================================
# 每轮记录的数据结构 · 落 JSONL
# ============================================================================

@dataclass
class RoundRecord:
    """单轮对话的全量观测数据，逐行写 JSONL 方便后续 4 策略对比。

    【5/25 增强字段】
    - is_probe / probe_id：标记该轮是否为评估 probe，评分脚本只统计 probe 轮
    - assistant_text_full：probe 轮存全文（评分用），非 probe 轮存预览
    - compression_*：S0 baseline 留空位（None / 0），S_A/B/C 实现时填
      面试官必问"PreCompact hook 到底压了什么"——光给数字答不上来，
      必须能展示"R20 丢了哪些 message、保留了哪些事实"
    """
    round_idx: int
    user_question: str
    assistant_text_preview: str          # 助手回答首 200 字（非 probe 轮）
    num_turns: int                       # ResultMessage.num_turns
    cost_usd: float
    ctx_total_tokens: int
    ctx_percentage: float
    ctx_max_tokens: int
    ctx_auto_compact_enabled: bool
    ctx_categories: dict[str, int]       # name -> tokens，便于看哪类在涨
    timestamp: str
    # ---- 5/25 增强：probe 标记 ----
    is_probe: bool = False
    probe_id: str | None = None          # eval_probes.json 里的 id（R10_single_fact 等）
    assistant_text_full: str | None = None  # probe 轮存全文，给 eval 评分用
    # ---- 5/25 增强：压缩快照（S_A/B/C 实现时填，S0 留 None） ----
    before_messages_count: int | None = None
    after_messages_count: int | None = None
    before_tokens: int | None = None
    after_tokens: int | None = None
    compression_action: str | None = None         # e.g. "kept_recent_8" / "summarized_R1-R10"
    retained_facts_count: int | None = None       # 策略保留的关键持仓事实数
    dropped_message_indices: list[int] | None = None


# ============================================================================
# 问题源 · live (synthetic_user) vs replay (JSONL)
# ============================================================================

class QuestionSource:
    """统一"取第 N 轮 user_question"的接口。

    优先级（5/25 新增）：
    1. probe_at_rounds[round_idx] 命中 → 强制返回 probe 文本（评估用）
    2. replay_from 非 None → 从 JSONL 按 round_idx 读
    3. 否则 → 调 synthetic_user.next_question() 动态产

    为什么 probe 优先级最高：评估题不能依赖被评估系统的输出。
    自然对话 / replay 都可能被前轮错位污染，probe 与对话历史无关，所有策略可比。
    """

    def __init__(
        self,
        replay_from: Path | None,
        probe_at_rounds: dict[int, str] | None = None,
    ) -> None:
        self.replay_from = replay_from
        self.probe_at_rounds = probe_at_rounds or {}
        self._replay_cache: list[str] = []
        if replay_from is not None:
            with replay_from.open() as f:
                for line in f:
                    rec = json.loads(line)
                    self._replay_cache.append(rec["user_question"])
            log.info("replay mode: loaded %d questions from %s", len(self._replay_cache), replay_from)
        if self.probe_at_rounds:
            log.info("probe mode: will inject at rounds %s", sorted(self.probe_at_rounds.keys()))

    def is_probe_round(self, round_idx: int) -> bool:
        return round_idx in self.probe_at_rounds

    async def get(self, round_idx: int, last_assistant_response: str | None) -> str:
        # 1. probe 优先：覆盖一切其他来源
        if round_idx in self.probe_at_rounds:
            return self.probe_at_rounds[round_idx]
        # 2. replay
        if self.replay_from is not None:
            i = round_idx - 1
            if i >= len(self._replay_cache):
                raise IndexError(f"replay 文件只有 {len(self._replay_cache)} 轮，要不到第 {round_idx} 轮")
            return self._replay_cache[i]
        # 3. live
        return await next_question(
            last_assistant_response=last_assistant_response,
            round_idx=round_idx,
        )


# ============================================================================
# 助手消息聚合 · 把一轮内的多条 message 揉成一个 RoundRecord
# ============================================================================

async def consume_one_round(
    client: ClaudeSDKClient,
    round_idx: int,
    user_question: str,
) -> tuple[str, ResultMessage | None]:
    """跑一轮 query 并消费完整消息流，返回 (完整助手文本, ResultMessage)。

    完整助手文本要喂给下一轮 synthetic_user，所以这里要拼全所有 TextBlock，
    而不是 stateful_assistant.handle_message 的预览版。
    """
    full_text_parts: list[str] = []
    result_msg: ResultMessage | None = None

    await client.query(user_question)
    async for msg in client.receive_response():
        if isinstance(msg, AssistantMessage):
            for block in msg.content:
                if isinstance(block, TextBlock):
                    full_text_parts.append(block.text)
        elif isinstance(msg, ResultMessage):
            result_msg = msg
            log.info(
                "R%d ── done  turns=%d  cost=$%.4f",
                round_idx,
                msg.num_turns,
                msg.total_cost_usd or 0,
            )

    return "\n".join(full_text_parts), result_msg


async def snapshot_ctx(client: ClaudeSDKClient, round_idx: int) -> dict:
    """拍一张当前 ctx 快照，返回标准化 dict（落 JSONL 用）。"""
    usage = await client.get_context_usage()
    cats = {c["name"]: c["tokens"] for c in usage["categories"]}
    log.info(
        "R%d ── ctx  total=%d (%.1f%%)  autoCompact=%s",
        round_idx,
        usage["totalTokens"],
        usage["percentage"],
        usage["isAutoCompactEnabled"],
    )
    return {
        "total": usage["totalTokens"],
        "pct": usage["percentage"],
        "max": usage["maxTokens"],
        "auto_compact": usage["isAutoCompactEnabled"],
        "categories": cats,
    }


# ============================================================================
# 主循环
# ============================================================================

async def run_dialogue(cfg: RunConfig) -> Path:
    """跑一次完整 N 轮对话，落 JSONL，返回输出路径。"""
    import random
    if cfg.seed is not None:
        random.seed(cfg.seed)

    output_path = EXPERIMENT_DIR / f"{cfg.strategy}_{cfg.run_tag}.jsonl"
    source = QuestionSource(cfg.replay_from, cfg.probe_at_rounds)

    log.info("=== run %s · %d rounds · output=%s ===", cfg.strategy, cfg.total_rounds, output_path)

    options = build_options()
    last_assistant_text: str | None = None

    with output_path.open("w") as out_f:
        async with ClaudeSDKClient(options=options) as client:
            for round_idx in range(1, cfg.total_rounds + 1):
                log.info("")
                log.info("--- R%d ---", round_idx)

                # 1. 取本轮 user_question
                try:
                    user_question = await source.get(round_idx, last_assistant_text)
                except Exception as exc:
                    log.error("R%d 取问题失败: %s", round_idx, exc)
                    if cfg.stop_on_error:
                        break
                    continue
                log.info("R%d → user: %s", round_idx, user_question)

                # 2. 跑一轮 assistant
                try:
                    assistant_text, result_msg = await consume_one_round(
                        client, round_idx, user_question
                    )
                except Exception as exc:
                    log.error("R%d assistant 跑挂: %s", round_idx, exc)
                    if cfg.stop_on_error:
                        break
                    continue

                # 3. 拍 ctx 快照
                try:
                    ctx = await snapshot_ctx(client, round_idx)
                except Exception as exc:
                    log.warning("R%d ctx 快照失败: %s", round_idx, exc)
                    ctx = {"total": -1, "pct": -1, "max": -1, "auto_compact": None, "categories": {}}

                # 4. 落 JSONL
                # probe 轮要存全文（评分用），非 probe 轮存预览（省空间）
                is_probe = source.is_probe_round(round_idx)
                probe_id = None
                if is_probe and cfg.probe_at_rounds:
                    # 简化：probe_id = "R{round}_probe"，跟 eval_probes.json 对应
                    probe_id = f"R{round_idx}_probe"
                    log.info("R%d ── PROBE ROUND (id=%s)", round_idx, probe_id)

                rec = RoundRecord(
                    round_idx=round_idx,
                    user_question=user_question,
                    assistant_text_preview=assistant_text[:200].replace("\n", " "),
                    num_turns=result_msg.num_turns if result_msg else -1,
                    cost_usd=float(result_msg.total_cost_usd or 0) if result_msg else 0.0,
                    ctx_total_tokens=ctx["total"],
                    ctx_percentage=ctx["pct"],
                    ctx_max_tokens=ctx["max"],
                    ctx_auto_compact_enabled=bool(ctx["auto_compact"]) if ctx["auto_compact"] is not None else False,
                    ctx_categories=ctx["categories"],
                    timestamp=datetime.now().isoformat(),
                    is_probe=is_probe,
                    probe_id=probe_id,
                    assistant_text_full=assistant_text if is_probe else None,
                    # 压缩快照字段：S0 留 None，S_A/B/C 实现时填
                )
                out_f.write(json.dumps(asdict(rec), ensure_ascii=False) + "\n")
                out_f.flush()

                # 5. 把完整助手文本喂给下轮 synthetic_user
                last_assistant_text = assistant_text

    log.info("=== run done · output=%s ===", output_path)
    return output_path


# ============================================================================
# CLI 入口
# ============================================================================

def load_probes(probes_path: Path | None) -> dict[int, str] | None:
    """加载 eval_probes.json，返回 {round_idx: question} 字典。

    eval_probes.json 结构（pre-registration / 预注册原则）：
    {
      "probes": [
        {"round": 10, "id": "R10_single_fact", "question": "...", "expected": ...},
        ...
      ]
    }
    """
    if probes_path is None:
        return None
    with probes_path.open() as f:
        data = json.load(f)
    result = {p["round"]: p["question"] for p in data["probes"]}
    log.info("loaded %d probes from %s: rounds=%s", len(result), probes_path, sorted(result.keys()))
    return result


async def _main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="W5 长对话 runner")
    parser.add_argument("--strategy", default="S0_baseline")
    parser.add_argument("--rounds", type=int, default=30)
    parser.add_argument("--tag", default="001")
    parser.add_argument("--replay-from", type=Path, default=None)
    parser.add_argument("--probes", type=Path, default=None,
                        help="eval_probes.json 路径，None=不注入 probe")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    cfg = RunConfig(
        strategy=args.strategy,
        total_rounds=args.rounds,
        run_tag=args.tag,
        replay_from=args.replay_from,
        seed=args.seed,
        probe_at_rounds=load_probes(args.probes),
    )
    await run_dialogue(cfg)


if __name__ == "__main__":
    asyncio.run(_main())
