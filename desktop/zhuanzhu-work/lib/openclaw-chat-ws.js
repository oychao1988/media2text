const { randomUUID } = require("node:crypto");
const { readGatewayToken } = require("./config");
const {
  buildChatBody,
  resolveSessionKey,
  normalizeChatMode,
  isFastChatMode,
} = require("./openclaw-chat");

const GATEWAY_WS_URL =
  process.env.OPENCLAW_GATEWAY_WS || "ws://127.0.0.1:18789";
const PROTOCOL_MIN = 3;
const PROTOCOL_MAX = 4;
const CONNECT_TIMEOUT_MS = 15_000;
const CHAT_TIMEOUT_MS = 120_000;
const WS_OPEN = 1;

/** @type {GatewayWsClient | null} */
let sharedClient = null;

function resetSharedGatewayWsClient() {
  if (sharedClient) {
    sharedClient.close();
    sharedClient = null;
  }
}

function getGatewayWsUrl() {
  return GATEWAY_WS_URL;
}

function extractAssistantText(message) {
  if (!message || typeof message !== "object") {
    return "";
  }
  if (typeof message.text === "string") {
    return message.text;
  }
  if (Array.isArray(message.content)) {
    return message.content
      .filter((block) => block?.type === "text" && typeof block.text === "string")
      .map((block) => block.text)
      .join("");
  }
  return "";
}

/**
 * @param {Record<string, unknown>} payload
 * @param {string} previousText
 */
function extractChatDelta(payload, previousText) {
  if (typeof payload.deltaText === "string" && payload.deltaText.length > 0) {
    return payload.deltaText;
  }
  const cumulative = extractAssistantText(payload.message);
  if (!cumulative) {
    return "";
  }
  if (!previousText) {
    return cumulative;
  }
  if (cumulative.startsWith(previousText)) {
    return cumulative.slice(previousText.length);
  }
  if (cumulative.length >= previousText.length) {
    return cumulative;
  }
  return "";
}

function buildConnectParams(token) {
  return {
    minProtocol: PROTOCOL_MIN,
    maxProtocol: PROTOCOL_MAX,
    client: {
      id: "gateway-client",
      version: "0.1.0",
      platform: process.platform,
      mode: "backend",
    },
    role: "operator",
    scopes: ["operator.read", "operator.write"],
    caps: [],
    auth: { token },
    locale: "zh-CN",
    userAgent: "zhuanzhu-work/0.1.0",
  };
}

function buildChatSendParams({ message, sessionKey, chatMode, fastMode, runId }) {
  const body = buildChatBody({
    message,
    sessionKey,
    stream: true,
    chatMode,
    fastMode,
  });
  const params = {
    sessionKey: body.session_key,
    message,
    deliver: false,
    idempotencyKey: runId,
    timeoutMs: CHAT_TIMEOUT_MS,
  };
  if (isFastChatMode(normalizeChatMode(chatMode))) {
    params.thinking = "off";
  }
  return params;
}

class GatewayWsClient {
  constructor(url) {
    this.url = url;
    /** @type {WebSocket | null} */
    this.ws = null;
    this.token = null;
    this.connectNonce = null;
    this.connected = false;
    this.connectPromise = null;
    /** @type {Map<string, { resolve: (v: unknown) => void, reject: (e: Error) => void }>} */
    this.pending = new Map();
    /** @type {Set<(frame: Record<string, unknown>) => void>} */
    this.eventListeners = new Set();
    this.closed = false;
  }

  close() {
    this.closed = true;
    this.pending.forEach(({ reject }) => {
      reject(new Error("gateway ws closed"));
    });
    this.pending.clear();
    if (this.ws) {
      try {
        this.ws.close();
      } catch {
        // ignore
      }
      this.ws = null;
    }
    this.connected = false;
    this.connectPromise = null;
  }

  onEvent(listener) {
    this.eventListeners.add(listener);
    return () => this.eventListeners.delete(listener);
  }

  emitEvent(frame) {
    for (const listener of this.eventListeners) {
      listener(frame);
    }
  }

  async ensureConnected(token) {
    if (this.connected && this.ws?.readyState === WS_OPEN) {
      return;
    }
    if (this.connectPromise) {
      return this.connectPromise;
    }
    this.token = token;
    this.connectPromise = this._connect(token).finally(() => {
      this.connectPromise = null;
    });
    return this.connectPromise;
  }

