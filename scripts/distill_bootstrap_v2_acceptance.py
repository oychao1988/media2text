#!/usr/bin/env python3
"""Live smoke for Creator Distill Bootstrap v2 Epic (spec §15)."""

from __future__ import annotations

import argparse
import json
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / ".tmp/distill-bootstrap-v2-acceptance.json"


def _check_doctor() -> dict[str, Any]:
    import subprocess

    proc = subprocess.run(
        ["media2text", "doctor", "--json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    result: dict[str, Any] = {"id": "CD1", "name": "doctor web + summarize", "pass": False}
    if proc.returncode != 0:
        result["detail"] = f"doctor exit {proc.returncode}"
        return result
    data = json.loads(proc.stdout)
    by_name = {c.get("name"): c for c in data.get("checks", [])}
    tavily = by_name.get("web_search_tavily") or {}
    summarize = by_name.get("summarize_llm") or {}
    result["web_search_tavily"] = tavily
    result["summarize_llm"] = summarize
    if tavily.get("ok") and summarize.get("ok"):
        result["pass"] = True
        result["detail"] = "web_search_tavily + summarize_llm ok"
    else:
        result["detail"] = f"tavily_ok={tavily.get('ok')} summarize_ok={summarize.get('ok')}"
    return result


def _check_tavily_six_channel() -> dict[str, Any]:
    from media2text.agent.creator_distill.web_research import run_six_channel_research
    from media2text.core.config import AppConfig

    cfg = AppConfig.load()
    distill = cfg.desktop.agent.distill
    result: dict[str, Any] = {"id": "CD2", "name": "live six-channel Tavily", "pass": False}
    with tempfile.TemporaryDirectory() as td:
        refs = Path(td) / "references" / "research"
        web = run_six_channel_research(
            cfg=distill,
            refs_dir=refs,
            display_name="万战寻道",
            platform="douyin",
        )
        files = sorted(p.name for p in refs.glob("*.md"))
        result["channels_ok"] = web.channels_ok
        result["files"] = files
        result["channel_status"] = web.channel_status
        if web.channels_ok >= 1 and len(files) >= 1:
            result["pass"] = True
            result["detail"] = f"{web.channels_ok} channels ok; files={files}"
        else:
            result["detail"] = f"channels_ok={web.channels_ok} files={files}"
    return result


def _check_env_hot_reload() -> dict[str, Any]:
    from media2text.agent.creator_distill.tavily_client import resolve_tavily_api_key
    from media2text.core.env_file import reload_dotenv, upsert_env_var

    result: dict[str, Any] = {"id": "CD3", "name": "Tavily key hot reload (.env)", "pass": False}
    env_path = ROOT / ".env"
    before = resolve_tavily_api_key()
    token = f"tvly-smoke-{uuid.uuid4().hex[:8]}"
    upsert_env_var("TAVILY_API_KEY", token, path=env_path)
    reload_dotenv(override=True)
    after = resolve_tavily_api_key()
    if before:
        upsert_env_var("TAVILY_API_KEY", before, path=env_path)
        reload_dotenv(override=True)
    result["resolved_after_upsert"] = after == token
    if after == token:
        result["pass"] = True
        result["detail"] = "resolve_tavily_api_key picks up .env without process restart"
    else:
        result["detail"] = "key not visible after upsert+reload"
    return result


def _check_web_only_bootstrap_gate() -> dict[str, Any]:
    """Web-only path: real Tavily + mock LLM; asserts gate proceed + research files."""
    import json

    from media2text.agent.creator_distill.bootstrap import run_bootstrap_job
    from media2text.agent.creator_distill.enqueue import enqueue_bootstrap
    from media2text.agent.profile_resolver import resolve_profile
    from media2text.core.config import AppConfig
    from media2text.core.storage.repos import CreatorAgentJobRepo, CreatorRepo
    from media2text.core.workspace import open_db

    result: dict[str, Any] = {
        "id": "CD4",
        "name": "web-only bootstrap (mock LLM)",
        "pass": False,
    }
    cfg = AppConfig.load()
    sec_uid = f"smoke_{uuid.uuid4().hex[:12]}"

    def mock_llm(_cfg, *, display_name, corpus_text) -> dict[str, Any]:
        del _cfg, display_name
        assert corpus_text.strip()
        return {
            "mental_models": [{"title": "smoke", "body": "epic", "limitation": "n/a"}],
            "decision_heuristics": ["acceptance"],
            "expression_dna": "test",
            "honest_boundaries": "非本人，非投资建议",
            "anti_patterns": [],
            "sources": ["web"],
        }

    conn = open_db(cfg)
    try:
        creator_id = CreatorRepo(conn).add(
            sec_uid=sec_uid,
            profile_url=f"https://www.douyin.com/user/{sec_uid}",
            platform="douyin",
            display_name="万战寻道",
        )
        job_id = enqueue_bootstrap(cfg, conn, creator_id=creator_id, trigger="manual")
        assert job_id
        out = run_bootstrap_job(cfg, conn, job_id=job_id, llm_fn=mock_llm)
        job = CreatorAgentJobRepo(conn).get(job_id)
        payload = json.loads(job.payload_json or "{}") if job else {}
    finally:
        conn.close()

    profile = resolve_profile(creator_id=creator_id, cfg=cfg)
    skill_root = profile.memory_paths.profile_dir / "skills"
    research_files = [
        str(p.relative_to(profile.memory_paths.profile_dir))
        for p in skill_root.glob("*/references/research/*.md")
    ]

    result["bootstrap_out"] = out
    result["job_status"] = job.status if job else None
    result["web_channels_ok"] = payload.get("web_channels_ok")
    result["research_files"] = research_files
    ok = (
        out.get("ok") is True
        and out.get("deferred") is not True
        and (payload.get("web_channels_ok") or out.get("web_channels_ok") or 0) >= 1
        and len(research_files) >= 1
        and job is not None
        and job.status == "done"
    )
    if ok:
        result["pass"] = True
        result["detail"] = f"bootstrap done; web_channels_ok={payload.get('web_channels_ok')}"
    else:
        result["detail"] = f"out={out} status={job.status if job else None}"
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Creator Distill Bootstrap v2 live acceptance")
    parser.add_argument("--skip-bootstrap", action="store_true", help="Skip CD4 (uses Tavily quota)")
    args = parser.parse_args()

    results: list[dict[str, Any]] = []
    steps = [_check_doctor, _check_tavily_six_channel]
    if not args.skip_bootstrap:
        steps.append(_check_web_only_bootstrap_gate)
    steps.append(_check_env_hot_reload)

    for fn in steps:
        print(f"== {fn.__name__} ==")
        r = fn()
        print(f"  [{'PASS' if r.get('pass') else 'FAIL'}] {r.get('detail')}")
        results.append(r)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "all_pass": all(r.get("pass") for r in results),
        "results": results,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nReport: {REPORT}")
    return 0 if payload["all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
