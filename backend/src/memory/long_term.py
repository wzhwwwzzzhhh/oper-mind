"""长期记忆：跨会话存储和检索"""

import json
import os
from datetime import datetime
from pathlib import Path

from src.project_paths import DATA_DIR


class LongTermMemory:
    """
    长期记忆：将历史诊断记录保存到本地文件，下次启动时可以检索。
    生产环境会用向量数据库（如Chroma），这里先用JSoN文件+关键词匹配模拟。
    面试时可以说："我用文件存储做MVP，理解原理后可迁移到向量数据库。"
    """

    def __init__(self, storage_path: str | Path | None = None):
        self.storage_path = Path(storage_path) if storage_path else DATA_DIR / "memory.json"
        self.records: list[dict] = []
        self.load()

    def load(self):
        """从文件加载历史记录"""
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    self.records = json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                print(f"加载历史记录时出错")
                self.records = []
        print(f"[Memoryl已加载{len(self.records)}条历史记录")

    def _save(self):
        """保存到文件"""
        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
        with open(self.storage_path, "w", encoding="utf-8") as f:
            json.dump(self.records, f, ensure_ascii=False, indent=2)

    def add_record(self, query: str, diagnosis: str, tags: list[str] = None):
        """
        保存一条诊断记录。
        query：用户的问题/SQLdiagnosis：诊断结论
        tags：标签，方便检索（如["慢SQL"，"索引"，"全表扫描"]）
        """
        record = {
            "id": len(self.records) + 1,
            "query": query,
            "diagnosis": diagnosis,
            "tags": tags or [],
            "timestamp": datetime.now().isoformat()
        }
        self.records.append(record)
        self._save()
        print(f"[Memory]已保存诊断记录#{record['id']}")

    def search(self, keywords: str, top_k: int = 3) -> list[dict]:
        """
        根据关键词检索历史记录。
        这里用简单的关键词匹配。生产环境会替换为向量检索（Embedding）。
        但原理一样：输入→ 转换成向量→找最相似的top_k。
        top_k：返回最相关的前几条。
        """
        keyword = keywords.lower()
        scored: list[tuple[int, dict]] = []  # (score, record)

        for record in self.records:
            score = 0
            # 查询匹配
            if keyword in record["query"].lower():
                score += 3
            # 诊断匹配
            if keyword in record["diagnosis"].lower():
                score += 2
            # 标签匹配
            for tag in record.get("tags", []):
                if keyword in tag.lower():
                    score += 1
            if score > 0:
                scored.append((score, record))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [r for _, r in scored[:top_k]]

    def get_recent(self, n: int = 5) -> list[dict]:
        """
        获取最近的n条记录
        """
        return self.records[-n:]

    def format_context(self, keyword: str = "") -> str:
        """
        将检索结果格式化为LLM 能读的上下文文本。
        在Agent的 system prompt中注入这个，让LLM参考历史。
        """
        if keyword:
            result = self.search(keyword)
        else:
            result = []

        if not result:
            # 搜索不到时，展示最近记录作为上下文
            result = self.get_recent(3)
            if not result:
                return ""

        context = "\n## 历史相关诊断记录\n"

        for r in result:
            context += f"- [{r['timestamp'][:10]}] {r['query'][:50]}... → {r['diagnosis'][:100]}...\n"
        return context