  async request(method, params) {
    if (!this.ws || this.ws.readyState !== WS_OPEN) {
      throw new Error("gateway ws not connected");
    }
    const id = randomUUID();
    const frame = { type: "req", id, method, params };
    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`gateway ws request timeout: ${method}`));
      }, CHAT_TIMEOUT_MS);
      this.pending.set(id, {
        resolve: (value) => {
          clearTimeout(timeout);
          resolve(value);
        },
        reject: (err) => {
          clearTimeout(timeout);
          reject(err);
        },
      });
      this.ws.send(JSON.stringify(frame));
    });
  }

  _connect(token) {
    return new Promise((resolve, reject) => {
      if (this.closed) {
        reject(new Error("gateway ws client closed"));
        return;
      }
      this.connectNonce = null;
      this.connected = false;
      const ws = new WebSocket(this.url);
      this.ws = ws;

      const timer = setTimeout(() => {
        reject(new Error("gateway ws connect timeout"));
        try {
          ws.close();
        } catch {
          // ignore
        }
      }, CONNECT_TIMEOUT_MS);

      const fail = (err) => {
        clearTimeout(timer);
        reject(err instanceof Error ? err : new Error(String(err)));
      };

      const onMessage = (event) => {
        let frame;
        try {
          frame = JSON.parse(String(event.data));
        } catch {
          return;
        }

        if (frame.type === "event") {
          if (frame.event === "connect.challenge") {
            this.connectNonce = frame.payload?.nonce;
            if (!this.connectNonce) {
              fail(new Error("gateway connect challenge missing nonce"));
              return;
            }
            const connectId = randomUUID();
            this.pending.set(connectId, {
              resolve: (payload) => {
                clearTimeout(timer);
                this.connected = true;
                resolve(payload);
              },
              reject: fail,
            });
            ws.send(
              JSON.stringify({
                type: "req",
                id: connectId,
                method: "connect",
                params: buildConnectParams(token),
              }),
            );
            return;
          }

          if (this.connected) {
            this.emitEvent(frame);
          }
          return;
        }

        if (frame.type === "res") {
          const pending = this.pending.get(frame.id);
          if (!pending) {
            return;
          }
          this.pending.delete(frame.id);
          if (frame.ok) {
            pending.resolve(frame.payload);
            return;
          }
          const message =
            frame.error?.message || frame.error?.code || "gateway ws request failed";
          pending.reject(new Error(message));
          if (!this.connected) {
            fail(new Error(message));
          }
        }
      };

      ws.addEventListener("message", onMessage);

      ws.addEventListener("error", () => {
        if (!this.connected) {
          fail(new Error("gateway ws connection error"));
        }
      });

      ws.addEventListener("close", () => {
        this.connected = false;
        this.ws = null;
        if (!this.closed) {
          this.connectPromise = null;
        }
      });
    });
  }
}

function getSharedGatewayWsClient() {
  if (!sharedClient) {
    sharedClient = new GatewayWsClient(getGatewayWsUrl());
  }
  return sharedClient;
}

/**
 * Stream chat over Gateway WebSocket (`chat.send` + `chat` events).
 * @param {object} opts
 */
async function openclawChatStreamWs({
  message,
  sessionKey,
  streamId,
  sender,
  chatMode,
  fastMode,
}) {
  const trimmed = String(message || "").trim();
  if (!trimmed) {
    sender.send("openclaw:chat-chunk", {
      streamId,
      error: "消息不能为空",
      done: true,
      ok: false,
    });
    return { ok: false, error: "消息不能为空" };
  }

  let token;
  try {
    token = readGatewayToken();
  } catch (err) {
    const hint = err?.message || String(err);
    sender.send("openclaw:chat-chunk", {
      streamId,
      error: hint,
      done: true,
      ok: false,
    });
    return { ok: false, error: hint };
  }

  const runId = randomUUID();
  const body = buildChatBody({
    message: trimmed,
    sessionKey,
    stream: true,
    chatMode,
    fastMode,
  });
  const client = getSharedGatewayWsClient();
  const emit = (payload) => {
    sender.send("openclaw:chat-chunk", { streamId, transport: "ws", ...payload });
  };

  await client.ensureConnected(token);

  let full = "";
  let cumulative = "";

  /** @type {() => void} */
  let unsubscribe = () => {};

  const streamPromise = new Promise((resolve, reject) => {
    const timeout = setTimeout(() => {
      unsubscribe();
      reject(new Error("gateway ws chat timeout"));
    }, CHAT_TIMEOUT_MS);

    unsubscribe = client.onEvent((frame) => {
      if (frame.event === "chat") {
        const payload = frame.payload || {};
        if (payload.runId !== runId) {
          return;
        }
        if (payload.state === "delta") {
          const delta = extractChatDelta(payload, cumulative);
          const next = extractAssistantText(payload.message);
          if (next) {
            cumulative = next;
          } else if (delta) {
            cumulative += delta;
          }
          if (delta) {
            full += delta;
            emit({ delta, done: false });
          }
          return;
        }
        if (payload.state === "final") {
          clearTimeout(timeout);
          unsubscribe();
          const finalText = extractAssistantText(payload.message);
          if (finalText && finalText.length > full.length) {
            const tail = finalText.slice(full.length);
            if (tail) {
              full += tail;
              emit({ delta: tail, done: false });
            }
            full = finalText;
          }
          const content = full.trim();
          if (!content) {
            reject(new Error("流式响应为空"));
            return;
          }
          emit({ done: true, ok: true, content, streamed: true, transport: "ws" });
          resolve({
            ok: true,
            content,
            sessionKey: body.session_key,
            streamed: true,
            transport: "ws",
          });
          return;
        }
        if (payload.state === "error") {
          clearTimeout(timeout);
          unsubscribe();
          reject(new Error(payload.errorMessage || "chat error"));
          return;
        }
        if (payload.state === "aborted") {
          clearTimeout(timeout);
          unsubscribe();
          reject(new Error("chat aborted"));
        }
        return;
      }

      if (
        frame.event === "session.tool" ||
        frame.event === "agent" ||
        frame.event === "chat.side_result"
      ) {
        emit({
          done: false,
          event: frame.event,
          eventPayload: frame.payload ?? null,
        });
      }
    });
  });

  await client.request(
    "chat.send",
    buildChatSendParams({
      message: trimmed,
      sessionKey: body.session_key,
      chatMode,
      fastMode,
      runId,
    }),
  );

  return streamPromise;
}

function wsChatEnabled() {
  return process.env.ZHUANZHU_CHAT_WS !== "0";
}

module.exports = {
  openclawChatStreamWs,
  getGatewayWsUrl,
  getSharedGatewayWsClient,
  resetSharedGatewayWsClient,
  extractAssistantText,
  extractChatDelta,
  buildConnectParams,
  buildChatSendParams,
  wsChatEnabled,
  GatewayWsClient,
};
