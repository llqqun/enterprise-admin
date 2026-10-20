"""Storage backends for uploaded files.

The point of the abstraction is that `file_service` never touches the filesystem
directly: switching to object storage later means writing another class that satisfies
`StorageBackend`, not editing the service.

`LocalStorage` resolves every path **under** a single root and refuses anything that
escapes it. That check is the reason this is not just `open(os.path.join(root, key))`:
a single unvalidated `..` is a full arbitrary-write primitive.
"""

from pathlib import Path
from typing import Protocol


class StorageError(Exception):
    """Storage rejected the request (bad key, escape attempt, missing object)."""


class StorageBackend(Protocol):
    def save(self, key: str, data: bytes) -> None: ...

    def read(self, key: str) -> bytes: ...

    def delete(self, key: str) -> None: ...

    def exists(self, key: str) -> bool: ...


class LocalStorage:
    """Files under one root directory, keyed by a relative POSIX-style path."""

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def _resolve(self, key: str) -> Path:
        """Map a relative key to an absolute path, or raise if it escapes the root.

        拒绝而不是「清理」：把 `..` 悄悄去掉会让调用方以为自己传对了，
        而真正安全的做法是让越界请求显式失败。
        """
        if not key or key.startswith(("/", "\\")) or ":" in key:
            raise StorageError(f"非法的存储键：{key!r}")
        candidate = (self._root / key).resolve()
        if candidate != self._root and self._root not in candidate.parents:
            raise StorageError(f"存储键越界：{key!r}")
        return candidate

    def save(self, key: str, data: bytes) -> None:
        target = self._resolve(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    def read(self, key: str) -> bytes:
        target = self._resolve(key)
        if not target.is_file():
            raise StorageError(f"对象不存在：{key!r}")
        return target.read_bytes()

    def delete(self, key: str) -> None:
        target = self._resolve(key)
        # 文件已经不在了也算删除成功：删除天然幂等，重复删除不该报错。
        target.unlink(missing_ok=True)

    def exists(self, key: str) -> bool:
        try:
            return self._resolve(key).is_file()
        except StorageError:
            return False
