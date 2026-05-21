import json

from media2text.core.compliance import (
    COMPLIANCE_VERSION,
    accept_compliance,
    compliance_path,
    is_compliance_accepted,
)


def test_accept_compliance_writes_file(tmp_path) -> None:
    record = accept_compliance(tmp_path)
    path = compliance_path(tmp_path)
    assert path.is_file()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["version"] == COMPLIANCE_VERSION
    assert payload["accepted_at"] == record.accepted_at
    assert is_compliance_accepted(tmp_path)


def test_compliance_not_accepted_by_default(tmp_path) -> None:
    assert not is_compliance_accepted(tmp_path)
