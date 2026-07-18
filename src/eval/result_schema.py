"""评测结果契约 —— 单条 CaseResult 与批次 EvalSummary。"""

from typing import Any

from pydantic import BaseModel, Field

from data.eval.schema import EvalCase


class CaseResult(BaseModel):
    """单条用例的扁平评测结果。"""

    case_id: str
    domain: str
    difficulty: str
    actual_strategy: str = Field(..., description="trace 实际策略")
    route_hit: bool
    target_hit: bool
    pipeline_complete: bool
    mechanism_hit: bool
    condition_complete: bool = Field(..., description="按实验条件解释的完成率")
    root_cause_score: float = Field(..., ge=0.0, le=1.0)
    key_points_recall: float = Field(..., ge=0.0, le=1.0)
    key_points_hit: list[str] = Field(default_factory=list)
    judge_is_stub: bool
    latency_ms: float = Field(..., ge=0.0, description="诊断至 Judge 完成的端到端耗时")
    report_text: str = ""
    error: str = ""

    @classmethod
    def from_run_result(cls, case: EvalCase, run_result: dict[str, Any]) -> "CaseResult":
        """将 Runner 嵌套结果与 EvalCase 拼接为可落盘契约。"""
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
            condition_complete=deterministic["condition_complete"],
            root_cause_score=judge["root_cause_score"],
            key_points_recall=judge["key_points_recall"],
            key_points_hit=judge["key_points_hit"],
            judge_is_stub=judge["method"] == "mock_stub",
            latency_ms=run_result["latency_ms"],
            report_text=run_result.get("report", ""),
            error=run_result.get("error", ""),
        )


class DomainStats(BaseModel):
    """按 domain 或 difficulty 切片的聚合指标。"""

    count: int
    route_hit_rate: float
    condition_complete_rate: float
    mean_root_cause_score: float
    mean_key_points_recall: float
    mean_latency_ms: float


class EvalSummary(BaseModel):
    """一批用例的聚合评测结果。"""

    config_hash: str
    total: int
    route_hit_rate: float
    target_hit_rate: float
    pipeline_complete_rate: float
    mechanism_hit_rate: float
    condition_complete_rate: float
    mean_root_cause_score: float
    mean_key_points_recall: float
    mean_latency_ms: float
    judge_is_stub: bool
    error_count: int = 0
    by_domain: dict[str, DomainStats] = Field(default_factory=dict)
    by_difficulty: dict[str, DomainStats] = Field(default_factory=dict)


def build_summary(config_hash: str, results: list[CaseResult]) -> EvalSummary:
    """将 CaseResult 聚合为全局、领域和难度切片汇总。"""

    def _stats(subset: list[CaseResult]) -> DomainStats:
        count = len(subset)
        if count == 0:
            return DomainStats(
                count=0,
                route_hit_rate=0.0,
                condition_complete_rate=0.0,
                mean_root_cause_score=0.0,
                mean_key_points_recall=0.0,
                mean_latency_ms=0.0,
            )
        return DomainStats(
            count=count,
            route_hit_rate=sum(result.route_hit for result in subset) / count,
            condition_complete_rate=sum(result.condition_complete for result in subset) / count,
            mean_root_cause_score=sum(result.root_cause_score for result in subset) / count,
            mean_key_points_recall=sum(result.key_points_recall for result in subset) / count,
            mean_latency_ms=sum(result.latency_ms for result in subset) / count,
        )

    total = len(results)
    by_domain = {
        domain: _stats([result for result in results if result.domain == domain])
        for domain in sorted({result.domain for result in results})
    }
    by_difficulty = {
        difficulty: _stats([result for result in results if result.difficulty == difficulty])
        for difficulty in sorted({result.difficulty for result in results})
    }
    return EvalSummary(
        config_hash=config_hash,
        total=total,
        route_hit_rate=sum(result.route_hit for result in results) / total if total else 0.0,
        target_hit_rate=sum(result.target_hit for result in results) / total if total else 0.0,
        pipeline_complete_rate=sum(result.pipeline_complete for result in results) / total if total else 0.0,
        mechanism_hit_rate=sum(result.mechanism_hit for result in results) / total if total else 0.0,
        condition_complete_rate=sum(result.condition_complete for result in results) / total if total else 0.0,
        mean_root_cause_score=sum(result.root_cause_score for result in results) / total if total else 0.0,
        mean_key_points_recall=sum(result.key_points_recall for result in results) / total if total else 0.0,
        mean_latency_ms=sum(result.latency_ms for result in results) / total if total else 0.0,
        judge_is_stub=all(result.judge_is_stub for result in results) if results else True,
        error_count=sum(1 for result in results if result.error),
        by_domain=by_domain,
        by_difficulty=by_difficulty,
    )
