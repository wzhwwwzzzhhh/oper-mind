# P4.3-model-settings-real · AC 证据

| AC | 验证 | 状态 |
|---|---|---|
| AC1–AC4 | `backend/tests/test_model_config_api.py`：4 passed，覆盖真实配置映射、mock、未配置、凭据/URL 脱敏 | PASS |
| AC5–AC7 | `frontend/src/features/models/ModelSettingsPage.test.tsx` 与 `frontend/src/app/App.test.tsx`：真实配置、错误态、未接入能力；相关测试通过 | PASS |
| AC8 | 后端全量 `101 passed`；前端全量 `8 files / 51 tests passed`；`npm run typecheck` 通过；`npm run build` 通过；工作包文件 `git diff --check` 通过 | PASS |

## 备注

- 构建有既有 bundle size warning，不影响构建成功。
- 全工作区 `git diff --check` 仍会报告其他既有文件 `docs/产品定义.md` 的尾随空格；本工作包文件检查干净，未修改该无关文件。
- OpenAPI 生成文件的部分字段为 `unknown`，源于仓库现有 Pydantic 序列化基类与生成器的既有推导限制；本工作包通过显式前端响应类型保持本功能契约，未手工修改生成文件。
