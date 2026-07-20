# M6 Step1 — API 契约与响应模型

> 状态：⚪ 计划（待开工时填写）

## 计划改动文件

- 新增 `src/api/schemas.py` —— request/response 的 Pydantic 模型（诊断请求、报告结构、错误体）。
- `src/app.py` —— 路由重整、统一异常处理、去掉 stub 端点或补实。
- `src/core/bootstrap.py` —— 若接口需要注入不同 system 构建方式则同步。

## 待填

- [ ] 契约字段定稿（供前端 TS 类型对齐）
- [ ] 错误码/错误体约定
- [ ] Code 锚点 + Test
