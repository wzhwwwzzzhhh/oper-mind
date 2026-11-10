# V2-2 WP1 服务冻结 · Design

> 状态：已确认（2026-10-29，用户确认；arch-review 两轮后 P1=0，§6 三项已拍板）
> 更新：2026-10-29
> 关联：[V2-2 PRD](../../prd/agent-runtime/V2-2-execution-capabilities.md)（已确认，Issue #142，阶段拆分见「阶段拆分」节）；[V2-1 Design](V2-1单主Agent地基Design.md)（已确认）。
> 关键代码：`backend/src/domain/main_agent.py`、`application/{run_execution,services}.py`、`application/errors.py`、`api/v1/{routes,schemas,resources}.py`、`frontend/src/features/workbench/MainAgentComposer.tsx`、`frontend/src/api/v1/queries.ts`。
> 本文只定架构；切片、验证命令与提交计划归 dev-plan。

## 1. 目标与范围

一句话：**让用户能在会话里选一个已注册的 PostgreSQL 服务，受理时校验并冻结进 Run，此后该 Run 的公开资源与重跑都能看到同一个服务**。

这是 V2-2 的第一片，只铺「服务引用」这条管道。它不涉及任何能力调用、不涉及结构化交付、不涉及数据库迁移。

做什么：

- `MainInputV1` 增加可选 `service_id`；`MainInputSnapshotV1` 增加可选 `service: MainServiceBindingV1`（`service_id`/`kind`/`title`）。
- 受理期两级校验：格式错误 → 422；未注册／类型不符／无凭据 → 409。**只查注册表，不建立连接。**
  - **不含「会话范围」校验**：PRD 该条仍是开放问题，本片不收紧（见 §2.2 末条）。
- `run.service_id` 落同一值，**含重跑路径**（带 `None` 守卫，见 §2.3）。
- 创建摘要与重跑摘要**仅在 `service_id` 非空时**追加该键（保证 V2-1 旧幂等记录逐字节不变）。
- 公开资源加法：`CreateMainAgentRunRequest.service_id`、`MainInputSnapshotResource.service`。
- 前端录入区增加服务选择器（只列 `kind==='postgres'` 且 `has_dsn` 的服务）。

明确不做（本片边界，防越界）：

- **不新增任何能力**，不改 `CapabilityDefinition`，不改 `core/main_agent_react.py`、`core/capability_tools.py`、`core/tool_gateway.py`。
- **不改交付**：`MainDeliveryV1` 仍是 `answer | needs_input | comparison`，不碰 `run_deliveries`、不碰迁移。
- **不建立真实连接**：本片只在受理期查注册表；执行期不读服务。服务是否可用不影响 Run 执行（没有能力用它）。
- 不新增端点、不新增事件类型、不新增依赖。
- 不实现服务健康/日志能力（属 WP2/WP3）。

## 2. 设计决策

### 2.1 数据放在哪一层

```text
公开请求  CreateMainAgentRunRequest.service_id: str | None
   ↓ routes._run_command
领域输入  MainInputV1.service_id: str | None            # 格式校验（复用 validate_service_instance_id）
   ↓ application._accept_run_in_transaction
受理校验  ServiceRegistry.resolve_binding(service_id, expected_kind="postgres")
          —— 只查注册表与 has_dsn，不建连接
   ↓
冻结快照  MainInputSnapshotV1.service: MainServiceBindingV1 | None
          MainServiceBindingV1 { service_id, kind, title }    # 只有显示信息
   ↓
Run 记录  run.service_id = service_id                    # 复用既有字段
```

**为什么服务信息同时进快照和 `run.service_id`**：`run.service_id` 是既有公开字段，列表/详情/导出已经在读它；快照 `service` 保存**受理时刻的显示信息**（title/kind），使历史 Run 不因服务后来改名或移除而显示漂移。两者同源、同时写入。

