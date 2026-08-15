# P8-message-edit-delete · 独立代码审查

> 审查者：readonly 独立子代理（与开发者视角分离）
> 审查对象：`git diff origin/main...HEAD`（提交 `cdf8d9b` / `f441272` / `9f29805`）
> 审查日期：2026-08-14

# 代码审查：P8-message-edit-delete

**总体：PASS**（无 P0/P1；P3 两项已修正/记录）

作为只读审查者，核对了 plan/PRD/Design、完整 diff（backend/src、tests、migrations、frontend/src、docs），
并实际执行了后端测试、迁移往返、前端 typecheck/test/build。未发现 P0/P1。

## 关键实现核对结论（重点维度）

- **分层与 TID251**：`MessageEditingApplicationService` 经 `MessageEditingWriter` Protocol 端口注入
  （application 层零 infrastructure 依赖）；`SqlAlchemyMessageEditingWriter` 在 `dependencies.py`
  装配；`pyproject.toml` 未新增白名单条目——符合 ruff 分层硬边界。
- **归属/角色/幂等（AC2/3/4/6/8）**：writer 单事务校验；重复删除幂等 204；已删除 PATCH → 404；测试断言齐全。
- **软删除与 Run/重跑链路**：`get_by_id` 不过滤 archived（历史追溯），`list_by_session` 过滤；
  AC7 实测删除输入消息后 `execute_run`（`_claim_run`）成功——硬保证成立。
- **成对普通回复随删**：cursor 排他扫描 + 下一条 user 消息断点；Run 输出（run_id 非空）绝不删；
  多轮/穿插场景测试覆盖，无误删。
- **迁移**：版本链 `13 → 12` 正确；SQLite downgrade 用 `PRAGMA foreign_keys=OFF` 保护被
  `diagnosis_runs` FK 引用的 messages 表；往返实测成功。
- **前端投影**：`RUN_INPUT_MESSAGE_MISSING` 保留卡片（input null + 占位）+ 按创建时间插入；
  adjacent 聚合加 null 守卫；`read_investigation` 新增 required `created_at` 与后端契约一致。
- **失败态诚实**：mutation 失败经 `safe_error` 如实展示，不本地伪造成功。
- **generated.ts**：diff 仅含本工作包增量。

## 发现

- [P3] Design §2.2 文案与实现不一致（文案写「注入 SessionFactory」，实现为 writer Protocol 端口）：
  方向正确（application 不直连 infra），已同步修正 Design 文案（`docs/design/session/P8消息编辑与删除Design.md`）。
- [P3] evidence.md 的 App.test.tsx flake 计数随环境抖动（34/2 vs 33/3），已披露为既有时序 flake，
  3 个 P8 新增交互测试全部通过，无 P8 AC 误报绿；evidence 措辞已收紧。
- [P3] plan 中 `docs/接口清单.md` / `docs/路线图.md` 登记列为「随 PR 收尾」动作，本阶段未改，符合流程。

## AC 证据表核对（逐 AC）

AC1–AC9：全部 PASS（测试文件/断言逐条核对存在且通过）。
AC10：PASS（有说明）——后端全量 502 passed / 2 skipped；前端 typecheck/build 通过；
既有 2–3 个 running/queued 调查渲染 flake 属基线可复现环境问题（stash 回基线复现验证），非本工作包所致。

## 结论：PASS

实现按 plan/Design 建齐，分层正确、软删不影响 Run 链路、成对随删边界安全、迁移往返正确、
前端投影变更保守且未破坏多服务聚合、失败态诚实；无越界文件、无凭据/证据泄露、
generated.ts 仅含本工作包增量。可进入提交与交付。
