const { test } = require("node:test");
const assert = require("node:assert/strict");

const { buildChatBody } = require("../lib/openclaw-chat");

test("buildChatBody adds fast flags when fastMode is true", () => {
  const body = buildChatBody({
    message: "hi",
    sessionKey: "agent:main:main",
    stream: true,
    fastMode: true,
  });
  assert.equal(body.thinking, "off");
  assert.equal(body.fast, true);
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
});

test("ZHUANZHU_CHAT_FAST env overrides config fastMode false", () => {
  const prev = process.env.ZHUANZHU_CHAT_FAST;
  process.env.ZHUANZHU_CHAT_FAST = "1";
  try {
    const body = buildChatBody({
      message: "hi",
      sessionKey: "agent:main:main",
      stream: true,
      fastMode: false,
    });
    assert.equal(body.thinking, "off");
    assert.equal(body.fast, true);
  } finally {
    if (prev === undefined) delete process.env.ZHUANZHU_CHAT_FAST;
    else process.env.ZHUANZHU_CHAT_FAST = prev;
  }
});
