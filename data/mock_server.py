"""模拟服务器指标数据，用于开发和测试"""

import random


def get_mock_cpu() -> dict:
    """模拟 CPU 指标"""
    return {
        "percent": random.uniform(20, 95),
        "count": 4,
        "load_avg": (random.uniform(1, 4), random.uniform(0.5, 3), random.uniform(0.5, 2)),
    }


def get_mock_memory() -> dict:
    """模拟内存指标"""
    total_gb = 16
    used_gb = random.uniform(4, 14)
    return {
        "total_gb": total_gb,
        "used_gb": round(used_gb, 1),
        "percent": round(used_gb / total_gb * 100, 1),
        "swap_used_gb": round(random.uniform(0, 3), 1),
    }


def get_mock_disk() -> list[dict]:
    """模拟磁盘指标"""
    return [
        {"mount": "/", "total_gb": 256, "used_gb": random.uniform(50, 200), "percent": random.uniform(20, 90)},
        {"mount": "/data", "total_gb": 512, "used_gb": random.uniform(100, 400), "percent": random.uniform(20, 90)},
    ]


def get_mock_processes() -> list[dict]:
    """模拟高负载进程"""
    processes = [
        {"name": "mysqld", "pid": 1234, "cpu": 85.0, "mem": 25.0},
        {"name": "java", "pid": 5678, "cpu": 45.0, "mem": 40.0},
        {"name": "nginx", "pid": 9012, "cpu": 5.0, "mem": 2.0},
    ]
    return processes
