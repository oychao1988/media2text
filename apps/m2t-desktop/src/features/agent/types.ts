import type { PiEvent, ToolResultPayload } from '@m2t/shared';

export type ChatMessage =
  | {
      id: string;
      role: 'user';
      text: string;
      persisted?: boolean;
    }
  | {
      id: string;
      role: 'assistant';
      text: string;
      thinkingText?: string;
      durationMs?: number;
      persisted?: boolean;
    }
  | {
      id: string;
      role: 'tool';
      result: Extract<PiEvent, { type: 'tool.result' }>;
    };

export type ActiveTurn = {
  phase: string;
  phaseLabel: string;
  thinkingText: string;
  assistantText: string;
};

export type ThreadRow = {
  id: string;
  creator_id: string;
  session_id: string | null;
  title: string | null;
  provider_name: string | null;
  model: string;
  updated_at?: string | null;
};

export type ChatProvider = {
  name: string;
  base_url: string;
  models: string[];
  configured: boolean;
};

export function toolPayloadFromMessage(msg: ChatMessage): ToolResultPayload | null {
  if (msg.role !== 'tool') return null;
  return msg.result.payload;
}
