from pathlib import Path

from media2text.core.config import AppConfig
from media2text.core.storage.models import LiveSessionRow
from media2text.core.summarize.merger import merge_sessions

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "summarize"


class StubBackend:
    engine = "openai"
    model = "stub"
    provider_base_url = None

    def summarize_text(self, profile: str, text: str, *, merge_pass: bool = False) -> str:
        return f"SUMMARY:{profile}:{len(text)}"

    def summarize_chunks(
        self, profile: str, chunks: list[str], *, merge_pass: bool = False
    ) -> str:
        return f"SUMMARY:{profile}:{sum(len(c) for c in chunks)}"


def test_merge_two_parts_writes_merged_sidecar(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    live_dir = tmp_path / "data" / "creators" / "uid" / "live"
    live_dir.mkdir(parents=True)
    p1 = live_dir / "20260601T124448Z.mp4"
    p2 = live_dir / "20260601T130643Z.mp4"
    p1.write_bytes(b"x")
    p2.write_bytes(b"x")
    p1.with_suffix(".transcript.json").write_text(
        (FIXTURES / "part1.json").read_text(), encoding="utf-8"
    )
    p2.with_suffix(".transcript.json").write_text(
        (FIXTURES / "part2.json").read_text(), encoding="utf-8"
    )

    cfg = AppConfig.load()
    sessions = [
        LiveSessionRow(
            id="s1",
            creator_id="c1",
            room_id="r",
            ffmpeg_pid=None,
            started_at="2026-06-01T12:00:00+00:00",
            ended_at="2026-06-01T12:30:00+00:00",
            local_path=str(p1),
            temp_path=None,
            status="completed",
            error=None,
        ),
        LiveSessionRow(
            id="s2",
            creator_id="c1",
            room_id="r",
            ffmpeg_pid=None,
            started_at="2026-06-01T12:31:00+00:00",
            ended_at="2026-06-01T13:00:00+00:00",
            local_path=str(p2),
            temp_path=None,
            status="completed",
            error=None,
        ),
    ]
    md, _ = merge_sessions(
        cfg, backend=StubBackend(), sessions=sessions, workspace=tmp_path / "data"
    )
    assert md.name == "20260601_merged.summary.md"
