# P6-knowledge-retrieval · AC 证据表

> 随提交推进逐条回写；证据 = 代码位置 + 测试输出 + 门禁结果。

## 验证记录

- 后端聚焦：`..\.venv\Scripts\python.exe -m pytest tests/test_knowledge_tool.py tests/test_knowledge_agent.py tests/test_tool_gateway.py -q` → **34 passed**
- 后端全量：`..\.venv\Scripts\python.exe -m pytest tests -q` → **139 passed**
- 前端回归：`npm run typecheck` ✅、`npm run test`（55 passed）✅、`npm run build` ✅
- 门禁：`git diff --check` 通过；`git diff -- data` 为空（mock 数据源零改动）；diff 中 `sk-`/password 字面量均为测试夹具（与既有 `test_tool_gateway.py` 惯例一致）
- 独立审查：首轮 FAIL（P1 隐藏文件未排除 + P2×2）→ 修复后复审 **PASS**

## AC 证据表

| AC | 证据（代码/测试） | PASS/FAIL |
|---|---|---|
| AC1 未配置/不存在→未配置 | `knowledge_tools.py` execute 空态分支；`test_未配置知识目录返回未配置状态`、`test_knowledge_dir缺失时返回未配置` | PASS |
| AC2 空目录→无文档 | `knowledge_tools.py`「知识目录为空，无 Markdown 文档」；`test_knowledge_dir为空时返回无文档` | PASS |
| AC3 命中摘要/排序/limit | `_match_docs` 标题优先+命中次数+标题名升序、limit 1–10；`test_命中返回标题文件名与摘要`、`test_标题匹配优先于正文命中`、`test_limit截断返回条数` | PASS |
| AC4 无匹配→无匹配文档 | `knowledge_tools.py`「无匹配：…」；`test_无匹配时返回无匹配文档`、`test_点目录查询不作为路径访问` | PASS |
| AC5 只读目录/路径逃逸拒绝 | 参数校验拒 `/`、`\`、控制字符；`resolve().relative_to(root)` 越界跳过；`test_路径分隔符查询被拒绝`、`test_符号链接越界不进入检索范围` | PASS |
| AC6 凭据文件排除 | `_EXCLUDED_SUFFIXES`/`_EXCLUDED_FILENAMES` + `"sk-" in text` 跳过 + 网关脱敏兜底；`test_凭据文件不在检索范围`、`test_命中摘要不含凭据经过网关脱敏` | PASS |
| AC7 网关白名单/限时/脱敏/进上下文 | `KnowledgeAgent` 注册 + bootstrap 装配 + 网关六道关；`test_search_knowledge经网关白名单准入`、`test_knowledge_agent_检索结果进入Agent上下文` | PASS |
| AC8 Trace 只展示脱敏摘要 | 网关 detail=`audit_summary()` 且过 `desensitize`；`test_knowledge_tool经网关后记录脱敏审计摘要`、`test_审计摘要仅含命中标题不含全文`、`test_audit_summary反映最近一次结果` | PASS |
| AC9 mock 不受影响/回归全绿 | `git diff -- data` 为空；`test_keyword_s1_s4路由结果不变`；后端 139 passed；前端三项通过 | PASS |

## DoD 核对

- [x] 全部 AC（AC1–AC9）通过
- [x] 相关回归测试全绿（后端 139 / 前端 55）
- [x] `git status` 只出现本 PRD 允许的文件（他人文件按隔离清单排除）
- [x] 未新增公开 API / 数据库迁移 / 凭据
- [x] 未打印/记录 DSN，未含凭据，未改 mock 数据源
- [x] 检索工具只读受管目录，凭据文件被排除（测试锁定）
