# media2text

Personal CLI to capture Douyin live/VOD media and transcribe for Agent workflows.

## Quick start

```bash
brew install ffmpeg
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
playwright install chromium
media2text doctor --json
media2text auth login --platform douyin
media2text creator add 'https://www.douyin.com/user/<profile>' --watch-live
media2text live watch --daemon
```

## Commands (MVP)

| Command | Status |
|---------|--------|
| `auth login` / `auth status` | Implemented |
| `doctor` | Implemented |
| `creator add` / `list` / `remove` | Implemented |
| `live watch` | Implemented (fixture mode without session; real API TBD) |
| `creator sync` | Implemented (fixture mode without session) |
| `download run` | Implemented |
| `transcribe run` | Implemented (requires `pip install -e ".[transcribe]"`) |
| `pipeline run` | Implemented |

Run tests: `pytest tests/ -v`

See `docs/superpowers/specs/2026-05-20-media2text-douyin-design.md` for full design.
