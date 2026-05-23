const { test } = require("node:test");
const assert = require("node:assert/strict");

const {
  buildChatBody,
  resolveSessionKey,
  FAST_SESSION_KEY,
} = require("../lib/openclaw-chat");

test("buildChatBody adds fast flags in fast mode", () => {
  const body = buildChatBody({
    message: "hi",
    sessionKey: "agent:main:wanzhan",
    stream: true,
    chatMode: "fast",
  });
  assert.equal(body.thinking, "off");
  assert.equal(body.fast, true);
  assert.equal(body.session_key, FAST_SESSION_KEY);
});

test("buildChatBody uses lens session in agent mode", () => {
  const body = buildChatBody({
    message: "hi",
    sessionKey: "agent:main:wanzhan",
    stream: false,
    chatMode: "agent",
  });
  assert.equal(body.thinking, undefined);
  assert.equal(body.fast, undefined);
  assert.equal(body.session_key, "agent:main:wanzhan");
});

test("buildChatBody omits fast flags by default", () => {
  const body = buildChatBody({
    message: "hi",
    sessionKey: "agent:main:main",
    stream: false,
    fastMode: false,
  });
  assert.equal(body.thinking, undefined);
  assert.equal(body.fast, undefined);
  assert.equal(body.session_key, "agent:main:main");
});

test("fastMode legacy flag maps to fast chat body", () => {
  const body = buildChatBody({
    message: "hi",
    sessionKey: "agent:main:archive",
    stream: true,
    fastMode: true,
  });
  assert.equal(body.thinking, "off");
  assert.equal(body.fast, true);
  assert.equal(body.session_key, FAST_SESSION_KEY);
});

test("ZHUANZHU_CHAT_FAST env overrides agent mode", () => {
  const prev = process.env.ZHUANZHU_CHAT_FAST;
  process.env.ZHUANZHU_CHAT_FAST = "1";
  try {
    const body = buildChatBody({
      message: "hi",
      sessionKey: "agent:main:main",
      stream: true,
      chatMode: "agent",
    });
    assert.equal(body.thinking, "off");
    assert.equal(body.fast, true);
    assert.equal(body.session_key, FAST_SESSION_KEY);
  } finally {
    if (prev === undefined) delete process.env.ZHUANZHU_CHAT_FAST;
    else process.env.ZHUANZHU_CHAT_FAST = prev;
  }
});

test("resolveSessionKey routes fast mode to dedicated session", () => {
  assert.equal(
    resolveSessionKey({ chatMode: "fast", sessionKey: "agent:main:nuwa" }),
    FAST_SESSION_KEY,
  );
  assert.equal(
    resolveSessionKey({ chatMode: "agent", sessionKey: "agent:main:nuwa" }),
    "agent:main:nuwa",
  );
});
