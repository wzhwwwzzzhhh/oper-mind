# V2 主 Agent 闭环 · 独立代码 Review

> 状态：已执行三轮。第 1 轮 FAIL（2×P1／4×P2）→ 修复；第 2 轮 FAIL（1×新 P1／3×P2）→ 修复其中 1×P1 与 1×P2；第 3 轮针对增量 **PASS**（0×P0／0×P1，2×P3）。
> 记法说明：`N×Px` 读作「该轮发现 P 级问题 N 条」，是条数不是编号；表内 `P1-1`／`P2-3` 才是同一轮内的序号，跨轮不复用（第 2 轮的 P1-1 是新问题，与第 1 轮 P1-1 无关）。「遗留」按问题身份计数，与轮次条数无关。
> 遗留 2 项 P2 属公开契约变更（错误码分类、损坏行的降级投影），按门禁交用户裁决，不在实现层自行发明。
> 本文件不复用[架构 Review PASS](Design-Review.md)冒充代码通过。

## 审查对象

- 工作区：`oper-mind-worktrees/v2-main-agent-capability-loop`，分支 `feat/v2-main-agent-capability-loop`，base `6706caa`（origin/main）。
- 差异：37 个已跟踪文件（+1963／−188）＋ 23 个未跟踪新文件（V2 内核、能力、迁移、测试、本工作包文档）。
- 基线：`PRD.md`（AC1–AC20）、`Design.md`（§2.3 输入、§2.4 内核、§2.6 能力、§2.8 资源投影、§2.9 录入契约）、`Workpack-计划.md`、`docs/事实源/开发规范.md`、仓库根 `AGENTS.md`。
- 方式：只读子代理独立审查（读 diff 与文档，不写文件、不改代码），主代理落盘结论。

## 第 1 轮发现与处置（结论 FAIL）

| 级别 | 发现 | 处置 |
|---|---|---|
| P1-1 | 会话 Run 摘要列表同时返回交付与冻结输入，A/B 原文出现在列表响应里，违反 Design §2.8「全局／会话摘要列表不带 A/B 原文」；是我以「AC19 刷新可省一次详情请求」为理由做出的、与已确认 Design 冲突的产品决定 | 已修：`routes.py:465` `_main_projection(with_snapshot=…)`，详情 `True`（`routes.py:490`）、列表 `False`（`routes.py:1459`）；前端 `MainAgentReply` 在成功态缺快照时懒读 `GET /runs/{id}`；测试断言反转并新增列表 `input_snapshot is None` 断言 |
| P1-2 | `validate_terminal_payload` 漏「非成功 Run 不得携带 `result`／`delivery`」 | 已修，新增 `test_run_resource_rejects_inconsistent_projection`（6 项拒绝＋1 项合法） |
| P2-1 | 同处删掉了历史口径「失败必须有安全错误、非终态不得携带安全错误」 | 已恢复在同一校验器内 |
| P2-2 | 交付／冻结输入行损坏时抛 `MainAgentDeliveryUnavailableError` → Run 详情乃至会话列表 500 | 保留（见「遗留」） |
| P2-3 | 会话导出对 V2 失败 Run 仍写「诊断执行失败」，注释还声称与 `resources` 同口径 | 已修：`session_export.py:47` 按 `runtime_kind` 取 `RunFailureCode.safe_message` 白名单 |
| P2-4 | `text_a`／`text_b` 无 schema 级上限，超大 body 要进领域层才被拒 | 已修：`max_length=MAX_MATERIAL_CODEPOINTS`，`test_limit_error_does_not_echo_material_text` 加零写入断言 |
| P3 | 注释与命名、错误文案措辞（「无对应行」vs PRD「无对应片段」）、行号引用过期若干处 | 部分随手修正，其余未动 |

## 第 2 轮发现与处置（结论 FAIL）

第 1 轮 5 项修复经复审确认全部真实落地（含「Pydantic v2 `max_length` 按 Unicode 码点计数，与 `MAX_MATERIAL_CODEPOINTS` 同语义，不存在 UTF-16 偏差」「导出白名单覆盖全部 5 个 `RunFailureCode`」）。新问题：

