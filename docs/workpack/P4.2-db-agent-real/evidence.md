# P4.2-db-agent-real · 验证证据

## 测试命令

| 命令 | 结果 |
|---|---|
| `..\\.venv\\Scripts\\python.exe -m pytest tests/test_db_tools_real.py tests/test_postgres_connector.py tests/test_p4_service_center.py tests/test_agent_gateway.py tests/test_tool_gateway.py -q` | 43 passed |
| `..\\.venv\\Scripts\\python.exe -m pytest tests -q` | 91 passed，1 个既有 httpx/Starlette 弃用警告 |
| `git diff --check -- <本工作包文件>` | 通过；仅有 Git 换行符提示 |

## AC 证据

| PRD 条目 | 代码/测试证据 | 结果 |
|---|---|---|
| AC1 mock 模式保持 | `test_mock模式保留原有Explain结果`；`_explain_mock` 保留原 `data/mock_db.py` 路径与格式 | PASS |
| AC2 无 DSN 降级 | `test真实模式无DSN返回未配置`；`_real_connection` 返回 None | PASS |
| AC3 连接失败降级 | `test连接失败返回不可用且不泄露异常`；真实分支捕获异常并返回中性文案 | PASS |
| AC4 非 SELECT 拒绝 | `test_explain拒绝非SELECT且不触库`、`test_explain拒绝多语句SELECT且不触库` | PASS |
| AC5 非法表名拒绝 | `test非法表名被拒绝且不触库`；标识符正则校验 | PASS |
| AC6 索引格式化 | `test_show_index格式化真实索引并使用参数化查询`；输出 indexname/indexdef | PASS |
| AC7 表不存在 | `test_show_index表不存在返回明确文案` | PASS |
| AC8 建表语句 | `test_show_create_table格式化列与约束`；输出 CREATE TABLE、约束、索引 | PASS |
| AC9 输出脱敏 | `test_gateway脱敏真实工具输出中的DSN`；网关 `desensitize` 测试 | PASS |
| AC10 回归 | 目标回归 43 passed；全量后端 91 passed | PASS |

## 未执行

- 未连接真实 PostgreSQL，符合 Design 中“不做真实库集成测试”的约束。
- 未执行 push、PR、合并；等待独立审查与交付阶段。
