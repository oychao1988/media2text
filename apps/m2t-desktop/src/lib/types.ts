export type StatusLight = 'green' | 'red' | 'yellow' | 'gray';

export type Creator = {
  id: string;
  platform: string;
  sec_uid: string;
  display_name: string | null;
  unique_id: string | null;
  profile_url: string | null;
  monitor_enabled: boolean;
  profile_stale: boolean;
  auto_record_override: 'inherit' | 'on' | 'off';
  status_light: StatusLight;
  is_live: boolean;
  badge: string;
  badge_class: string;
  status_abbr: string;
  status_label: string;
  avatar_url: string | null;
  signature: string | null;
  follower_count: number | null;
  profile_synced_at: string | null;
  active_session_id: string | null;
  live_snapshot?: {
    is_live: boolean;
    room_id: string | null;
    title: string | null;
    checked_at: string | null;
  } | null;
};

export type DaemonStatus = {
  ok?: boolean;
  running: boolean;
  pid: number | null;
  lock_pid: number | null;
  live_tick_interval_sec: number;
  post_process: {
    max_workers: number;
    pending: number;
    running: number;
  };
  monitor_tasks?: {
    pending: number;
    running: number;
    failed: number;
    dlq?: number;
  };
  active_recordings: number;
  log_path: string;
};

export type RuntimeHealth = 'stopped' | 'degraded' | 'healthy';

export type RuntimeStatus = {
  ok: boolean;
  health: RuntimeHealth;
  health_reasons: string[];
  managed_by: 'embedded' | 'external' | 'none';
  daemon: {
    running: boolean;
    pid: number | null;
    lock_pid: number | null;
    started_at: string | null;
    last_tick_at: string | null;
    tick_age_sec: number | null;
    live_poll_interval_sec: number;
  };
  recordings: {
    active_count: number;
    items: ActiveRecording[];
  };
  queues: {
    post_process: {
      pending: number;
      running: number;
      max_workers: number;
    };
    monitor_tasks: {
      pending: number;
      running: number;
      failed_total: number;
      failed_recent_24h: number;
      dlq: number;
    };
  };
  observability: {
    snapshots_stale_count: number;
    monitored_creators: number;
  };
  log_path: string;
};

export type TranscriptSegment = {
  start: number;
  end: number;
  text: string;
};

export type TranscriptPayload = {
  ok?: boolean;
  session_id?: string;
  session_status?: string;
  session_finalized?: boolean;
  partial?: boolean;
  text?: string;
  segments?: TranscriptSegment[];
  markdown?: string;
};

export type HistoryKind = 'live' | 'vod';

export type LiveSessionSummary = {
  kind: HistoryKind;
  item_id: string;
  session_id: string;
  aweme_id: string | null;
  title: string | null;
  creator_id: string;
  started_at: string | null;
  ended_at: string | null;
  status: string | null;
  media_type?: string | null;
  local_path: string | null;
  temp_path: string | null;
  media_path: string | null;
  pipeline_mode: string | null;
  transcribe_status: string | null;
  cloud_upload_status: string | null;
  cloud_file_id: string | null;
  cloud_relative_path: string | null;
  cloud_available: boolean;
  has_transcript: boolean;
  has_summary: boolean;
  media_available: boolean;
  media_format?: string | null;
  discontinuity_at?: number[];
  part_durations?: number[];
  transcript_path: string | null;
  summary_path: string | null;
};

export type LiveGroup = {
  date?: string;
  summary_path?: string;
  session_ids?: string[];
  label?: string;
};

export type LlmProvider = {
  name: string;
  base_url: string;
  api_key_envs: string[];
  models: string[];
  configured: boolean;
  /** Plaintext key for desktop config UI (loopback only). */
  api_key?: string | null;
  /** API reachability from GET /models probe; null = not tested (no key). */
  connected?: boolean | null;
};

export type ConfigDto = {
  theme: string;
  notifySound: boolean;
  livePollInterval: number;
  vodPollInterval: number;
  maxCreatorsPerVodTick: number;
  scanConcurrency: number;
  douyinLivePoll: number;
  douyinPollInterval: number;
  biliLivePoll: number;
  biliArchivePoll: number;
  biliDynamicPoll: number;
  pipelineMode: string;
  autoRecord: boolean;
  streamingSttEnabled: boolean;
  streamingSttEngine: string;
  streamingSttModel: string;
  flushIntervalSec: number;
  offlineConfirmSec: number;
  summarizeEnabled: boolean;
  summarizeProviderId: string;
  summarizeModel: string;
  aliyunEnabled: boolean;
  aliyunRootFolder: string;
  aliyunDeleteLocal: boolean;
  aliyunUploadSidecar: boolean;
  notifyEnabled: boolean;
  feishuWebhookUrl: string | null;
  feishuConfigured: boolean;
  deepgramConfigured: boolean;
  deepgramApiKeyEnv: string;
  llmProviders: LlmProvider[];
  activeProviderId: string;
  agentModel: string;
  maxContextChars: number;
  tavilyConfigured: boolean;
  tavilyApiKey: string | null;
  tavilyApiKeyEnv: string;
  bootstrapWebResearch: boolean;
};

export type AuthPlatformStatus = {
  configured: boolean;
};

export type ActiveRecording = {
  session_id: string;
  creator_id: string;
  display_name: string | null;
  started_at: string | null;
  recording_age_sec: number;
  offline_since_at: string | null;
  ffmpeg_pid: number | null;
  status: string;
  pipeline_mode: string | null;
  transcribe_status: string | null;
};

export type WsEvent = {
  type: string;
  creator_id?: string;
  session_id?: string;
  [key: string]: unknown;
};
