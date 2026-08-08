# P7-knowledge-page · 独立审查

> dev-execute Phase 4 由 readonly 子代理独立审查产出；首轮 FAIL → 修复 → 复审 PASS。

## 首轮审查（FAIL，P1×3）

- [P1] 列表/检索的标题与命中片段未过 `desensitize()`：非 `sk-` 凭据（连接串、`password=`）可经接口响应流出，违反 Design §2.1/§2.5。
- [P1] 检索接口接受纯空白检索词并返回全部文档（应 422），契约破坏 + 意外全量返回。
- [P1] `KnowledgePage.tsx` 在真实 tsconfig（strict）下有 20 个 TS 错误（绕过既有 `read_items` 防御式读取）；`npm run typecheck`（根 `files: []`）空转，`tsc -b` 构建失败，AC10「前端 typecheck/build 全绿」未达成。

## 修复

- 资源映射层对 title/snippets 统一 `desensitize()`（`resources.py`），`read_document` 详情正文本就脱敏；
  `test_检索与列表结果不含凭据明文` 改为非 `sk-` 凭据 + 正文词命中实际生成片段并断言不泄漏。
- `search_knowledge` 对 `query.strip()` 后为空或含路径分隔符/控制字符一律 422；新增 `test_检索接口纯空白检索词返回422`。
- `KnowledgePage.tsx` 改用 `read_items`/`resource_string`/`resource_optional_string`/`read_array`/`resource_value`
  防御式读取；`tsc -b` 退出码 0，`npm run test` 知识页 5/5 通过。
- 附带补强：URL 编码穿越测试、reader 层直接路径逃逸测试、尾斜杠契约测试（404 契约）、
  `_knowledge_service` 返回类型 `| None`、`KNOWLEDGE_DOCUMENT_NOT_FOUND` 注册进状态映射。

## 复审（PASS）

- P1-1 凭据脱敏：PASS（资源映射层覆盖 title+snippets，非空洞测试锁定）。
- P1-2 空白检索词：PASS（strip 后为空 → 422，测试覆盖 `"   "`/`"\t\n"`）。
- P1-3 前端 TS 构建：PASS（`tsc -b` 退出码 0，知识页测试 5/5）。
- P2 附带项：全部 PASS（URL 编码穿越、reader 层路径逃逸、尾斜杠契约、非空洞脱敏测试）。
- 新回归：无。后端全量 298 passed, 2 skipped（skip 为既有符号链接环境跳过）；前端 78 passed + `tsc -b` + build 全绿。

## 结论：PASS

无 P0/P1 未决；越界文件检查通过（仅本工作包文件 + PRD/Design/workpack 文档）；
`git diff -- data` 为空；无凭据、无裸 except、无新增生产 print。
