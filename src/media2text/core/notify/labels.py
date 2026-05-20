from __future__ import annotations

from media2text.core.storage.models import CreatorRow


def creator_label(creator: CreatorRow) -> str:
    if creator.display_name:
        return creator.display_name
    if creator.unique_id:
        return creator.unique_id
    return creator.sec_uid[:16] + ("…" if len(creator.sec_uid) > 16 else "")
