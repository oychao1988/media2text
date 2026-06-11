"""Session HLS playback: cloud upload resolution (thin service, spec U13)."""

from __future__ import annotations

from media2text.core.storage.repos import CloudUploadRepo


def find_part_upload(conn, *, session_id: str, part_index: int):
    for row in CloudUploadRepo(conn).list_for_session(session_id):
        if row.part_index == part_index and row.upload_status == "done" and row.cloud_file_id:
            return row
        if (
            row.upload_status == "done"
            and row.cloud_file_id
            and row.file_kind == "m4s"
            and f"seg-{part_index:05d}.m4s" in (row.file_name or "")
        ):
            return row
    return None


def find_init_upload(conn, *, session_id: str):
    for row in CloudUploadRepo(conn).list_for_session(session_id):
        if row.upload_status == "done" and row.cloud_file_id and row.file_kind == "init_mp4":
            return row
        if row.upload_status == "done" and row.cloud_file_id and row.file_name == "init.mp4":
            return row
    return None


def find_m3u8_upload(conn, *, session_id: str):
    for row in CloudUploadRepo(conn).list_for_session(session_id):
        if row.upload_status == "done" and row.cloud_file_id and row.file_kind == "m3u8":
            return row
        if row.upload_status == "done" and row.cloud_file_id and row.file_name == "master.m3u8":
            return row
    return None
