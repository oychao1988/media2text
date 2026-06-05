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
  avatar_url: string | null;
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

export type TranscriptSegment = {
  start: number;
  end: number;
  text: string;
};

export type TranscriptPayload = {
  ok?: boolean;
  session_id?: string;
  partial?: boolean;
  text?: string;
  segments?: TranscriptSegment[];
  markdown?: string;
};

export type LiveSessionSummary = {
  session_id: string;
  creator_id: string;
  started_at: string | null;
  ended_at: string | null;
  status: string | null;
  local_path: string | null;
  temp_path: string | null;
  media_path: string | null;
  pipeline_mode: string | null;
  transcribe_status: string | null;
  cloud_upload_status: string | null;
  has_transcript: boolean;
  has_summary: boolean;
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
