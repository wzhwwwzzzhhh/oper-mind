# 任务 P3-包7：模型服务页（按设计稿）

## 背景（只读）
按 `frontend/参考原型/model-settings.html`（设计稿）实现模型服务配置页。
已有壳：窄图标导航 + 双模式共用壳。全局导航已有「模型设置」图标（当前点了没反应，见 `GlobalNav.tsx`）。

**重要事实：后端没有模型/Provider API。** 本页做**静态展示 + 本地状态**（localStorage），不接后端、不伪造"已连接"。页面如实展示默认配置（示例 Provider 列表），用户改的是本地偏好，不持久化到后端。

## 只允许修改/创建这些文件
1. 新建 `frontend/src/features/models/ModelSettingsPage.tsx`
2. 新建 `frontend/src/styles/model-settings.css`
3. 改 `frontend/src/features/shell/GlobalNav.tsx`（「模型设置」图标点击 → `/models`）
4. 改 `frontend/src/features/shell/ServiceContextNav.tsx`（如需为 /models 显示对应上下文栏，或复用服务中心栏）
5. 改 `frontend/src/app/App.tsx`（新增 `/models` 路由，壳判断 `is_services` 或新增 `is_models`）
6. 改 `frontend/src/main.tsx`（import 新 css）
7. 改 `frontend/src/app/App.test.tsx`（如有必要）

**严禁触碰其他文件**（不改后端、不改 P2 链路、不改已有会话/服务中心页）。

## 设计稿结构 → 组件映射
- 第二栏上下文：模型服务上下文（模型服务 / 可用模型 / 默认策略 / 安全权限 + 当前生效模型卡）
- 主区自上而下：
  - 面包屑「会话工作台 / 模型服务」
  - 标题 + 「检查全部连接 / 添加模型服务」按钮
  - 4 个摘要卡：当前生效模型 / 已配置服务 / 可用模型 / 最近调用
  - 已配置模型服务：Provider 列表（Ollama / DeepSeek / OpenAI / 公司网关），每行 logo+名称+tags+连接状态+操作
  - 可用模型：模型卡片网格（DeepSeek Reasoner / Chat / qwen3:8b / gpt-4.1 / llama3.2 / deepseek-r1）
  - Agent 调用策略：Coordinator / DB / Server / Log / Debate / Reflection / Report 各 Agent 一行（分配模型 + 开关）
  - 运行边界：安全说明列表
  - 添加模型服务弹窗：选 Provider 类型

## 静态数据定义（照设计稿，硬编码在页面组件内）
- Provider 列表 4 个：Ollama(本地/4模型/流式)、DeepSeek(官方API/2模型)、OpenAI(未配置)、公司网关(需关注)
- 模型列表 6 个：DeepSeek Reasoner(默认)、DeepSeek Chat、qwen3:8b、gpt-4.1、llama3.2、deepseek-r1
- Agent 策略 7 行：各 Agent 默认模型（Reasoner 或 Chat）+ 默认开启

## 本地交互（localStorage 持久化）
- 「添加模型服务」弹窗选 Provider 类型 → 关闭后 toast 提示"已进入 X 配置流程"(本次不实现真实表单)
- Agent 策略开关可切换(存 localStorage `opermind:model-policy`)
- 当前生效模型 / 各开关状态刷新后保留

## 验收
- `npm run typecheck` / `npm run test` / `npm run build` 全绿
- 手动：窄导航点「模型设置」→ `/models` 显示设计稿页面，上下文栏切换，弹窗可用，开关状态刷新保留
- `git status` 只出现上面允许的文件

## 完成后
**不要 commit。** 停下告诉我"包7完成"，我审 diff + 跑测试后自己提交。

## 交差前自审清单（必须在完成报告里逐条回答）
跑完 `npm run typecheck` / `npm run test` / `npm run build` 后，逐条自审并写进完成报告：
1. `git status --short` 完整输出 —— 确认只出现本任务允许的文件（新建 ModelSettingsPage.tsx、model-settings.css；修改 GlobalNav.tsx、ServiceContextNav.tsx、App.tsx、main.tsx、App.test.tsx）。
2. `npm run test` 最终通过数 —— 确认没有为了通过而删/改已有测试断言。**不许为了绿而改测试。**
3. typecheck / build 是否绿。
4. 明确说明：本页是静态展示 + localStorage，**没有接后端、没有伪造"已连接/已配置"**（如"DeepSeek 官方 API"是默认展示，不表示真连上了）。
5. 列出一个"我改了什么"的简短清单（每个文件的改动点）。
