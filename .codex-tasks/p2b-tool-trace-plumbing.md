# 任务 P2-B：把工具调用审计记录串成 tool_invoked 运行事件（后端管道）

## 背景（只读）
P2-A 已让 `BaseAgent` 每次工具调用产出 `ToolInvocation` 记录，可用
`agent.get_tool_invocations()` 取回（返回 `list`，每项字段：
`tool: str`、`status: str`（取值 `ok/rejected/timeout/error`）、
`started_at: str`、`duration_ms: int`、`detail: str`（已脱敏的简要说明））。

数据库迁移已由我完成并验证：`run_events.type` 现已放行 `tool_invoked`（不要动迁移/模型）。

本任务把这些记录**串进现有 Trace 管道**，最终让执行器输出 `tool_invoked` 安全事件。
**纯后端管道，不碰前端、不碰迁移、不碰 models.py、不碰 tool_gateway.py / agent.py。**

## 只允许修改/创建这些文件
1. 改 `backend/src/domain/diagnosis.py`
2. 改 `backend/src/core/graph.py`
3. 改 `backend/src/core/coordinator.py`
4. 改 `backend/src/infrastructure/diagnosis/coordinator_executor.py`
5. 改 `backend/src/application/services.py`
6. 建 `backend/tests/test_p2b_tool_trace.py`

**严禁触碰其他任何文件。** 若认为被测代码有 bug，不要修，在测试里 `# 疑似缺陷:` 标注。

---

## 改动 1：domain/diagnosis.py —— 枚举加一个值
在 `class RunEventType` 里，`RUN_CANCELLED = "run_cancelled"` 之后加一行：
```python
    TOOL_INVOKED = "tool_invoked"
```

---

## 改动 2：graph.py —— 节点收集工具记录塞进 trace
在文件里合适位置（如工具函数区）新增一个 helper：
```python
def _tool_traces(agent) -> list[dict]:
    """把一个 Agent 本次 run 的工具调用审计记录转成 trace 事件字典。"""
    getter = getattr(agent, "get_tool_invocations", None)
    records = getter() if callable(getter) else []
    return [
        {
            "node": "tool",
            "detail": r.detail,
            "status": r.status,
            "duration_ms": r.duration_ms,
        }
        for r in records
    ]
```

然后在三个节点里，**在该 agent 跑完之后、追加该节点自身 trace 之前**插入工具 trace：

- `direct_node`：`thinking = ...` 那行之后、`trace = trace + [{"node": "direct", ...}]` 之前，加：
  ```python
          trace = trace + _tool_traces(agent)
  ```
  （注意缩进：它在 `else:` 分支内，与 `agent = agents[target]` 同级。`target not in agents`
  的分支没有 agent，不要加。）

- `chain_node`：循环体内 `thinking_map[name] = ...` 之后、`context += ...` 之前，加：
  ```python
            trace = trace + _tool_traces(agent)
  ```

- `parallel_node`：把内部 `_run` 改为在线程内一并取回工具 trace，避免竞态：
  ```python
      def _run(name):
          agent = agents[name]
          res = agent.run(query)
          think = agent.get_thinking() if hasattr(agent, "get_thinking") else []
          tools = _tool_traces(agent)   # 线程内取，防止 run 后状态被覆盖
          return name, res, think, tools

      results, thinking_map = {}, {}
      with ThreadPoolExecutor(max_workers=max(1, len(names))) as pool:
          for name, res, think, tools in pool.map(_run, names):
              results[name] = res
              thinking_map[name] = think
              trace = trace + tools
  ```

---

## 改动 3：coordinator.py —— 映射类型 + 保留结构化字段
### 3a. 类型映射
`_EVENT_TYPE_BY_NODE` 字典里加一项：
```python
    "tool": "tool_invoked",
```

### 3b. TraceRecord 增可选字段
顶部 import 处加（与现有 typing 导入并列，用 typing_extensions 兼容各版本）：
```python
from typing_extensions import NotRequired
```
把 `class TraceRecord(TypedDict):` 改为带两个可选字段：
```python
class TraceRecord(TypedDict):
    """标准化后的诊断编排事件。"""

    type: str
    node: str
    detail: str
    timestamp: str
    status: NotRequired[str]        # 仅 tool_invoked 事件携带
    duration_ms: NotRequired[int]   # 仅 tool_invoked 事件携带
```

### 3c. `_normalize_trace` 为 tool 事件保留 status/duration_ms
把方法体改为（在构造 record 后，对 tool 节点补两个字段）：
```python
    def _normalize_trace(self, raw_trace: list[dict[str, Any]]) -> list[TraceRecord]:
        """补全 API 事件需要的类型与时间戳，同时兼容旧 trace 字段。"""
        normalized: list[TraceRecord] = []
        for event in raw_trace:
            node = str(event.get("node", "unknown"))
            record: TraceRecord = {
                "type": _EVENT_TYPE_BY_NODE.get(node, "report"),
                "node": node,
                "detail": str(event.get("detail", "节点已完成")),
                "timestamp": str(event.get("timestamp") or self._timestamp()),
            }
            if node == "tool":
                status = event.get("status")
                if isinstance(status, str):
                    record["status"] = status
                duration = event.get("duration_ms")
                if isinstance(duration, int) and not isinstance(duration, bool):
                    record["duration_ms"] = duration
            normalized.append(record)
        return normalized
```

---

