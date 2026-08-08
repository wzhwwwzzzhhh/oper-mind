# P7-knowledge-page · AC 证据表

> 随提交推进逐条回写；证据 = 代码位置 + 测试输出 + 门禁结果。

## 验证记录

- 后端聚焦 S1：`python -m pytest tests/test_knowledge_api.py tests/test_knowledge_service.py tests/test_knowledge_tool.py tests/test_knowledge_agent.py -q` → 36 passed, 1 skipped
- 后端全量 S1：`python -m pytest tests -q` → **288 passed, 2 skipped**
- 前端 S2：`npm run typecheck` ✅、`npm run test`（78 passed）✅、`npm run build` ✅
- 生成类型：`openapi-typescript` 重新生成 `generated.ts`，`npm run typecheck` 通过
- 门禁：`git diff --check` 通过；`git diff -- data` 为空（mock 数据源零改动）；diff 中 `sk-` 字面量仅为测试夹具

## AC 证据表

| AC | 证据（代码/测试） | PASS/FAIL |
|---|---|---|
| AC1 未配置/不存在→未配置 | `routes.py` list/detail 未配置分支 + `KnowledgeReaderService.configured/root`；`test_列表与详情接口目录未配置返回not_configured`、`test_未配置目录返回not_configured`；前端 `list_empty_text`「知识库未配置」空态 | PASS |
| AC2 目录空→无文档 | `routes.py` `empty` 状态 + reader `list_documents`；`test_列表接口目录为空返回empty`、`test_目录为空返回empty`；前端「暂无文档」 | PASS |
| AC3 列表返回清单/进详情 | `routes.py` `GET /knowledge/documents` + `knowledge_document_resource`；`test_列表接口返回受管文档清单`；`KnowledgePage` 列表视图点击进详情；`KnowledgePage.test.tsx`「点击文档进入详情并返回列表」 | PASS |
| AC4 检索命中/排序/条数受限/无匹配 | `routes.py` `GET /knowledge/search` + reader `search_documents`；`test_检索接口命中返回匹配文档与片段`、`test_检索接口limit截断返回条数`、`test_检索接口无匹配返回no_match`、`test_检索接口非法检索词返回422`；前端检索框 + 结果列表 +「无匹配文档」空态；`KnowledgePage.test.tsx`「页面内检索命中」「无匹配」 | PASS |
| AC5 详情只读受管目录/路径逃逸拒绝 | `reader.read_document` resolve 根前缀 + 段级拒绝 + `_ILLEGAL_PATH_RE`；`test_详情接口路径逃逸被拒绝`、`test_详情接口非markdown被拒绝` | PASS |
| AC6 凭据文件不出现 | `reader.collect_docs`/`list_documents`/`read_document` 排除 + `"sk-" in text`；`test_凭据文件不进入列表检索与详情`、`test_含sk内容文档不进入列表检索与详情` | PASS |
| AC7 详情正文脱敏兜底 | `reader.read_document` 返回前 `desensitize()`；`test_详情接口返回脱敏正文`、`test_检索与列表结果不含凭据明文` | PASS |
| AC8 导航入口可访问 /knowledge + 来源标注 | `GlobalNav` `docs` 启用（`go('docs')`→`/knowledge`）、`chat` 排除 `/knowledge`；`App.tsx` `/knowledge` 路由 + `is_operations` 扩展；`ServiceContextNav` knowledge 分支 + 「受管知识目录 · 只读」；`KnowledgePage` 顶部与检索区来源标注；`KnowledgePage.test.tsx`「导航入口可用并渲染文档列表与来源标注」 | PASS |
| AC9 请求失败→失败空态可重试 | `KnowledgePage` `isError` + `refetch` 重试按钮；`KnowledgePage.test.tsx`「列表读取失败时显示失败空态并可重试」（MSW 500） | PASS |
| AC10 回归：mock 评测不变 / P6 Tool 行为不变 / 既有测试全绿 | `SearchKnowledgeTool` 改用共享 reader 输出格式不变（`test_knowledge_tool.py`/`test_knowledge_agent.py` 全绿）；`git diff -- data` 为空；后端全量 288 passed；前端 78 passed + typecheck + build | PASS |

## DoD 核对

- [x] 全部 AC（AC1–AC10）通过
- [ ] 全量回归终验（S3 收尾后回填最终数字）
- [x] `git status` 只出现本 PRD 允许的文件（他人 P7 Design 文件按隔离清单排除）
- [x] 未新增数据库迁移 / 持久化 / 凭据
- [x] 未打印/记录 DSN，未含凭据，未改 mock 数据源
- [x] 检索与详情均只读受管目录，凭据文件被排除（测试锁定）
