#!/usr/bin/env python3
"""Compare media2text client vs foyoux/aligo on the same refresh_token.

Requires: pip install -e ".[aliyundrive]"  (or pip install aligo)
Token: data/sessions/aliyundrive.token.json from scripts/aliyundrive_login.py
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOKEN_PATH = ROOT / "data" / "sessions" / "aliyundrive.token.json"
sys.path.insert(0, str(ROOT / "src"))

from media2text.core.cloud.aliyundrive import (  # noqa: E402
    AliyunDriveClient,
    from_aligo,
    load_token,
)


def fmt_gb(n: int) -> str:
    return f"{n / (1024 ** 3):.2f} GB"


def main() -> int:
    if not TOKEN_PATH.is_file():
        print(f"Missing {TOKEN_PATH}", file=sys.stderr)
        return 1

    token = load_token(TOKEN_PATH)
    refresh = token.get("refresh_token")
    if not refresh:
        print("token missing refresh_token", file=sys.stderr)
        return 1

    print("== media2text AliyunDriveClient ==")
    with AliyunDriveClient.open(TOKEN_PATH) as client:
        cap = client.get_account_capacity()
        items = client.list_files(limit=3)
        print(f"capacity: used={fmt_gb(cap.used)} total={fmt_gb(cap.total)} free={fmt_gb(cap.free)}")
        print(f"root items: {len(items)}")
        for item in items:
            print(f"  - {item.get('name')}")

    print("\n== foyoux/aligo ==")
    ali = from_aligo(refresh, level=logging.WARNING)
    cap2 = ali.get_user_capacity_info()
    d = cap2.drive_capacity_details
    print(
        f"capacity: used={fmt_gb(d.drive_used_size)} total={fmt_gb(d.drive_total_size)} "
        f"free={fmt_gb(d.drive_total_size - d.drive_used_size)}"
    )
    ll = ali.get_file_list(limit=3)
    print(f"root items: {len(ll)}")
    for f in ll:
        print(f"  - {f.name}")

    print("\nBoth clients OK (same API surface as aligo Config paths).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
