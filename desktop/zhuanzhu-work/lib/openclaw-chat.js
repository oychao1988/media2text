const { readGatewayToken, assessOpenClawSetup } = require("./config");
const { openClawConfigPath } = require("./paths");
const { gatewayUnreachableMessage } = require("./gateway");

const DEFAULT_SESSION_KEY = "agent:main:main";
/** Dedicated lightweight session for 快速 mode (separate from lens sessions). */
const FAST_SESSION_KEY = "agent:main:fast";
const GATEWAY_URL =
  process.env.OPENCLAW_GATEWAY_HTTP ||
  "http://127.0.0.1:18789/v1/chat/completions";

const CHAT_MODES = new Set(["agent", "fast"]);

function normalizeChatMode(mode) {
  if (mode === "fast" || mode === "agent") return mode;
  return "agent";
}

function isFastChatMode(chatMode) {
  return (
    process.env.ZHUANZHU_CHAT_FAST === "1" ||
    normalizeChatMode(chatMode) === "fast"
  );
}

function resolveSessionKey({ chatMode, sessionKey }) {
  if (isFastChatMode(chatMode)) {
    return FAST_SESSION_KEY;
  }
  return sessionKey || DEFAULT_SESSION_KEY;
}

function gatewayAuthError(err) {
  const setup = assessOpenClawSetup();
  const hint = setup.complete
    ? err.message
    : `${err.message} 可在「${openClawConfigPath()}」完成配置。`;
  return { ok: false, error: hint, configIncomplete: !setup.complete };
}

function buildChatBody({ message, sessionKey, stream, chatMode, fastMode }) {
  const mode =
    fastMode === true && chatMode === undefined
      ? "fast"
      : normalizeChatMode(chatMode);
  const body = {
    model: "openclaw",
    stream: Boolean(stream),
    session_key: resolveSessionKey({ chatMode: mode, sessionKey }),
    messages: [{ role: "user", content: message }],
  };
  if (isFastChatMode(mode)) {
    body.thinking = "off";
    body.fast = true;
  }
  return body;
}

function extractAssistantContent(data) {
  const choices = data?.choices || [];
  const content = choices[0]?.message?.content;
  if (typeof content === "string" && content.trim()) {
    return content.trim();
  }
  return null;
}

async function openclawChat({ message, sessionKey, chatMode, fastMode }) {
  const trimmed = String(message || "").trim();
  if (!trimmed) {
    return { ok: false, error: "消息不能为空" };
  }

  let token;
  try {
    token = readGatewayToken();
  } catch (err) {
    return gatewayAuthError(err);
  }

  const body = buildChatBody({
    message: trimmed,
    sessionKey,
    stream: false,
    chatMode,
    fastMode,
  });
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 120_000);

  try {
    const resp = await fetch(GATEWAY_URL, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
      signal: controller.signal,
    });

    const raw = await resp.text();
    let data;
    try {
      data = raw ? JSON.parse(raw) : {};
    } catch {
      data = { raw };
    }

    if (!resp.ok) {
      const detail =
        data?.error?.message || data?.message || raw || resp.statusText;
      const setup = assessOpenClawSetup();
      const suffix = setup.complete
        ? ""
        : ` 请检查模型 Provider API Key：${openClawConfigPath()}`;
      return {
        ok: false,
        error: `Gateway 返回 ${resp.status}：${detail}${suffix}`,
        configIncomplete: !setup.complete,
      };
    }

    const content = extractAssistantContent(data);
    if (content) {
      return {
        ok: true,
        content,
        sessionKey: body.session_key,
        chatMode: normalizeChatMode(chatMode),
        streamed: false,
      };
    }

    return {
      ok: false,
      error: "Gateway 响应中无 assistant 内容",
      raw: data,
    };
  } catch (err) {
    return { ok: false, error: gatewayUnreachableMessage(err) };
  } finally {
    clearTimeout(timeout);
  }
}

function parseSseLines(buffer, onDelta) {
  const lines = buffer.split("\n");
  const rest = lines.pop() || "";
  for (const line of lines) {
    if (!line.startsWith("data:")) continue;
    const payload = line.slice(5).trim();
    if (!payload || payload === "[DONE]") continue;
    try {
      const json = JSON.parse(payload);
      const delta = json.choices?.[0]?.delta?.content;
      if (delta) onDelta(delta);
    } catch {
      // ignore malformed chunks
    }
  }
  return rest;
}

async function openclawChatStream({
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
    const authErr = gatewayAuthError(err);
    sender.send("openclaw:chat-chunk", {
      streamId,
      error: authErr.error,
      done: true,
      ok: false,
    });
    return authErr;
  }

  const body = buildChatBody({
    message: trimmed,
    sessionKey,
    stream: true,
    chatMode,
    fastMode,
  });
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 120_000);

  const emit = (payload) => {
    sender.send("openclaw:chat-chunk", { streamId, ...payload });
  };

  if (process.env.ZHUANZHU_CHAT_WS !== "0") {
    try {
      const { openclawChatStreamWs } = require("./openclaw-chat-ws");
      return await openclawChatStreamWs({
        message: trimmed,
        sessionKey,
        streamId,
        sender,
        chatMode,
        fastMode,
      });
    } catch {
      // Fall through to HTTP SSE (P5 pattern).
    }
  }

  try {
    const resp = await fetch(GATEWAY_URL, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
        Accept: "text/event-stream",
      },
      body: JSON.stringify(body),
      signal: controller.signal,
    });

    if (!resp.ok) {
      const raw = await resp.text();
      let data;
      try {
        data = raw ? JSON.parse(raw) : {};
      } catch {
        data = {};
      }
      const detail =
        data?.error?.message || data?.message || raw || resp.statusText;
      throw new Error(`Gateway 返回 ${resp.status}：${detail}`);
    }

    if (!resp.body) {
      throw new Error("Gateway 未返回可流式读取的 body");
    }

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let full = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      buffer = parseSseLines(buffer, (delta) => {
        full += delta;
        emit({ delta, done: false });
      });
    }

    if (buffer.trim()) {
      parseSseLines(`${buffer}\n`, (delta) => {
        full += delta;
        emit({ delta, done: false });
      });
    }

    const content = full.trim();
    if (!content) {
      throw new Error("流式响应为空");
    }

    emit({ done: true, ok: true, content, streamed: true });
    return { ok: true, content, sessionKey: body.session_key, streamed: true };
  } catch (err) {
    const fallback = await openclawChat({
      message: trimmed,
      sessionKey,
      chatMode,
      fastMode,
    });
    if (fallback.ok && fallback.content) {
      emit({
        delta: fallback.content,
        done: true,
        ok: true,
        content: fallback.content,
        streamed: false,
        fallback: true,
      });
      return { ...fallback, streamed: false, fallback: true };
    }

    const error = fallback.error || err?.message || String(err);
    emit({ error, done: true, ok: false });
    return { ok: false, error };
  } finally {
    clearTimeout(timeout);
  }
}

module.exports = {
  openclawChat,
  openclawChatStream,
  buildChatBody,
  resolveSessionKey,
  normalizeChatMode,
  isFastChatMode,
  DEFAULT_SESSION_KEY,
  FAST_SESSION_KEY,
  CHAT_MODES,
};
