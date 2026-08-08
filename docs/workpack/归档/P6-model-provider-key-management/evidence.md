# P6-model-provider-key-management · AC 证据表

> 状态：审查 PASS（独立子代理只读审查，结论见 `review.md`）
> 覆盖：S1 加密持久化 + Provider 读写/激活 API；S2 连接验证；S3 配置生效贯通 + 前端。
> 回归基线：`tests/test_monitoring.py` 3 项失败为**预置测试时间炸弹**（`_snapshot()` 与 redis 标量用例硬编码 `observed_at=2026-08-05 12:00 UTC`，采样保留窗口 24h 在真实时钟越过 2026-08-06 12:00 UTC 后将其判为过期删除；main 最后一次 CI 于 08-06 11:32 UTC 恰好早于边界通过）。非本工作包代码引入，但阻塞一切 PR 的 CI；经用户确认以**越界修复**纳入本 PR（2 行改为动态时间，随交付提交一并纳入）。

| AC | 证据（代码/测试） | 结果 |
|---|---|---|
| AC1 保存加密、掩码展示、不落明文 | `src/infrastructure/secrets.py` AES-256-GCM；`tests/test_secrets.py`（加解密往返/错误密钥失败）；`tests/test_model_provider_api.py::test_创建Provider保存APIKey并掩码展示`（断言响应无明文、无 `api_key_encrypted` 字段） | PASS |
| AC2 读取不返回明文 | `src/api/v1/resources.py::provider_resource` 只映射安全字段；`tests/test_model_provider_api.py::test_读取列表不泄露明文` 等 | PASS |
| AC3 连接成功返回成功 | `src/infrastructure/model_provider_verify.py`；`tests/test_model_provider_verify.py::test_验证成功返回OK`；`tests/test_model_provider_api.py::test_验证成功更新为ok` | PASS |
| AC4 失败/超时脱敏原因 | verify 仅返回分类码（`TIMEOUT`/`HTTP_401`/`NO_API_KEY`/`SECRET_KEY_NOT_CONFIGURED`）；断言响应不回显响应体/凭据 | PASS |
| AC5 会话链路使用生效配置 | `src/api/v1/dependencies.py::_resolved_coordinator_factory` 每 Run `resolve_model_config`→`build_llm_from_config`→`build_coordinator`；`tests/test_model_provider_resolver.py::test_激活Provider优先于env`；`test_激活Provider后生效配置反映DB` | PASS |
| AC6 未配置诚实降级 | `build_llm_from_config` 缺省 mock + `set_active_scenario`；`resolve_model_config` 永不 raise（SQLAlchemyError 回退）；`tests/test_model_provider_resolver.py::test_应用库不可用时不抛错回退env` | PASS |
| AC7 变更即生效、mock/real 如实标注 | `app.py` 移除 `_shared_llm` 单例、每 Run 构造；`GET /model/config` 改读 `resolve_model_config`；`test_激活Provider后生效配置反映DB`（激活后 mode=real） | PASS |
| AC8 回归 | `tests/test_model_config_api.py`（3 项，契约兼容）、`test_agent_gateway.py`、`test_api.py`（fixture 改走 env 兜底）；后端全量 **200 passed / 1 skipped**（含越界修复后的 `test_monitoring.py` 4 项全绿）；前端 `typecheck`/`test`（63）/`build` 通过；迁移 upgrade→downgrade→upgrade 往返验证 | PASS |
| AC9 日志/Trace/响应/前端无明文 | 全 diff 敏感字面量扫描无 `sk-`/明文；无日志打印 Key；前端 `localStorage` 仅存 policy/current-model；掩码仅末 4 位（Key≥8 强制） | PASS |

## 实现说明（与 Design/plan 的一致性）

- **API Key 加密落库**：AES-256-GCM，主密钥 `OPERMIND_SECRET_KEY`（≥32 字符）走环境变量，HKDF 派生；密文 + nonce Base64 存 `model_providers`，无明文字段；主密钥缺失时保存 Key 返回 409，元数据仍可保存。
- **掩码展示**：接口仅返回 `has_api_key` 与 `masked_tail`（末 4 位），前端组合 `••••••••` + 末 4 位；短 Key 整体打码。
- **配置生效**：`resolve_model_config` 解析 DB 激活 Provider（优先）→ env/YAML 兜底；`build_v1_services` 每 Run 构造 LLM，保存/激活/删除后下一次 Run 生效；`GET /model/config` 与 `/health` 读取同一解析层，应用库不可用时回退 env（健康探针不崩）。
- **连接验证**：确定性受控 Connector，只发最小只读 `GET {base_url}/models`，5s 限时，SSRF 主机校验（非 localhost 拒绝私有/保留地址段，域名解析后复核），失败只返回脱敏分类码；verify 默认无 Token 消耗。
- **幂等**：POST create 要求 `Idempotency-Key`，24h 保留，过期键允许重新创建，同键不同载荷返回 409。
- **改动面偏差说明**：plan/Design 原列 `backend/src/config.py` 新增 `OPERMIND_SECRET_KEY` 读取，实现在 `src/infrastructure/secrets.py` 完成（功能等价，密钥逻辑集中在单一模块）；`config/config.example.yaml` 已补充文档化说明。

## 已知后续项（非阻塞，审查 P2/P3）

- P2 加固：verify 存在 DNS-rebinding TOCTOU（校验后到连接间存在改址窗口），已用 5s 限时 + 最小只读请求收窄爆炸半径；建议后续用 IP 固定传输 + `Host` 头。
- P3：新迁移无独立 downgrade 自动化测试（已手动验证 upgrade→downgrade→upgrade 往返）；`/health` 每探针查询应用库（错误已回退，建议后续为健康路径设独立超时）。
