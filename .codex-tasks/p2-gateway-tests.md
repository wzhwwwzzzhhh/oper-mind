# 任务：为 ToolGateway 编写 pytest 测试套

## 唯一目标
为已实现的 `backend/src/core/tool_gateway.py` 编写单元测试，覆盖网关六道关与脱敏。

## 只允许创建/修改这一个文件
`backend/tests/test_tool_gateway.py`

**严禁触碰任何其他文件**（不改 tool_gateway.py、不改任何 src 代码、不改 conftest、不改依赖）。
若你认为被测代码有 bug，**不要修它**，在测试里用注释标注 `# 疑似缺陷:` 即可。

## 被测 API（照此调用，不要臆测）
- `from src.core.tool_gateway import ToolGateway, GatewayResult, ToolInvocation, desensitize`
- `from src.core.tool_registry import ToolRegistry, Tool`
- 构造：`ToolGateway(registry: ToolRegistry, timeout_seconds: float = 10.0)`
- 调用：`gw.invoke(name: str, arguments: str) -> GatewayResult`（`arguments` 是 JSON 字符串）
- `GatewayResult.output: str`（脱敏后的工具输出）
- `GatewayResult.record: ToolInvocation`，字段：`tool: str`、`status: Literal["ok","rejected","timeout","error"]`、`started_at: str`、`duration_ms: int`、`detail: str`
- `desensitize(text: str) -> str`
- 记得 `gw.shutdown()` 释放线程池（可用 pytest fixture 的 teardown）

## 必须覆盖的用例（每条一个测试函数，中文 docstring）
1. 调用未注册工具 → `status == "rejected"`
2. 缺必填参数 → `status == "rejected"`
3. 非法 JSON 字符串（如 `"{bad"`）→ `status == "rejected"`
4. 参数是 JSON 但非对象（如 `"[]"`）→ `status == "rejected"`
5. 参数类型错误（Schema 声明 string 却传 int）→ `status == "rejected"`
6. 正常调用 → `status == "ok"` 且 `output` 含工具真实返回内容
7. 脱敏：工具返回含 `password=hunter2`、`sk-abcdef123456`、连接串 `pg://user:pass@host` → `output` 中三者均被替换，**不得出现原始明文**
8. 超时：工具 `execute` 内 `time.sleep(1)`、`timeout_seconds=0.2` → `status == "timeout"`
9. 工具内部抛异常 → `status == "error"` 且 `output`/`detail` **不含原始异常堆栈或异常消息原文**（安全：不外泄异常详情）
10. 记录完整性：任一成功调用的 `record.duration_ms >= 0`、`record.tool` 等于被调工具名、`record.detail` 不含上面任何敏感明文

## 测试自建桩工具
在测试文件内定义继承 `Tool` 的最小桩类（如 EchoTool / SlowTool / BoomTool），**不要**依赖 src 里已有工具或 mock 数据源。

## 验收
`pytest tests/test_tool_gateway.py -q` 全绿。测试要真断言行为，不许写 `assert True` 凑数。
