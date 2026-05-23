#!/usr/bin/env node
/**
 * Benchmark OpenClaw Gateway chat latency over WebSocket (chat.send + chat events).
 * Compare with scripts/benchmark_chat_latency.py (HTTP SSE).
 */
const { readFileSync } = require("node:fs");
const { homedir } = require("node:os");
const { join } = require("node:path");
const { performance } = require("node:perf_hooks");
const { randomUUID } = require("node:crypto");

const {
  extractAssistantText,
  extractChatDelta,
  buildConnectParams,
  buildChatSendParams,
} = require("../desktop/zhuanzhu-work/lib/openclaw-chat-ws");

function loadToken() {
  const env = process.env.OPENCLAW_GATEWAY_TOKEN?.trim();
  if (env) return env;
  const configPath =
    process.env.OPENCLAW_CONFIG_PATH || join(homedir(), ".openclaw", "openclaw.json");
  const data = JSON.parse(readFileSync(configPath, "utf8"));
  const token = data?.gateway?.auth?.token;
  if (!token) {
    throw new Error(`gateway.auth.token missing in ${configPath}`);
  }
  return String(token);
}

function runOnce({ url, token, sessionKey, message, chatMode }) {
  return new Promise((resolve, reject) => {
    const t0 = performance.now();
    let ttfbMs = null;
    let ttftMs = null;
    let totalMs = null;
    let firstText = "";
    let cumulative = "";
    let full = "";
    const runId = randomUUID();

    const ws = new WebSocket(url);
    const fail = (error) => {
      try {
        ws.close();
      } catch {
        // ignore
      }
      resolve({
        ok: false,
        error: error?.message || String(error),
        ttfb_ms: ttfbMs,
        transport: "ws",
      });
    };

    const timer = setTimeout(() => fail(new Error("ws chat timeout")), 120_000);

    ws.addEventListener("message", (event) => {
      let frame;
      try {
        frame = JSON.parse(String(event.data));
      } catch {
        return;
      }

      if (frame.type === "event" && frame.event === "connect.challenge") {
        ttfbMs = performance.now() - t0;
        const connectId = randomUUID();
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

      if (frame.type === "res" && frame.ok && frame.payload?.type === "hello-ok") {
        ws.send(
          JSON.stringify({
            type: "req",
            id: randomUUID(),
            method: "chat.send",
            params: buildChatSendParams({
              message,
              sessionKey,
              chatMode,
              runId,
            }),
          }),
        );
        return;
      }

      if (frame.type === "event" && frame.event === "chat") {
        const payload = frame.payload || {};
        if (payload.runId !== runId) return;
        if (payload.state === "delta") {
          const delta = extractChatDelta(payload, cumulative);
          const next = extractAssistantText(payload.message);
          if (next) cumulative = next;
          if (delta) {
            if (ttftMs === null) {
              ttftMs = performance.now() - t0;
              firstText = delta.slice(0, 80);
            }
            full += delta;
          }
          return;
        }
        if (payload.state === "final") {
          clearTimeout(timer);
          const finalText = extractAssistantText(payload.message);
          if (finalText) full = finalText;
          totalMs = performance.now() - t0;
          try {
            ws.close();
          } catch {
            // ignore
          }
          resolve({
            ok: true,
            ttfb_ms: round(ttfbMs),
            ttft_ms: round(ttftMs),
            total_ms: round(totalMs),
            first_text: firstText,
            transport: "ws",
          });
          return;
        }
        if (payload.state === "error") {
          clearTimeout(timer);
          fail(new Error(payload.errorMessage || "chat error"));
        }
      }
    });

    ws.addEventListener("error", () => fail(new Error("ws error")));
  });
}

function round(n) {
  return n == null ? null : Math.round(n * 10) / 10;
}

function parseArgs(argv) {
  const out = {
    runs: 3,
    sessionKey: "agent:main:main",
    message: "回复一个字：好",
    mode: null,
    url: process.env.OPENCLAW_GATEWAY_WS || "ws://127.0.0.1:18789",
  };
  for (let i = 2; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--runs" && argv[i + 1]) {
      out.runs = Number(argv[++i]);
    } else if (arg === "--session-key" && argv[i + 1]) {
      out.sessionKey = argv[++i];
    } else if (arg === "--message" && argv[i + 1]) {
      out.message = argv[++i];
    } else if (arg === "--mode" && argv[i + 1]) {
      out.mode = argv[++i];
    } else if (arg === "--url" && argv[i + 1]) {
      out.url = argv[++i];
    }
  }
  if (out.mode === "fast") {
    out.sessionKey = "agent:main:fast";
  }
  return out;
}

async function main() {
  const args = parseArgs(process.argv);
  let token;
  try {
    token = loadToken();
  } catch (err) {
    console.error(JSON.stringify({ ok: false, error: err.message }));
    process.exit(1);
  }

  const runs = [];
  let failures = 0;
  for (let i = 0; i < args.runs; i += 1) {
    const result = await runOnce({
      url: args.url,
      token,
      sessionKey: args.sessionKey,
      message: args.message,
      chatMode: args.mode === "fast" ? "fast" : "agent",
    });
    result.run = i + 1;
    result.session_key = args.sessionKey;
    result.mode = args.mode;
    runs.push(result);
    if (!result.ok) failures += 1;
  }

  const ttfts = runs
    .filter((r) => r.ok && r.ttft_ms != null)
    .map((r) => r.ttft_ms)
    .sort((a, b) => a - b);

  const summary = {
    ok: failures === 0,
    transport: "ws",
    url: args.url,
    runs,
    failures,
    mode: args.mode,
    session_key: args.sessionKey,
    ttft_ms_p50: ttfts.length ? ttfts[Math.floor(ttfts.length / 2)] : null,
  };

  console.log(JSON.stringify(summary, null, 2));
  if (failures === runs.length) process.exit(1);
  if (failures) process.exit(4);
}

main().catch((err) => {
  console.error(JSON.stringify({ ok: false, error: String(err) }));
  process.exit(1);
});
