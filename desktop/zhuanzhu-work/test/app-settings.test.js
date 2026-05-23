const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const os = require("os");
const path = require("path");

const {
  normalizeChatSettings,
  loadAppSettings,
  setChatMode,
} = require("../lib/app-settings");

test("normalizeChatSettings migrates fastMode true to mode fast", () => {
  const chat = normalizeChatSettings({ fastMode: true });
  assert.equal(chat.mode, "fast");
  assert.equal(chat.fastMode, true);
});

test("normalizeChatSettings prefers explicit mode", () => {
  const chat = normalizeChatSettings({ mode: "agent", fastMode: true });
  assert.equal(chat.mode, "agent");
  assert.equal(chat.fastMode, false);
});

test("setChatMode persists mode in userData config.json", () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "zhuanzhu-settings-"));
  const fakeApp = {
    getPath(name) {
      if (name === "userData") return tmp;
      throw new Error(`unexpected path ${name}`);
    },
  };

  setChatMode(fakeApp, "fast");
  const loaded = loadAppSettings(fakeApp);
  assert.equal(loaded.chat.mode, "fast");
  assert.equal(loaded.chat.fastMode, true);

  setChatMode(fakeApp, "agent");
  const again = loadAppSettings(fakeApp);
  assert.equal(again.chat.mode, "agent");
  assert.equal(again.chat.fastMode, false);
});
