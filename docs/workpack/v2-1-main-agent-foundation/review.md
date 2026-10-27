# V2-1-main-agent-foundation · 独立审查记录

> 结论：**PASS**（P0 = 0，P1 = 0）
> 审查方式：只读子代理独立审查（不修改文件；未替代执行方跑测试）
> 审查范围：worktree `D:/market-handsome/oper-mind-worktrees/v2-1-main-agent-foundation` 相对 `main` 的全部改动（代码、测试、Design、Workpack）
> 复审轮次：2 轮（首轮 FAIL：1 个 P1；修复后复审 PASS；P2 加固后再确认"无新增 P0/P1"）

## 1. 首轮结论（FAIL）

- 发现 **P1 × 1，P0 × 0**：
  - `backend/src/api/v1/resources.py` 的能力归属投影对来自事件 JSON 的 `decision`／`status`／`capability_kind`／`outcome` 直接做 set 成员判断，未先校验标量类型。损坏行出现 `list`／`dict` 值时抛 `TypeError: unhashable type`，会让 Run 详情、会话 Run 列表、全局 Run 列表返回 500，违反"损坏事件只标记 unavailable"的约定。
- 同时记录多条 P2（`absent` 语义、终态校验、固定 `note`、前端知识徽标/来源、实时能力条、`steps=null` 文案、夹具 `skill_id`、真实 SkillSource 测试、plan 文件清单等）。

## 2. 修复与复审（PASS）

| 首轮问题 | 修复 |
|---|---|
| P1：非标量事件字段导致 500 | `resources.py` 对 `decision/status/capability_kind/outcome` 增加 `isinstance(str)` 守卫；新增参数化测试 `test_non_scalar_capability_event_fields_fail_closed`，覆盖 `decision/status/capability_kind/outcome` 的 list/dict，并断言详情、会话列表、全局列表均返回 200 且投影为 `unavailable` |
| `absent` 语义相反 | 无 `used`／`degraded` 时返回 `absent`；直答测试同步修正 |
| 非终态能力归属 | `routes.py` 按 `_TERMINAL_RUN_STATUSES` 传入 `terminal`；非终态不投影；`schemas.py` 增加"非终态不得携带能力字段"和"明细/状态成对"约束及测试 |
| `note` 契约过宽 | `MainKnowledgeGroundingResource.note` 改为固定 `Literal` |
| 前端缺知识徽标/来源 | `MainDeliveryPanel` 增加固定徽标与"来源：内置只读排查手册 …（未检索、未联网）"，有测试 |
| `steps=null` 未文案化 | 能力条显示"步骤未知" |
| 实时态无能力条 | 新增 `read_live_main_capabilities`，Workbench 实时态由事件流驱动能力条，含 reader 与 UI 测试 |
| 夹具 `skill_id` 错误 | 改为真实值 `ops.readonly_playbook` |
| 真实 SkillSource 缺测试 | 补 missing／too_large／digest_mismatch／empty/OSError／success 六类测试 |
| plan 文件清单失真 | 对齐实际改动文件 |

复审结论：原 P1 已关闭，未发现新增 P0/P1；仅保留 P2 与已知边界。P2 加固（实时 reader 对 `failed`/`budget_exhausted` 的语义、`step <= 6`、失败/取消夹具形状、`_safe_event_data` 标量守卫）完成后，复审再次确认：**无新增 P0/P1**。

## 3. 复审 AC 结论

| AC | 复审结论 | 说明 |
|---|---|---|
| AC1–AC2 | 通过 | 注册表/版本激活/类型不符；知识装载与两步回答 |
| AC3 | 通过（P2 残余） | 固定标注、徽标、来源与禁词断言齐全；模型正文本身无运行时禁词过滤，仅靠 Prompt 约束（已知边界） |
| AC4–AC9 | 通过 | 降级、比较复算、预算、取消、非法决策零工具执行 |
| AC10 | **通过（按 PR #140 澄清后的 AC10）** | 模型输入/观察、Run 列表、事件、导出、Trace、审计、usage 与日志不含材料原文；Run 详情仅返回当前 Run 的冻结输入（用户自己提供的材料），用于回看本次输入，不进入上述其他面 |
| AC11–AC16 | 通过 | 交付可区分、能力展示、取消、重跑/版本、V1 回归、加法字段 |
| AC17 | 存疑 | 测试全部使用脚本客户端/临时 SQLite，无真实外部依赖；但无 V2 专项"mock 标注"断言，沿用 V2-0 顶栏 |
| AC18–AC20 | 通过 | 无迁移、无新依赖、无子 Agent/多 Agent/真实连接 |

## 4. 剩余 P2 / 已知边界

1. 实时能力条无法校验 `capability_id/version` 是否在注册表中：前端按 Design 不持有能力目录；依赖服务端事件写路径白名单。
2. AC3 的动态回答正文没有运行时禁词过滤：Design 只要求固定标注与前端禁词断言，不新增正文过滤策略。
4. 无 HTTP 级"非终态 main_agent Run"用例：代码路径已核对，非终态返回能力字段全 null。
5. `application/run_execution.py` 复核知识接地使用 `CapabilityQuery.get`，会接受"已注册但未激活"的版本；执行器不会产生该状态，属纵深防御残余。
6. 非终态 Run 若数据库中存在损坏的 delivery 行，仍会触发既有"非成功不得携带交付"校验而 500；该路径非本次引入。
7. AC17 的 mock 标注：V2-1 未新增专项 UI 断言，沿用既有 TopBar 与服务端 `mode` 事件字段。

## 5. 审查执行的只读检查

- `git status --short`、`git diff --stat`、`git diff --check`：确认改动面未越界（无 V1 Coordinator、迁移、依赖变更）。
- 逐文件核对后端能力/内核/执行器/服务/API/测试与前端 readers/Panel/Strip/Workbench/Trace/Composer。
- 未执行 pytest／ruff／mypy／typecheck／build（会写缓存或数据库）；最终命令结果由执行方运行并记录在 [evidence.md](evidence.md)。
