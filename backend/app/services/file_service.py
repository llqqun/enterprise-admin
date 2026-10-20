"""文件上传：落盘 + 元数据。

**安全规则集中在这个文件里**，因为文件上传是最容易写出漏洞的地方：

1. **扩展名白名单，不是黑名单。** 黑名单永远漏（`.phtml`、`.jspx`、`.svgz`…）。
   这里只放行明确的几种，其余一律拒绝。
2. **绝不用客户端文件名做路径。** 原始名可以含 `..\\`、`/`、NUL、双扩展名。
   存储用 `uuid4().hex + "." + ext`，原始名只作为元数据与下载时的文件名。
3. **下载一律 `attachment`。** 否则一个上传的 `.html` 会在本站源的上下文里执行。
4. **内容类型由我们自己映射**，不采信客户端声明的 `Content-Type`。
5. **大小上限在读取时校验**，不能只信 `Content-Length`。
"""

import uuid
from datetime import datetime
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.constants import DelFlagEnum
from app.core.deps import CurrentUser
from app.core.exceptions import BusinessException, NotFoundException
from app.core.response import PageParams
from app.models.file import SysFile
from app.services.storage import LocalStorage, StorageBackend, StorageError

#: 允许上传的扩展名。刻意不含 svg / html / js（可在本站源执行脚本）、
#: 也不含 exe / dll / ps1 / bat（可执行）。
ALLOWED_EXTENSIONS: frozenset[str] = frozenset(
    {
        "png", "jpg", "jpeg", "gif", "webp", "bmp",
        "pdf", "txt", "md", "csv",
        "doc", "docx", "xls", "xlsx",
        "zip",
    }
)

#: 我们自己映射 MIME，不用客户端说的那个。
CONTENT_TYPES: dict[str, str] = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "webp": "image/webp",
    "bmp": "image/bmp",
    "pdf": "application/pdf",
    "txt": "text/plain; charset=utf-8",
    "md": "text/markdown; charset=utf-8",
    "csv": "text/csv; charset=utf-8",
    "doc": "application/msword",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xls": "application/vnd.ms-excel",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "zip": "application/zip",
}

MAX_UPLOAD_BYTES = 10 * 1024 * 1024

_storage: StorageBackend | None = None


def get_storage() -> StorageBackend:
    """进程内单例。换成对象存储时只改这里。"""
    global _storage
    if _storage is None:
        _storage = LocalStorage(Path(get_settings().UPLOAD_DIR))
    return _storage


def _split_extension(filename: str) -> str:
    """取最后一段扩展名并规范化。

    `"report.tar.gz"` → `"gz"`；`"a.PNG"` → `"png"`；没有扩展名 → `""`。
    只取最后一段是有意的：`"shell.php.png"` 的扩展名是 `png`，而它作为一个 png 被服务是安全的
    —— 真正危险的是「按第一段当成可执行类型处理」，那才是漏洞。
    """
    name = filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    if "." not in name:
        return ""
    return name.rsplit(".", 1)[-1].lower()


async def upload(
    db: AsyncSession, upload_file: UploadFile, current: CurrentUser
) -> SysFile:
    original_name = upload_file.filename or ""
    extension = _split_extension(original_name)
    if extension not in ALLOWED_EXTENSIONS:
        raise BusinessException(
            f"不允许的文件类型：{extension or '（无扩展名）'}；允许：{', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )

    data = await upload_file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise BusinessException(f"文件超过 {MAX_UPLOAD_BYTES // (1024 * 1024)} MB 上限")
    if not data:
        raise BusinessException("文件为空")

    today = datetime.now()
    # 存储名完全由服务端生成：客户端文件名只作为元数据保存。
    stored_name = f"{uuid.uuid4().hex}.{extension}"
    storage_path = f"{today:%Y/%m/%d}/{stored_name}"

    get_storage().save(storage_path, data)

    row = SysFile(
        stored_name=stored_name,
        # 原始名只用于展示；截断到列宽，避免超长文件名把写库变成失败点。
        original_name=(original_name or stored_name)[:255],
        storage_path=storage_path,
        extension=extension,
        content_type=CONTENT_TYPES.get(extension, "application/octet-stream"),
        size_bytes=len(data),
        upload_by=current.user_name,
        del_flag=DelFlagEnum.EXISTS,
    )
    db.add(row)
    await db.flush()
    await db.refresh(row)
    return row


async def list_files(
    db: AsyncSession, params: PageParams, *, original_name: str | None = None
) -> tuple[list[SysFile], int]:
    statement = select(SysFile)
    if original_name:
        statement = statement.where(SysFile.original_name.contains(original_name))

    total = int(await db.scalar(select(func.count()).select_from(statement.subquery())) or 0)
    offset = (params.page_num - 1) * params.page_size
    rows = list(
        await db.scalars(
            statement.order_by(SysFile.file_id.desc()).limit(params.page_size).offset(offset)
        )
    )
    return rows, total


async def get_file(db: AsyncSession, file_id: int) -> SysFile:
    row = await db.scalar(select(SysFile).where(SysFile.file_id == file_id))
    if row is None:
        raise NotFoundException("文件不存在")
    return row


async def read_file(db: AsyncSession, file_id: int) -> tuple[SysFile, bytes]:
    row = await get_file(db, file_id)
    try:
        return row, get_storage().read(row.storage_path)
    except StorageError as exc:
        # 记录在、文件不在：这是数据不一致，不是「文件不存在」——
        # 两者对调用方含义不同，所以给出不同的消息。
        raise BusinessException(f"文件已丢失（记录仍在）：{exc}") from exc


async def delete_files(db: AsyncSession, file_ids: list[int]) -> None:
    rows = list(await db.scalars(select(SysFile).where(SysFile.file_id.in_(file_ids))))
    for row in rows:
        # 先删字节再删记录：反过来的话，删记录成功后删字节失败就留下一个不可见的孤儿文件。
        get_storage().delete(row.storage_path)
        row.del_flag = DelFlagEnum.DELETED
    await db.flush()
