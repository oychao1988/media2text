#!/usr/bin/env python3
"""Smoke-test personal Aliyun Drive Web API (client aligned with foyoux/aligo)."""

from __future__ import annotations

import argparse
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOKEN_PATH = ROOT / "data" / "sessions" / "aliyundrive.token.json"

sys.path.insert(0, str(ROOT / "src"))

from media2text.core.cloud.aliyundrive import AliyunDriveClient  # noqa: E402


def fmt_bytes(n: int | None) -> str:
    if n is None:
        return "?"
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    size = float(n)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{n} B"


def fmt_gb_app(n: int | None) -> str:
    if n is None:
        return "?"
    return f"{n / (1024 ** 3):.2f} GB"


def print_section(title: str) -> None:
    print(f"\n== {title} ==")


def print_capacity(client: AliyunDriveClient) -> None:
    cap = client.get_account_capacity()
    print("account space (matches app 容量管理 / aligo get_user_capacity_info):")
    print(
        f"  used={fmt_gb_app(cap.used)} total={fmt_gb_app(cap.total)} "
        f"free={fmt_gb_app(cap.free)} ({cap.used_percent:.0f}% used)"
    )
    print("  breakdown:")
    for label, size in (
        ("备份文件", cap.backup_used),
        ("其他文件", cap.resource_used),
        ("相册", cap.album_used),
        ("笔记", cap.note_used),
    ):
        if size:
            print(f"    - {label}: {fmt_gb_app(size)}")

    drive = client.get_default_drive_usage()
    print(
        "default drive only (V2_DRIVE_GET, NOT account total):",
        f"used={fmt_gb_app(drive.get('used_size'))}",
        f"name={drive.get('name') or drive.get('drive_name')}",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Aliyun Drive API smoke test")
    parser.add_argument("--keep", action="store_true", help="keep uploaded test file")
    args = parser.parse_args()

    if not TOKEN_PATH.is_file():
        print(f"Missing {TOKEN_PATH}; run scripts/aliyundrive_login.py first", file=sys.stderr)
        return 1

    with AliyunDriveClient.open(TOKEN_PATH) as client:
        print_section("auth")
        print("token refresh: ok")

        print_section("user")
        user = client.get_user()
        print("user:", user.get("user_name") or user.get("nick_name") or user.get("user_id"))
        print("drive_id:", client.drive_id)

        print_section("drive + capacity")
        print_capacity(client)

        print_section("list root")
        items = client.list_files(limit=10)
        print(f"{len(items)} item(s) (limit 10, newest first)")
        for item in items:
            kind = item.get("type", "?")
            size = item.get("size")
            size_s = fmt_bytes(size) if kind == "file" and size is not None else ""
            suffix = f" size={size_s}" if size_s else ""
            print(f"  - [{kind}] {item.get('name')} ({item.get('file_id', '')[:12]}...){suffix}")

        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        remote_name = f"media2text-api-test-{stamp}.txt"
        expected_text = f"media2text api smoke test @ {stamp}\n"
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as tmp:
            tmp.write(expected_text)
            tmp_path = Path(tmp.name)

        uploaded_file_id: str | None = None
        try:
            print_section("upload")
            print(f"uploading: {remote_name} ...")
            uploaded = client.upload_file(tmp_path, parent_file_id="root", remote_name=remote_name)
            uploaded_file_id = uploaded.get("file_id")
            print(
                "upload ok:",
                uploaded.get("name"),
                "file_id=",
                uploaded_file_id,
                "size=",
                uploaded.get("size"),
            )

            print_section("search")
            hits = client.search_by_name(
                "media2text-api-test", limit=20, name_prefix=remote_name
            )
            print(f'search name match "media2text-api-test" (filter {remote_name}): {len(hits)} hit(s)')
            for hit in hits:
                print(f"  - {hit.get('name')} ({hit.get('file_id', '')[:12]}...)")
            if not hits:
                print("  (search index may lag; continuing with uploaded file_id)")

            if not uploaded_file_id:
                raise RuntimeError("upload did not return file_id")

            print_section("file metadata")
            meta = client.get_file(uploaded_file_id)
            print("name:", meta.get("name"))
            print("type:", meta.get("type"))
            print("size:", meta.get("size"))
            print("updated_at:", meta.get("updated_at"))

            print_section("download")
            content = client.download_bytes(uploaded_file_id)
            print(f"downloaded bytes: {len(content)}")
            if content.decode("utf-8") != expected_text:
                raise RuntimeError("download content mismatch")
            print("download content: verified")

            if not args.keep:
                print_section("delete (recycle bin)")
                trashed = client.trash(uploaded_file_id)
                print(
                    "trash ok:",
                    trashed.get("file_id") or uploaded_file_id,
                    f"(HTTP {trashed.get('status_code', 200)})",
                )
                uploaded_file_id = None
                hits_after = client.search_by_name(
                    "media2text-api-test", limit=20, name_prefix=remote_name
                )
                if [h for h in hits_after if h.get("name") == remote_name]:
                    print("warning: file still appears in search after trash")
                else:
                    print("search after trash: file not found (expected)")
            else:
                print_section("delete")
                print("skipped (--keep)")
        finally:
            tmp_path.unlink(missing_ok=True)
            if uploaded_file_id and not args.keep:
                try:
                    client.trash(uploaded_file_id)
                except Exception:
                    pass

    print("\nAPI smoke test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
