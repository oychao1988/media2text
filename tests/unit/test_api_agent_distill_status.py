import json

import pytest

from media2text.api.routes.agent_profiles import _job_dict
from media2text.core.storage.models import CreatorAgentJobRow

pytestmark = pytest.mark.desktop


def _row(**payload) -> CreatorAgentJobRow:
    return CreatorAgentJobRow(
        id="job-1",
        creator_id="c1",
        kind="bootstrap",
        status="deferred",
        trigger="manual",
        source_id=None,
        payload_json=json.dumps(payload),
        created_at="2026-06-08T00:00:00+00:00",
        updated_at="2026-06-08T00:00:00+00:00",
    )


def test_job_dict_exposes_gate_payload_fields() -> None:
    d = _job_dict(
        _row(
            web_channels_ok=3,
            local_chars=120,
            truncated=True,
            deferred_reason="web_and_local_insufficient",
        )
    )
    assert d["webChannelsOk"] == 3
    assert d["localChars"] == 120
    assert d["truncated"] is True
    assert d["deferredReason"] == "web_and_local_insufficient"


def test_job_dict_none_job() -> None:
    assert _job_dict(None) == {}
