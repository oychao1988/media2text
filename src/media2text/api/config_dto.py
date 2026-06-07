"""camelCase config DTO ↔ AppConfig for desktop API."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from media2text.core.config import AppConfig, SummarizeLlmProviderConfig
from media2text.core.env_file import read_env_var, reload_dotenv, upsert_env_var
from media2text.core.errors import ConfigError

_MASKED_SECRET = "***"


class ConfigPatchDto(BaseModel):
    model_config = ConfigDict(extra="ignore")

    theme: str | None = None
    notifySound: bool | None = None
    livePollInterval: int | None = None
    vodPollInterval: int | None = None
    maxCreatorsPerVodTick: int | None = None
    scanConcurrency: int | None = None
    douyinLivePoll: int | None = None
    douyinPollInterval: int | None = None
    biliLivePoll: int | None = None
    biliArchivePoll: int | None = None
    biliDynamicPoll: int | None = None
    pipelineMode: str | None = None
    autoRecord: bool | None = None
    streamingSttEnabled: bool | None = None
    streamingSttEngine: str | None = None
    streamingSttModel: str | None = None
    flushIntervalSec: float | None = None
    offlineConfirmSec: int | None = None
    summarizeEnabled: bool | None = None
    summarizeProviderId: str | None = None
    summarizeModel: str | None = None
    aliyunEnabled: bool | None = None
    aliyunRootFolder: str | None = None
    aliyunDeleteLocal: bool | None = None
    aliyunUploadSidecar: bool | None = None
    notifyEnabled: bool | None = None
    feishuWebhookUrl: str | None = None
    clearFeishuWebhook: bool = False
    llmProviders: list[dict[str, Any]] | None = None
    activeProviderId: str | None = None
    agentModel: str | None = None
    maxContextChars: int | None = None
    tavilyApiKey: str | None = None
    bootstrapWebResearch: bool | None = None


def _env_configured(env_name: str) -> bool:
    return bool(os.environ.get(env_name, "").strip())


def _tavily_api_key(cfg: AppConfig) -> str:
    from media2text.core.tavily_client import resolve_tavily_api_key

    return resolve_tavily_api_key(env_key=cfg.desktop.agent.distill.tavily_api_key_env)


def _tavily_configured(cfg: AppConfig) -> bool:
    return bool(_tavily_api_key(cfg))


def _apply_tavily_api_key(cfg: AppConfig, api_key: Any) -> None:
    if api_key is None or not isinstance(api_key, str):
        return
    trimmed = api_key.strip()
    if not trimmed or trimmed == _MASKED_SECRET:
        return
    env_name = cfg.desktop.agent.distill.tavily_api_key_env
    upsert_env_var(env_name, trimmed)
    reload_dotenv(override=True)


def _feishu_configured(cfg: AppConfig) -> bool:
    url = (cfg.notify.feishu.webhook_url or "").strip()
    if url:
        return True
    env_key = cfg.notify.feishu.webhook_url_env
    return _env_configured(env_key)


def _mask_feishu(cfg: AppConfig) -> str | None:
    if _feishu_configured(cfg):
        return "***"
    return None


def _default_api_key_env(provider_name: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "_", (provider_name or "").strip().upper()).strip("_")
    return f"M2T_LLM_{slug}_API_KEY" if slug else "M2T_LLM_API_KEY"


def _primary_api_key_env(p: SummarizeLlmProviderConfig) -> str:
    if p.api_key_envs:
        return p.api_key_envs[0]
    return _default_api_key_env(p.name)


def _provider_api_key_envs(p: SummarizeLlmProviderConfig) -> list[str]:
    if p.api_key_envs:
        return list(p.api_key_envs)
    return [_default_api_key_env(p.name)]


def _provider_api_key(p: SummarizeLlmProviderConfig) -> str:
    """Prefer `.env` on disk over stale ``os.environ`` (desktop saves update `.env`` first)."""
    for env in _provider_api_key_envs(p):
        api_key = read_env_var(env).strip()
        if api_key:
            os.environ[env] = api_key
            return api_key
        api_key = os.environ.get(env, "").strip()
        if api_key:
            return api_key
    return ""


def _probe_http_auth(
    req: urllib.request.Request,
    *,
    timeout: float = 3,
) -> bool | None:
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return 200 <= resp.status < 300
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            return False
        if exc.code >= 500:
            return None
        return False
    except urllib.error.URLError:
        return None
    except TimeoutError:
        return None
    except Exception:
        return None


def _probe_provider_connected(
    p: SummarizeLlmProviderConfig,
    *,
    api_key: str | None = None,
) -> bool | None:
    """Probe OpenAI-compatible endpoint auth; None when key/base URL missing or network unreachable."""
    base = (p.base_url or "").strip().rstrip("/")
    if not base:
        return None
    resolved_key = (api_key or "").strip() or _provider_api_key(p)
    if not resolved_key:
        return None
    headers = {
        "Authorization": f"Bearer {resolved_key}",
        "User-Agent": "media2text-config-probe/1.0",
    }

    model = next((m.strip() for m in p.models if m and m.strip()), "")
    if model:
        chat_url = f"{base}/chat/completions"
        body = json.dumps(
            {
                "model": model,
                "messages": [{"role": "user", "content": "."}],
                "max_tokens": 1,
            }
        ).encode("utf-8")
        chat_req = urllib.request.Request(
            chat_url,
            data=body,
            headers={**headers, "Content-Type": "application/json"},
            method="POST",
        )
        chat_result = _probe_http_auth(chat_req)
        if chat_result is not None:
            return chat_result

    models_req = urllib.request.Request(
        f"{base}/models",
        headers=headers,
        method="GET",
    )
    return _probe_http_auth(models_req)


def _provider_fingerprint(p: SummarizeLlmProviderConfig) -> str:
    env = _primary_api_key_env(p) if p.api_key_envs else _default_api_key_env(p.name)
    return f"{(p.base_url or '').strip().rstrip('/')}|{env}"


def _provider_probe_cache_path(cfg: AppConfig) -> Path:
    return Path(cfg.workspace) / "sessions" / "llm_provider_probe.json"


def _load_provider_probe_cache(cfg: AppConfig) -> dict[str, Any]:
    path = _provider_probe_cache_path(cfg)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _save_provider_probe_cache(cfg: AppConfig, entries: dict[str, dict[str, Any]]) -> None:
    if not entries:
        return
    path = _provider_probe_cache_path(cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    merged = _load_provider_probe_cache(cfg)
    merged.update(entries)
    path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")


def _cached_provider_connected(cfg: AppConfig, p: SummarizeLlmProviderConfig) -> bool | None:
    entry = _load_provider_probe_cache(cfg).get(p.name)
    if not isinstance(entry, dict):
        return None
    if entry.get("fingerprint") != _provider_fingerprint(p):
        return None
    connected = entry.get("connected")
    if connected is True:
        return True
    if connected is False:
        return False
    return None


def _llm_providers_dto(cfg: AppConfig, *, probe: bool = False) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    cache_updates: dict[str, dict[str, Any]] = {}
    for p in cfg.summarize.llm.providers:
        api_key = _provider_api_key(p)
        configured = bool(api_key)
        if probe:
            connected = _probe_provider_connected(p, api_key=api_key or None)
            cache_updates[p.name] = {
                "connected": connected,
                "fingerprint": _provider_fingerprint(p),
            }
        else:
            connected = _cached_provider_connected(cfg, p)
        out.append(
            {
                "name": p.name,
                "base_url": p.base_url,
                "api_key_envs": list(p.api_key_envs),
                "models": list(p.models),
                "configured": configured,
                "connected": connected,
                "api_key": _MASKED_SECRET if api_key else None,
            }
        )
    if probe:
        _save_provider_probe_cache(cfg, cache_updates)
    return out


def _apply_llm_provider_api_key(p: SummarizeLlmProviderConfig, api_key: Any) -> None:
    if api_key is None:
        return
    if not isinstance(api_key, str):
        return
    trimmed = api_key.strip()
    if not trimmed or trimmed == _MASKED_SECRET:
        return
    env_name = _primary_api_key_env(p) if p.api_key_envs else _default_api_key_env(p.name)
    p.api_key_envs = [env_name]
    upsert_env_var(env_name, trimmed)
    reload_dotenv(override=True)


def _consolidate_provider_api_key_envs(p: SummarizeLlmProviderConfig) -> None:
    """Keep a single env var name; prefer the first env that already has a value."""
    envs = _provider_api_key_envs(p)
    chosen = ""
    for env in envs:
        if read_env_var(env).strip() or os.environ.get(env, "").strip():
            chosen = env
            break
    if not chosen:
        chosen = envs[0] if envs else _default_api_key_env(p.name)
    p.api_key_envs = [chosen]


def _normalize_llm_provider_patch(raw: dict[str, Any]) -> SummarizeLlmProviderConfig:
    api_key = raw.get("api_key")
    cleaned = {
        k: v
        for k, v in raw.items()
        if k not in ("configured", "connected", "api_key")
    }
    provider = SummarizeLlmProviderConfig.model_validate(cleaned)
    if not provider.api_key_envs:
        provider.api_key_envs = [_default_api_key_env(provider.name)]
    _consolidate_provider_api_key_envs(provider)
    _apply_llm_provider_api_key(provider, api_key)
    return provider


def _resolve_summarize_selection(cfg: AppConfig) -> tuple[str, str]:
    """Fill null default_provider/default_model for desktop selects."""
    providers = cfg.summarize.llm.providers
    provider_id = (cfg.summarize.llm.default_provider or "").strip()
    if not provider_id and providers:
        provider_id = providers[0].name
    prov = next((p for p in providers if p.name == provider_id), None)
    if prov is None and providers:
        prov = providers[0]
        provider_id = prov.name
    model = (cfg.summarize.llm.default_model or "").strip()
    if not model and prov and prov.models:
        model = next((m.strip() for m in prov.models if m and m.strip()), "")
    return provider_id, model


def _providers_need_probe(providers_dto: list[dict[str, Any]]) -> bool:
    return any(p.get("configured") and p.get("connected") is None for p in providers_dto)


def config_to_dto(cfg: AppConfig, *, probe_providers: bool = False) -> dict[str, Any]:
    summarize_provider_id, summarize_model = _resolve_summarize_selection(cfg)
    engine = cfg.transcribe.engine
    if engine == "deepgram":
        stt_model = cfg.transcribe.deepgram.model
    elif engine == "openai":
        stt_model = cfg.transcribe.openai.model
    else:
        stt_model = cfg.transcribe.whisper.model

    dg_env = cfg.transcribe.deepgram.api_key_env
    return {
        "theme": cfg.desktop.theme,
        "notifySound": cfg.notify.sound,
        "livePollInterval": cfg.live.live_poll_interval_sec,
        "vodPollInterval": cfg.monitor.vod_poll_interval_sec,
        "maxCreatorsPerVodTick": cfg.monitor.max_creators_per_vod_tick,
        "scanConcurrency": cfg.live.scan_concurrency,
        "douyinLivePoll": cfg.platforms.douyin.live_poll_interval_sec,
        "douyinPollInterval": cfg.platforms.douyin.poll_interval_sec,
        "biliLivePoll": cfg.platforms.bilibili.live_poll_interval_sec,
        "biliArchivePoll": cfg.platforms.bilibili.archive_poll_interval_sec,
        "biliDynamicPoll": cfg.platforms.bilibili.dynamic_poll_interval_sec,
        "pipelineMode": cfg.live.pipeline_mode,
        "autoRecord": cfg.live.auto_record,
        "streamingSttEnabled": cfg.live.streaming_stt.enabled,
        "streamingSttEngine": cfg.live.streaming_stt.engine,
        "streamingSttModel": stt_model,
        "flushIntervalSec": cfg.live.streaming_stt.flush_interval_sec,
        "offlineConfirmSec": cfg.live.offline_confirm_sec,
        "summarizeEnabled": cfg.summarize.enabled,
        "summarizeProviderId": summarize_provider_id,
        "summarizeModel": summarize_model,
        "aliyunEnabled": cfg.aliyundrive.enabled,
        "aliyunRootFolder": cfg.aliyundrive.root_folder,
        "aliyunDeleteLocal": cfg.aliyundrive.delete_local_after_upload,
        "aliyunUploadSidecar": cfg.aliyundrive.upload_transcripts,
        "notifyEnabled": cfg.notify.enabled,
        "feishuWebhookUrl": _mask_feishu(cfg),
        "feishuConfigured": _feishu_configured(cfg),
        "deepgramConfigured": _env_configured(dg_env),
        "deepgramApiKeyEnv": dg_env,
        "llmProviders": _llm_providers_dto(cfg, probe=probe_providers),
        "activeProviderId": summarize_provider_id,
        "agentModel": cfg.desktop.chat.default_model,
        "maxContextChars": cfg.desktop.chat.max_context_chars,
        "tavilyConfigured": _tavily_configured(cfg),
        "tavilyApiKey": _MASKED_SECRET if _tavily_configured(cfg) else None,
        "tavilyApiKeyEnv": cfg.desktop.agent.distill.tavily_api_key_env,
        "bootstrapWebResearch": cfg.desktop.agent.distill.bootstrap_web_research,
    }


def _patch_restart_flags(
    before: dict[str, Any], patch: ConfigPatchDto
) -> tuple[list[str], list[str]]:
    daemon_keys: list[str] = []
    agent_keys: list[str] = []
    if patch.pipelineMode is not None and patch.pipelineMode != before.get("pipelineMode"):
        daemon_keys.append("pipelineMode")
    if patch.streamingSttEnabled is not None and patch.streamingSttEnabled != before.get(
        "streamingSttEnabled"
    ):
        daemon_keys.append("streamingSttEnabled")
    if patch.streamingSttEngine is not None and patch.streamingSttEngine != before.get(
        "streamingSttEngine"
    ):
        daemon_keys.append("streamingSttEngine")
    if patch.llmProviders is not None:
        agent_keys.append("llmProviders")
    if patch.activeProviderId is not None and patch.activeProviderId != before.get(
        "activeProviderId"
    ):
        agent_keys.append("activeProviderId")
    if patch.agentModel is not None and patch.agentModel != before.get("agentModel"):
        agent_keys.append("agentModel")
    if patch.maxContextChars is not None and patch.maxContextChars != before.get(
        "maxContextChars"
    ):
        agent_keys.append("maxContextChars")
    return daemon_keys, agent_keys


def apply_dto_patch(cfg: AppConfig, patch: ConfigPatchDto) -> tuple[list[str], list[str]]:
    """Apply partial DTO patch to cfg; return restart/reload hint keys."""
    before = config_to_dto(cfg)

    if patch.theme is not None:
        cfg.desktop.theme = patch.theme
    if patch.notifySound is not None:
        cfg.notify.sound = patch.notifySound
    if patch.livePollInterval is not None:
        cfg.live.live_poll_interval_sec = patch.livePollInterval
    if patch.vodPollInterval is not None:
        cfg.monitor.vod_poll_interval_sec = patch.vodPollInterval
    if patch.maxCreatorsPerVodTick is not None:
        cfg.monitor.max_creators_per_vod_tick = patch.maxCreatorsPerVodTick
    if patch.scanConcurrency is not None:
        cfg.live.scan_concurrency = patch.scanConcurrency
    if patch.douyinLivePoll is not None:
        cfg.platforms.douyin.live_poll_interval_sec = patch.douyinLivePoll
    if patch.douyinPollInterval is not None:
        cfg.platforms.douyin.poll_interval_sec = patch.douyinPollInterval
    if patch.biliLivePoll is not None:
        cfg.platforms.bilibili.live_poll_interval_sec = patch.biliLivePoll
    if patch.biliArchivePoll is not None:
        cfg.platforms.bilibili.archive_poll_interval_sec = patch.biliArchivePoll
    if patch.biliDynamicPoll is not None:
        cfg.platforms.bilibili.dynamic_poll_interval_sec = patch.biliDynamicPoll
    if patch.pipelineMode is not None:
        cfg.live.pipeline_mode = patch.pipelineMode
    if patch.autoRecord is not None:
        cfg.live.auto_record = patch.autoRecord
    if patch.streamingSttEnabled is not None:
        cfg.live.streaming_stt.enabled = patch.streamingSttEnabled
    if patch.streamingSttEngine is not None:
        cfg.live.streaming_stt.engine = patch.streamingSttEngine
    if patch.flushIntervalSec is not None:
        cfg.live.streaming_stt.flush_interval_sec = patch.flushIntervalSec
    if patch.offlineConfirmSec is not None:
        cfg.live.offline_confirm_sec = patch.offlineConfirmSec
    if patch.summarizeEnabled is not None:
        cfg.summarize.enabled = patch.summarizeEnabled
    if patch.summarizeProviderId is not None:
        cfg.summarize.llm.default_provider = patch.summarizeProviderId
    if patch.summarizeModel is not None:
        cfg.summarize.llm.default_model = patch.summarizeModel
    if patch.aliyunEnabled is not None:
        cfg.aliyundrive.enabled = patch.aliyunEnabled
    if patch.aliyunRootFolder is not None:
        cfg.aliyundrive.root_folder = patch.aliyunRootFolder
    if patch.aliyunDeleteLocal is not None:
        cfg.aliyundrive.delete_local_after_upload = patch.aliyunDeleteLocal
    if patch.aliyunUploadSidecar is not None:
        cfg.aliyundrive.upload_transcripts = patch.aliyunUploadSidecar
    if patch.notifyEnabled is not None:
        cfg.notify.enabled = patch.notifyEnabled

    if patch.clearFeishuWebhook:
        cfg.notify.feishu.webhook_url = ""
    elif patch.feishuWebhookUrl is not None and patch.feishuWebhookUrl.strip():
        cfg.notify.feishu.webhook_url = patch.feishuWebhookUrl.strip()

    if patch.streamingSttModel is not None:
        engine = (patch.streamingSttEngine or cfg.live.streaming_stt.engine or cfg.transcribe.engine)
        eng = engine.strip().lower()
        if eng == "deepgram":
            cfg.transcribe.deepgram.model = patch.streamingSttModel
        elif eng == "openai":
            cfg.transcribe.openai.model = patch.streamingSttModel
        else:
            cfg.transcribe.whisper.model = patch.streamingSttModel

    if patch.llmProviders is not None:
        cfg.summarize.llm.providers = [
            _normalize_llm_provider_patch(dict(p)) for p in patch.llmProviders
        ]
    if patch.activeProviderId is not None:
        cfg.summarize.llm.default_provider = patch.activeProviderId
    if patch.agentModel is not None:
        cfg.desktop.chat.default_model = patch.agentModel
    if patch.maxContextChars is not None:
        cfg.desktop.chat.max_context_chars = patch.maxContextChars
    if patch.bootstrapWebResearch is not None:
        cfg.desktop.agent.distill.bootstrap_web_research = patch.bootstrapWebResearch
    if patch.tavilyApiKey is not None:
        _apply_tavily_api_key(cfg, patch.tavilyApiKey)

    try:
        AppConfig.model_validate(cfg.model_dump())
    except Exception as exc:
        raise ConfigError(str(exc)) from exc

    return _patch_restart_flags(before, patch)
