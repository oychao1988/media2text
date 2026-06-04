"""camelCase config DTO ↔ AppConfig for desktop API."""

from __future__ import annotations

import os
from typing import Any

from pydantic import BaseModel, ConfigDict

from media2text.core.config import AppConfig
from media2text.core.errors import ConfigError


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


def _env_configured(env_name: str) -> bool:
    return bool(os.environ.get(env_name, "").strip())


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


def _llm_providers_dto(cfg: AppConfig) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for p in cfg.summarize.llm.providers:
        out.append(
            {
                "name": p.name,
                "base_url": p.base_url,
                "api_key_envs": list(p.api_key_envs),
                "models": list(p.models),
                "configured": any(_env_configured(e) for e in p.api_key_envs),
            }
        )
    return out


def config_to_dto(cfg: AppConfig) -> dict[str, Any]:
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
        "summarizeProviderId": cfg.summarize.llm.default_provider,
        "summarizeModel": cfg.summarize.llm.default_model,
        "aliyunEnabled": cfg.aliyundrive.enabled,
        "aliyunRootFolder": cfg.aliyundrive.root_folder,
        "aliyunDeleteLocal": cfg.aliyundrive.delete_local_after_upload,
        "aliyunUploadSidecar": cfg.aliyundrive.upload_transcripts,
        "notifyEnabled": cfg.notify.enabled,
        "feishuWebhookUrl": _mask_feishu(cfg),
        "feishuConfigured": _feishu_configured(cfg),
        "deepgramConfigured": _env_configured(dg_env),
        "deepgramApiKeyEnv": dg_env,
        "llmProviders": _llm_providers_dto(cfg),
        "activeProviderId": cfg.summarize.llm.default_provider,
        "agentModel": cfg.desktop.chat.default_model,
        "maxContextChars": cfg.desktop.chat.max_context_chars,
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
        from media2text.core.config import SummarizeLlmProviderConfig

        cfg.summarize.llm.providers = [
            SummarizeLlmProviderConfig.model_validate(p) for p in patch.llmProviders
        ]
    if patch.activeProviderId is not None:
        cfg.summarize.llm.default_provider = patch.activeProviderId
    if patch.agentModel is not None:
        cfg.desktop.chat.default_model = patch.agentModel
    if patch.maxContextChars is not None:
        cfg.desktop.chat.max_context_chars = patch.maxContextChars

    try:
        AppConfig.model_validate(cfg.model_dump())
    except Exception as exc:
        raise ConfigError(str(exc)) from exc

    return _patch_restart_flags(before, patch)
