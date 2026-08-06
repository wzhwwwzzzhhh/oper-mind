---
name: prd-reviewing
description: Use when reviewing a written PRD (Product Requirements Document) for correctness, testability, boundary clarity, engineering feasibility, implementation drift, and alignment with the OperMind product north star. Trigger on "审查PRD", "PRD对不对", "review PRD", "检查需求", "自审PRD", "对照PRD", "PRD验收", or any change touching docs/prd/. For development planning, use dev-plan instead.
---

# PRD 审查（OperMind 项目专属）

## 核心原则
审查不是审"写得好不好看"，而是审「**执行 AI 拿着它会不会做错 / 跑偏 / 漏做**」。
回答的问题：这份 PRD 交出去，能不能让执行 AI 产出符合大方向、不越界、可验收的成果？

## 何时用
- 写完一份 PRD 后、交给执行 AI 前（**自审**）。
- 大阶段验收时，核对执行 AI 成果是否满足 PRD（需求侧核验）。
- 用户要求确认某需求"对不对 / 合不合大方向"时。

**不用**：写 PRD 的过程中（那是 `prd-writing` 的职责）；审代码实现（那是 code review 的职责）。

## 审查维度（逐条过）

### A. 大方向对齐（用户最后只看这一层）
- [ ] 是否符合产品定义的主脊（会话主入口 / 服务中心 / 多 Agent 内核 / 受控 Connector/Tool）？
- [ ] 是否违背路线图的阶段规划（不抢跑、不造旁路、不做演示叙事）？
- [ ] 是否解决真实用户/运维问题，而非技术自嗨？
- [ ] 若涉及未授权能力（新服务类型 / 凭据 / 审批 / 写操作 / 破坏性改动），是否注明需先 Design→Review？

### B. 范围与边界
- [ ] 是否有明确的「不做什么」清单？
- [ ] 范围是否过度（scope creep）或过窄（无法独立交付/验收）？
- [ ] 是否在边界外混入"顺便修一下"的无关改动？

### C. 验收标准可测性（最关键）
- [ ] 每条 AC 是否形如「当 <条件> 时，应 <可验证行为>」？
- [ ] 是否有不可验证表述（"系统应稳定 / 快速 / 良好"）？
- [ ] 是否覆盖降级路径（无配置 / 连接失败 / 超时 / 空数据）？
- [ ] 是否至少有一条回归保护（既有行为 / 既有测试不破）？
- [ ] AC 能否被执行 AI 逐个打勾？有无"看似 AC 实为愿望"的条目？

### D. 安全与架构边界
- [ ] 是否默认只读 / 最小权限 / 脱敏？
- [ ] 凭据是否只走环境变量，不进文档 / 日志 / Trace / 前端 / 截图？
- [ ] 是否遵守既有架构（Tool 继承 Tool、Connector 经显式端口、前端不直连、跨层走 Pydantic/TypedDict）？
- [ ] 是否诚实空态（无数据 / 未配置如实展示，不伪造）？

### E. 一致性与可追溯
- [ ] 是否与既有 PRD / Design / 产品文档冲突？
- [ ] 是否引述关联文档路径（执行 AI 能回溯决策）？
- [ ] 是否与本域 `README.md` 登记一致（PRD 已在域索引中）？
- [ ] PRD 推进「已确认」后是否已建 GitHub issue（frontmatter `issue` 编号存在，issue 状态与 PRD 状态一致）？

### F. 实现 vs 需求
- [ ] 功能需求是否在"行为 / 输出"层面描述，而非"怎么做"（新建类 / 改文件 / 具体查询）？
- [ ] 若含关键技术约束（只读 / 双模式 / 限时），是否标注为「已确认决策」并引述 Design，而非当作功能正文？
- [ ] 完成定义是否给了能力级边界（可改什么 / 不可改什么），而非含糊"只出现允许的文件"？

## 审查输出格式
```
# PRD 审查：<标题>
总体：PASS / FAIL（FAIL 需列出阻塞项）
发现：
- [阻塞] C2: AC3 表述不可验证（"系统应稳定"）→ 改为可测条件
- [建议] F1: 功能 #4 混入"查询 pg_indexes"实现细节 → 收敛为"查询只读系统目录"并引述 Design
行动：阻塞项必须修改；建议项择机修改
```

## 审查后动作
- 自审出 FAIL → 修改 PRD 直到 PASS，再交用户。
- 自审 PASS → 仍交用户做轻量方向确认（用户只需看 背景 / 目标 / 范围 是否符合大方向）。
- 用户确认方向后 → 把 PRD 状态推进为「已确认」：**双写** PRD 文件顶部 frontmatter `status: 已确认` 与 `docs/prd/README.md`（及所在域 README）索引，两处必须一致，缺一即未完成登记（对齐 `prd-writing` 状态推进责任矩阵）。
- **建 GitHub issue（协作入口）** → 用 `gh issue create` 建 issue（title=PRD 标题，body=PRD 内容 + 关联 Design 路径 + 关联 PRD 路径，labels=域+阶段），把 issue 编号写回 frontmatter `issue` 字段（双写）。issue 放需求层，协作方从 issue 开工。

## 常见错误（审查者自己别犯）
| 错误 | 修正 |
|---|---|
| 只审写作质量，不审"执行 AI 会不会做错" | 以"交出去会不会跑偏"为第一问题 |
| 对不可验证的 AC 放过 | 每条 AC 逐字问"可不可测" |
| 漏审降级路径 | 无配置 / 失败 / 超时必须有 AC |
| 忽略与大方向对齐 | 先对产品定义 / 路线图，再对细节 |
| 把"实现建议"混入审查意见 | 审查只谈需求正确性，实现留给执行 AI |

## 红灯（STOP）
- AC 全是"系统应稳定 / 快速"这类不可测表述
- 没有「不做什么」清单
- 凭据 / 连接 / 写操作出现在 PRD 里却没写明安全边界
- 范围里混进"顺便修复"的无关项
- 与大方向（产品定义 / 路线图）明显冲突却未注明需先设计

**发现任一红灯 ⇒ FAIL，必须修改后才能交付。**