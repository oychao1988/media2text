from pathlib import Path
from unittest.mock import MagicMock, patch

from media2text.core.ffmpeg import remux_to_mp4


@patch("media2text.core.ffmpeg.subprocess.run")
def test_remux_calls_ffmpeg(mock_run: MagicMock, tmp_path: Path) -> None:
    src = tmp_path / "a.flv"
    src.write_bytes(b"fake")
    dst = tmp_path / "out.mp4"

    def _create_output(*_args, **_kwargs) -> None:
        dst.write_bytes(b"ok")

    mock_run.side_effect = _create_output
    remux_to_mp4(ffmpeg="ffmpeg", src=src, dst=dst)
    assert mock_run.called
    assert mock_run.call_args[0][0][0] == "ffmpeg"