**为什么 `service` 放快照而不新增表**：`MainInputSnapshotV1` 是 `extra="forbid"` + `schema_version=1`，加一个**可选字段**后旧行缺省为 `None`、严格解析照常通过。`run_inputs.payload` 是 JSON 列，**无需迁移**。

### 2.2 校验时机与错误分类

两级，分开报错（不让用户把「格式错」和「服务不可用」混为一谈）：

| 情况 | 时机 | 结果 |
|---|---|---|
| `service_id` 含非法字符 / 超 64 字符 | `MainInputV1` 构造期 | `VALIDATION_ERROR` → **422** |
| 服务未注册 / 类型不是 postgres / 无凭据 | 受理事务内 | `MAIN_AGENT_SERVICE_UNAVAILABLE` → **409** |

- 格式校验复用 `domain/services.py::validate_service_instance_id`（`[a-z0-9][a-z0-9._-]*`，1–64），不另写一套。
- 语义校验用既有 `ServiceRegistry.resolve_binding(service_id, expected_kind="postgres")`，**不新增查表路径**。它实际覆盖：`POISONED`（条目已被隔离）、`NOT_FOUND`（未注册／非 BindingCapable／capability 缺失／id 不符）、`TYPE_MISMATCH`、`CREDENTIAL_UNAVAILABLE`（`has_dsn` 为假）。本片不传 `investigation_id`，故 `INVESTIGATION_NOT_SUPPORTED` 不可达。
- **`title` 的来源（必须写清，否则有 TOCTOU 空洞）**：`RegistryBinding` 只有 `service_id`/`kind`/`supported_investigations`/`capability`/`origin`，**不含 `title`**。因此冻结时再做一次 `registry.get_connector(service_id)` 取 `definition().title`。
  - 若该次读取返回 `None`（服务在两次读取之间被移除或隔离）→ **按服务不可用处理（409）**，不写入半截快照。这与「不建立连接」不冲突：`get_connector` 只读内存注册表。
  - 备选方案（若实现时认为两次读取不可接受）：给 `RegistryBinding` 增加 `title` 字段（纯加法，既有消费方不受影响）。**二者择一，不并存**；选后者时 §3 须把 `domain/services.py` 列入改动面。
- **PRD 里「只读」与「当前可用」两项在本片的准确口径**（如实写清，避免读者误以为受理期已验证）：
  - **只读**：`resolve_binding` **不检查**只读属性；只读由 Connector 契约保证（`opermind_readonly` 角色 + 只读事务 + 列级授权）。受理期不验证，也不建立连接。
  - **当前可用**：本片解释为「已注册且已配置 DSN」。**不探测连通性**——探测会在受理期打开真实连接，与本片「零外部访问」的目标冲突，且会让受理因网络抖动失败。
- **校验位置在幂等重放判定之后**：同键重放直接返回原 Run，不因服务后来被移除而把重放变成 409。
- **校验只对 `CreateMainAgentRunCommand` 生效**，不对 `MainAgentRerunCommand` 生效——重跑复用冻结事实，服务被移除不应让历史 Run 不可重跑。
- `registry` 未注入（单测夹具）时：带 `service_id` 一律拒绝（fail-closed），不带则行为不变。
- 错误文案固定：「所选服务当前不可用，请重新选择」。**不回显 DSN、host、port、服务列表或失败细节。**
- **会话范围校验（本片不做）**：PRD 的「会话已声明 `service_ids` 时冻结服务是否必须属于该集合」仍是**开放问题**。本片按「任意已注册且已配置的服务均可选」实现，不做收紧——收紧属权限变化，须先回写 PRD 并由用户确认（WP2 再定）。

### 2.3 快照与指纹

```text
MainInputSnapshotV1（schema_version 仍为 1）
  query / text_a / text_b / rule_version / context   # 既有
  service: MainServiceBindingV1 | None = None        # 新增，可选
```

