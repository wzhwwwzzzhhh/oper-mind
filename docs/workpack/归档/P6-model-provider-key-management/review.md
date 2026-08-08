# 代码审查：P6-model-provider-key-management

> 审查方式：独立只读子代理（Explore），只读 diff 与文档，未写文件/改代码。
> 结论：**PASS**（无 P0/P1）。P2/P3 已按下方记录处理或作为后续项。

## 审查范围
- plan：`docs/workpack/P6-model-provider-key-management/plan.md`
- PRD：`docs/prd/model/P6-model-provider-key-management.md`（进行中）
- Design：`docs/design/model/P6模型Provider与APIKey管理Design.md`（已确认）
- 基线：`docs/产品定义.md` / `docs/路线图.md` / `docs/开发规范.md`
- 实现：worktree `feat/p6-model-provider-key-management` 相对 `main` 全量 diff（20 改 + 8 新增）

## 结论摘要
- 与 plan「只做」逐项对应，无漏项；「明确不做」均未越界，无过度实现。
- 安全红线通过：API Key 明文不落库/日志/响应/前端持久化；主密钥只走 `OPERMIND_SECRET_KEY` 环境变量；verify 只发最小只读请求、5s 限时、脱敏分类码、SSRF 主机校验；掩码仅末 4 位。
- `GET /model/config` 契约兼容（结构不变，改为 DB 优先解析，未激活时回退 env）。
- AC1–AC9 全部有代码与测试证据，见 `evidence.md`。
- 交付期补充（用户 2026-08-07 确认）：越界修复 `tests/test_monitoring.py` 硬编码观测时间（2026-08-05）导致的 CI 时间炸弹——非本工作包代码引入，但阻塞 CI 硬门禁；2 行改为动态时间，随交付提交一并纳入，与本工作包审查结论无关。

## 审查发现与处置

| 级别 | 发现 | 处置 |
|---|---|---|
| P2 | 编辑 Provider 后验证状态未重置，可能展示过期「连接正常」 | **已修复**：update 将 `verify_status` 重置为 `unknown`、清空 `last_verified_at`/`verify_error_code`，并补测试 |
| P2 | 前端「空串清除」不可达、表单文案误导 | **已修复**：新增「清除已保存的 API Key」显式开关，空输入=保持不变，文案改为「留空保持不变」 |
| P2 | Idempotency-Key TTL（24h）未生效、过期记录仍命中重放 | **已修复**：过期键删除旧记录并按新创建继续 |
| P2 | verify DNS-rebinding TOCTOU（校验后连接间改址窗口） | 接受（5s 限时 + 最小只读请求收窄半径），列入后续加固项 |
| P3 | `config.example.yaml` 未文档化 `OPERMIND_SECRET_KEY`；`config.py` 未按 plan 修改 | **已修复**：补充文档化说明；密钥读取实现在 `secrets.py`（功能等价，已记录偏差） |
| P3 | MSW activate handler 未回填 `active_endpoint` | **已修复**：按请求体 `endpoint` 回填 |
| P3 | 新迁移无独立 downgrade 自动化测试 | 手动验证 upgrade→downgrade→upgrade 往返；列入后续项 |
| P3 | `/health` 每探针查询应用库 | 接受（错误已回退），列入后续项 |

## AC 证据表
见 `docs/workpack/P6-model-provider-key-management/evidence.md`。

## 结论：PASS
P0/P1 不存在，P2/P3 已处理或如实记录，可进入提交与交付。
