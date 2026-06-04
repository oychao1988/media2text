#!/usr/bin/env node
import { readEnvContext } from './context.js';
import { emitAssistant, emitError, emitReady } from './emit.js';
import { createM2tAgentSession, readSidecarVersion } from './session.js';

async function main(): Promise<void> {
  process.on('unhandledRejection', (reason) => {
    const message = reason instanceof Error ? reason.message : String(reason);
    emitError(message, 'UNHANDLED_REJECTION');
  });

  const version = readSidecarVersion();
  let agentSession: Awaited<ReturnType<typeof createM2tAgentSession>> | null = null;

  try {
    agentSession = await createM2tAgentSession((text, meta) => emitAssistant(text, meta));
    emitReady(version);
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    emitError(message, 'SIDECAR_INIT_FAILED');
    emitReady(version);
  }

  process.stdin.setEncoding('utf8');
  let buffer = '';

  process.stdin.on('data', (chunk) => {
    buffer += chunk;
    let idx: number;
    while ((idx = buffer.indexOf('\n')) >= 0) {
      const line = buffer.slice(0, idx).trim();
      buffer = buffer.slice(idx + 1);
      if (!line) continue;
      void handleLine(line);
    }
  });

  async function handleLine(line: string): Promise<void> {
    try {
      const msg = JSON.parse(line) as { type?: string; payload?: Record<string, unknown> };
      if (msg.type === 'context.refresh') {
        const env = readEnvContext();
        if (msg.payload?.creatorId != null) {
          process.env.M2T_CREATOR_ID = String(msg.payload.creatorId);
        }
        if (msg.payload?.sessionId != null) {
          process.env.M2T_SESSION_ID = String(msg.payload.sessionId);
        }
        if (msg.payload?.threadId != null) {
          process.env.M2T_THREAD_ID = String(msg.payload.threadId);
        }
        Object.assign(env, readEnvContext());
        if (agentSession) await agentSession.reloadContext();
        return;
      }
      if (msg.type === 'message.user') {
        const text = String(msg.payload?.text ?? '').trim();
        if (!text) return;
        if (!agentSession) {
          emitError('Agent 会话未初始化，请检查 LLM API Key 配置。', 'SIDECAR_NOT_READY');
          return;
        }
        await agentSession.reloadContext();
        agentSession.beginUserTurn();
        const providerId = String(msg.payload?.providerId ?? '');
        const model = msg.payload?.model;
        const modelSelection =
          typeof model === 'string' && model.trim()
            ? (model.trim() as string | 'auto')
            : 'auto';
        await agentSession.applyUserMessageLlm({
          text,
          providerId,
          model: modelSelection === 'auto' ? 'auto' : modelSelection,
        });
        await agentSession.session.prompt(text);
        return;
      }
      emitError('未知的 stdin 消息类型', 'INVALID_MESSAGE');
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      emitError(message, 'HANDLE_MESSAGE_FAILED');
    }
  }
}

void main();