**指纹兼容（钉死）**：`main_agent_create_fingerprint` 与 `main_agent_rerun_fingerprint` 的 payload **仅在 `service_id` 非空时**追加 `"service_id"` 键，`None` 时**绝不写 `"service_id": None`**。

理由：V2-1 已落库的幂等记录是用「无该键」的 payload 算的。若无条件加键，同一无服务请求的新旧指纹会不同，历史幂等键会被判成「同键不同请求」。条件追加让无服务请求的序列化结果**逐字节不变**。

**写入兼容（钉死，本片唯一的回滚风险点）**：`SqlAlchemyRunInputRepository.add` 用 `snapshot.model_dump(mode="json")` 整模型写入，pydantic v2 **默认包含值为 `None` 的字段**（已实测：`{'schema_version': 1, 'query': 'q', 'service': None}`）。若照直实现，**WP1 之后每一条新 Run（包括完全没选服务的）**的 `run_inputs.payload` 都会多出 `"service": null`；旧代码的 `MainInputSnapshotV1` 是 `extra="forbid"`，会把**所有**新行判为 `MainAgentInputUnavailableError`。

因此写入侧必须做**条件序列化**：

```text
payload = snapshot.model_dump(mode="json")
if snapshot.service is None:
    payload.pop("service", None)
```

效果：无服务的新行与 WP1 之前的行**格式完全一致**；只有真正选了服务的 Run 才带 `service`。这样回滚影响面收窄为「WP1 之后受理的、带服务的 Run」，而不是「WP1 之后的所有 Run」。

> 实现约束：条件序列化必须落在**仓储写入点**（唯一 `model_dump` 处），不要分散到调用方；加单测断言「无服务快照写入后 payload 不含 `service` 键」。

**重跑**：`rebuild_main_input_snapshot` 复制 `service`（不重新解析注册表——冻结事实不因部署变化而改写）；`_accept_run_in_transaction` 在 `MainAgentRerunCommand` 分支写 `run.service_id`。

> **必须带 `None` 守卫（本片第二个回滚/兼容风险点）**：WP1 之前的 V2-1 Run 的 `run_inputs.payload` 没有 `service` 键，解析后 `snapshot.service is None`。若按字面写 `snapshot.service.service_id`，**重跑任何既有 V2-1 Run 都会 `AttributeError` → 500**（该异常不是 `ApplicationError`，`raise_application_error` 捕不到），既有用例 `test_rerun_main_agent_run_copies_frozen_input` 会立刻失败。
>
> 正确写法：
>
> ```text
> target_service_id = snapshot.service.service_id if snapshot.service is not None else None
> ```
>
> 语义：旧 Run（无服务）重跑后仍是 `run.service_id = None`，与它自己的快照一致。

> 现状：`target_service_id` 只在 `CreateRunCommand` 分支解析（`services.py`），主 Agent 分支会得到 `None`。这是本片必须补的一处，否则重跑 Run 的公开 `service_id` 为空、与快照 `service` 不一致。

### 2.4 公开 API（只做加法）

```text
CreateMainAgentRunRequest
  + service_id: str | None = Field(default=None, min_length=1, max_length=64)

MainInputSnapshotResource
  + service: MainServiceBindingResource | None = None

MainServiceBindingResource
  { service_id: str, kind: str, title: str }        # 只有显示信息
```

- `DiagnosisRunResource.service_id` 已存在，**不加字段**。
- 不新增端点；`generated.ts` 只允许 `npm run generate:api` 重新生成。

### 2.5 前端

`MainAgentComposer.tsx` 增加服务选择器：

