# P8-rerun-investigation · AC 证据表

> 证据先于断言：本表随切片推进逐步回写，所有「通过」均有测试输出支撑。
> 关联 PRD：`docs/prd/session/P8-rerun-investigation.md`（issue #65）；Design：`docs/design/session/P8调查重跑Design.md`（已确认）。

## 验证记录

### S1 重跑后端链路（含迁移）

| 命令 | 结果 |
|---|---|
| `pytest tests/test_run_rerun.py -q` | **13 passed**（AC1–AC7 服务端面 / AC9 + 归档 409 / 指纹冲突 409 / 服务上下文复用 / 全局列表来源字段 / 迁移 downgrade 防御 / 唯一键竞争重读） |
| `pytest tests/test_api.py tests/test_p2_application_services.py tests/test_p5_controlled_action.py tests/test_runs_list.py tests/test_session_search.py -q` | 39 passed（回归，1 项字段白名单断言同步后全绿） |
| `pytest tests/test_service_registration_api.py -q` | 16 passed（迁移守卫测试改目标 revision 适配新迁移链） |
| `pytest tests/test_p2_schema.py -q` | 6 passed（diagnosis_runs 外键集合断言加入自引用 FK） |
| `pytest tests -q`（分三段覆盖全部文件） | **436 passed**（145 + 169 + 122，全量） |
| `alembic upgrade head`（测试内临时库） | 通过（`test_run_rerun`/`test_runs_list` fixture 均经 Alembic 建 schema） |
| `python -m py_compile`（全部改动后端文件） | OK |

### S2 前端重跑入口与关联展示

| 命令 | 结果 |
|---|---|
| `npm run generate:api`（dump OpenAPI → openapi-typescript） | 成功，`generated.ts` 含 `rerun_of_run_id` |
| `npm run typecheck` | 通过（tsc --noEmit 无错误） |
| `npm run test` | **133 passed**（17 文件全绿） |
| `npm run build` | 通过（vite build） |

## AC 映射

- [x] AC1：succeeded / failed / cancelled 可重跑，新 Run 记录 `rerun_of_run_id`
  → `test_run_rerun.py::test_rerun_终态run受理新run并记录来源关联` / `test_rerun_失败run可重跑` / `test_rerun_cancelled与queued状态的服务层校验`（cancelled 分支）
- [x] AC2：queued / running 重跑明确错误
  → `test_rerun_cancelled与queued状态的服务层校验`（queued/running 抛 RunNotTerminalError）+ `test_rerun_未终态API返回409明确错误`（409 RUN_NOT_TERMINAL）
- [x] AC3：复用原 Run 的 query 与 service 上下文
  → `test_rerun_终态run受理新run并记录来源关联`（input message 内容比对）+ `test_rerun_复用绑定服务的service上下文`
- [x] AC4：幂等重放不产生重复 Run；同键不同原 Run 指纹冲突
  → `test_rerun_幂等重放不产生重复run` + `test_rerun_同幂等键对不同原run重跑返回指纹冲突`（409 IDEMPOTENCY_KEY_REUSED）
- [x] AC5：新 Run 展示「重跑自」；原 Run「已被重跑」前端推导
  → 后端字段断言 + `conversation-turns.test.ts`（rerun_by_latest 倒序先到先得）+ `App.test.tsx`（重跑自 / 已被重跑标记）
- [x] AC6：全局 Run 列表展示来源关系
  → `test_rerun_全局run列表含来源字段`（GET /runs 携带）+ `RunsPage.test.tsx`（重跑自标记）
- [x] AC7：响应无未脱敏内容
  → `test_rerun_响应无未脱敏内容`（无 evidence/sk-/DSN；失败重跑走白名单）
- [x] AC8：前端已结束 Run「重新生成」按钮，loading 防重复，进入新 Run
  → `App.test.tsx`（三个交互测试：重跑闭环 / 未结束无按钮 / 失败如实提示）
- [x] AC9：历史 Run（无来源字段）按普通 Run 处理
  → `test_rerun_终态run受理新run并记录来源关联`（原 Run 详情 rerun_of_run_id null）
- [x] AC10：回归全绿
  → 上表 S1/S2 验证记录；后端 436 passed、前端 133 passed + typecheck + build

## 备注
- 全量后端测试存在「单进程全量顺序收尾挂起」现象（测试点全输出后 pytest 退出卡住），已改为分三段跑全量规避；单文件/分片批跑均正常退出，各段结果与单跑一致。
- 迁移链新增 12 后，`test_service_registration_api` 的 downgrade 守卫测试目标 revision 从 `-1` 改为 `20260810_10_p8_model_mode`（`-1` 现在先回滚新迁移、触不到守卫）；`test_p2_schema` 的 diagnosis_runs 外键集合断言加入自引用 FK；`test_runs_list` 字段白名单断言加入 `rerun_of_run_id`。
- 文档收尾（独立代码审查 P1 修复）：`docs/接口清单.md` 缺表「重跑/重新生成」标已交付 + 补 `POST /runs/{run_id}/rerun` 行（汇总 21/43/41）；`docs/路线图.md` 登记 issue #65。
- 独立代码审查两轮：首轮 FAIL（P1 文档缺失 + P2 迁移守卫测试 / 竞争重读测试 / handlers 可变状态）→ 修复后复审 PASS。