| 级别 | 发现 | 处置 |
|---|---|---|
| P1-1（新） | Design §2.9 要求「提供／未提供可独立切换，支持显式空文本」，但 `MainAgentComposer` 把留空一律塌缩为 `null`，**显式空文本在产品入口不可达**；AC5「双方显式为空」只有内核证据（`test_identical_and_explicit_empty_texts_have_no_difference`），公开链无任何提交 `text_a:""` 的用例；`Workpack-计划.md` 的勾选与代码相悖 | 已修：每侧独立复选框 `提供文本 A`／`提供文本 B`（`MainAgentComposer.tsx:91`、`:110`），未勾选提交 `null`、勾选后原样提交（含空串），未勾选侧 textarea `disabled`；新增前端用例与后端公开链 `test_main_agent_explicit_empty_materials_report_no_difference` |
| P2（新） | 导出白名单的 V2 分支无失败用例覆盖 | 已补：`test_session_export_uses_main_agent_safe_error_for_failed_run` |
| P2（新，保留） | `_failure_code()`（`run_executor.py:169`）把 `MODEL_UNAVAILABLE`／`MODEL_DECISION_INVALID`／`TOOL_FAILED` 一律收敛为 `MAIN_AGENT_FAILED`，与 AC11「显示相应安全失败／不可用」有差距 | 保留（见「遗留」） |
| P2（新） | 一条损坏／未知版本行可让会话列表整体 500；复审认为 Design §2.8「未知 kind／版本报安全不可用，不猜测」其实已要求映射为安全不可用投影，即第 1 轮 P2-2 的「需要新契约」理由只半成立 | 保留（见「遗留」），并如实记入 `Workpack-证据.md` 已知边界 |
| P3 | 列表逐行读交付的 N+1；码点计数只在错误文案里提示、无实时计数；`max_length` 在 `strip()` 前计数；`LegacyDiagnosisRunAdapter` 命名误导；V2 新模块零日志（失败不可观测） | 未改，记入待办 |

另外纠正了 `Workpack-证据.md` 中与代码不符的表述：AC3／AC4 标成「公开链」实为混合（运维词汇、无效决策只有内核用例）；AC10／AC16 只有内核；AC13 用量半边无证据；「5 个 ValidationError」实为 6 个。

## 第 3 轮（增量复审，结论 PASS）

只审第 2 轮 P1 修复的增量：`MainAgentComposer.tsx` 的提供／未提供开关、`main-agent.test.tsx` 新用例、两个新后端测试。结论 0×P0／0×P1／2×P3：

- 提交后草稿与勾选态不复位（只清 `query`）判为可接受：§2.9 禁的是「不从上一次 Run 自动借用材料」，可见草稿框不构成自动重放；记为 P3 备忘。
- 外层 `<label>` 同时包裹 checkbox 与 textarea 两个 labelable 控件，标签归属不严格；两侧都有显式 `aria-label`，不影响可访问名解析。P3。
- 两项新测试确认「名副其实」：空材料用 `MainMockScenario.COMPARE` 是正确替身（双 refs 存在才走能力调用），导出用例 `scenario=None` 命中 `MODEL_UNAVAILABLE → MAIN_AGENT_FAILED` 的封闭失败路径，无重名、无顺序依赖。

## AC 证据表（三轮合并，链＝公开 HTTP／界面／内核）

