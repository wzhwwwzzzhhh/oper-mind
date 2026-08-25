# P8-judge-runtime-truthfulness · 工作包计划

> 阶段：P8 完善收口｜切片：judge-runtime-truthfulness｜issue：#104
> 基线：main（2eb058c，#99 已合入）｜分支：`feat/P8-judge-runtime-truthfulness`
> worktree：`D:/market-handsome/oper-mind-worktrees/P8-judge-runtime-truthfulness`
> 关联：PRD `docs/prd/agent-runtime/judge-runtime-truthfulness.md`（已确认）、
> Design `docs/design/agent-runtime/P8Judge运行时真实性与配置面收口Design.md`（已确认，2026-08-27）

## 范围

### 只做
- AC1/AC2（路径 B 全面收口）：模型设置页与 `/model/config` 不再展示"裁判生效/裁判模型"；
  `judge_model` 恒表达"未启用"（字段结构保留）；页面如实说明质量节点由主诊断模型承担。
- env 消费下线：`config.py` 删 `OPERMIND_JUDGE_*` 映射与 `load_config` 的 `require_judge_llm` 参数；
  `app.py:_env_config_fallback` 移除 `judge_llm` 键；`config.example.yaml` 移除/标注 judge_llm 段。
- DB judge 消费下线：`resolve_model_config` 不再叠加 judge 激活 Provider（D2）。
- 激活入口收口：`activate` 对 judge 抛 `JudgeEndpointNotEnabledError`（400，D3/D7）；存量 judge 行
  保留但 `provider_resource` 投影值收口为 null（未启用）。
- AC3/AC4 死代码清理：删 `core/fallback.py` + `tests/test_diagnosis.py`、`llm.py:_mock_response`；
  更新 `api/v1/dependencies.py`、`debate.py`、`reflection.py`、`model_runtime_mode.py`、`config.py`
  docstring/注释。
- AC5：质量节点驱动来源如实标注（页面说明由主诊断模型承担，不出现独立裁判复核语义）。
- AC9 文档同步：`docs/完善清单.md` P0-6（按实测标 ✅）、`docs/跑通验证.md` C3 相关记录、
  `docs/产品定义.md` §6/§7、`docs/路线图.md`。
- 配套：PRD/Design 文档入库（`docs/prd/`、`docs/design/agent-runtime/`）、workpack 三件套。

### 明确不做
- 不接线独立 Judge（路径 A）、不改变 Debate/Reflection 编排语义（仍用主诊断 llm）。
- 不改 `GET /model/config` 字段结构（`judge_model` 字段保留）；不改 `active_endpoint`/`endpoint` Literal。
- 不新增数据库迁移、不改 DB 约束、不清理存量 judge 行。
- 不新增公开 API、Connector、真实外部连接、高风险动作能力。
- 不改变 DB/Server/Log/Knowledge 工具边界与 #98/#99 互斥角色白名单。

## 切片拆分（3 片，独立可验收）

- [ ] S1 展示层收口：前端 `ModelSettingsPage` 删裁判卡片/设为裁判按钮/裁判生效标签，judge 显示为
      未启用，新增"质量复核由主诊断模型承担"说明；前端测试同步。
- [ ] S2 后端配置面/激活收口 + 死代码清理：`judge_model` 恒未启用、env/DB 消费下线、judge 激活 400、
      `provider_resource` 值收口、fallback.py/`_mock_response`/过时注释清理；后端测试同步。
- [ ] S3 文档与回归：文件代码全部完成 → 后端全量 pytest、前端 typecheck/test/build、
      `git diff --check` → 回写完善清单/跑通验证/产品定义/路线图 → workpack 归档 → PR。

## 改动面（文件级）

### 后端 `backend/`
- `src/config.py`（删 env 映射/参数/校验分支 + docstring）
- `src/application/errors.py`（新增 `JudgeEndpointNotEnabledError`）
- `src/application/model_providers.py`（resolve_model_config 删 judge 叠加；activate 拒 judge + docstring）
- `src/api/v1/routes.py`（judge_model 恒 None；错误码 400 登记；provider_resource 值收口）
- `src/app.py`（_env_config_fallback 删 judge_llm 键）
- `src/domain/model_runtime_mode.py`（docstring）
- `src/core/llm.py`（删 `_mock_response`）
- `src/core/debate.py`、`src/core/reflection.py`（更新"简化实现"注释）
- `src/api/v1/dependencies.py`（更新"审批执行器仍为空骨架"注释）
- **删除** `src/core/fallback.py`、`tests/test_diagnosis.py`
- `tests/test_api.py`、`tests/test_model_config_api.py`、`tests/test_model_provider_api.py`（同步断言 + 新增收口用例）

### 前端 `frontend/`
- `src/features/models/ModelSettingsPage.tsx`、`ModelSettingsPage.test.tsx`
- `src/test/handlers.ts`（mock 与收口契约一致）
- `src/api/v1/client.ts`、`generated.ts`：**不改**（字段结构不变）

### 配置 / 文档
- `config/config.example.yaml`
- `docs/完善清单.md`、`docs/跑通验证.md`、`docs/产品定义.md`、`docs/路线图.md`
- `docs/prd/README.md`、`docs/prd/agent-runtime/README.md`（judge PRD 索引）
- `docs/design/agent-runtime/P8Judge运行时真实性与配置面收口Design.md`（新增，已确认）
- `docs/workpack/P8-judge-runtime-truthfulness/{plan,review,evidence}.md`
- **无迁移、无公开 API 字段增删、无 DB 结构变更**

## 验证方法
- 后端：`..\.venv\Scripts\python.exe -m pytest tests -q`（worktree 内 `backend/` 执行）；
  聚焦：`test_model_config_api.py`、`test_model_provider_api.py`、`test_api.py`。
- 前端：`npm run typecheck`、`npm run test`、`npm run build`（worktree 内 `frontend/` 执行）。
- 门禁：`git diff --check`；`git grep -n "judge\|裁判"` 核对展示面无残留误导；PR diff 只含本工作包文件。

## 提交计划
- 1 个提交（切片紧凑、交付完整）：`feat: Judge 运行时真实性与配置面收口——路径 B 全面收回裁判配置面（P8，#104）`
  （含 PRD/Design/代码/文档/workpack；提交前按 CLAUDE.md 只暂存本工作包文件，禁止 `git add .`）