"""Rolling cleanup helpers for Aliyun Drive live backups."""

from __future__ import annotations

from dataclasses import dataclass

VIDEO_CLEANUP_FILE_KINDS: frozenset[str] = frozenset({"mp4", "flv", "m4s", "init_mp4"})


@dataclass(frozen=True)
class RollingCleanupResult:
    db: tuple[str, ...] = ()
    recycle_bin: tuple[str, ...] = ()

    @property
    def total(self) -> int:
        return len(self.db) + len(self.recycle_bin)

    def __bool__(self) -> bool:
        return self.total > 0


def format_rolling_cleanup_notify_body(result: RollingCleanupResult) -> str:
    parts = [f"云盘滚动清理，已删除 {result.total} 个文件："]
    if result.db:
        parts.append("[DB 记录]")
        parts.extend(f"- {name}" for name in result.db)
    if result.recycle_bin:
        parts.append("[回收站]")
        parts.extend(f"- {name}" for name in result.recycle_bin)
    return "\n".join(parts)


def is_video_cleanup_file_kind(file_kind: str) -> bool:
    return file_kind in VIDEO_CLEANUP_FILE_KINDS


def is_video_cleanup_filename(name: str) -> bool:
    lower = name.lower().strip()
    if not lower:
        return False
    if lower == "init.mp4":
        return True
    if lower.endswith((".mp4", ".flv", ".m4s")):
        return True
    return lower.startswith("seg-") and lower.endswith(".m4s")


def is_stale_cloud_delete_error(exc: BaseException) -> str | None:
    """Return reason when cloud file is gone or not deletable; DB row may be dropped."""
    msg = str(exc).lower()
    if "recycle bin" in msg and (
        "operationnotsupport" in msg or "not supported" in msg
    ):
        return "recycle_bin"
    if "notfound.fileid" in msg or "/v3/file/delete failed 404" in msg:
        return "not_found"
    return None


def is_recycle_bin_delete_error(exc: BaseException) -> bool:
    """True when /v3/file/delete rejects a file already in Aliyun recycle bin."""
    return is_stale_cloud_delete_error(exc) == "recycle_bin"
