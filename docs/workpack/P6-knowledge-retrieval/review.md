# P6-knowledge-retrieval · 独立审查

> dev-execute Phase 4 由只读子代理审查产出；结论已获确认。

## 结论

**PASS**（首轮 FAIL → 修复后复审 PASS）

## 首轮问题与修复

### P1（必须修复）
- 隐藏文件/隐藏目录未排除，`.hidden.md`、`.notes/secret-ops.md` 会被检索返回，违反 Design §2.3 与决策 #3。
  - 修复：`knowledge_tools.py` 新增 `_has_hidden_part()`，`_collect_docs` 对含点号开头的路径段一律排除；新增测试 `test_隐藏文件与隐藏目录不在检索范围`。

### P2
- `audit_summary()` 在无匹配/拒绝调用后返回陈旧命中摘要，影响 Trace 诚实性。
  - 修复：新增 `_finish()` 统一回写 `_last_summary`，覆盖全部返回分支；新增测试 `test_audit_summary反映最近一次结果`。
- 符号链接越界仅代码防护、缺测试锁定。
  - 修复：新增测试 `test_符号链接越界不进入检索范围`（实际执行通过，非 skip）。

## 复审问题（均无 P0/P1/P2）

- P3：关键词兜底路由优先级 db > server > log > knowledge，PRD 用户故事在 mock 兜底模式下路由到 db 而非 knowledge——这是遵循 Design「knowledge 在 log 之后判定、不破坏 S1–S4 既有路由」的刻意取舍，真实 LLM 路径不受影响。

## AC 证据表

| AC | 证据 | PASS/FAIL |
|---|---|---|
| AC1 | 未配置/不存在 → 未配置（`execute` 空态 + 两测试） | PASS |
| AC2 | 空目录 → 无 Markdown 文档（测试） | PASS |
| AC3 | 命中摘要/相关度排序/limit 截断（`_match_docs` + 三测试） | PASS |
| AC4 | 无匹配 → 无匹配文档（测试） | PASS |
| AC5 | 路径逃逸拒绝/只读/符号链接越界（测试锁定） | PASS |
| AC6 | 凭据文件排除（文件名 + `sk-` 内容 + 网关脱敏，测试） | PASS |
| AC7 | 网关白名单/限时/脱敏/进上下文（Agent + 网关测试） | PASS |
| AC8 | Trace 只展示脱敏摘要（audit_summary 过 desensitize，测试） | PASS |
| AC9 | mock S1–S4 不受影响、后端 139/前端 55 全绿（`git diff -- data` 为空） | PASS |

## 验证命令

- 聚焦：`pytest tests/test_knowledge_tool.py tests/test_knowledge_agent.py tests/test_tool_gateway.py -q` → 34 passed
- 全量：`pytest tests -q` → 139 passed
- 前端：typecheck / test(55) / build 通过；`git diff --check` 干净
