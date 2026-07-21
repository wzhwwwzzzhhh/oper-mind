"""评测数据集契约 —— 用 Pydantic 定死每条评测用例的结构。

评测层契约，独立于诊断运行时链路的 DiagnosisState。
用例存 data/eval/cases.jsonl（每行一条 JSON），加载后逐条过本模型校验。

设计见 docs/开发/M1-评测数据集/design.md。
"""

from typing import Literal

from pydantic import BaseModel, Field, field_validator


# 与 src/core/graph.py 的路由契约保持一致
Domain = Literal["db", "server", "log", "compound"]
Strategy = Literal["direct", "chain", "parallel"]
Difficulty = Literal["easy", "medium", "hard"]
Source = Literal["seed", "synthetic"]

# 合法的 Agent 注册名（见 src/core/bootstrap.build_system）
VALID_AGENTS = {"db", "server", "log"}


class EvalCase(BaseModel):
    """单条评测用例。

    字段语义见 design.md 第 3.1 节。所有用例的 query 必须含能在
    mock 关键词兜底路由下命中 expected_strategy / expected_agents 的关键词。
    """

    case_id: str = Field(..., description="稳定 ID，如 db-001 / chain-003")
    query: str = Field(..., description="用户自然语言问题（含可路由关键词）")
    domain: Domain = Field(..., description="领域标签")
    expected_strategy: Strategy = Field(..., description="期望路由策略")
    expected_agents: list[str] = Field(..., description="期望参与的 Agent 注册名")
    difficulty: Difficulty = Field(..., description="难度分级")
    golden_root_cause: str = Field(..., description="golden 根因，供 LM-as-judge 对照")
    golden_key_points: list[str] = Field(
        ..., description="期望命中的关键结论点，供逐点计分"
    )
    expects_debate: bool = Field(
        False, description="是否期望触发辩论（仅 parallel 可能为 true）"
    )
    source: Source = Field(..., description="来源：seed=迁移自旧用例 / synthetic=新造")
    notes: str = Field("", description="备注，如注入的 mock 现象说明")
    scenario: str = Field(
        "S1", description="绑定的 mock 故障场景 key（见 data/scenarios.py），默认 S1"
    )

    @field_validator("expected_agents")
    @classmethod
    def _check_agents(cls, v: list[str]) -> list[str]:
        """expected_agents 非空，且取值必须是合法注册名"""
        if not v:
            raise ValueError("expected_agents 不能为空")
        illegal = set(v) - VALID_AGENTS
        if illegal:
            raise ValueError(f"非法 Agent 名：{illegal}，合法取值：{VALID_AGENTS}")
        return v

    @field_validator("golden_key_points")
    @classmethod
    def _check_key_points(cls, v: list[str]) -> list[str]:
        """至少一个关键结论点，供评分对照"""
        if not v:
            raise ValueError("golden_key_points 不能为空")
        return v

    def model_post_init(self, __context: object) -> None:
        """跨字段一致性校验：策略与 Agent 数量、debate 约束"""
        n = len(self.expected_agents)
        if self.expected_strategy == "direct" and n != 1:
            raise ValueError(
                f"[{self.case_id}] direct 策略应只有 1 个 expected_agent，实际 {n} 个"
            )
        if self.expected_strategy in ("chain", "parallel") and n < 2:
            raise ValueError(
                f"[{self.case_id}] {self.expected_strategy} 策略应有 ≥2 个 expected_agent，实际 {n} 个"
            )
        if self.expects_debate and self.expected_strategy != "parallel":
            raise ValueError(
                f"[{self.case_id}] expects_debate=true 仅允许 parallel 策略"
            )
