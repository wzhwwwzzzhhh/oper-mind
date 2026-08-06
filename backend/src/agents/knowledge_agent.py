"""Knowledge Agent — 受管知识目录检索

从受管 Markdown 知识目录检索运维文档/SOP，供结论引用；只读，不越权访问目录外文件。
"""

from src.core.agent import BaseAgent
from src.core.llm import LLMClient
from src.core.tool_registry import ToolRegistry
from src.tools.knowledge_tools import SearchKnowledgeTool


KNOWLEDGE_SYSTEM_PROMPT = """你是知识检索 Agent，负责从受管知识目录检索运维文档、SOP 和历史排障记录。

## 工具使用规则
- 只能使用提供的知识检索工具，检索时先明确关键词再查询
- 拿到检索结果后，基于检索到的文档要点给出回答，并说明引用了知识库
- 一次检索不够时可调整关键词多次检索

## 诚实与边界
- 工具返回「未配置」「为空」「无匹配」时如实告知，不得编造文档内容
- 只能检索受管知识目录，不得访问目录外文件或任何外部资源
- 检索到的片段只作引用要点，不承诺文档全文内容

## 回答要求
- 用中文回答
- 结论中引用知识文档的标题作为来源
- 若检索不到依据，明确说明知识库中没有相关内容
"""


class KnowledgeAgent(BaseAgent):
    """知识检索 Agent：在受管目录内按关键词确定性检索 Markdown 文档。"""

    def __init__(
        self,
        llm: LLMClient,
        knowledge_dir: str | None = None,
        max_steps: int = 8,
        enable_long_term_memory: bool = True,
    ) -> None:
        tools = ToolRegistry()
        tools.register(SearchKnowledgeTool(directory=knowledge_dir))

        super().__init__(
            llm=llm,
            tools=tools,
            system_prompt=KNOWLEDGE_SYSTEM_PROMPT,
            max_steps=max_steps,
            enable_long_term_memory=enable_long_term_memory,
        )