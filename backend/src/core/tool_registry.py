""" Tool注册中心：管理所有可用的工具"""


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
