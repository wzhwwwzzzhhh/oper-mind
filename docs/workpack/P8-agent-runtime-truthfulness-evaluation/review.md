# P8-agent-runtime-truthfulness-evaluation · 独立代码 Review

> 状态：第三轮独立终审 PASS，无 P0–P3

## 第一轮（2026-08-23）

- 结论：FAIL；无 P0，5 个 P1、2 个 P2。
- P1：real 模式 `direct + target=null` 的默认 DB 路由被破坏。
- P1：证据不足的 Conflict/Reflection 虚假通过，direct/chain 缺 skipped，修订上限未 failed，mock Debate 未基于本次证据。
- P1：mock 结论未绑定实际工具/输出类别，且缺“模拟场景”标识与 Knowledge 安全标题。
- P1：公开投影遗漏单段 Unix 路径、根挂载点及 JSON/键值工具实参。
- P1：评测矩阵缺四单域 direct、chain、拒绝/unavailable、实际 Debate；负向评测器覆盖不足。
- P2：畸形工具菜单需整体失败关闭；交付证据与清单状态提前标记 PASS。
- 处理：已先回退证据、切片、完善清单和跑通验证状态；完成代码/测试整改后再复审。

## 第二轮（2026-08-23）

- 结论：FAIL；无 P0，3 个 P1、2 个 P2。
- 已关闭：real 默认 DB、质量 skipped/failed、mock 工具事实绑定与模拟标识、Knowledge 安全标题、畸形菜单。
- P1：带引号/反引号的 Unix 路径、规范 JSON 工具实参和敏感键仍可绕过投影。
- P1：负向门禁仍不能自动识别合法 `server/check_cpu` 与错误“磁盘耗尽”结论的错配；Debate 测试缺工具审计记录。
- P1：Knowledge 未配置时工具事件仍为 `ok`，四 direct 矩阵缺临时受管知识目录的正向命中。
- P2：mock Debate 已执行状态需与已确认 Design 对齐为 `ok`；证据数字需同步 27/603。
- 处理：投影规则与哨兵已扩展；评测器新增工具输出/结论类别校验；Debate 改用实际 Gateway 审计记录；Knowledge 增加字符串结果状态钩子及正反矩阵；mock Debate 对齐 Design 为 `ok`。

## 第三轮终审（2026-08-23）

- 结论：PASS；无 P0、P1、P2、P3。
- 第二轮 3 个 P1 与 2 个 P2 全部关闭：JSON/Markdown 路径投影、证据类别错配门禁、带 ToolGateway 审计的 actual Debate、Knowledge 正向/不可用矩阵、Debate Design 状态与最新验证数字均通过复核。
- Reviewer 未修改任何文件；建议在本 PASS 落盘后按实收口完善清单与 C3。