- **查询归属**：选择器在 `MainAgentComposer` 内**自持** `useQuery({...list_services_query()})`，不复用 `WorkbenchPage` 的 `services_query`——后者以会话 `service_ids` 为 `enabled` 条件，而 V2 会话通常不带 `service_ids`，复用会让选择器在主要场景恒为空。根级 `QueryClientProvider` 已存在，直接可用。
- 只列 `kind === 'postgres'` 且 `has_dsn === true` 的服务。`generated.ts` 里这些字段类型是 `unknown`，需窄化后再过滤。
- **三态区分（钉死，不得把不可用伪装成空）**：
  - **加载中** → 「正在读取服务列表…」
  - **读取失败**（`/services` 返回 503 `SERVICE_CENTER_UNAVAILABLE` 等）→ 「服务列表读取失败，请稍后重试」，不显示「没有可用服务」
  - **成功但为空** → 「没有可用的 PostgreSQL 服务」
- **文案固定为未来时，且不可配置**：「服务选择将在后续版本用于健康摘要与日志扫描（本片未启用）；服务在本次请求内冻结。」——不用现在时承诺，也不把诚实提示做成可选项。
- 提交时带 `service_id`；`queries.ts` 的 `create_main_agent_run_mutation` 变量加 `service_id?: string | null`。
- 错误提示：`MAIN_AGENT_SERVICE_UNAVAILABLE` → 「所选服务当前不可用，请重新选择」。

### 2.6 安全

- 服务显示信息只有 `service_id`/`kind`/`title`（均为既有公开字段），**不含 DSN、host、port、凭据引用**。
- **受理与执行路径不建立连接**。但需如实说明：选择器的数据源是既有 `GET /services`，该端点会**逐个服务调用 `connector.health_snapshot()`**（3 秒超时），因此「打开 V2 录入区」会触发一轮既有健康快照读取。这是既有端点的既有行为，本片不新增读取路径，也不改变它；但「没有新的外部访问面」的说法不准确——准确说法是「不新增外部访问路径，复用既有 `/services` 的读取」。
- 日志只记 `service_id` 与封闭失败原因，不记 DSN 或注册表内部信息。

## 3. 文件改动面

后端修改：

- `backend/src/domain/main_agent.py`：`MainInputV1.service_id`、`MainInputSnapshotV1.service`、**`MainServiceBindingV1`（唯一定义处，紧跟 `MainInputSnapshotV1`）**
- `backend/src/infrastructure/persistence/repositories.py`：`SqlAlchemyRunInputRepository.add` 条件序列化（`service is None` 时 `payload.pop("service")`）
- `backend/src/application/run_execution.py`：`build_main_input_snapshot` / `rebuild_main_input_snapshot` 带 `service`；两个指纹条件追加 `service_id`
- `backend/src/application/services.py`：受理期服务校验（重放判定之后）、`run.service_id`（含重跑分支的 `None` 守卫）
- `backend/src/application/errors.py`：`MainAgentServiceUnavailableError`
- `backend/src/api/v1/schemas.py`：`CreateMainAgentRunRequest.service_id`、`MainServiceBindingResource`、`MainInputSnapshotResource.service`
- `backend/src/api/v1/routes.py`：`_run_command` 透传、`APPLICATION_ERROR_STATUS` 加 409
- `backend/src/api/v1/resources.py`：`main_input_snapshot_resource` 投影 `service`

前端修改：

- `frontend/src/features/workbench/MainAgentComposer.tsx`（服务选择器）
- `frontend/src/api/v1/queries.ts`（mutation 变量）
- `frontend/src/api/v1/generated.ts`（**只允许**重新生成）
- `frontend/src/test/handlers.ts`（加法 mock）

**数据库变更**：无。**公开端点**：无新增（请求加可选字段、响应加可选字段）。**事件类型**：无。**依赖**：无新增。

无功能改动：`core/` 全部、`CapabilityDefinition`、`run_deliveries`、迁移、V1 全部模块。

**已知的既有契约反转（必须在实现时点名，否则会被当成回归）**：

