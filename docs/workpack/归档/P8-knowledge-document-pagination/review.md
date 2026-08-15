# P8-knowledge-document-pagination · 独立审查结论（dev-execute Phase 4）

> 审查者：只读子代理（与实现者视角分离）；审查时间：2026-08-15。
> 审查输入：plan.md、PRD（AC1–AC9）、Design（已确认）、`git diff`（工作区未提交改动 + 已提交 docs commit f965547）、
> 参考实现（WorkbenchPage useInfiniteQuery、list_session_runs 等既有分页端点）。审查过程未修改任何文件。

# 代码审查：P8-knowledge-document-pagination

总体：**PASS**（无 P0/P1，仅 P3 级意见，不阻断）

## 发现

- [P3] 命名一致性（后端）：`list_documents_page` 的 cursor 字段是 `relative_path`，而
  `KnowledgeDocumentMeta` 条目字段是 `relative_name`，同域模块两套命名。但 Design 2.1 明确规定
  cursor 字段名为 `relative_path`（opaque base64 编码、客户端不可依赖），非实现偏离。
- [P3] 前端翻页失败时 UX：`hasNextPage` 与「加载更多失败 ←重试」可同时出现（按钮与重试都能重试
  同一页）。功能正确（按钮 disabled 于 `isFetchingNextPage`，不会重复分派），仅冗余。
  → **已采纳**：加载更多按钮增加 `!list_query.isError` 门控，错误态下只展示失败提示 + 重试。
- [P2]（信息性）`list_documents_page` 内 `limit = max(1, limit)` 为防御性 no-op（API `Query(ge=1)`
  与应用层已保证 `>=1`），无害，符合 reader 为独立底座的职责。

未发现 P0/P1：diff 无凭据/`sk-` 明文、无写操作/破坏性改动、MSW 为测试桩非实况冒充、无越界文件、
search/单篇契约未动、AC1 无参数调用返回首页。

## 特别核对结论

- **键集语义**：跳过 `<= cursor`（严格大于）、limit 截断、满 limit 时 next_cursor=最后一条、
  未满/超尾页空 items+None —— 正确，AC2/AC3/AC6 一致。
- **status 语义**：`not_configured` 不变；`empty` 仅当 cursor 为 None 且无文档；超尾页 `ok`+空+None —— 正确。
- **API 契约**：cursor 非法→400 INVALID_CURSOR（复用 parse_page_cursor→decode_cursor 模型校验）；
  limit 越限/非法→FastAPI 422；响应 `page: CursorPage{next_cursor,has_more}` 与既有分页端点同构；
  `CursorT` union 已加 `KnowledgeDocumentCursor` 并补 import。
- **排除逻辑**：逐页沿用 `collect_docs`（隐藏/凭据/越权）+ `sk-`/空过滤；cursor 仅作字典序比较、
  绝不参与文件访问（无穿越面）。
- **前端**：`useInfiniteQuery` 与 WorkbenchPage 完全同构；`generated.ts` 与后端 schema 一致且为
  自动生成产物，无手改痕迹；`list_knowledge_documents_query` 删除无残留引用。
- **越界文件**：改动文件全在计划改动面内；`git diff --check` 干净。

## AC 证据表

| AC | 内容 | 证据 | 结论 |
|---|---|---|---|
| AC1 | 无参数返回首页兼容 | `test_无分页参数返回首页兼容既有调用`；既有列表接口测试（含 page 断言） | ✅ |
| AC2 | 超页分页、不重不漏、不超上限 | `test_分页按页返回不重不漏且确定性排序`、`test_分页按相对路径翻页不重不漏` | ✅ |
| AC3 | 超尾页空 items + 无更多不抛错 | `test_分页超出末尾返回空items与无更多语义`；KnowledgePage.test 超尾页不误显空态 | ✅ |
| AC4 | 未配置 not_configured + 空 | `test_列表与详情接口目录未配置返回not_configured`（含 page.has_more=false） | ✅ |
| AC5 | 非法参数明确错误 | `test_分页参数非法返回明确错误`（limit→422 / cursor→400 INVALID_CURSOR） | ✅ |
| AC6 | 确定性排序 | `test_分页按页返回不重不漏且确定性排序`（重复请求一致） | ✅ |
| AC7 | 不含隐藏/凭据/sk- | `test_分页沿用排除逻辑不含隐藏凭据与sk内容` | ✅ |
| AC8 | 前端分页 + 诚实三态 | KnowledgePage useInfiniteQuery + 加载更多 + 失败重试 + 空态门控；KnowledgePage.test.tsx | ✅ |
| AC9 | 回归 + typecheck/test/build | evidence.md：后端 45 passed / 全量 494 passed；typecheck、build EXIT 0；本包 7 用例全绿 | ✅ |

## 结论

**PASS** —— 实现与 plan/PRD/Design 完全映射，AC1–AC9 全部以正确实现 + 测试证据达成，无 P0/P1；
仅 2 项 P3 风格性意见（其中 1 项已采纳修正），不阻断合并。
