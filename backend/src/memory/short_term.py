"""短期记忆：SlidingWindow管理对话历史"""

class ShortTermMemory:
    """
    短期记忆：保留最近N轮对话。
    原理：
    messages列表不断增长，但只保留最近的max_rounds轮。
    每轮= 1条user+1条assistant（可能还有若干条tool 消息）
    system prompt 始终保留在最前面，不被截掉。
    """

    def __init__(self, system_prompt: str, max_rounds: int = 5):
        """
        max_rounds：保留最近几轮对话。设太小（如1）会失忆，
        设太大（如20）浪费token。5是一个平衡值。
        """
        self.system_prompt = {"role": "system", "content": system_prompt}
        self.max_rounds = max_rounds
        self.messages: list[dict] = [self.system_prompt]

    def add_message(self, message: dict):
        """
        添加一条消息到记忆中。
        """
        self.messages.append(message)
        self._trim()

    def _trim(self):
        """
        裁剪历史，只保留最近的max_rounds 轮。
        轮数计算：从后往前数user消息的数量。
        system prompt固定不动。
        """
        #  先分离 system prompt
        system_msgs = [m for m in self.messages if m["role"] == "system"]
        other_msgs = [m for m in self.messages if m["role"] != "system"]

        #  统计user消息数量（一轮对话的标志）
        user_count = sum(1 for m in other_msgs if m["role"] == "user")

        if user_count > self.max_rounds:
            #  需要裁剪：保留最近的max_rounds条user消息
            #  找到第（user_count-max_rounds）条user消息的位置
            to_skip = user_count - self.max_rounds
            skipped = 0
            keep_from = 0
            for i, m in enumerate(other_msgs):
                if m["role"] == "user":
                    skipped += 1
                    if skipped == to_skip:
                        keep_from = i + 1
                        break
            other_msgs = other_msgs[keep_from:]

        self.messages = system_msgs + other_msgs

    def get_messages(self) -> list[dict]:
        """
        返回完整的对话历史
        """
        return self.messages

    def get_messages_for_llm(self) -> list[dict]:
        """
        返回给 LLM的消息列表（和get_messages 一样，但更语义化）
        """
        return self.messages

    def clear(self):
        """
        清空对话历史,保留system prompt
        """
        self.messages = [self.system_prompt]
