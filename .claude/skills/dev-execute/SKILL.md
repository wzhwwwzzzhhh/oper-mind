---
name: dev-execute
description: Use when implementing a confirmed workpack plan against an OperMind PRD — developing in slices, running tests, invoking an independent readonly sub-agent review, and committing with evidence. Trigger on "开发", "实现", "写代码", "跑测试", "自审", "独立审查", "按计划开发", "提交". It is Phase 3-5 of the dev workflow, called after dev-plan has a user-confirmed plan.md.
---

# 工作包执行（OperMind 项目专属）

## 核心原则
按 `plan.md` 逐切片开发，先测试后实现；完成后**独立子代理只读审查**产生 P0–P3 分级结论与 AC 证据表；未通过不回改则不得提交。
证据先于断言：没有测试输出、`git diff --check` 结果，不宣称"做完了"。

## 前置要求
- `docs/workpack/<阶段>-<切片>/plan.md` 必须存在且已被用户确认；无确认回 `dev-plan`。
- 当前分支必须是该工作包专用分支，且分支名与 `plan.md` 记录一致；否则停止并回 `dev-plan`。
- 若工作区在开工前已有其他改动，必须存在隔离清单；混合文件只能提交已核对的代码块，不能整文件盲目暂存。
- 基线：`docs/产品定义.md`、`docs/路线图.md`、`docs/开发规范.md`、当前 PRD。

## 执行流程

### Phase 3 开发（逐切片，S1 → S2 …）
1. 每一切片：**先补/改测试**（预期红），再实现业务代码（转绿），最后小步重构。测试框架以仓库实际为准（后端 pytest，前端 Vitest/jsdom + MSW）。
2. 跨层数据走 Pydantic 或 TypedDict，禁止隐式字典协议；Tool 继承 `Tool` 并实现受控 `execute`；Connector/Collector 经显式 Application port 或 Executor 注入。
3. 实现中每新增行为自问「对应哪条 PRD 需求/AC」；无法映射视为范围外，暂停回 `dev-plan`。
4. 禁止裸 `except`、新增生产 `print`；中文注释、中文用户可见日志；公开函数带类型标注。
5. 默认只读、最小权限、脱敏：凭据只走环境变量，不得进日志 / 数据库普通字段 / Trace / 事件 / 结果 / 截图 / 接口响应。

### Phase 4 子代理独立审查（必须）
1. 调用 **Task 工具 readonly 子代理**（explore 类型，只读 diff 与文档），输入：
   - `docs/workpack/<阶段>-<切片>/plan.md`
   - 当前 PRD 路径
   - 本次 `git diff`（工作区/暂存区）
   - 基线文档路径
2. 要求子代理输出 `review.md`：
   - 与 plan/PRD 的映射结论（漏项、越界、过度实现）
   - P0–P3 分级问题：
     - P0：安全红线（凭据泄露、写操作未经白名单、破坏性改动、mock 冒充真实）
     - P1：功能错误 / 漏 AC / 契约破坏 / 越界文件
     - P2：边界与降级缺失、可测性、错误处理
     - P3：风格、命名、注释
   - AC 证据表：逐条 AC → 代码/接口/测试证据 → PASS/FAIL
   - 结论：PASS / FAIL（P0/P1 存在即 FAIL）
3. 子代理**不得写文件、不得改代码**；产出内容由主 agent 落盘到 `review.md`。
4. 存在 P0/P1 → 回到 Phase 3 修复后再审；不得以"代码能跑"为由放行。
5. 非本技能环境无法派子代理时 → 如实写 `tooling_blocked` 并交用户，不得冒充 PASS。

### Phase 5 提交（审查 PASS 后）
1. 只暂存**本工作包**改动的文件；禁止无检查 `git add .`，不提交凭据/`.env`/`config.local.yaml`/`sk-` 内容。
2. 对混合文件逐段核对；必要时先生成补丁再应用，提交前检查 `git diff --cached` 只包含本工作包。
3. `git diff --check` 必须干净。
4. 提交信息 `git commit -m "<类型>: <中文描述>"`，一个切片一个提交；不直推 `main`。
5. 每切片完成后更新 `docs/workpack/<阶段>-<切片>/evidence.md`（AC 证据随提交推进）。
6. 记入 `evidence.md` 的验证记录：相关后端 pytest、前端 typecheck/test/build（如适用）、`git diff --check`。

## 关键纪律
1. **证据先于断言**：任何"完成"声明必须有测试输出 / 命令结果支撑。
2. **审查必须独立**：审查者与开发视角分离，P0/P1 一票否决。
3. **不越界**：只改工作包文件；发现需要动它处，停下说明。
4. **不伪装**：未启用能力如实标明；mock 不当真实执行或实时监控；一次快照不当历史监控。
5. **安全默认**：只读、最小权限、脱敏、超时、参数校验、审计摘要。

## 常见错误
| 错误 | 修正 |
|---|---|
| 没跑测试就宣称完成 | 先补正测试输出再断言 |
| 跳过子代理审查或伪造 PASS | 派 readonly 子代理，FAIL 即回改 |
| `git add .` 全量暂存 | 只暂存工作包文件 |
| 混合文件未经核对直接暂存 | 先审阅 staged diff，必要时按代码块隔离 |
| 不映射 AC 就加行为 | 每行为对应 PRD 需求/AC，不能映射即范围外 |
| P0/P1 被"能跑"豁免 | P0/P1 一票否决，回到 Phase 3 |

## 红灯（STOP）
- 无用户确认的 `plan.md`
- 当前分支不是工作包专用分支，或混合工作区没有逐文件/逐代码块隔离清单
- 凭据 / DSN / 原始 SQL / CoT 进日志、Trace、响应、截图或文档
- 新增未经确认的公开接口、迁移、Connector、真实外部访问或高风险动作
- P0/P1 未修复或越界
- 相关测试未跑绿（或未如实标注未跑）

**发现任一红灯 ⇒ 停在当前切片，修复或取得用户确认前不提交。**
