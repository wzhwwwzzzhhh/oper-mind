# V2-1-main-agent-foundation · 验收证据

> 状态：实现、自测与独立审查完成（审查 PASS，P0/P1=0）；PR [#139](https://github.com/wzhwwwzzzhhh/oper-mind/pull/139) 已合并（442c32e）；用户验收：2026-10-27 本地 mock 两条路径界面冒烟通过。
> 环境：worktree `D:/market-handsome/oper-mind-worktrees/v2-1-main-agent-foundation`，分支 `feat/v2-1-main-agent-foundation`，基线本地 `main` 548baa9。
> 原则：只记录实际执行过的命令与结果；未执行或未覆盖的项在「已知缺口」明确标注。

## 命令与结果

后端（worktree/backend，使用仓库根 `.venv`）：

| 命令 | 结果 |
|---|---|
| `python -m pytest tests/test_main_agent_runtime.py tests/test_main_agent_runs_api.py tests/test_runs_list.py tests/test_capability_contract.py -q` | `152 passed, 1 warning in 112.25s` |
| `python -m pytest tests -q` | `1052 passed, 5 warnings in 392.89s` |
| `python -m ruff check src tests` | `All checks passed!` |
| `python -m mypy src` | `Success: no issues found in 140 source files` |

前端（worktree/frontend）：

| 命令 | 结果 |
|---|---|
| `npm run typecheck` | 通过（`tsc --noEmit`，无输出错误） |
| `npm run test` | `Test Files 26 passed (26)`；`Tests 270 passed (270)` |
| `npm run build` | 通过（`tsc -b && vite build`；仅既有 chunk 体积提示） |

其他：

| 检查 | 结果 |
|---|---|
| `git diff --check` | 通过（仅 CRLF 提示，无空白错误） |
| 敏感字面量扫描（`sk-`、`password=`、带凭据 DSN） | 仅命中仓库既有测试假值与 `.gitleaks.toml` 白名单；新增生产代码无命中 |
| OpenAPI → `generated.ts` 一致性 | 从当前后端重新 dump + `openapi-typescript` 生成，`sha256sum -c` 一致（无手工漂移） |
| 数据库迁移 | 无（diff 不含 `backend/alembic/versions/*`） |

## AC 证据表

| AC | 结论 | 证据 |
|---|---|---|
| AC1 | 通过 | `test_capability_contract.py::test_registry_registers_explicit_versions_and_activates_highest`、`test_registry_duplicate_same_id_and_version_is_rejected`、`test_registry_rejects_kind_mismatch_without_leaking_definition`；`test_main_agent_runtime.py::test_kernel_rejects_slot_shape_and_unknown_capability`、`test_kind_mismatch_is_rejected_for_both_directions`、`test_executor_mock_unknown_capability_and_wrong_version_fail_closed` |
| AC2 | 通过 | `test_knowledge_load_then_answer_attaches_program_grounding`、`test_executor_mock_knowledge_loads_skill_and_answers_with_grounding`；API `test_main_agent_knowledge_answer_projects_grounding_and_message_prefix`（两次决策，无工具） |
| AC3 | 通过 | 后端固定前缀测试 `test_knowledge_answer_is_prefixed_and_persisted_with_grounding`；前端 `main-agent.test.tsx::知识辅助回答展示固定标注…`、`main-capability-strip.test.tsx::知识辅助回答只使用固定标注…`、`main-delivery.test.tsx::知识辅助回答显示固定徽标与内置来源…`（断言不出现「已校验/已读取/已诊断」） |
| AC4 | 通过 | `_UnavailableSkillSource` + `test_knowledge_degrade_continues_and_never_fakes_grounding`、`test_repeated_load_of_degraded_capability_fails_without_new_observation`、`test_executor_mock_knowledge_unavailable_is_degraded_then_answers`；真实来源 `test_builtin_skill_source_rejects_missing_content`/`…oversized…`/`…digest_mismatch`/`…empty_or_unreadable…`/`…returns_verified_managed_skill`；API `test_main_agent_degraded_knowledge_projects_unavailable_without_grounding`；前端降级投影与能力条用例 |
| AC5 | 通过 | `test_text_compare.py`（既有断言未改）、`test_text_compare_contract_migration_keeps_compatibility_surface`、`test_executor_mock_compare_runs_real_deterministic_tool`、`test_comparison_delivery_is_rejected_unless_blocks_recompute_exactly`；API `test_main_agent_comparison_delivery_uses_real_deterministic_tool` |
| AC6 | 通过 | 单一 `CapabilityRegistry.resolve()` + 统一决策/观察路径；契约测试与 `test_declaration_keeps_knowledge_and_execution_boundaries`；代码审查未发现按 `text.literal_compare` / `ops.readonly_playbook` 写死的主循环分支（工具绑定按声明解析） |
| AC7 | 通过 | `test_decision_budget_is_consumed_before_call_and_degrades_to_closed_failure`、`test_knowledge_load_budget_is_enforced_before_loading`、`test_tool_budget_is_consumed_before_call`；API `test_main_agent_budget_exhaustion_is_safe_terminal_failure`（`MAIN_AGENT_BUDGET_EXHAUSTED`，无部分交付） |
| AC8 | 通过 | `test_clipped_timeout_maps_to_budget_exhausted`、`test_fixed_cap_timeout_stays_tool_failed`、`test_budget_clips_blocking_call_to_remaining_wall_clock`；取消：`test_cancel_checked_after_model_call_discards_decision_without_tool`、`test_cancel_checked_after_tool_call_discards_result`、`test_cancel_before_decision_stops_without_any_model_call`、`test_cancel_during_model_call_discards_decision_and_leaves_no_late_writes`、`test_cancel_winning_a_concurrent_run_leaves_no_late_delivery`、`test_main_agent_event_after_cancel_is_discarded` |
| AC9 | 通过 | `test_model_adapter_rejects_invalid_json_or_schema`、`test_foreign_material_refs_are_rejected_without_tool_execution`、`test_same_material_on_both_sides_is_rejected_without_tool_execution`、`test_missing_tool_binding_fails_closed_without_gateway_call`、`test_needs_input_slots_must_match_actual_missing_side`；API 无效决策具体失败码测试 |
| AC10 | 通过（按 PR #140 澄清后的 AC10） | 模型输入/观察、Run 列表、事件、导出、Trace、审计、usage 与日志不含材料原文：`test_real_client_prompt_carries_material_ids_but_not_material_text`、`test_events_sse_and_lists_do_not_carry_material_text`、`test_limit_error_does_not_echo_material_text`、`test_session_export_uses_neutral_main_run_summary`；Run 详情仅返回当前 Run 的冻结输入（用户自己提供的材料），用于回看本次输入。`_safe_event_data` 白名单与 TraceCard 只渲染封闭摘要 |
| AC11 | 通过 | `test_delivery_discriminator_rejects_unknown_or_extra_fields`、`test_knowledge_grounding_is_fixed_and_round_trips_through_union`；前端 `main-delivery-readers.test.ts` 区分 answer/needs_input/comparison，知识标注结构不符即拒绝背书 |
| AC12 | 通过 | API `test_main_agent_projects_capability_usage_and_steps`、`test_openapi_exposes_capability_projection_without_catalog`、`test_corrupted_capability_event_projects_safe_unavailable`、`test_non_scalar_capability_event_fields_fail_closed`；前端 `main-capability-strip.test.tsx`（展示/空态/不可用/缺省/损坏/步骤未知）、`main-delivery-readers.test.ts`（实时事件投影）、`main-agent.test.tsx`（失败、取消、交付不可用终态、实时能力条）；`trace-card.test.tsx::主 Agent 决策与完成事件展示安全摘要…`（不含 CoT/Prompt/原始输出） |
| AC13 | 通过 | 上述四类取消测试 + `test_cancel_terminated_main_agent_run_returns_409`；前端 `main-agent.test.tsx::取消终态仍展示已有能力归属…`。取消粒度为 step 边界，模型调用中/工具等待中返回后的结果均丢弃 |
| AC14 | 通过 | `test_accept_main_agent_run_freezes_input_and_replays_same_key`、`test_main_agent_rerun_copies_frozen_input_with_new_material_ids`、`test_rerun_uses_version_active_at_rerun_time`、`test_inactive_old_version_is_rejected_even_after_new_version_registration`、`test_corrupt_or_unknown_run_input_fails_safe` |
| AC15 | 通过（自动回归） | `test_legacy_request_keeps_diagnosis_kind_and_result`、`test_legacy_adapter_preserves_query_and_service`；前端 `main-agent.test.tsx::默认仍是服务调查（V1）录入…`；后端全量 1042 项含既有 V1 套件。未做用户侧 48 项人工逐项点击复验 |
| AC16 | 通过 | `test_openapi_exposes_capability_projection_without_catalog`、`test_run_resource_requires_knowledge_to_match_delivery`、`test_摘要字段白名单…`（新增字段为加法）、`test_run_resource_rejects_inconsistent_projection`（终态/成对约束）；`generated.ts` 仅由 OpenAPI dump + `openapi-typescript` 重新生成；路由 diff 无新增端点 |
| AC17 | 通过（自动测试） | `test_mock_scenarios_are_explicit_and_not_inferred_from_query`；执行器 `mode = "mock"/"target"` 事件标注；所有新增测试使用 scripted client、临时 SQLite 与假 SkillSource，无真实模型/数据库/Redis/日志/外部网络 |
| AC18 | 通过 | 无数据库迁移；`run_deliveries.kind` CHECK 未改；仅新增应用层投影字段与事件 data 白名单 |
| AC19 | 通过 | 见「命令与结果」：后端全量、前端三件套、ruff、mypy、`git diff --check`、敏感扫描均通过 |
| AC20 | 通过（diff 审查） | 无新依赖、无子 Agent/多主 Agent/长期记忆/Recovery/RAG/MCP/真实外部连接；V1 默认入口与调查链未改；`core/react_graph.py`、`core/tool_gateway.py`、`core/tool_registry.py`、`core/llm.py` 未改 |

## 已知缺口 / 边界

1. **用户界面验收未执行**：PRD DoD 要求用户按界面完成知识排查回答与文本比较两条路径；本次只完成自动测试与构建，未代替用户做人工验收。
2. **回滚边界**：回滚到 V2-0 代码时，带 `knowledge_grounding` 的交付行会被旧代码判为 `unavailable`（安全不可用投影，不 500、不伪造）；比较与追问行不受影响。
3. **基线网络**：建立 worktree 时 `git fetch origin main` 网络失败，基线为本地 `main` 548baa9；推送/建 PR 前需重新 fetch + merge，并以最终 main 为准重跑检查。
4. **取消语义**：取消检查点在 step 边界；模型调用或工具等待进行中不会强杀线程，返回后丢弃结果、不写迟到交付。这是 Design 确认的粒度，不是"立即中断底层调用"。
5. **知识内容**：`ops.readonly_playbook@1` 是仓库内置静态 Skill，不读取实时指标、日志、SQL 或服务状态；界面固定标注"知识辅助回答 · 未读取实时数据"。
6. **输入契约**：V2-1 只支持 material slots（`text_a`/`text_b`）；服务/资源输入按设计留给 V2-2。
7. **敏感扫描**：命中项均为仓库既有测试假值与 `.gitleaks.toml` 白名单，无新增真实凭据；该项不是完整 secret 扫描器结论。
8. **独立审查**：[review.md](review.md) 结论 PASS（P0/P1=0）；首轮 P1（非标量事件导致 500）已修复并有参数化回归测试，复审确认关闭。
9. **动态正文禁词**：固定标注与前端禁词断言已覆盖；模型生成的回答正文本身没有运行时"已校验/已读取/已诊断"过滤，仅由系统提示约束（PR #140 已澄清该口径）。
10. **实时能力条边界**：前端不持有能力目录，无法校验事件中的 `capability_id/version` 是否已注册；依赖服务端 `_safe_event_data` 的 id 白名单与事件写路径。
11. **测试稳健性**：`main-agent.test.tsx` 首个整页用例在并发跑全量时曾出现 5 秒超时，已把该文件的两个整页用例超时提高到 20 秒；其余用例未改断言。
