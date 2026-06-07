"""Manual acceptance integration for agent-self-evolution epic (S10, S15)."""

from __future__ import annotations

import json
import threading
import time

import pytest
from typer.testing import CliRunner

from media2text.agent.ai_agent import AIAgent
from media2text.agent.curator import list_backups, run_curator
from media2text.agent.hermes_state import SessionDB
from media2text.agent.profile_resolver import resolve_profile, save_profile_yaml
from media2text.agent.run_agent import agent_app
from media2text.agent.runtime_provider import LlmCompletion, LlmToolCall, MockChatClient
from media2text.agent.skill_usage import is_pinned, mark_agent_created
from media2text.core.config import AppConfig
from media2text.core.storage.db import connect
from media2text.core.storage.repos import CreatorRepo

pytestmark = pytest.mark.agent

_REVIEW_MARKERS = (
    "background memory review",
    "background skill review",
    "silent background review",
)


def _seed_creator(workspace, *, sec_uid: str, nickname: str) -> str:
    conn = connect(workspace / "media2text.db")
    cid = CreatorRepo(conn).add(
        sec_uid=sec_uid,
        profile_url=f"https://www.douyin.com/user/{sec_uid}",
        platform="douyin",
        display_name=nickname,
    )
    conn.close()
    return cid


class SkillReviewTrackingClient(MockChatClient):
    """Routes mock completions to foreground vs background review by prompt markers."""

    def __init__(self, foreground: list[LlmCompletion], review: list[LlmCompletion]) -> None:
        super().__init__(foreground)
        self._review = list(review)
        self.review_calls: list[dict] = []
        self._lock = threading.Lock()

    def complete(self, **kwargs):
        messages = kwargs.get("messages") or []
        is_review = any(
            m.get("role") == "user"
            and isinstance(m.get("content"), str)
            and any(marker in m["content"].lower() for marker in _REVIEW_MARKERS)
            for m in messages
        )
        if is_review:
            with self._lock:
                self.review_calls.append(kwargs)
                if self._review:
                    item = self._review.pop(0)
                    return item
                return LlmCompletion(content="review done")
        return super().complete(**kwargs)


def test_s10_review_patches_distill_perspective_pitfall(tmp_path) -> None:
    """S10: user tone correction → background review patches distill perspective pitfall."""
    ws = tmp_path / "data"
    slug = "creator-a-perspective"
    old_pitfall = "口吻偏书面，爱用书面总结"
    new_pitfall = "更口语、少说黑话，像直播聊天"
    cfg = AppConfig.model_validate(
        {
            "workspace": str(ws),
            "memory": {"nudge_interval": 0},
            "skills": {"creation_nudge_interval": 1},
            "agent": {"review_enabled": True},
        }
    )

    cid = _seed_creator(ws, sec_uid="sec_s10", nickname="Creator A")
    profile = resolve_profile(creator_id=cid, cfg=cfg)
    save_profile_yaml(profile, {"distill": {"skill_slug": slug}})
    profile = resolve_profile(creator_id=cid, cfg=cfg)

    skill_dir = profile.memory_paths.profile_dir / "skills" / slug
    refs = skill_dir / "references" / "research"
    refs.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {slug}\ndescription: persona\n---\n# Pitfall\n{old_pitfall}\n",
        encoding="utf-8",
    )
    corpus_path = refs / "00-local-corpus.md"
    corpus_path.write_text("CORPUS_ORIGINAL", encoding="utf-8")

    from media2text.agent.skill_usage import pin

    pin(profile, slug)

    conn = connect(ws / "media2text.db")
    db = SessionDB(conn)
    thread_id = "t-s10"
    db.create_session(display_thread_id=thread_id, title="s10", creator_id=cid)

    review_client = SkillReviewTrackingClient(
        foreground=[
            LlmCompletion(
                tool_calls=[
                    LlmToolCall(
                        id="fg-1",
                        name="skills_list",
                        arguments="{}",
                    )
                ]
            ),
            LlmCompletion(content="好的，我会按更口语的方式理解这位博主。"),
        ],
        review=[
            LlmCompletion(
                tool_calls=[
                    LlmToolCall(
                        id="rev-1",
                        name="skill_manage",
                        arguments=json.dumps(
                            {
                                "action": "patch",
                                "name": slug,
                                "old_string": old_pitfall,
                                "new_string": new_pitfall,
                            }
                        ),
                    )
                ]
            ),
            LlmCompletion(content=""),
        ],
    )

    agent = AIAgent(db, cfg=cfg, llm=review_client)
    user_text = "你对口吻的描述不对，这位博主说话应该更口语、少说黑话。"
    reply = agent.run_conversation(display_thread_id=thread_id, user_text=user_text)
    assert "更口语" in reply

    deadline = time.time() + 8.0
    skill_md = skill_dir / "SKILL.md"
    while time.time() < deadline:
        if review_client.review_calls and skill_md.is_file():
            text = skill_md.read_text(encoding="utf-8")
            if new_pitfall in text and old_pitfall not in text:
                break
        time.sleep(0.05)
    else:
        pytest.fail("background review did not patch distill perspective pitfall in time")

    assert corpus_path.read_text(encoding="utf-8") == "CORPUS_ORIGINAL"
    assert is_pinned(profile, slug)
    assert review_client.review_calls
    review_user_text = " ".join(
        str(m.get("content") or "")
        for m in review_client.review_calls[0].get("messages") or []
        if m.get("role") == "user"
    ).lower()
    assert any(
        marker in review_user_text
        for marker in ("background skill review", "silent background review")
    )
    conn.close()


def test_s15_curator_rollback_restores_backup(tmp_path, monkeypatch) -> None:
    """S15: mutating curator run creates backup; rollback restores corrupted skill."""
    ws = tmp_path / "data"
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(f"workspace: {ws}\ncurator:\n  backup_keep: 3\n", encoding="utf-8")
    monkeypatch.setenv("MEDIA2TEXT_CONFIG", str(cfg_path))
    monkeypatch.chdir(tmp_path)

    cfg = AppConfig.load()
    profile = resolve_profile(creator_id=None, cfg=cfg)
    skill_name = "rollback-demo-skill"
    original = "# Rollback Demo\nORIGINAL_CONTENT\n"
    skill_dir = profile.memory_paths.profile_dir / "skills" / skill_name
    skill_dir.mkdir(parents=True)
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text(original, encoding="utf-8")
    mark_agent_created(profile, skill_name, write_origin="background_review")

    run_curator(cfg, dry_run=False, run_llm=False)
    backups = list_backups(profile)
    assert backups, "expected curator backup after mutating run"

    skill_md.write_text("CORRUPTED_BY_TEST", encoding="utf-8")
    assert "CORRUPTED" in skill_md.read_text(encoding="utf-8")

    backup_name = backups[0].name
    runner = CliRunner()
    result = runner.invoke(agent_app, ["curator", "rollback", backup_name])
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload.get("ok") is True

    restored = skill_md.read_text(encoding="utf-8")
    assert "ORIGINAL_CONTENT" in restored
    assert "CORRUPTED" not in restored
