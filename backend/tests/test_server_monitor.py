"""服务监控。

断言只针对**形状与合理区间**，不针对具体的 CPU 数值 —— 后者每次运行都不一样，
写死等于给自己留一个随机失败的测试。唯独「CPU 占用不是永远 0」这一条是刻意的：
`cpu_percent()` 不传 interval 时第一次调用必定返回 0.0，那样的监控页比没有更糟。
"""

import time

from httpx import AsyncClient

SERVER_URL = "/api/v1/monitor/server"


async def test_shape(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    resp = await client.get(SERVER_URL, headers=admin_headers)

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert set(data) == {"cpu", "memory", "swap", "disk", "process", "runtime", "packages"}


async def test_cpu_readings(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    cpu = (await client.get(SERVER_URL, headers=admin_headers)).json()["data"]["cpu"]

    assert cpu["cores_logical"] >= 1
    assert 0.0 <= cpu["percent"] <= 100.0


async def test_cpu_percent_uses_a_sampling_window(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    """`cpu_percent()` 不传 interval 时第一次调用返回 0.0 —— 一个永远显示 0% 的监控页比没有更糟。

    直接度量 `collect()` 的耗时：采样窗口是 100ms，所以它不可能瞬间返回。
    """
    from app.services.server_service import collect

    started = time.perf_counter()
    snapshot = collect()
    elapsed = time.perf_counter() - started

    assert elapsed >= 0.08, f"collect() returned in {elapsed:.3f}s; the CPU sampling window is missing"
    assert 0.0 <= snapshot["cpu"]["percent"] <= 100.0


async def test_memory_readings_are_consistent(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    memory = (await client.get(SERVER_URL, headers=admin_headers)).json()["data"]["memory"]

    assert memory["total_mb"] > 0
    assert 0 <= memory["used_mb"] <= memory["total_mb"]
    assert 0.0 <= memory["percent"] <= 100.0


async def test_disk_entries_are_plausible(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    disks = (await client.get(SERVER_URL, headers=admin_headers)).json()["data"]["disk"]

    assert disks, "at least one mounted filesystem should be reported"
    for entry in disks:
        assert entry["total_mb"] > 0
        assert entry["mount"]
        assert 0.0 <= entry["percent"] <= 100.0


async def test_process_and_runtime(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    data = (await client.get(SERVER_URL, headers=admin_headers)).json()["data"]

    assert data["process"]["pid"] > 0
    assert data["process"]["uptime_seconds"] >= 0
    assert data["runtime"]["python"].startswith("3.")
    assert data["runtime"]["implementation"] == "CPython"


async def test_package_versions_are_reported(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    packages = (await client.get(SERVER_URL, headers=admin_headers)).json()["data"]["packages"]

    assert "fastapi" in packages
    assert packages["fastapi"], "a dependency that is definitely installed must have a version"
    assert packages["psutil"]


async def test_requires_authentication(client: AsyncClient) -> None:
    assert (await client.get(SERVER_URL)).status_code == 401


async def test_requires_the_permission(client: AsyncClient, staff_headers: dict[str, str]) -> None:
    assert (await client.get(SERVER_URL, headers=staff_headers)).status_code == 403
