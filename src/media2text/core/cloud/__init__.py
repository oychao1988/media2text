"""Cloud storage adapters."""

from media2text.core.cloud.aliyundrive import (
    AliyunDriveClient,
    AccountCapacity,
    compute_pre_hash,
    decide_duplicate_action,
)
from media2text.core.cloud.live_upload import maybe_upload_live_to_aliyundrive
from media2text.core.cloud.paths import file_pre_hash, sanitize_path_segment

__all__ = [
    "AccountCapacity",
    "AliyunDriveClient",
    "compute_pre_hash",
    "decide_duplicate_action",
    "file_pre_hash",
    "maybe_upload_live_to_aliyundrive",
    "sanitize_path_segment",
]
