# 契约、验证与 API

> 核验日期：2026-10-12。资料入口与核验边界见[学习目录](../README.md)。
> 共 8 项；“先学 / 按需学 / 进阶”表示建议顺序，不是开发门禁。

先把“契约”理解为双方对输入、输出和失败的明确约定。Schema 描述结构，验证检查约束；权限、任务归属、完成条件和版本兼容还需应用层规则，不能只靠一份 JSON Schema。

<a id="k01"></a>

## K01 · Pydantic Models

- 官方入口：[Pydantic Models](https://docs.pydantic.dev/latest/concepts/models/)
- 形式／优先级：官方文档；先学。
- 重点看：BaseModel、模型创建、model_validate、model_dump 及配置。
- 对应疑问：怎样明确表达任务输入、能力输出和错误信息？

<a id="k02"></a>

## K02 · Pydantic Fields

- 官方入口：[Pydantic Fields](https://docs.pydantic.dev/latest/concepts/fields/)
- 形式／优先级：官方文档；按需学。
- 重点看：必填、默认值、字段约束、别名。
- 对应疑问：一个字段可省略、可为 null、有默认值，含义有什么区别？

<a id="k03"></a>

## K03 · Pydantic Validators

- 官方入口：[Pydantic Validators](https://docs.pydantic.dev/latest/concepts/validators/)
- 形式／优先级：官方文档；按需学。
- 重点看：字段验证与模型级验证的边界及顺序。
- 对应疑问：怎样检查字段之间的关系，而不是只检查类型？

<a id="k04"></a>

## K04 · Pydantic Strict Mode

- 官方入口：[Pydantic Strict Mode](https://docs.pydantic.dev/latest/concepts/strict_mode/)
- 形式／优先级：官方文档；先学。
- 重点看：默认类型转换与 strict 的区别，以及 Python/JSON 输入差异。
- 对应疑问：模型输出的字符串能否当数字使用，应在哪里拒绝含糊输入？
- 使用边界：严格类型校验不代表资源存在、用户有权限或业务结果正确。

<a id="k05"></a>

## K05 · JSON Schema: Getting started step-by-step

- 官方入口：[JSON Schema: Getting started step-by-step](https://json-schema.org/learn/getting-started-step-by-step)
- 形式／优先级：规范组织官方教程；按需学。
- 重点看：type、properties、required、additionalProperties 与组合约束。
- 对应疑问：不同语言或工具之间怎样表达共同的数据结构？

<a id="k06"></a>

## K06 · OpenAPI Specification 3.1.1

- 官方入口：[OpenAPI Specification 3.1.1](https://spec.openapis.org/oas/v3.1.1.html)
- 形式／优先级：官方规范；进阶。
- 重点看：按需查 Schema、Request Body、Response；无需从头背规范。
- 对应疑问：接口文档怎样描述请求和响应，如何与前端类型生成衔接？
- 使用边界：这是指定版本的参考资料，不代表项目接口已采用该版本；实施时核对当前 app.openapi()。

<a id="k07"></a>

## K07 · FastAPI Request Body

- 官方入口：[FastAPI Request Body](https://fastapi.tiangolo.com/tutorial/body/)
- 形式／优先级：官方教程；先学。
- 重点看：Pydantic 请求模型、字段约束与验证反馈。
- 对应疑问：用户或模型传来的输入如何进入后端的确定性边界？

<a id="k08"></a>

## K08 · FastAPI Response Model

- 官方入口：[FastAPI Response Model](https://fastapi.tiangolo.com/tutorial/response-model/)
- 形式／优先级：官方教程；按需学。
- 重点看：response_model、输出验证和字段过滤。
- 对应疑问：内部状态为什么不能直接原样返回前端？
- 使用边界：字段过滤不能代替凭据防泄露、数据授权与证据脱敏；需检查完整输出路径。

## 学完如何记录

在[学习路线与问题记录](../学习路线与问题记录.md)写下自己的解释、仍不确定的点和对应资料编号。材料收藏、看过视频和能解释／验证机制是不同状态，不自动把任何问题标成“已理解”。
