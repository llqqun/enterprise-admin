"""服务监控：把本机的运行状态读出来。

只做**读取**，不尝试修复或告警 —— 一个「看一眼现在怎么样」的页面。真正的告警属于外部系统
（Prometheus 之类），在应用进程里做告警只会多一个会挂掉的东西。

`cpu_percent(interval=0.1)` 会**阻塞 100 毫秒**：不传 interval 时 psutil 返回的是「自上次调用以来」
的占用率，第一次调用永远是 0.0 —— 一个永远显示 0% 的监控页比没有更糟。
"""

import os
import platform
import sys
import time
from importlib.metadata import PackageNotFoundError, version
from typing import Any

import psutil

#: 关心的依赖版本。查不到时返回 `None` 而不是抛错 —— 监控页不该因为一个包装法不一样就整页 500。
WATCHED_PACKAGES = ("fastapi", "starlette", "sqlalchemy", "asyncmy", "alembic", "pydantic", "psutil")

_MB = 1024 * 1024


def _mib(value: int) -> int:
    return int(value // _MB)


def _package_versions() -> dict[str, str | None]:
    collected: dict[str, str | None] = {}
    for name in WATCHED_PACKAGES:
        try:
            collected[name] = version(name)
        except PackageNotFoundError:
            collected[name] = None
    return collected


def _disk_usage() -> list[dict[str, Any]]:
    partitions: list[dict[str, Any]] = []
    for part in psutil.disk_partitions(all=False):
        try:
            usage = psutil.disk_usage(part.mountpoint)
        except (PermissionError, OSError):
            # 光驱、断开的网络盘会让 disk_usage 抛错；跳过而不是让整页失败。
            continue
        partitions.append(
            {
                "mount": part.mountpoint,
                "fstype": part.fstype,
                "total_mb": _mib(usage.total),
                "used_mb": _mib(usage.used),
                "free_mb": _mib(usage.free),
                "percent": round(usage.percent, 1),
            }
        )
    return partitions


def collect() -> dict[str, Any]:
    """采集一次快照。"""
    process = psutil.Process()
    memory = psutil.virtual_memory()
    swap = psutil.swap_memory()

    started_at = process.create_time()
    return {
        "cpu": {
            "cores_logical": psutil.cpu_count(logical=True),
            "cores_physical": psutil.cpu_count(logical=False),
            # 0.1 秒的采样窗口：够稳定，又不至于让一个监控请求明显变慢。
            "percent": psutil.cpu_percent(interval=0.1),
        },
        "memory": {
            "total_mb": _mib(memory.total),
            "used_mb": _mib(memory.total - memory.available),
            "available_mb": _mib(memory.available),
            "percent": round(memory.percent, 1),
        },
        "swap": {
            "total_mb": _mib(swap.total),
            "used_mb": _mib(swap.used),
            "percent": round(swap.percent, 1),
        },
        "disk": _disk_usage(),
        "process": {
            "pid": process.pid,
            "rss_mb": _mib(process.memory_info().rss),
            "threads": process.num_threads(),
            "uptime_seconds": int(time.time() - started_at),
            "started_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(started_at)),
        },
        "runtime": {
            "python": sys.version.split()[0],
            "implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "hostname": platform.node(),
            "pid": os.getpid(),
        },
        "packages": _package_versions(),
    }
