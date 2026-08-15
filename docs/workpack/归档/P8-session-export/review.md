# P8-session-export · 独立代码审查

> 审查者：独立只读子代理（dev-execute Phase 4，与开发视角分离）
> 日期：2026-08-15
> 范围：S1 后端导出接口 + S2 前端导出入口 全量 diff

## 总体：PASS（无 P0 / P1）

P0（凭据泄露 / 未白名单写 / 破坏性改动 / mock 冒充真实）与 P1（漏 AC、契约破坏、越界）均未发现：
导出为纯只读聚合、只含既有公开投影子集 + `desensitize()` + 连接串兜底，失败 Run 错误收敛为白名单
安全文案，无导出时间戳（AC7），空态诚实（AC4），503 不落半截文档（AC5），application service 经
`SessionExportStore` Protocol 端口注入（无新增 infrastructure 直连），前端测试用显式 MSW mock。

## 发现与处置

| 级别 | 问题 | 处置 |
|---|---|---|
| P2 | 构建步骤原在 try 之外，异常会走 500 而非 Design §2.4 声明的 503 | ✅ 已修：读取与构建同 try，`(SQLAlchemyError, ValueError)` 统一映射 503 |
| P2 | 逐 Run `get_result` 最坏 200 次查询（N+1），Design 明确接受 | ✅ 已记录取舍于 evidence.md；与已确认 Design §2.1 一致，不改 |
| P3 | `_safe_export_run_error` 两分支同常量（死检查）且与 resources 手动重复 | ✅ 已修：收敛为单返回值函数 + 同步注释 |
| P3 | docstring「所有文本字段过 desensitize()」与 service_id 实际未过不符 | ✅ 已修：收敛措辞，说明 service_id 沿用既有投影口径 |
| P3 | 导出路由 `apply_headers(response, meta)` 对注入对象无效（随后返回新 Response） | ✅ 已修：移除无效调用与未用参数，新 Response 显式携带 X-Request-Id |
| P3 | plan「docs/prd/ 不动」与实际状态翻片偏差 | ✅ 已修：plan 澄清「内容不改，仅状态翻片登记」 |
| P3 | generated.ts 把 export 200 描述为 application/json（生成器默认） | ✅ 已记录于 evidence.md；禁止手编，客户端 `request_text` 不依赖 |

## AC 证据表

| AC | 证据 | 结论 |
|---|---|---|
| AC1 | `build_session_export_markdown` 头部+时间线 + `test_导出包含会话标题与消息时间线` | PASS |
| AC2 | `_run_summary_block` 含 query/status/severity/confidence/summary/证据摘要 + `test_导出包含Run结论摘要` | PASS |
| AC3 | `SessionNotFoundError`→404 + `test_会话不存在返回404` | PASS |
| AC4 | `empty=True`+「无可导出内容」+ 前端空态不发请求 + 前后端两测试 | PASS |
| AC5 | `SessionExportUnavailableError`→503 + `test_读取失败返回503` | PASS |
| AC6 | 投影子集 + `desensitize()` + 连接串兜底 + `test_导出不含敏感内容` | PASS |
| AC7 | 文档仅稳定字段 + `test_重复导出一致`（字节相等） | PASS |
| AC8 | `request_text`/`export_session_markdown` + 工具栏/失败重试/空态 + `session-export.test.tsx` 3 用例 | PASS |
| AC9 | 后端全量 496/2 + 聚焦 8 pass + 前端 typecheck/新增用例 3 pass | PASS（前端全量 test 的既有 flaky 见 evidence.md） |

## 结论

**PASS**。P2/P3 完善项已全部落实，AC1–AC9 证据闭环。