## 改动 4：coordinator_executor.py —— 为工具事件填 data
现在 `stream()` 构造 `DiagnosisExecutionEvent` 时没有传 `data`。改成传 `data=_event_data(event)`：
```python
                if event_type is not None:
                    yield DiagnosisExecutionEvent(
                        type=event_type,
                        node=_safe_node(event.get("node")),
                        occurred_at=_parse_timestamp(event.get("timestamp")),
                        data=_event_data(event),
                    )
```
并在模块内新增 helper（放在 `_event_type` 附近）：
```python
def _event_data(event: dict[str, Any]) -> dict[str, Any]:
    """仅为工具事件构造安全 data；其余事件保持空 data，维持既有行为。"""
    if str(event.get("type")) != "tool_invoked":
        return {}
    data: dict[str, Any] = {}
    detail = event.get("detail")
    if isinstance(detail, str) and detail:
        data["summary"] = detail[:280]
    status = event.get("status")
    if isinstance(status, str):
        data["status"] = status
    duration = event.get("duration_ms")
    if isinstance(duration, int) and not isinstance(duration, bool):
        data["duration_ms"] = duration
    return data
```

---

## 改动 5：services.py —— status 白名单接纳网关状态
`_safe_event_data` 里那句 status 白名单：
```python
    if status in {"running", "completed", "failed", "skipped"}:
```
改为（并入网关四态）：
```python
    if status in {"running", "completed", "failed", "skipped", "ok", "rejected", "timeout", "error"}:
```
**只改这一处集合，其余不动。**

---

## 测试 `backend/tests/test_p2b_tool_trace.py`（不依赖数据库）
用真断言覆盖两个安全关键接缝：

### A. coordinator_executor 正确产出 tool_invoked 事件且不泄敏
构造一个假 coordinator（一个有 `route_stream(self, query)` 方法的最小类），
让它 yield：
1. 一条 trace 项：
   ```python
   {"kind": "trace", "event": {
       "type": "tool_invoked", "node": "tool",
       "detail": "调用 explain_sql 成功", "status": "ok",
       "duration_ms": 7, "timestamp": "2026-08-02T00:00:00+00:00"}}
   ```
2. 一条 complete 项：`{"kind": "complete", "strategy": "direct", "result": "报告正文"}`

用 `CoordinatorDiagnosisExecutor(lambda: fake)` 包装，迭代 `.stream("q")`，断言：
- 产出的第一个 `DiagnosisExecutionEvent` 的 `type == RunEventType.TOOL_INVOKED`
- 其 `data["summary"] == "调用 explain_sql 成功"`、`data["status"] == "ok"`、`data["duration_ms"] == 7`
- 再补一条：detail 含敏感明文（如 `"sk-abcdef123456"`）时——注意：此路 detail 已是上游脱敏后的，
  这里断言 executor **不会新增**泄漏即可；用一条正常 detail 验证 data 组装正确即可，不强求脱敏。
- 非工具事件（如 `type="route_decided"` 的 trace 项）产出的事件 `data == {}`（保持既有行为）。

被导入的符号：
```python
from src.infrastructure.diagnosis.coordinator_executor import CoordinatorDiagnosisExecutor
from src.application.contracts import DiagnosisExecutionEvent, DiagnosisExecutionResult
from src.domain.diagnosis import RunEventType
```

### B. services `_safe_event_data` 保留网关状态与摘要
```python
from src.application.services import _safe_event_data
from src.application.contracts import DiagnosisExecutionEvent
from src.domain.diagnosis import RunEventType
from datetime import datetime, timezone
```
构造一个 `DiagnosisExecutionEvent(type=RunEventType.TOOL_INVOKED, node="tool",
occurred_at=datetime.now(timezone.utc), data={"summary": "调用 x 成功", "status": "ok", "duration_ms": 7})`，
调用 `_safe_event_data(event)`，断言返回 dict 里 `summary/status/duration_ms` 都被保留、
`status == "ok"`。再构造一个 `status="rejected"` 的，断言 `rejected` 也被保留。

### C. coordinator `_normalize_trace` 为 tool 事件保留结构化字段
```python
from src.core.coordinator import CoordinatorAgent
```
构造 `CoordinatorAgent(llm=object())`（不驱动图，只调用方法），
调 `agent._normalize_trace([{"node": "tool", "detail": "调用 x 成功", "status": "ok", "duration_ms": 7}])`，
断言结果第一项 `type == "tool_invoked"`、`status == "ok"`、`duration_ms == 7`；
再传一条 `{"node": "route", "detail": "x"}`，断言其结果**没有** `status`/`duration_ms` 键。

---

## 验收（用带 alembic 的 venv 解释器跑，见下）
```
../.venv/Scripts/python.exe -m pytest tests/test_p2b_tool_trace.py -q
../.venv/Scripts/python.exe -m pytest tests/test_agent_gateway.py tests/test_tool_gateway.py -q
```
两条都要全绿。若你的环境跑不动带数据库的 P2 套件（需要 alembic），不必强跑，我会在审查时用 venv 补跑
`tests/test_p2_application_services.py`、`tests/test_p2_diagnosis_adapter.py` 验证无回归。
不许 `assert True` 凑数。`git status` 只应出现上面允许的 6 个文件。

## 完成后
**不要 commit。** 停下并告诉我"P2-B 完成"，我审 diff + 用 venv 跑全套后自己提交。
