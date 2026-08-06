---
name: arch-review
description: Use when a completed OperMind Design document (docs/*Design.md) needs independent review before it can gate development — checking the design against the product spine, the confirmed PRD, security boundaries, and architecture consistency, producing P0–P3 graded findings and a PASS/FAIL verdict. Trigger on "审Design", "审架构", "Design审查", "架构评审", "Design对不对", "架构审查". Do NOT use for writing the design (arch-design), PRD review (prd-reviewing), or code review (dev-execute Phase 4).
---

# 架构审查（OperMind 项目专属）

## 核心原则
审查不是审"设计写得好不好看"，而是审「**这份 Design 交出去，dev-plan 照着建会不会建出自毁 / 越界 / 破坏主脊的东西**」。回答的问题：这份 Design 能不能作为 `Design → Review → 用户确认` 闸门的依据。

**写审分离**：arch-design 写，arch-review 审，两个角色视角分离。审查者不得同时是设计者；除非独立子代理不可用且用户明确知情，否则不得冒充独立审查。

## 何时用
- Design 文档写完后、交给 dev-plan 前（独立子代理只读审查，必须）。
- 大阶段验收时，核对架构方案是否落地、有无漂移。
- 用户要求确认某架构"对不对 / 合不合主脊"时。

**不用**：PRD 审查（那是 `prd-reviewing`）；代码审查（那是 `dev-execute` Phase 4）；写 Design（那是 `arch-design`）。

## 前置要求
- 基线：`docs/产品定义.md`、`docs/路线图.md`、`docs/开发规范.md`、`docs/架构与开发路径.md`。
- 被审 Design：`docs/design/<域>/*Design.md`（或用户指定路径）。
- 关联的已确认 PRD：`docs/prd/<域>/`。
- 关键实现锚点：`backend/src/core/`（tool_gateway / graph / bootstrap / coordinator）、`backend/src/agents/`、`backend/src/tools/`。

## 审查维度（逐条过）

### A. 主脊对齐（第一层）
- [ ] 是否沿一条主脊（消息 → Run → 大脑 → 工具网关 → Connector → 证据 → 结果 → Trace → 提案/审批/执行/验证 → 留痕）？
- [ ] 新能力是否「能力即插件」（新 Tool + Connector 绑定 + 注册），而非新端点 / 新流程 / 新模式 / 新独立脚本/页面？
- [ ] 是否把 demo / 靶场 / 旧技术切片 / 报告页当产品能力设计？

### B. 与 PRD 一致（需求锚定）
- [ ] 是否锚定唯一已确认 PRD？引用的 PRD 状态是否为「已确认」（或本工作包已建的「进行中」）？
- [ ] Design 是否**悄悄扩了 PRD 范围**（设计隐含改用户可见行为 / 扩数据 / 扩权限，却没有双写回 PRD）？
- [ ] 「明确不做」是否与 PRD 的「不做什么」一致，有无把排除项设计进去？

### C. 安全边界（不可妥协）
- [ ] 是否默认只读 / 最小权限 / 脱敏 / 限时 / 参数校验 / 审计摘要 / 诚实降级？
- [ ] 模型/Agent 是否永不直连 DB/Shell/网络？是否全经工具网关（权限 + schema + 限时 + 脱敏）？
- [ ] 高风险动作是否只走白名单模板 → 提议 → 审批 → 白名单执行 → 独立验证，而非 LLM 直执行？
- [ ] 凭据是否只走环境变量，不进文档 / 日志 / Trace / 响应 / 截图？
- [ ] Trace 是否只是 Run 事件的安全只读投影，不含 CoT/Prompt/原始数据/原始异常/原始 SQL？
- [ ] 是否诚实空态（未配置 / 无数据如实标注，不伪造能力）？

### D. 架构一致性（与既有代码/设计）
- [ ] Tool 是否继承 `Tool` 并实现受控 `execute`？Connector 是否经显式 Application port / Executor 注入？
- [ ] 跨层数据是否走 Pydantic / TypedDict，而非隐式字典协议？
- [ ] Agent 是否只收 AgentTask、回 findings + 证据引用 + 安全摘要（大脑薄）？
- [ ] 是否对齐既有 Design / 产品文档，有无重复建设或冲突？

### E. Design / plan 分界
- [ ] Design 是否**没有**混入切片拆解 / 验证命令 / 提交计划（那些归 dev-plan 的 plan.md）？
- [ ] 是否给了「建议拆 N 片 / 每片验收语义 / 门禁项」的指引而不是写死的切片？

### F. 可实施性
- [ ] 文件级改动面是否真实、可核对（真实路径，非"相关文件"）？
- [ ] 配置契约是否明确（环境变量优先 + YAML 兜底，敏感值走 `OPERMIND_*`）？
- [ ] 是否标了涉及迁移 / 接口契约 / 数据库变更的项？
- [ ] 回滚是否明确（无迁移 / 无公开 API 时，说明回滚即移除新增注册）？

## 审查输出格式
```
# 架构审查：<Design 标题>
总体：PASS / FAIL（P0/P1 存在即 FAIL）
发现：
- [P1] B2: Design 隐含新增公开 API（<端点>），PRD「不做什么」未含 → 需回写 PRD 并交用户确认
- [P2] D1: 新 Tool 未说明继承 Tool / 受控 execute 的装配方式
- [P3] F2: 配置默认值未写明，建议补
结论：FAIL（存在 P1）
```

## P0–P3 分级
- **P0**：安全红线（凭据泄露、未授权写操作、Agent 直连外部、破坏性改动、把未启用写成已支持、mock 冒充真实）。
- **P1**：功能错误 / 悄悄扩 PRD 范围 / 契约破坏 / 违反横切边界 / 与主脊冲突。
- **P2**：边界与降级缺失、可测性、错误处理、与既有架构不一致。
- **P3**：命名、风格、文档完备性。

**P0/P1 存在即 FAIL，回 arch-design 修改后再审；不得以"设计看着可行"为由放行。**

## 审查后动作
- FAIL → 回 arch-design 修，改完重审。
- PASS → 交用户确认设计决策清单（§6「待用户确认的设计决策」）；用户确认后，把 Design 顶部 `> 状态：草稿` 改为 `> 状态：已确认`，放行到 dev-plan。草稿状态不得作为闸门依据。

## 独立子代理要求
- 审查应尽量用 readonly 子代理（独立视角，与设计者分离），输入：Design 路径、关联 PRD、基线文档、关键实现锚点。
- 子代理不得写文件、不得改代码；产出由主 agent 落盘。
- 非本技能环境无法派子代理时 → 如实标注 `tooling_blocked` 交用户，不得冒充独立审查。

## 常见错误（审查者自己别犯）
| 错误 | 修正 |
|---|---|
| 只审写作质量，不审"dev-plan 照着建会不会出事" | 以"建出来会不会自毁"为第一问题 |
| 对悄悄扩 PRD 范围的设计放过 | 任何范围外推都要回写 PRD + 交用户 |
| 漏审安全边界 | 只读 / 最小权限 / 凭据 / 网关 / 脱敏逐条过 |
| 把切片建议当 Design 缺陷 | 分界：Design 给指引，plan 写切片；混入切片才是缺陷 |
| 设计者审自己的设计 | 写审分离，用独立子代理 |

## 红灯（STOP）
- 存在 P0 / P1
- 设计违反横切边界（Agent 直连 / 未授权写 / 凭据落库 / 未启用当已支持）
- Design 悄悄扩 PRD 范围未回写
- Design 混入切片 / 验证 / 提交计划
- 草稿状态 Design 被当作闸门依据
- 设计者自审或冒充独立审查

**发现任一红灯 ⇒ FAIL，修改后再审。**
