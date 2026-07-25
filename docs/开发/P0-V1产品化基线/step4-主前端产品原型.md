# P0 Step4 — 主前端产品原型

> 日期：2026-07-25　|　状态：已完成并提交　|　基线提交：`a55b709 docs: 完成P0.3 API契约草案`

## Design

用户授权读取并编辑 `frontend/mockup.html` 后，先审计了原型：原页面是阶段一 M7 风格的深色诊断控制台，优势是紧凑、清晰的运维信息密度；问题是把完整 Trace 时间线和 M5 实验指标放在视觉中心，且仍写阶段一 `/diagnose/stream`，不符合 V1 产品的结果优先和 API v1 契约。

P0.4 保留专业运维工作台的克制样式，重构为三层信息优先级：

1. 当前会话、环境与用户问题；
2. `DiagnosisResult` 的根因、置信度、证据、影响、建议、风险和审批需求；
3. Run/协作摘要与受控的 `report/` 完整 Trace 入口。

所有内容是 API v1 契约示例数据，不声明 Session、Run、SSE、审批、环境或告警能力已接通。

## Step

1. 阅读 P0 HANDOFF、P0.3 API 契约与现有未跟踪 `frontend/mockup.html`。
2. 把 Trace 主导布局改为会话工作台：左侧会话/诚实空状态，中间结构化结果，右侧环境、Run、协作摘要和审批状态。
3. 将成功、运行中、失败、空状态做成静态交互切换；创建按钮仅切换到运行中状态，不发起网络请求。
4. 在运行中状态展示 `Last-Event-ID` / `after_sequence` 恢复语义，不展开完整 Trace 时间线。
5. 检查响应式 CSS、脚本语法、必需契约术语和暂存边界；记录浏览器本地预览受限事实。

## Code

- `frontend/mockup.html:1`：单页高保真原型，包含 Session、Run、DiagnosisResult、Evidence、Approval 和诚实空状态。
- `frontend/mockup.html:154`：成功/运行中/失败/空状态的静态状态开关与可见性规则。
- `frontend/mockup.html:616`：运行中状态表达最后事件序号与恢复语义，完整 Trace 只提供 `report/` 受控入口。
- `frontend/mockup.html:648`：仅前端状态切换脚本；不执行 fetch、SSE、路由跳转或任何后端调用。

## Visual QA

- 桌面布局：三列为 `252px / 主工作区 / 294px`；宽度小于 `1100px` 时隐藏右栏并把结果改为单列；宽度小于 `760px` 时隐藏会话栏、保留状态切换和单列结果区。
- 文本约束：长 Run ID 使用省略；卡片标题、建议、证据和空状态均允许换行；按钮在窄屏可换行或占满可用宽度。
- 交互检查：成功、运行中、失败、空状态可切换；“创建诊断 Run”只切换到运行中；完整 Trace 入口只提示转往 `report/`，不加载任何页面。
- 静态检查：脚本经 `node --check` 通过；检查了 `DiagnosisResult`、`root_causes`、`evidence`、`impact`、`recommendations`、`risks`、`requires_approval`、`agent_summary`、`Last-Event-ID`、`after_sequence` 和移动端媒体查询。
- 浏览器截图：受 Codex 本地页面访问策略限制，`file://` 与 `http://127.0.0.1:4174` 预览均被阻止，未绕过限制。视觉验收以上述布局规则、DOM/脚本静态检查与人工 CSS 审读完成；用户应在本机打开原型确认视觉方向。

## Review

- 已完成独立审查，详见 `docs/开发/P0-V1产品化基线/review.md` 的 P0.4 小节。
- 审查确认原型以结构化结果为主，完整 Trace 不在工作区展开；四种 Run 状态和未实现能力均有诚实表达；页面无 API 调用、构建工具或后端改动。
- 结论：通过，已获用户视觉确认。允许创建 P0.4 提交；确认不授权初始化 React 工程。
