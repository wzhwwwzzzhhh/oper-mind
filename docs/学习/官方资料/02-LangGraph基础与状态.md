# LangGraph 基础与状态

> 核验日期：2026-10-12。资料入口与核验边界见[学习目录](../README.md)。
> 共 10 项；“先学 / 按需学 / 进阶”表示建议顺序，不是开发门禁。

这一组建立底层执行模型。State、Node、Edge、Reducer、Checkpoint 不应只记名词，要能解释一次调用的数据如何变化。

<a id="g01"></a>

## G01 · LangGraph overview

- 官方入口：[LangGraph overview](https://docs.langchain.com/oss/python/langgraph/overview)
- 形式／优先级：官方文档；先学。
- 重点看：框架定位及核心能力入口。
- 对应疑问：LangGraph 是执行框架，还是已经替我们定义好产品与 Agent？

<a id="g02"></a>

## G02 · Thinking in LangGraph

- 官方入口：[Thinking in LangGraph](https://docs.langchain.com/oss/python/langgraph/thinking-in-langgraph)
- 形式／优先级：官方教程；先学。
- 重点看：从任务步骤识别节点、边和所需状态。
- 对应疑问：一段业务逻辑何时适合变成节点，何时适合单独的工作流？

<a id="g03"></a>

## G03 · LangGraph quickstart

- 官方入口：[LangGraph quickstart](https://docs.langchain.com/oss/python/langgraph/quickstart)
- 形式／优先级：官方入门示例；先学。
- 重点看：从最小循环理解模型调用、工具调用和停止条件。
- 对应疑问：主 Agent 的循环实际执行哪些步骤？

<a id="g04"></a>

## G04 · Graph API overview

- 官方入口：[Graph API overview](https://docs.langchain.com/oss/python/langgraph/graph-api)
- 形式／优先级：官方文档；先学。
- 重点看：State / Schema / Multiple schemas / Reducers；随后看 Nodes、Edges、Send、Command、Runtime context。
- 对应疑问：输入、内部状态、输出如何区分？并行分支返回的数据如何合并？
- 使用边界：Reducer 定义状态更新规则，不是全局锁、权限裁决器或所有并发问题的解决方案。

<a id="g05"></a>

## G05 · Functional API

- 官方入口：[Functional API](https://docs.langchain.com/oss/python/langgraph/functional-api)
- 形式／优先级：官方文档；按需学。
- 重点看：entrypoint、task 与执行组织方式；和 Graph API 对照。
- 对应疑问：何时图结构更清晰，何时普通函数组织更合适？
- 使用边界：理解替代接口即可，不因资料存在就同时维护两套运行时。

<a id="g06"></a>

## G06 · Workflows and agents

- 官方入口：[Workflows and agents](https://docs.langchain.com/oss/python/langgraph/workflows-agents)
- 形式／优先级：官方模式与示例；先学。
- 重点看：Workflow 与 Agent 的区别；顺序、并行、路由、编排等示例。
- 对应疑问：固定业务流程和由 Agent 动态选步骤可以怎样组合？

<a id="g07"></a>

## G07 · Streaming

- 官方入口：[Streaming](https://docs.langchain.com/oss/python/langgraph/streaming)
- 形式／优先级：官方文档；按需学。
- 重点看：流式输出模式、状态更新与消息输出的区别。
- 对应疑问：前端看到的进度、消息和最终结果是不是同一种数据？
- 使用边界：官方原始流不是产品公开事件协议；仍需按现有脱敏与安全 Trace 边界投影。

<a id="g08"></a>

## G08 · Persistence

- 官方入口：[Persistence](https://docs.langchain.com/oss/python/langgraph/persistence)
- 形式／优先级：官方文档；按需学。
- 重点看：Threads、Checkpoints、状态读取与恢复；留意重放及副作用边界。
- 对应疑问：一次 Run、一次会话和一个持久化 thread 有何区别？
- 使用边界：添加 checkpointer 不等于完成产品级取消、恢复、鉴权或同会话并发控制。

<a id="g09"></a>

## G09 · Memory

- 官方入口：[Memory](https://docs.langchain.com/oss/python/langgraph/add-memory)
- 形式／优先级：官方文档；按需学。
- 重点看：短期记忆、长期记忆及它们对应的存储范围。
- 对应疑问：消息历史、图状态和跨任务知识是不是一回事？

<a id="g10"></a>

## G10 · Interrupts

- 官方入口：[Interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)
- 形式／优先级：官方文档；按需学。
- 重点看：暂停、恢复、恢复值及重执行注意事项。
- 对应疑问：等待人工输入时，状态如何保留，恢复时哪些步骤可能再次执行？
- 使用边界：interrupt 是执行机制，不是完整审批系统；审批归属、白名单执行与 Verify 仍需服务器边界。

## 学完如何记录

在[学习路线与问题记录](../学习路线与问题记录.md)写下自己的解释、仍不确定的点和对应资料编号。材料收藏、看过视频和能解释／验证机制是不同状态，不自动把任何问题标成“已理解”。
