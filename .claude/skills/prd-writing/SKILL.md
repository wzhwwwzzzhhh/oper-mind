---
name: prd-writing
description: Use when writing or organizing a PRD (Product Requirements Document) for the OperMind project, including converting existing design docs or task specs into PRDs, planning feature requirements across product domains, or structuring the docs/prd/ directory. Trigger on "写PRD", "写需求", "PRD", "需求文档", "需求规格".
---

# PRD 写作（OperMind 项目专属）

## 核心原则
PRD 是**执行 AI 的唯一事实来源**。它决定"做成什么样才算好"，但不规定"怎么做"。
不写实现细节、不写代码、不写测试代码；验收标准与边界必须钉死，防止执行 AI 自由发挥/漂移。

## 何时写 / 何时不写
**写**：用户要求把某需求变成可执行需求，或要新增一个产品能力、修复一个产品行为，或把 Design/任务书转成 PRD。
**不写**：当前正在进行中的执行、纯技术重构、无用户价值的内部实现、可直接在对话里定的小改。

## 前置要求
- 写 PRD 前必须**先读**：`docs/产品定义.md`、`docs/路线图.md`、`docs/开发规范.md`，以及关联域的既有 PRD。
- 若 PRD 涉及安全边界（凭据/连接/权限/审批/写操作），必须参考 `docs/` 下已确认的 Design 决策，并在 PRD 里引述。

## 目录结构（docs/prd/，域 + 阶段两级）
```
docs/prd/
  README.md                      # 索引：所有域、每个域当前进展、执行 AI 如何用
  session/                       # 会话工作台域
    README.md
    P4.2-db-agent-real.md        # 命名：{阶段}-{功能}.md
  service-center/                # 服务中心域
    README.md
  monitor/                       # 服务监控域
  model/                         # 模型设置域
  approval/                      # 审批/受控动作域
  knowledge/                     # 知识库域
```
- 每个域一个文件夹 + 一个 README 索引（列出该域所有 PRD、状态、关联阶段）。
- PRD 文件名：`{阶段}-{功能kebab}.md`，如 `P4.2-db-agent-real.md`。
- **状态双写一致（硬规则）**：PRD 状态流 `草稿 → 已确认 → 进行中 → 完成` 必须同时记录在 **PRD 文件顶部 frontmatter `status`** 和 **`docs/prd/README.md` 索引表**（及所在域 README）两处，两处必须一致，不得只改一处。

## 状态推进责任矩阵（谁在哪个阶段推进哪个状态）

| 状态 | 何时推进 | 谁推进 | 更新位置 |
|---|---|---|---|
| 草稿 | PRD 首次写入 | PM（prd-writing） | frontmatter + README |
| 已确认 | 用户确认 PRD 方向/决策 | PM（prd-reviewing + 用户确认后） | frontmatter + README |
| 进行中 | 执行 AI 开始开发（dev-plan 建 workpack） | 执行 AI | frontmatter + README |
| 完成 | 工作包交付归档（dev-deliver Phase 7） | 执行 AI | frontmatter + README |

**关键**：任何一次状态推进都必须**同时更新 frontmatter 和 README 两处**，缺一即视为未完成状态登记。dev-deliver 收尾时尤其要确认 PRD frontmatter 也标了 `status: 完成`，不能只改 README。

## PRD 模板（必须遵循）
每份 PRD 含以下小节，顺序固定。缺哪节补哪节，没有的内容明确写"无"。

```markdown
---
title: <一句话需求标题>
status: 草稿
domain: <所属域>
phase: <所属阶段，如 P4.2>
updated: <YYYY-MM-DD>
---

# <标题> · PRD

## 背景
为什么做这个需求；现状与痛点；关联的阶段/文档/既有 PRD。

## 目标
做成后用户/系统能获得什么。1-3 条，可验证。

## 用户故事
作为<角色>，我想要<能力>，以便<价值>。（若适用，含具体触发场景）

## 范围
### 做什么
- <本需求包含的、明确的用户可见或系统能力>

### 不做什么（明确排除）
- <明确排除的项，防止执行 AI 自由发挥>

## 功能需求
### 1. <功能标题>
- **输入**：<用户或系统的输入，含边界>
- **行为**：<系统应做的行为，按可验证步骤>
- **输出**：<用户可见或系统产生的输出>

## 非功能需求（按需）
性能 / 安全 / 可靠性 / 可访问性 / 一致性 要求。

## 数据与接口影响（按需）
- 数据：<涉及的数据模型、持久化、迁移>
- 接口：<涉及的前后端 API 契约变化；无则写"无，接口契约不变">

## 验收标准
每条用"当 <条件> 时，应 <可验证行为>"句式，执行 AI 逐条核验。**必须可测**。
- [ ] AC1: 当 <条件> 时，应 <行为>
- [ ] AC2: ...

## 边界与约束
- 安全边界：<凭据/连接/权限/写操作等硬约束>
- 降级策略：<未配置/连接失败/超时时系统应如何表现>
- 兼容性：<对既有 mock 评测、接口契约的影响>

## 完成定义（DoD）
- [ ] 全部 AC 通过
- [ ] 相关回归测试全绿
- [ ] 未改动的文件清单确认
- [ ] <按需求补充>

## 开放问题（无则留空）
- <待用户/设计确认的问题>
```

## 关键纪律
1. **边界 > 功能**：不做什么清单与验收标准同样重要，是防漂移的第一道墙。
2. **验收可测**：AC 必须"可测"，不能是"系统应稳定"这种不可验证的表述。
3. **不写实现**：不要出现"新建一个类/函数/文件"等实现指令；实现方式由执行 AI 定。
4. **诚实空态**：无数据/未配置时系统应如实展示空态或"未配置"，不得伪造。
5. **安全默认**：涉及凭据/连接/写操作，默认只读、默认最小权限、默认脱敏，PRD 里写明。
6. **关联可溯**：背景里引述关联 Design/PRD 文档路径，执行 AI 能回溯决策。

## 常见错误
| 错误 | 修正 |
|---|---|
| 把 AC 写成"系统应稳定/快速" | 改成可测条件：如"当慢查询超过阈值时，应返回..." |
| 写了实现指令（新建类/改某函数） | 删掉，只留"应产出 X 能力" |
| 漏写边界，导致执行 AI 自由发挥 | 补"不做什么"与降级策略 |
| 与既有 Design/PRD 脱节 | 背景里引述关联文档，保持单一事实来源 |
| PRD 写进实现细节 | 剥离到执行阶段，PRD 只留"做成什么样" |
| 状态只改 frontmatter 或只改 README | frontmatter 与 README 双写一致，一处状态变更两处同步 |
