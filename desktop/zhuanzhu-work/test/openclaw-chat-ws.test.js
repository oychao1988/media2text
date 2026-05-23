const { test } = require("node:test");
const assert = require("node:assert/strict");
const { EventEmitter } = require("node:events");

const {
  extractAssistantText,
  extractChatDelta,
  buildChatSendParams,
  buildConnectParams,
  GatewayWsClient,
  resetSharedGatewayWsClient,
} = require("../lib/openclaw-chat-ws");

test("extractChatDelta prefers deltaText suffix", () => {
  const delta = extractChatDelta(
    { deltaText: " world", message: { text: "hello world" } },
    "hello",
  );
  assert.equal(delta, " world");
});

test("extractChatDelta diffs cumulative message text", () => {
  const first = extractChatDelta({ message: { text: "hel" } }, "");
  const second = extractChatDelta({ message: { text: "hello" } }, "hel");
  assert.equal(first, "hel");
  assert.equal(second, "lo");
});

test("buildChatSendParams maps fast mode to thinking off", () => {
  const params = buildChatSendParams({
    message: "hi",
    sessionKey: "agent:main:wanzhan",
    chatMode: "fast",
    runId: "run-1",
  });
  assert.equal(params.thinking, "off");
  assert.equal(params.sessionKey, "agent:main:fast");
  assert.equal(params.idempotencyKey, "run-1");
});

test("buildConnectParams uses gateway-client backend operator", () => {
  const params = buildConnectParams("tok");
  assert.equal(params.client.id, "gateway-client");
  assert.equal(params.client.mode, "backend");
  assert.equal(params.role, "operator");
  assert.equal(params.auth.token, "tok");
});

test("GatewayWsClient streams chat deltas in order", async () => {
  resetSharedGatewayWsClient();

  const instances = [];
  class FakeWebSocket extends EventEmitter {
    static OPEN = 1;
    constructor(url) {
      super();
      this.url = url;
      this.readyState = 0;
      instances.push(this);
      queueMicrotask(() => {
        this.readyState = 1;
        this.emit("open");
        this._receive({
          type: "event",
          event: "connect.challenge",
          payload: { nonce: "nonce-1" },
        });
      });
    }

    addEventListener(type, listener) {
      this.on(type, listener);
    }

    removeEventListener(type, listener) {
      this.off(type, listener);
    }

    send(raw) {
      const frame = JSON.parse(raw);
      if (frame.method === "connect") {
        this._receive({
          type: "res",
          id: frame.id,
          ok: true,
          payload: { type: "hello-ok", protocol: 4 },
        });
        return;
      }
      if (frame.method === "chat.send") {
        const runId = frame.params.idempotencyKey;
        this._receive({
          type: "event",
          event: "chat",
          payload: {
            runId,
            sessionKey: frame.params.sessionKey,
            state: "delta",
            deltaText: "你",
            message: { text: "你" },
          },
        });
        this._receive({
          type: "event",
          event: "chat",
          payload: {
            runId,
            sessionKey: frame.params.sessionKey,
            state: "delta",
            deltaText: "好",
            message: { text: "你好" },
          },
        });
        this._receive({
          type: "res",
          id: frame.id,
          ok: true,
          payload: { runId },
        });
        this._receive({
          type: "event",
          event: "chat",
          payload: {
            runId,
            sessionKey: frame.params.sessionKey,
            state: "final",
            message: { text: "你好" },
          },
        });
      }
    }

    close() {
      this.readyState = 3;
      this.emit("close");
    }

    _receive(frame) {
      this.emit("message", { data: JSON.stringify(frame) });
    }
  }

  const prevToken = process.env.OPENCLAW_GATEWAY_TOKEN;
  process.env.OPENCLAW_GATEWAY_TOKEN = "test-token";

  const original = global.WebSocket;
  global.WebSocket = FakeWebSocket;
  const chunks = [];
  const sender = {
    send(_channel, payload) {
      chunks.push(payload);
    },
  };

  try {
    const { openclawChatStreamWs } = require("../lib/openclaw-chat-ws");
    const result = await openclawChatStreamWs({
      message: "ping",
      sessionKey: "agent:main:main",
      streamId: "s1",
      sender,
      chatMode: "agent",
    });
    assert.equal(result.ok, true);
    assert.equal(result.content, "你好");
    assert.equal(result.transport, "ws");
    const deltas = chunks.filter((c) => c.delta).map((c) => c.delta);
    assert.deepEqual(deltas, ["你", "好"]);
    assert.equal(chunks.at(-1)?.done, true);
    assert.equal(chunks.at(-1)?.ok, true);
  } finally {
    global.WebSocket = original;
    resetSharedGatewayWsClient();
    if (prevToken === undefined) {
      delete process.env.OPENCLAW_GATEWAY_TOKEN;
    } else {
      process.env.OPENCLAW_GATEWAY_TOKEN = prevToken;
    }
  }
});

test("extractAssistantText reads content blocks", () => {
  const text = extractAssistantText({
    role: "assistant",
    content: [{ type: "text", text: "hello" }],
  });
  assert.equal(text, "hello");
});
