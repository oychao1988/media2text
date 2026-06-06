import { z } from 'zod';

export const ToolUiKindSchema = z.enum([
  'table',
  'sync_job',
  'import_report',
  'item_card',
  'text',
]);

export const ToolResultPayloadSchema = z.object({
  ok: z.boolean(),
  data: z.unknown().optional(),
  error: z
    .object({
      code: z.string(),
      message: z.string(),
      details: z.record(z.unknown()).optional(),
    })
    .optional(),
  ui: z
    .object({
      kind: ToolUiKindSchema,
      payload: z.unknown(),
      deep_link: z.string().optional(),
      app_path: z.string().optional(),
    })
    .optional(),
});

export type ToolResultPayload = z.infer<typeof ToolResultPayloadSchema>;

export const TurnPhaseKindSchema = z.enum(['preparing', 'thinking', 'tool', 'composing']);
export type TurnPhaseKind = z.infer<typeof TurnPhaseKindSchema>;

/** PiEvent NDJSON schema (placeholder; aligned with scmclaw shared). */
export const PiEventSchema = z.discriminatedUnion('type', [
  z.object({
    type: z.literal('message.user'),
    payload: z.object({ text: z.string() }),
  }),
  z.object({
    type: z.literal('turn.start'),
    payload: z.object({ startedAt: z.number().optional() }),
  }),
  z.object({
    type: z.literal('turn.phase'),
    payload: z.object({
      phase: TurnPhaseKindSchema,
      label: z.string(),
    }),
  }),
  z.object({
    type: z.literal('message.thinking'),
    payload: z.object({ text: z.string() }),
  }),
  z.object({
    type: z.literal('message.assistant.delta'),
    payload: z.object({ delta: z.string() }),
  }),
  z.object({
    type: z.literal('message.assistant'),
    payload: z.object({
      text: z.string(),
      durationMs: z.number().optional(),
      thinkingText: z.string().optional(),
    }),
  }),
  z.object({
    type: z.literal('turn.end'),
    payload: z.object({ durationMs: z.number() }),
  }),
  z.object({
    type: z.literal('tool.result'),
    payload: ToolResultPayloadSchema,
  }),
  z.object({
    type: z.literal('approval.request'),
    payload: z.object({
      id: z.string(),
      action: z.string(),
      summary: z.string(),
      detail: z.record(z.unknown()).optional(),
    }),
  }),
  z.object({
    type: z.literal('job.progress'),
    payload: z.object({
      job_id: z.string(),
      progress: z.number().optional(),
      status: z.string().optional(),
    }),
  }),
  z.object({
    type: z.literal('error'),
    payload: z.object({
      message: z.string(),
      code: z.string().optional(),
    }),
  }),
  z.object({
    type: z.literal('sidecar.ready'),
    payload: z.object({
      version: z.string(),
    }),
  }),
]);

export type PiEvent = z.infer<typeof PiEventSchema>;

export function parsePiEventLine(line: string): PiEvent | null {
  const trimmed = line.trim();
  if (!trimmed) return null;
  try {
    const json = JSON.parse(trimmed) as unknown;
    const parsed = PiEventSchema.safeParse(json);
    return parsed.success ? parsed.data : null;
  } catch {
    return null;
  }
}
