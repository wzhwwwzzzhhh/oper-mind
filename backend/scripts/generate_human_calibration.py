"""M4 人工抽检样本生成器 —— 逐条落盘，支持中断后续跑。"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from scripts._bootstrap import DATA_DIR, EXPERIMENTS_DIR
except ModuleNotFoundError:
    from _bootstrap import DATA_DIR, EXPERIMENTS_DIR

from data.eval.validate import load_cases
from src.core.bootstrap import build_judge_llm, build_system
from src.core.experiment import get_experiment_condition
from src.eval.runner import run_case


SAMPLE_IDS = (
    "db-001", "db-003", "db-014",
    "server-001", "server-006", "server-013",
    "log-001", "log-005", "log-011",
    "parallel-002", "chain-001", "parallel-005",
)


def _write_json(path: Path, payload: Any) -> None:
    """原子写入 JSON，避免中断时留下半文件。"""
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temp_path.replace(path)


def _record_path(records_dir: Path, sample_no: int, case_id: str) -> Path:
    """返回样本记录的稳定文件路径。"""
    return records_dir / f"{sample_no:02d}-{case_id}.json"


def _build_blind_review(records: list[dict[str, Any]]) -> str:
    """构建不含 Judge 结论的人工盲审 Markdown。"""
    lines = [
        "# M4 人工抽检盲审表",
        "",
        "> 请独立阅读每条诊断报告，并标出报告明确覆盖的 Golden 关键点编号。",
        "> 在“人工命中 ID”填写 `KP1, KP3`；没有明确命中请填写 `无`。",
        "> 不需要评估根因分数；不要根据 Golden 文本推测报告未写出的内容。",
        "",
    ]
    for record in records:
        lines.extend([
            f"## 样本 {record['sample_no']}：{record['case_id']}",
            "",
            f"- 领域：{record['domain']}",
            f"- 难度：{record['difficulty']}",
            f"- 问题：{record['query']}",
            "",
            "### Golden 关键点（仅用于编号标注）",
            *[
                f"- KP{index}: {point}"
                for index, point in enumerate(record["golden_key_points"], start=1)
            ],
            "",
            "### 诊断报告",
            record["report"] or "【报告为空】",
            "",
            "### 人工标注",
            "- 人工命中 ID：",
            "- 备注：",
            "",
            "---",
            "",
        ])
    return "\n".join(lines)


def _load_completed_records(records_dir: Path) -> list[dict[str, Any]]:
    """读取已落盘样本，供断点续跑与盲审表重建。"""
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(records_dir.glob("*.json"))
    ]


def _write_artifacts(output_dir: Path, records: list[dict[str, Any]]) -> None:
    """每完成一条样本后重建盲审表与 Judge 内部对照文件。"""
    records.sort(key=lambda record: record["sample_no"])
    (output_dir / "blind_review.md").write_text(
        _build_blind_review(records),
        encoding="utf-8",
    )
    _write_json(output_dir / "judge_reference.json", records)


def generate(output_dir: Path) -> None:
    """生成或续跑 12 条真实人工抽检样本。"""
    cases, errors = load_cases(str(DATA_DIR / "eval" / "cases.jsonl"))
    if errors:
        raise RuntimeError(f"评测数据加载失败：{errors}")
    case_by_id = {case.case_id: case for case in cases}
    missing_ids = set(SAMPLE_IDS) - set(case_by_id)
    if missing_ids:
        raise RuntimeError(f"抽检样本不存在：{sorted(missing_ids)}")

    output_dir.mkdir(parents=True, exist_ok=True)
    records_dir = output_dir / "records"
    records_dir.mkdir(exist_ok=True)
    manifest_path = output_dir / "manifest.json"
    if not manifest_path.exists():
        judge_llm_for_manifest = build_judge_llm()
        coordinator_for_manifest = build_system(
            enable_long_term_memory=False,
            experiment_condition=get_experiment_condition("full"),
        )
        _write_json(
            manifest_path,
            {
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "arm": "full",
                "sample_ids": list(SAMPLE_IDS),
                "diagnosis_model": coordinator_for_manifest.llm.model,
                "judge_model": judge_llm_for_manifest.model,
                "selection": "db/server/log/compound 各 3 条，每个领域覆盖 easy/medium/hard。",
                "blind_review_file": "blind_review.md",
                "judge_reference_file": "judge_reference.json",
            },
        )

    judge_llm = build_judge_llm()
    completed = _load_completed_records(records_dir)
    completed_ids = {record["case_id"] for record in completed}
    _write_artifacts(output_dir, completed)

    for sample_no, case_id in enumerate(SAMPLE_IDS, start=1):
        if case_id in completed_ids:
            print(f"[skip] 样本 {sample_no:02d} {case_id} 已完成")
            continue

        case = case_by_id[case_id]
        coordinator = build_system(
            enable_long_term_memory=False,
            experiment_condition=get_experiment_condition("full"),
        )
        result = run_case(coordinator, judge_llm, case)
        record = {
            "sample_no": sample_no,
            "case_id": case.case_id,
            "domain": case.domain,
            "difficulty": case.difficulty,
            "query": case.query,
            "golden_root_cause": case.golden_root_cause,
            "golden_key_points": case.golden_key_points,
            "report": result["report"],
            "trace_nodes": [event["node"] for event in coordinator.get_trace()],
            "latency_ms": result["latency_ms"],
            "run_error": result.get("error", ""),
            "judge": result["judge"],
        }
        _write_json(_record_path(records_dir, sample_no, case_id), record)
        completed.append(record)
        completed_ids.add(case_id)
        _write_artifacts(output_dir, completed)
        print(
            {
                "saved": f"{sample_no:02d}-{case_id}",
                "judge_method": result["judge"]["method"],
                "run_error": result.get("error", ""),
            }
        )

    print(
        json.dumps(
            {
                "output_dir": str(output_dir),
                "completed": len(completed),
                "blind_review": str(output_dir / "blind_review.md"),
            },
            ensure_ascii=False,
        )
    )


def main() -> None:
    """解析输出目录并启动可续跑抽检生成。"""
    parser = argparse.ArgumentParser(description="生成可续跑的 M4 人工抽检样本")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=EXPERIMENTS_DIR / "m4-human-calibration",
        help="抽检产物目录；重复运行会跳过已完成样本。",
    )
    args = parser.parse_args()
    generate(args.output_dir)


if __name__ == "__main__":
    main()
