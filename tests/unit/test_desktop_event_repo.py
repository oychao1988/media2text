import pytest

from media2text.core.storage.db import connect
from media2text.core.storage.repos import DesktopEventRepo

pytestmark = pytest.mark.desktop


def test_enqueue_and_claim_pending(tmp_path) -> None:
    conn = connect(tmp_path / "media2text.db")
    repo = DesktopEventRepo(conn)
    eid = repo.enqueue_creator_updated("creator-1")
    pending = repo.claim_pending(limit=10)
    assert len(pending) == 1
    assert pending[0].id == eid
    assert pending[0].creator_id == "creator-1"
    assert pending[0].event_type == "creator.updated"
    conn.close()


def test_mark_delivered_excludes_from_claim(tmp_path) -> None:
    conn = connect(tmp_path / "media2text.db")
    repo = DesktopEventRepo(conn)
    eid = repo.enqueue_creator_updated("creator-1")
    repo.mark_delivered(eid)
    assert repo.claim_pending(limit=10) == []
    conn.close()
