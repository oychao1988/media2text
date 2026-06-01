"""Personal Aliyun Drive (alipan.com) Web API client.

API paths and headers follow foyoux/aligo:
https://github.com/foyoux/aligo (src/aligo/core/Config.py, Auth.py, Create.py)

Uses httpx only (no aligo runtime dependency). Optional aligo bridge: ``from_aligo()``.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

# --- aligo Config.py ---
API_HOST = "https://api.aliyundrive.com"
AUTH_HOST = "https://auth.aliyundrive.com"
V2_ACCOUNT_TOKEN = "/v2/account/token"
V2_USER_GET = "/v2/user/get"
V2_DRIVE_GET = "/v2/drive/get"
V2_FILE_GET = "/v2/file/get"
V2_FILE_SEARCH = "/v2/file/search"
V2_FILE_COMPLETE = "/v2/file/complete"
V2_FILE_GET_UPLOAD_URL = "/v2/file/get_upload_url"
V2_FILE_GET_DOWNLOAD_URL = "/v2/file/get_download_url"
V2_RECYCLEBIN_TRASH = "/v2/recyclebin/trash"
ADRIVE_V3_FILE_LIST = "/adrive/v3/file/list"
ADRIVE_V2_FILE_CREATEWITHFOLDERS = "/adrive/v2/file/createWithFolders"
ADRIVE_V1_USER_GET_USER_CAPACITY_INFO = "/adrive/v1/user/getUserCapacityInfo"

# aligo UNI_HEADERS + Content-Type for JSON POST
DEFAULT_HEADERS = {
    "Referer": "https://aliyundrive.com",
    "User-Agent": (
        "AliApp(AYSD/5.8.0) com.alicloud.databox/37029260 "
        "Channel/36176927979800@rimet_android_5.8.0 language/zh-CN /Android Mobile/Xiaomi Redmi"
    ),
    "x-canary": "client=Android,app=adrive,version=v5.8.0",
    "Content-Type": "application/json",
}

# aligo Create.__UPLOAD_CHUNK_SIZE (10 MiB)
UPLOAD_CHUNK_SIZE = 10 * 1024 * 1024

DOWNLOAD_REFERER = "https://www.aliyundrive.com/"

DEFAULT_TOKEN_REL = Path("sessions/aliyundrive.token.json")

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class AccountCapacity:
    """Account-level quota (matches Aliyun Drive app 容量管理)."""

    total: int
    used: int
    backup_used: int
    resource_used: int
    album_used: int
    note_used: int

    @property
    def free(self) -> int:
        return self.total - self.used

    @property
    def used_percent(self) -> float:
        if not self.total:
            return 0.0
        return self.used / self.total * 100


def default_token_path(workspace: Path) -> Path:
    return workspace / DEFAULT_TOKEN_REL


def load_token(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"Missing token file: {path} (run scripts/aliyundrive_login.py)")
    return json.loads(path.read_text(encoding="utf-8"))


def save_token(token: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(token, ensure_ascii=False, indent=2), encoding="utf-8")
    path.chmod(0o600)


def _part_info_list(file_size: int, *, chunk_size: int = UPLOAD_CHUNK_SIZE) -> list[dict[str, int]]:
    count = max(1, math.ceil(file_size / chunk_size))
    return [{"part_number": i + 1} for i in range(count)]


class AliyunDriveClient:
    """httpx client for personal Aliyun Drive Web API."""

    def __init__(
        self,
        *,
        token: dict[str, Any],
        token_path: Path | None = None,
        timeout: float = 60.0,
    ) -> None:
        self._token = token
        self._token_path = token_path
        self._http = httpx.Client(headers=dict(DEFAULT_HEADERS), timeout=timeout)
        self._drive_id: str | None = token.get("default_drive_id")

    def __enter__(self) -> AliyunDriveClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def close(self) -> None:
        self._http.close()

    @classmethod
    def open(cls, token_path: Path, *, timeout: float = 60.0) -> AliyunDriveClient:
        token = load_token(token_path)
        client = cls(token=token, token_path=token_path, timeout=timeout)
        client.refresh()
        return client

    @property
    def drive_id(self) -> str:
        if not self._drive_id:
            user = self.post(V2_USER_GET, {})
            self._drive_id = self._token.get("default_drive_id") or user.get("default_drive_id")
        if not self._drive_id:
            raise RuntimeError("missing default_drive_id")
        return str(self._drive_id)

    def refresh(self) -> dict[str, Any]:
        refresh_token = self._token.get("refresh_token")
        if not refresh_token:
            raise RuntimeError("token missing refresh_token")
        resp = self._http.post(
            f"{AUTH_HOST}{V2_ACCOUNT_TOKEN}",
            json={"grant_type": "refresh_token", "refresh_token": refresh_token},
        )
        resp.raise_for_status()
        self._token.update(resp.json())
        self._http.headers["Authorization"] = self._token["access_token"]
        if self._token_path:
            save_token(self._token, self._token_path)
        return self._token

    def post(self, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        resp = self._http.post(f"{API_HOST}{path}", json=body or {})
        if resp.status_code >= 400:
            raise RuntimeError(f"{path} failed {resp.status_code}: {resp.text[:500]}")
        if not resp.content.strip():
            return {"ok": True, "status_code": resp.status_code}
        return resp.json()

    def get_user(self) -> dict[str, Any]:
        return self.post(V2_USER_GET, {})

    def list_files(
        self,
        *,
        parent_file_id: str = "root",
        limit: int = 100,
        drive_id: str | None = None,
    ) -> list[dict[str, Any]]:
        listing = self.post(
            ADRIVE_V3_FILE_LIST,
            {
                "drive_id": drive_id or self.drive_id,
                "parent_file_id": parent_file_id,
                "limit": limit,
                "order_by": "updated_at",
                "order_direction": "DESC",
            },
        )
        return listing.get("items") or []

    def search_by_name(
        self,
        name_match: str,
        *,
        limit: int = 20,
        name_prefix: str | None = None,
        drive_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search using aligo DSL: ``name match \"...\"``."""
        query = f'name match "{name_match}"'
        result = self.post(
            V2_FILE_SEARCH,
            {"drive_id": drive_id or self.drive_id, "query": query, "limit": limit},
        )
        items: list[dict[str, Any]] = result.get("items") or []
        if name_prefix:
            items = [i for i in items if str(i.get("name", "")).startswith(name_prefix)]
        return items

    def get_file(self, file_id: str, *, drive_id: str | None = None) -> dict[str, Any]:
        return self.post(V2_FILE_GET, {"drive_id": drive_id or self.drive_id, "file_id": file_id})

    def get_account_capacity(self) -> AccountCapacity:
        cap = self.post(ADRIVE_V1_USER_GET_USER_CAPACITY_INFO, {})
        d = cap.get("drive_capacity_details") or {}
        return AccountCapacity(
            total=int(d.get("drive_total_size") or 0),
            used=int(d.get("drive_used_size") or 0),
            backup_used=int(d.get("backup_drive_used_size") or 0),
            resource_used=int(d.get("resource_drive_used_size") or 0),
            album_used=int(d.get("album_drive_used_size") or 0),
            note_used=int(d.get("note_drive_used_size") or 0),
        )

    def get_default_drive_usage(self) -> dict[str, Any]:
        """Single default drive stats only — not full account usage."""
        return self.post(V2_DRIVE_GET, {"drive_id": self.drive_id})

    def get_download_url(self, file_id: str, *, drive_id: str | None = None, expire_sec: int = 900) -> str:
        result = self.post(
            V2_FILE_GET_DOWNLOAD_URL,
            {"drive_id": drive_id or self.drive_id, "file_id": file_id, "expire_sec": expire_sec},
        )
        url = result.get("url") or result.get("cdn_url") or result.get("internal_url")
        if not url:
            raise RuntimeError(f"get_download_url missing url: {result}")
        return str(url)

    def download_bytes(self, file_id: str, *, drive_id: str | None = None) -> bytes:
        url = self.get_download_url(file_id, drive_id=drive_id)
        with httpx.Client(timeout=120.0, follow_redirects=True) as dl:
            resp = dl.get(url, headers={"Referer": DOWNLOAD_REFERER})
        if resp.status_code >= 400:
            raise RuntimeError(f"download failed {resp.status_code}: {resp.text[:200]}")
        return resp.content

    def trash(self, file_id: str, *, drive_id: str | None = None) -> dict[str, Any]:
        return self.post(V2_RECYCLEBIN_TRASH, {"drive_id": drive_id or self.drive_id, "file_id": file_id})

    def upload_file(
        self,
        local_path: Path,
        *,
        parent_file_id: str = "root",
        remote_name: str | None = None,
        drive_id: str | None = None,
        check_name_mode: str = "auto_rename",
    ) -> dict[str, Any]:
        """Upload local file (aligo-style createWithFolders + multipart PUT)."""
        data = local_path.read_bytes()
        size = len(data)
        name = remote_name or local_path.name
        did = drive_id or self.drive_id
        parts = _part_info_list(size)

        create_body: dict[str, Any] = {
            "drive_id": did,
            "parent_file_id": parent_file_id,
            "name": name,
            "type": "file",
            "size": size,
            "check_name_mode": check_name_mode,
            "part_info_list": parts,
        }
        if size > 1024:
            create_body["pre_hash"] = hashlib.sha1(data[:1024]).hexdigest()

        created = self.post(ADRIVE_V2_FILE_CREATEWITHFOLDERS, create_body)
        if created.get("rapid_upload"):
            return created

        file_id = created["file_id"]
        upload_id = created["upload_id"]
        upload_parts = created.get("part_info_list") or []
        if not upload_parts:
            parts_resp = self.post(
                V2_FILE_GET_UPLOAD_URL,
                {
                    "drive_id": did,
                    "file_id": file_id,
                    "upload_id": upload_id,
                    "part_info_list": parts,
                },
            )
            upload_parts = parts_resp.get("part_info_list") or []

        for part in upload_parts:
            num = int(part["part_number"])
            start = (num - 1) * UPLOAD_CHUNK_SIZE
            chunk = data[start : start + UPLOAD_CHUNK_SIZE]
            self._put_part(str(part["upload_url"]), chunk)

        return self.post(
            V2_FILE_COMPLETE,
            {
                "drive_id": did,
                "file_id": file_id,
                "upload_id": upload_id,
                "part_info_list": upload_parts,
            },
        )

    @staticmethod
    def _put_part(upload_url: str, chunk: bytes) -> None:
        # OSS presigned URL: no API Authorization / x-canary (see aligo issue patterns).
        with httpx.Client(timeout=120.0) as put_client:
            resp = put_client.put(upload_url, content=chunk)
        if resp.status_code not in (200, 201, 409):
            raise RuntimeError(f"upload part failed: {resp.status_code} {resp.text[:200]}")


def from_aligo(refresh_token: str, *, level: int = logging.WARNING) -> Any:
    """Optional bridge to foyoux/aligo when ``pip install aligo`` is available."""
    try:
        from aligo import Aligo
    except ImportError as exc:
        raise ImportError(
            "aligo not installed; run: pip install aligo  or  pip install -e '.[aliyundrive]'"
        ) from exc
    return Aligo(refresh_token=refresh_token, level=level)
