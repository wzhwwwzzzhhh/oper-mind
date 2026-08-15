# P8-knowledge-document-pagination · AC 证据表

> 由 dev-execute 逐步回写；最终以独立子代理 review.md 的 PASS 与下列命令输出为准。

## 验证记录

| 项 | 命令 | 结果 |
|---|---|---|
| 后端聚焦测试 | `.venv\Scripts\python.exe -m pytest tests/test_knowledge_api.py tests/test_knowledge_service.py tests/test_knowledge_tool.py -q`（worktree backend/） | 45 passed, 1 skipped |
| 后端全量回归 | `.venv\Scripts\python.exe -m pytest tests -q` | 494 passed, 2 skipped |
| 后端 lint | `.venv\Scripts\python.exe -m ruff check`（本工作包 6 个改动文件） | All checks passed |
| 后端类型 | `.venv\Scripts\python.exe -m mypy`（本工作包 4 个 src 文件） | Success: no issues found |
| 前端类型 | `npm run typecheck`（frontend/） | EXIT 0 |
| 前端交互测试 | `npx vitest run src/features/knowledge/KnowledgePage.test.tsx` | 7 passed（含 2 个新增分页用例） |
| 前端全量测试 | `npm run test` | 本工作包用例全绿；App/Approvals/Audit/Models/Runs/ServiceCenter 既有失败 12 个，已在 pristine main（8a644f3）复现（14–23 个同类失败，运行间不稳定），与本工作包无关 |
| 前端构建 | `npm run build` | EXIT 0 |
| diff 门禁 | `git diff --check` | 干净 |
| 类型生成 | 后端 8000 起服务 + `npm run generate:api` | 重新生成，未手改 |

## AC 证据

| AC | 内容 | 证据 | 结论 |
|---|---|---|---|
| AC1 | 无分页参数返回首页（兼容既有） | routes.py 无参数调用；test_knowledge_api.py::test_无分页参数返回首页兼容既有调用；既有 test_列表接口返回受管文档清单 | ✅ |
| AC2 | 超过页大小分页返回、每页不超上限、不重不漏 | reader.list_documents_page 键集切片；test_knowledge_api.py::test_分页按页返回不重不漏且确定性排序；test_knowledge_service.py::test_分页按相对路径翻页不重不漏 | ✅ |
| AC3 | 超出最后一页返回空 items 与「无更多」语义，不抛错 | 应用服务超尾页 ok+空+None；test_knowledge_api.py::test_分页超出末尾返回空items与无更多语义；KnowledgePage.test.tsx 超尾页不误显空态 | ✅ |
| AC4 | 目录未配置返回 not_configured + 空列表（不变） | application 层 not_configured 分支不变；test_列表与详情接口目录未配置返回not_configured（含 page 断言） | ✅ |
| AC5 | 非法分页参数明确错误 | limit 超限/非法 → FastAPI 422；cursor 非法 → 400 INVALID_CURSOR；test_分页参数非法返回明确错误 | ✅ |
| AC6 | 确定性排序 | collect_docs 相对路径排序不变；test_分页按页返回不重不漏且确定性排序（重复请求一致） | ✅ |
| AC7 | 分页不含隐藏/凭据/sk- 文档 | 沿用 collect_docs + sk- 过滤；test_分页沿用排除逻辑不含隐藏凭据与sk内容 | ✅ |
| AC8 | 前端分页浏览，加载中/空态/失败态诚实展示 | KnowledgePage useInfiniteQuery + 加载更多 + 失败重试；KnowledgePage.test.tsx（分页浏览/失败重试/空态不误显） | ✅ |
| AC9 | 回归：知识库相关测试全绿 + typecheck/test/build | 上表验证记录；知识库测试 45 passed；typecheck/build 绿 | ✅ |

## 独立审查

- review.md：只读子代理产出 **PASS**（2026-08-15，无 P0/P1；2 项 P3 中 1 项已采纳修正：
  加载更多按钮错误态门控）。AC1–AC9 全部 ✅。
