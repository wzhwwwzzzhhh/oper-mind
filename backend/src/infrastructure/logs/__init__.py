"""日志真实源接入：受管日志目录只读 Connector。

真实模式下 Log Agent 经本 Connector 读取绑定服务实例的受管日志目录，
只做行级只读检索 / 错误聚合 / 慢查询与超时模式解析；不做任何写操作。
凭据只走环境变量（`OPERMIND_SERVICE_<INSTANCE_ID>_LOG_DIR`）、零落库。
"""

from src.infrastructure.logs.log_source import LogSourceConnector

__all__ = ["LogSourceConnector"]