| AC | 关键证据 | 判定 |
|---|---|---|
| AC1 | `test_main_agent_answer_request_delivers_plain_answer`；浏览器 answer／compare 分派 | 公开链 PASS（片段） |
| AC2 | `test_main_agent_missing_material_asks_for_input`；浏览器 `needs_input` | 公开链＋界面 PASS（片段） |
| AC3 | 公开链只证明「不继承服务、走文本能力」；「含运维词汇仍走文本」只有内核 `test_executor_mock_answer_ignores_comparison_and_ops_wording` | 混合，部分仅内核 |
| AC4 | 公开链 `test_main_agent_request_rejects_service_id_and_unknown_field`；失败关闭只有内核 `test_model_adapter_rejects_invalid_json_or_schema`、`test_decision_cannot_smuggle_a_tool_outside_the_gateway`、`test_agent_fails_when_declared_tool_is_not_registered` | 混合，部分仅内核 |
| AC5 | 新增公开链 `test_main_agent_explicit_empty_materials_report_no_difference` ＋ 前端开关用例 ＋ 浏览器「逐行一致｜差异块 0 个」实测 ＋ 内核 `test_identical_and_explicit_empty_texts_have_no_difference` | 公开链＋界面 PASS（片段） |
| AC6–AC8 | `test_main_agent_comparison_delivery_uses_real_deterministic_tool`、浏览器真实 `difflib` 块、内核 added／deleted／modified 与换行／重复行用例 | PASS（片段） |
| AC9 | `test_limit_error_does_not_echo_material_text`（含零写入）、浏览器真实 422、前端码点提示 | PASS（片段） |
| AC10 | 内核 `test_comparison_delivery_is_rejected_unless_blocks_recompute_exactly`；前端 readers 行号倒挂拒绝 | 片段（服务端重算仅内核） |
| AC11 | `test_model_failure_is_reported_as_safe_unavailable`、浏览器失败态；真实 Provider 未测；失败码分类保真待裁决 | 部分 PASS，保留 P2 |
| AC12 | 浏览器事件计数（比较 4 事件 1 工具、追问 3 事件 0 工具）；预算上限只有内核 `test_main_agent_task_rejects_budget_above_hard_caps` | 混合 |
| AC13 | 顶栏「未配置 · 演示」，mock 不写 usage；`tests/` 对 main_agent 无 usage 断言 | 用量半边无证据 |
| AC14 | `test_rerun_main_agent_run_copies_frozen_input`、`test_accept_main_agent_run_freezes_input_and_replays_same_key`、`test_cancel_terminated_main_agent_run_returns_409`；「同键不同输入冲突」公开链无 V2 用例 | PASS（部分仅内核） |
| AC15 | 内核 `test_cancel_winning_a_concurrent_run_leaves_no_late_delivery` 等；浏览器未计时验证 | 未新增界面证据 |
| AC16 | 内核 `test_guard_run_stream_requires_single_terminal_at_normal_eof`、`test_guard_run_stream_maps_exceptions_to_closed_codes` | 仅内核 |
| AC17 | `test_sensitive_input_is_rejected_before_any_write` ＋浏览器真实 422 零写入 | PASS（片段） |
| AC18 | `test_events_sse_and_lists_do_not_carry_material_text`、两个导出用例、浏览器泄露探测；Trace／审计对 V2 无逐项断言 | 片段，审计无断言 |
| AC19 | 刷新恢复实测（列表带交付＋1 次 `GET /runs/{id}` 补输入、无第二次受理、`localStorage` 为空）；SSE 断线重连无用例 | 界面片段 |
| AC20 | 后端全量、前端全量串行、V1 默认录入保留 | 片段 |

**整条 AC 的验收判定留到最终交付门**；本表只说明「片段是否属实、缺口在哪」，不据此宣称首闭环交付。

## V2-0 收口裁决（2026-10-26）

三项遗留已由用户拍板并实现：

1. **失败码保真**：拆为 `MAIN_AGENT_MODEL_UNAVAILABLE`、`MAIN_AGENT_DECISION_INVALID`、`MAIN_AGENT_CAPABILITY_UNAVAILABLE`、`MAIN_AGENT_TOOL_FAILED`，保留 `MAIN_AGENT_FAILED` 兜底。内部封闭失败一一映射，安全文案由 `RunFailureCode.safe_message` 唯一提供。
2. **损坏行投影**：交付／冻结输入读取失败不再抛 500。列表和详情返回 `main_delivery_status` / `main_input_status`（`available` / `unavailable` / `absent`）；损坏行只标记 `unavailable`，不带原文或原始异常，一条坏行不再拖垮会话列表。
3. **默认入口**：V2-0 期间保持 V1 服务调查默认，V2 显式切换；等 V2-2 首批只读调查达到对等并经用户确认后再切默认。

增量验证见 [Workpack-证据](Workpack-证据.md)「V2-0 收口验证」。本轮为收口增量，未重新派独立子代理审查；既有三轮独立审查结论只覆盖其审查时的差异。

## 验证与提交状态

三轮修复后的验证记录（命令与原始输出）见 [Workpack-证据.md](Workpack-证据.md) 的「实施-3 · 命令与结果」章节。V2-0 收口增量验证见同文件「V2-0 收口验证」；提交与 PR 状态以远端记录为准。
