# P4.3-model-settings-real · 独立审查

## 结论

PASS（P0/P1 均已清除）。

## 修复记录

- 接口失败时页面不再渲染静态模型偏好区域，符合 AC6；独立页面测试覆盖该行为。
- 诊断配置缺失或不完整时返回 `status=not_configured` 安全空态，不返回 500。
- 后端 `mode` / `status` 使用 `Literal` 约束。
- 计划响应包装修正为实际已确认的顶层 `config` + `meta` 契约；PRD 未要求额外 `data` 包装。
- `base_url_host` 仅作为本次用户确认的模型配置安全视图字段使用，不推广为其他接口的通用连接细节展示规则。

## P0-P3

- P0：无凭据泄露、写操作、外部连接或破坏性改动问题。
- P1：无功能漏项、越界 API 或错误降级问题。
- P2：`openapi-typescript` 对仓库现有 Pydantic 序列化基类生成的多个字段（包括本次新增字段）退化为 `unknown`；前端 client 使用显式本地安全接口类型，`typecheck`、测试和构建均通过。修复全仓 OpenAPI 类型推导属于独立工程工作，不在本 PRD 范围内。
- P3：无阻断性风格问题。

## AC 证据

| AC | 证据 | 结论 |
|---|---|---|
| AC1 | `GET /api/v1/model/config`；`test_model_config_api.py` 验证诊断 provider/host/model | PASS |
| AC2 | mock API Key 返回 `mode=mock`，后端测试覆盖 | PASS |
| AC3 | 裁判配置缺失返回 `judge_model=null`，前端显示未配置空态 | PASS |
| AC4 | 后端测试验证 API Key、`sk-`、完整 URL、密码、查询参数不出现在响应 | PASS |
| AC5 | React Query 挂载读取真实配置；`ModelSettingsPage.test.tsx` 和 `App.test.tsx` 覆盖成功态 | PASS |
| AC6 | 查询错误显示错误状态，成功专属的 Provider/本地模型区域不渲染；页面测试覆盖 | PASS |
| AC7 | 添加模型服务、连接测试、模型发现、刷新列表等按钮禁用或明确未启用 | PASS |
| AC8 | 后端 `101 passed`；前端 `8 files / 51 tests passed`；`typecheck`、`build`、工作包文件 `git diff --check` 通过 | PASS |

## 边界

- 未新增 API Key 保存/编辑、Provider 编辑、连接测试、模型发现、数据库迁移或外部调用。
- `generated.ts` 通过 `npm run generate:api` 更新；其无关旧类型删除与当前后端已移除旧入口一致，未手工编辑生成文件。
- 工作区存在其他工作包改动，提交时只暂存 P4.3 文件。
