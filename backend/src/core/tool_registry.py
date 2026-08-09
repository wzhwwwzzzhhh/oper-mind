""" Tool注册中心：管理所有可用的工具"""

import json

from src.core.approval import check_operation_safety, is_alter_table_safe, is_high_risk_sql


class Tool:
    """ 单个工具的定义"""
    def __init__(self, name: str, description: str, parameters: dict):
        """
        parameters 是 JSON Schema 格式，描述参数的类型和约束。

        示例：
        {
            "type": "object",
            "properties": {
                "sql": {"type": "string", "description": "要分析的SQL"}
            },
            "required": ["sql"]
        }
        """
        self.name = name
        self.description = description
        self.parameters = parameters
    def to_openai_schema(self)-> dict:
        """转换成 OpenAI Function Calling要求的格式"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters
            }
        }

    def execute(self, **kwargs) -> str:
        """子类重写此方法"""
        raise NotImplementedError("子类必须实现此方法")

class ToolRegistry:
    """工具注册中心"""

    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """注册一个工具"""
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        """按名取回已注册工具；未注册返回 None（供网关做准入判定）。"""
        return self._tools.get(name)

    def get_schemas(self) -> list[dict]:
        """返回所有工具的OpenAI Schema列表，传给LLM"""
        return [t.to_openai_schema() for t in self._tools.values()]

    def execute_tool(self,name: str, arguments: str) -> str:
        """
        执行指定工具。
        arguments是JsoN字符串，需要先解析。
        """
        if name not in self._tools:
            return json.dumps({"error": f"工具{name}不存在"}, ensure_ascii=False)

        try:
            args = json.loads(arguments)
            # === 安全检查 ===
            # 如果传递了 SQL，检查是否高危
            sql = args.get("sql", "")
            if sql and is_high_risk_sql(sql):
                # 检查 ALTER TABLE 是否安全
                if "alter" in sql.lower():
                    if is_alter_table_safe(sql):
                        # ALTER TABLE ADD INDEX 是安全的
                        pass
                    else:
                        # 其他 ALTER 操作需要审批
                        if not check_operation_safety("alter_table", {"sql": sql}):
                            return json.dumps(
                                {"warning": "ALTER TABLE 操作被拒绝，仅允许 ADD INDEX"},
                                ensure_ascii=False,
                            )
                else:
                    # 其他高危操作需要审批
                    if not check_operation_safety("kill_query", args):
                        return json.dumps(
                            {"warning": "高危操作被拒绝"},
                            ensure_ascii=False,
                        )

            # === 执行 ===
            result = self._tools[name].execute(**args)
            return str(result)
        except json.JSONDecodeError:
            return json.dumps({"error": "参数必须是有效的JSON"}, ensure_ascii=False)
        except TypeError as e:
            return json.dumps({"error": f"参数不匹配：{e}"}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": f"执行异常：{e}"}, ensure_ascii=False)
