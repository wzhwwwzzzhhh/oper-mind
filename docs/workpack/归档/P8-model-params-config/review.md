# P8-model-params-config · 独立审查

## 审查信息
- 审查时间：2026-08-12
- 审查范围：`git diff origin/main...HEAD`（S1 参数持久化+API / S2 LLM 调用链 / S3 前端表单 / 降级补测，4 提交）
- 审查方式：readonly 子代理独立审查（Explore 类型，只读 diff 与文档）

## 结论：PASS（无 P0/P1）

## 实测验证
- 后端全量 `pytest tests -q`：460 passed（含 test_model_params_api 20 + 降级补测 2、test_llm_client 8、test_model_config_api 4）
- 前端 typecheck / test（17 文件 130 tests，含 3 个新参数用例）/ build 全部通过
- `git diff --check` 干净；`git status` 无越界文件

## 发现（全部处理）
- [P2] `resolve_model_params` / `service.get` 的 SQLAlchemyError 回退与损坏 JSON 降级路径无测试 → **已补 2 个测试**（损坏 JSON 诚实降级、应用库不可用回退默认不 raise），test_model_params_api.py 22 passed。
- [P3] 收尾文档未入分支（plan.md / Design / PRD 状态）→ 本收尾提交补齐。
- [P3] 前端无客户端校验、temperature=0.0 显示「已配置：0」→ 记录在案，后端 422 兜底保证 AC3，前端体验后续优化。
- [P3] 脱敏断言 `"token" → "token=secret"` 放宽 → 因新字段 max_tokens 含 "token" 子串必要，password/api_key/sk-/DSN 断言保留。

## AC 证据表
| AC | 证据 | 状态 |
|---|---|---|
| AC1 | test_构造默认temperature进入调用链（0.5→SDK kwargs）+ 保存后 PUT/GET 一致 | PASS |
| AC2 | 未配置返回 params 全 None + params_defaults(0.0/None)；chat 默认 0.0、max_tokens 不传；损坏 JSON/应用库不可用降级 | PASS |
| AC3 | 7 组非法载荷 422 + 边界值（0/2/1/102400）合法 | PASS |
| AC4 | test_重启后参数保持（同 SQLite 重建 runtime） | PASS |
| AC5 | PUT/GET 一致 + 前端「保存后展示已配置值」测试 | PASS |
| AC6 | 响应无 api_key/sk-/DSN | PASS |
| AC7 | 表单仅 temperature/max_tokens 两字段 | PASS |
| AC8 | mock 路径不读参数、mock 下保存成功且模式不变、前端标注「仅 real 生效」 | PASS |
| AC9 | 后端 460 passed、前端 typecheck/test/build 全绿 | PASS |

## 核验要点（均通过）
- 范围映射：3 切片与 plan 一一对应；未做 top_p、未按 Provider 作用域、未复活 localStorage、graph.py:158/269 与 debate.py:77 显式 0.0 保持不动。
- 安全：参数接口不含凭据；mock 路径 `_mock_chat` 不读参数；写接口仅 PUT /model/params，与 PUT /model/mode 同权限级别。
- 契约：`GET /model/config` 仅追加 params/params_defaults 字段；`PUT /model/params` 全量替换、null=清除、幂等；app_settings 键 `model.params` 无迁移。
- 纪律：跨层数据走 Pydantic/TypedDict；core（llm/bootstrap）只依赖 domain，应用层解析 infrastructure；中文注释、公开函数类型标注齐全，无裸 except、无新增 print。
