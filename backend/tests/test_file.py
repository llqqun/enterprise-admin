"""文件上传。

这个文件里的大部分断言是**安全断言**，不是功能断言：扩展名白名单、路径穿越、
下载强制附件。文件上传是最容易写出漏洞的功能，所以每条规则都单独钉一下。
"""

from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.file import SysFile
from app.services import file_service
from app.services.storage import LocalStorage, StorageError

FILE_URL = "/api/v1/file"


@pytest.fixture(autouse=True)
def temp_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """把存储指向临时目录。

    不这么做的话，测试会往 `backend/uploads` 里写真实文件 —— 跑一次测试留一堆垃圾，
    而且用例之间会互相看到对方的文件。
    """
    monkeypatch.setattr(file_service, "_storage", LocalStorage(tmp_path))
    return tmp_path


async def _upload(
    client: AsyncClient, headers: dict[str, str], name: str, payload: bytes = b"hello", content_type: str = "image/png"
) -> tuple[int, dict]:
    resp = await client.post(
        f"{FILE_URL}/upload",
        headers=headers,
        files={"file": (name, payload, content_type)},
    )
    return resp.status_code, resp.json()


# ---------------------------------------------------------------------------
# 存储层：路径穿越
# ---------------------------------------------------------------------------


def test_storage_refuses_to_escape_its_root(tmp_path: Path) -> None:
    """一个没校验的 `..` 就是一个任意写原语。"""
    storage = LocalStorage(tmp_path / "root")

    with pytest.raises(StorageError):
        storage.save("../../escaped.txt", b"x")
    with pytest.raises(StorageError):
        storage.read("/etc/passwd")
    with pytest.raises(StorageError):
        storage.save("C:/Windows/evil.txt", b"x")


def test_storage_roundtrip(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path / "root")

    storage.save("2026/10/20/a.txt", b"hello")

    assert storage.exists("2026/10/20/a.txt")
    assert storage.read("2026/10/20/a.txt") == b"hello"
    storage.delete("2026/10/20/a.txt")
    assert not storage.exists("2026/10/20/a.txt")
    # 删不存在的对象不报错（删除天然幂等）
    storage.delete("2026/10/20/a.txt")


# ---------------------------------------------------------------------------
# 上传
# ---------------------------------------------------------------------------


async def test_upload_stores_a_generated_name(
    client: AsyncClient, admin_headers: dict[str, str], db_session: AsyncSession
) -> None:
    status, body = await _upload(client, admin_headers, "报告.pdf", b"%PDF-1.4 fake")

    assert status == 200
    row = body["data"]
    assert row["original_name"] == "报告.pdf"
    assert row["extension"] == "pdf"
    assert row["content_type"] == "application/pdf"
    # 存储名由服务端生成，与原始名无关
    stored = await db_session.scalar(select(SysFile).where(SysFile.file_id == row["file_id"]))
    assert stored is not None
    assert stored.stored_name != "报告.pdf"
    assert stored.stored_name.endswith(".pdf")
    assert ".." not in stored.storage_path


async def test_upload_rejects_non_whitelisted_extensions(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    """白名单而不是黑名单：`.html` / `.svg` 能在本站源执行脚本，`.exe` 可执行。"""
    for name in ("evil.html", "evil.svg", "evil.exe", "evil.ps1", "noextension"):
        status, body = await _upload(client, admin_headers, name)
        assert status == 400, f"{name} should have been rejected"
        assert "不允许的文件类型" in body["msg"]


async def test_a_traversal_filename_cannot_escape(
    client: AsyncClient, admin_headers: dict[str, str], db_session: AsyncSession
) -> None:
    """`../../x.png` 的扩展名是 png，所以会被接受 —— 但落盘路径必须仍在根目录下。"""
    status, body = await _upload(client, admin_headers, "../../evil.png", b"png bytes")

    assert status == 200
    stored = await db_session.scalar(
        select(SysFile).where(SysFile.file_id == body["data"]["file_id"])
    )
    assert stored is not None
    assert ".." not in stored.storage_path
    assert "/" not in stored.stored_name
    assert stored.storage_path.count("/") >= 2  # YYYY/MM/DD/<name>


async def test_double_extension_is_treated_as_the_last_one(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    """`shell.php.png` 按 png 处理并作为 png 下发，是安全的；按 php 处理才是漏洞。"""
    status, body = await _upload(client, admin_headers, "shell.php.png")

    assert status == 200
    assert body["data"]["extension"] == "png"
    assert body["data"]["content_type"] == "image/png"


async def test_empty_file_is_rejected(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    status, body = await _upload(client, admin_headers, "empty.png", b"")

    assert status == 400
    assert "为空" in body["msg"]


async def test_oversized_file_is_rejected(
    client: AsyncClient, admin_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """上限在读取后校验，不依赖客户端声明的 Content-Length。"""
    monkeypatch.setattr(file_service, "MAX_UPLOAD_BYTES", 8)

    status, body = await _upload(client, admin_headers, "big.txt", b"0123456789")

    assert status == 400
    assert "上限" in body["msg"]


# ---------------------------------------------------------------------------
# 下载
# ---------------------------------------------------------------------------


async def test_download_returns_bytes_as_an_attachment(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    payload = b"%PDF-1.4 hello"
    _, body = await _upload(client, admin_headers, "doc.pdf", payload)
    file_id = body["data"]["file_id"]

    resp = await client.get(f"{FILE_URL}/download/{file_id}", headers=admin_headers)

    assert resp.status_code == 200
    assert resp.content == payload
    # 强制附件：上传的 html 若被内联渲染就是本站源上的 XSS
    assert "attachment" in resp.headers["content-disposition"]
    assert resp.headers["x-content-type-options"] == "nosniff"


async def test_download_of_an_unknown_id_is_404(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    assert (await client.get(f"{FILE_URL}/download/999999", headers=admin_headers)).status_code == 404


# ---------------------------------------------------------------------------
# 列表与删除
# ---------------------------------------------------------------------------


async def test_list_is_paged(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    await _upload(client, admin_headers, "a.png")
    await _upload(client, admin_headers, "b.png")

    resp = await client.get(FILE_URL, headers=admin_headers, params={"page_size": 1})

    data = resp.json()["data"]
    assert data["total"] == 2
    assert len(data["rows"]) == 1


async def test_delete_removes_bytes_and_record(
    client: AsyncClient, admin_headers: dict[str, str], db_session: AsyncSession
) -> None:
    _, body = await _upload(client, admin_headers, "doomed.png", b"bytes")
    file_id = body["data"]["file_id"]
    stored = await db_session.scalar(select(SysFile).where(SysFile.file_id == file_id))
    assert stored is not None
    key = stored.storage_path
    assert file_service.get_storage().exists(key)

    resp = await client.delete(f"{FILE_URL}/{file_id}", headers=admin_headers)

    assert resp.status_code == 200
    # 字节已删除
    assert not file_service.get_storage().exists(key)
    # 记录是软删除：行还在
    row = await db_session.scalar(
        select(SysFile).where(SysFile.file_id == file_id).execution_options(include_deleted=True)
    )
    assert row is not None and row.del_flag == "2"


# ---------------------------------------------------------------------------
# 权限
# ---------------------------------------------------------------------------


async def test_upload_requires_permission(
    client: AsyncClient, staff_headers: dict[str, str]
) -> None:
    status, _ = await _upload(client, staff_headers, "x.png")
    assert status == 403


async def test_list_requires_authentication(client: AsyncClient) -> None:
    assert (await client.get(FILE_URL)).status_code == 401
