"""评测结果契约 —— 单条结果 CaseResult 与整批汇总 EvalSummary。

CaseResult.from_run_result 把 runner.run_case() 的嵌套返回字典
（{case_id, report, deterministic: {...}, judge: {...}, error?}）
拼上 EvalCase 的 domain/difficulty，铸成扁平契约，方便落盘为 jsonl。

不是运行时 DiagnosisState，也不是数据层 EvalCase：三者职责分离。
设计见 docs/开发/M2-评测Harness/design.md 第 3.1 / 6 节。
"""

from typing import Any

from pydantic import BaseModel, Field

from data.eval.schema import EvalCase


class CaseResult(BaseModel):
    """单条用例的评测结果"""

    case_id: str
    domain: str
    difficulty: str

    # 确定性指标（来自 metrics.compute_deterministic）
    actual_strategy: str = Field(..., description="trace 实际路由到的策略，未识别为空串")
    route_hit: bool = Field(..., description="实际策略 == expected_strategy")
    target_hit: bool = Field(..., description="direct 模式目标 Agent 命中；非 direct 恒 True")
    pipeline_complete: bool = Field(..., description="trace 是否同时含 report 与 reflection")
    mechanism_hit: bool = Field(..., description="expects_debate 与实际是否触发 debate 一致")

    # 质量指标（来自 judge.judge_report）
    root_cause_score: float = Field(..., ge=0.0, le=1.0)
    key_points_recall: float = Field(..., ge=0.0, le=1.0)
    key_points_hit: list[str] = Field(default_factory=list)
    judge_is_stub: bool = Field(..., description="judge_report 是否走 mock_stub 路径")

    # 留痕
    report_text: str = ""
    error: str = ""

    @classmethod
    def from_run_result(cls, case: EvalCase, run_result: dict[str, Any]) -> "CaseResult":
        """把 runner.run_case() 的返回字典 + 对应 EvalCase 拼成 CaseResult"""
        deterministic = run_result["deterministic"]
        judge = run_result["judge"]
        return cls(
            case_id=run_result["case_id"],
            domain=case.domain,
            difficulty=case.difficulty,
            actual_strategy=deterministic["actual_strategy"],
            route_hit=deterministic["route_hit"],
            target_hit=deterministic["target_hit"],
            pipeline_complete=deterministic["pipeline_complete"],
            mechanism_hit=deterministic["mechanism_hit"],
            root_cause_score=judge["root_cause_score"],
            key_points_recall=judge["key_points_recall"],
            key_points_hit=judge["key_points_hit"],
            judge_is_stub=judge["method"] == "mock_stub",
            report_text=run_result.get("report", ""),
            error=run_result.get("error", ""),
        )


class DomainStats(BaseModel):
    """按域 / 按难度切片的聚合统计"""

    count: int
    route_hit_rate: float
    mean_root_cause_score: float
    mean_key_points_recall: float


class EvalSummary(BaseModel):
    """整批汇总"""

    config_hash: str = Field(..., description="被测配置指纹，复现关键")
    total: int
    route_hit_rate: float
    target_hit_rate: float
    pipeline_complete_rate: float
    mechanism_hit_rate: float
    mean_root_cause_score: float
    mean_key_points_recall: float
    judge_is_stub: bool = Field(..., description="整批是否 stub judge（真 LLM 时应为 False）")
    error_count: int = Field(0, description="跑批过程中异常兜底的用例数")
    by_domain: dict[str, DomainStats] = Field(default_factory=dict)
    by_difficulty: dict[str, DomainStats] = Field(default_factory=dict)


def build_summary(config_hash: str, results: list[CaseResult]) -> EvalSummary:
    """从一批 CaseResult 聚合出 EvalSummary。"""

    def _stats(subset: list[CaseResult]) -> DomainStats:
        n = len(subset)
        if n == 0:
            return DomainStats(count=0, route_hit_rate=0.0, mean_root_cause_score=0.0, mean_key_points_recall=0.0)
        return DomainStats(
            count=n,
            route_hit_rate=sum(r.route_hit for r in subset) / n,
            mean_root_cause_score=sum(r.root_cause_score for r in subset) / n,
            mean_key_points_recall=sum(r.key_points_recall for r in subset) / n,
        )

    total = len(results)
    by_domain: dict[str, DomainStats] = {}
    by_difficulty: dict[str, DomainStats] = {}

    for domain in sorted({r.domain for r in results}):
        by_domain[domain] = _stats([r for r in results if r.domain == domain])
    for difficulty in sorted({r.difficulty for r in results}):
        by_difficulty[difficulty] = _stats([r for r in results if r.difficulty == difficulty])

    return EvalSummary(
        config_hash=config_hash,
        total=total,
        route_hit_rate=sum(r.route_hit for r in results) / total if total else 0.0,
        target_hit_rate=sum(r.target_hit for r in results) / total if total else 0.0,
        pipeline_complete_rate=sum(r.pipeline_complete for r in results) / total if total else 0.0,
        mechanism_hit_rate=sum(r.mechanism_hit for r in results) / total if total else 0.0,
        mean_root_cause_score=sum(r.root_cause_score for r in results) / total if total else 0.0,
        mean_key_points_recall=sum(r.key_points_recall for r in results) / total if total else 0.0,
        judge_is_stub=all(r.judge_is_stub for r in results) if results else True,
        error_count=sum(1 for r in results if r.error),
        by_domain=by_domain,
        by_difficulty=by_difficulty,
    )
