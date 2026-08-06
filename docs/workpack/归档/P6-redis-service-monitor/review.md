# P6-redis-service-monitor · 独立审查

> 审查人：独立只读子代理（explore）
> 审查范围：`feat/redis-service-monitor` 分支全部改动（S1–S3）
> 结论：**PASS**（无 P0/P1）

## 1. 验证记录（只读执行）

| 验证项 | 结果 |
|---|---|
| 后端全量 `pytest tests -q` | 132 passed |
| AC10 指定回归 5 文件 | 26 passed |
| 前端 `npm run typecheck` | 通过 |
| 前端 `npm run test` | 58 passed（9 文件） |
| 前端 `npm run build` | 通过（仅既有 chunk 大小警告） |
| `git diff --check` | 干净（仅 generated.ts LF/CRLF 提示） |
| 敏感字面量扫描 | 无 DSN 明文 / 密码 / `sk-`；唯一 `OPERMIND_SERVICE_` 命中为测试负断言 |

## 2. 与 plan/PRD 映射结论

- **漏项**：无。AC1–AC11 均实现并有测试。
- **越界**：无。未动 mock 数据源、sessions 约束迁移、既有接口契约结构；Redis 调查诚实未启用。
- **过度实现**：无显著。ServiceCenterPage 动态 intent（原硬编码 `orders_slow_query.v1`）为计划内「避免误导性 intent」，但对既有 PG 服务调查入口行为有变更（见 P2-2）。

## 3. 分级问题

### P0（安全红线）
无。

### P1（功能/契约/越界）
无。

### P2（边界与降级等，非阻塞）
1. **`POST /services/{id}/sessions` 对无调查服务直接调用会 500**（`service_center.py` 不校验调查能力，Redis 落库撞 `sessions.service_id` CHECK 约束）。与 plan 决议「不放开约束、前端禁用」一致；`postgres-target` 同样模式，非本包独有。已记录为已知边界，不扩范围。
2. **前端动态 intent 改变既有 PG 入口**：`WorkbenchPage` 只识别 `orders_slow_query.v1`，改造后 PG 服务不再错误预填订单服务文案（有意为之），但预填消失。属计划内「避免误导性 intent」的必然结果，记录待交付确认。

### P3（风格/健壮性/文档）
1. 趋势卡片单行 JSX 与缩放 magic number（`ServiceDetailPage.tsx`）——延续既有风格，未改。
2. Redis `memory_bytes=null` 时仍画最小柱高——与既有 PG 图表行为一致，非本包独有。
3. `test_api.py` 补 redis `kind` 与 `not_configured` 直断（已补）。
4. `test_p4_service_center.py` 未清空 redis env 断言（已补 `monkeypatch.delenv`）。
5. 前端测试落在 `App.test.tsx` 而非独立页面测试文件——沿用仓库既有模式，覆盖满足。

## 4. AC 证据表

| AC | 证据 | 结果 |
|---|---|---|
| AC1 | `dependencies.py` 注册；`test_api.py` id/kind/not_configured 断言；`test_redis_connector.py` definition | PASS |
| AC2 | `redis_connector.py` 缺 DSN → not_configured；`test_redis_connector.py` | PASS |
| AC3 | 连接失败/超时/非法 DSN → unavailable；异常不外泄 | PASS |
| AC4 | server_metrics 三专用标量；未配置/不可用为 null | PASS |
| AC5 | 仅 PING/INFO/CLIENT/SLOWLOG；命令序列精确断言 | PASS |
| AC6 | 快照/接口无 DSN/env 名/密码/sk- | PASS |
| AC7 | MonitorSampler 采样 Redis；样本落库；history API 返回专用标量 | PASS |
| AC8 | 前端列表/详情复用 kind=redis 分支；未配置显示「未配置」 | PASS |
| AC9 | 专用标量字段；PG 语义字段对 Redis null；页面不冒充 PG 延迟 | PASS |
| AC10 | 全量 132 passed；指定 5 文件 26 passed | PASS |
| AC11 | 前端 typecheck/test/build 通过 | PASS |

## 5. 结论

**PASS**。安全边界（只读命令、凭据零外泄、诚实降级、不伪造调查入口）与「不做」清单均守约。P2 两项为已知边界/有意变更，已记录；P3 已部分修复，其余为既有风格一致性，不阻塞。
