from unittest.mock import MagicMock

import pytest

from media2text.api.services.drain_interval import resolve_drain_interval_sec
from media2text.core.config import AppConfig, DesktopConfig

pytestmark = pytest.mark.desktop


def test_drain_interval_external(tmp_path) -> None:
    cfg = AppConfig(
        workspace=tmp_path / "data",
        desktop=DesktopConfig(external_drain_interval_sec=5),
    )
    sup = MagicMock()
    sup.status_dict.return_value = {"managed_by": "external"}
    assert resolve_drain_interval_sec(cfg, supervisor=sup) == 5.0


def test_drain_interval_embedded(tmp_path) -> None:
    cfg = AppConfig(
        workspace=tmp_path / "data",
        desktop=DesktopConfig(external_drain_interval_sec=5),
    )
    sup = MagicMock()
    sup.status_dict.return_value = {"managed_by": "embedded"}
    assert resolve_drain_interval_sec(cfg, supervisor=sup) == 1.5


def test_drain_interval_default_without_supervisor(tmp_path) -> None:
    cfg = AppConfig(workspace=tmp_path / "data")
    assert resolve_drain_interval_sec(cfg, supervisor=None) == 1.5
