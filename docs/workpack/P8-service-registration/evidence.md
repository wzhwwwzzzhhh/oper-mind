# P8-service-registration · AC 证据表

> 证据日期：2026-08-10
> 相关测试：后端 358 pytest 全绿；前端 typecheck / test（102）/ build 全绿；mypy/ruff 全仓通过。

| AC | 验证点 | 证据 | 结果 |
|---|---|---|---|
| AC1 | POST /services 返回安全视图、响应无 DSN 明文 | `tests/test_service_registration_api.py::test_注册服务返回安全视图且响应无明文`（断言 id/kind/title/has_dsn/掩码尾号 + 明文不入响应 + DB 行密文断言）；前端 `ServiceCenterPage.test.tsx` 添加服务测试 | PASS |
| AC2 | 实例 ID 与硬编码实例冲突 → 明确错误 | `test_注册服务ID与既有硬编码实例冲突返回409`、`test_重复注册同ID返回409`（`SERVICE_INSTANCE_CONFLICT`） | PASS |
| AC3 | 主密钥未配置拒绝创建 | `test_主密钥未配置时注册被拒绝`（409 `SECRET_KEY_NOT_CONFIGURED`，明文不入响应） | PASS |
| AC4 | 已注册服务进入 GET /services 同列 | `test_已注册服务进入列表且与其他服务同列`；前端列表掩码展示测试 | PASS |
| AC5 | PUT 更新标题/DSN 并重置状态 | `test_更新标题与DSN并重置状态`（掩码随新 DSN 更新）；`test_更新不存在服务返回404` | PASS |
| AC6 | DELETE 204、重复 204、列表不再出现 | `test_删除服务返回204且重复删除仍204`；`test_删除硬编码实例不影响运行时注册表`；前端移除测试 | PASS |
| AC7 | test-connection healthy/unavailable/not_configured + 安全原因 | `test_连接测试对不可达服务返回unavailable与安全原因`（断言无明文、分类码）；`test_连接测试不存在服务返回404`；前端测试连接测试 | PASS |
| AC8 | 应用库/日志/Trace/响应无 DSN 明文 | 注册测试的 DB 行 `dsn_encrypted` 密文断言 + 响应无明文断言；加密走 `secrets.py encrypt_dsn`（AES-256-GCM + DSN 独立 key-info）；掩码尾号仅末 4 位 | PASS |
| AC9 | 前端未验证/未配置如实标注 | `ServiceCenterPage.tsx` availability_text（正常/需关注/未配置）+ mode_text（未接入）；前端测试不伪造 healthy；"DSN 已存 · 尾号"诚实展示 | PASS |
| AC10 | 移除服务后历史会话/监控/活动留痕保留 | `test_动态注册服务可创建会话并保留历史`（删除后会话仍可查，service_id 保留）；删除不触碰 sessions/session_services/monitor_samples 行 | PASS |
| AC11 | 回归全绿 | 后端 358 pytest（含 test_p4_service_center/test_postgres_connector/test_redis_connector/test_monitoring/test_api/test_p2_schema/test_p6_cross_service/test_persistence_infrastructure）；前端 typecheck/test(102)/build；mypy/ruff 全仓；`registry_loader` 默认 None 保持既有装配语义 | PASS |

## 设计决策落实（Design §6）

1. DSN AES-256-GCM 加密落库（`secrets.py encrypt_dsn`，`service_registry` 表密文列）✓
2. 注册不立刻探连接（`create` 不调 health_snapshot，存"未验证"由下次列表读取探活）✓
3. 仅 postgres/redis 类型（schema + 命令层白名单）✓
4. 掩码 `••••`+末4位（`dsn_masked_tail` 字段，前端展示）✓
5. 移除保留历史留痕（delete 只删 registry 行 + 凭据密文）✓
6. MonitorSampler 改持 registry 引用每轮读 `list_connectors()` ✓
7. PUT 不接受改能力声明（命令无 kind/能力字段，由类型模板派生）✓
8. 迁移放宽 `session_service_id_valid`/`session_services_service_id_valid` CHECK（downgrade 有动态 ID 守卫）✓
9. POST /services 以 instance_id 唯一作自然幂等（重复 409，不要求 Idempotency-Key）✓

## 验证记录

- 后端：`..\.venv\Scripts\python.exe -m pytest tests -q` → 358 passed
- 迁移：`alembic upgrade head` → `downgrade -1` → `upgrade head` 通过；动态 ID 守卫测试通过
- 前端：`npm run typecheck` ✓、`npm run test` → 102 passed、`npm run build` ✓
- 静态：`mypy src` 无问题、`ruff check src` 全过、`git diff --check` 干净