- `backend/tests/test_main_agent_runs_api.py` 里有一条用例断言「V2 请求携带 `service_id` → 422 `VALIDATION_ERROR`」（docstring 为「V2 请求不接受 service_id，未知字段失败关闭」）。**本片有意反转这个安全断言**：`service_id` 从「拒绝」变成「接受并校验」。该用例须改写为新的契约断言（未知字段仍 422、非法格式仍 422、已注册服务成功），**不允许直接删除**。

## 4. 切片与验证（指引，不写死）

建议 2 片（文件清单见 §3，此处不重复）：

1. **S1 后端管道**：领域字段 + 条件序列化 + 受理校验 + 指纹 + 公开资源。验收语义：格式错 422、不可用 409、重放不因服务移除而变 409、无服务请求指纹逐字节不变、**无服务快照写入后 payload 不含 `service` 键**、重跑保留 `service_id`、旧行照常解析、既有 422 断言已改写。
2. **S2 前端选择器**：选择器 + 提交 + 错误提示 + 三态区分。验收语义：只列可用 postgres 服务、加载中/失败/确实为空三态可区分、未选时不伪造、文案为未来时且不可配置。

门禁项：

- **公开 API 加法**（请求 `service_id`、快照 `service`）——需用户确认。
- **不触及**：数据库迁移、新端点、新事件类型、Connector、凭据、能力定义、内核、交付。

## 5. 风险、回滚与门禁

| 风险 | 缓解 |
|---|---|
| 指纹无条件加键破坏 V2-1 旧幂等记录 | 仅在 `service_id` 非空时追加；专项测试断言无服务请求指纹与改动前逐字节相同 |
| **`model_dump` 把 `None` 写进 payload，波及全部新 Run** | 仓储写入点做条件序列化（`service is None` 时 `pop`）；单测断言无服务 payload 不含 `service` 键。**这是本片最关键的一条**：不做则回滚影响面从「带服务的 Run」扩大到「WP1 之后的所有 Run」 |
| 重跑丢 `run.service_id` | 重跑分支显式写 `run.service_id = snapshot.service.service_id`，加用例覆盖 |
| 服务在校验后被移除 | 本片没有能力消费服务，执行不受影响；公开资源仍显示冻结时的 title（如实反映受理时刻） |
| 前端让用户以为能力已可用 | 文案固定为「服务选择将在后续版本用于健康摘要与日志扫描（本片未启用）」，不可配置 |
| 前端把「读取失败」渲染成「没有可用服务」 | 三态区分：加载中 / 读取失败 / 确实为空 |
| 既有 422 断言被当成回归 | Design 已点名该用例；实现时改写为等价的新契约断言，不删除 |

**回滚**：无迁移、无新端点。回退提交即可；公开字段为可选，旧客户端不受影响。

**已知数据边界（条件序列化后）**：只有**真正选了服务**的 Run 才带 `service` 字段，回滚后旧代码读这类行会判为 `unavailable`（安全投影，不 500）。因此回滚前置条件是「确认 WP1 之后没有受理过**带服务**的 Run」——而不是「没有受理过任何 Run」。

## 6. 已确认的设计决策（2026-10-29）

1. **服务与会话的绑定松紧**：本片按「任意已注册且已配置 DSN 的 postgres 服务均可选」实现，**不做**会话范围收紧。PRD 该条保持开放，留到 WP2 有真实消费场景后再定；届时若收紧属权限变化，须先回写 PRD。
2. **服务选择器位置**：放在 `MainAgentComposer` 录入区，与请求一起提交（语义是「这次问哪个服务」）。不做会话级「选一次后续沿用」——那会让换服务变成隐式操作，用户分不清当前 Run 用的是哪个。
3. **既有 422 断言反转**：确认反转。`service_id` 从「V2 拒绝」变为「接受并校验」，因为 V2-1 的拒绝是「V2 还不接服务」时的临时安全锁，本片正是要打开它。该用例改写为等价新断言（未知字段仍 422、非法格式仍 422、已注册服务成功），**不删除**。
