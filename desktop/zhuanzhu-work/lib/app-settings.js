const fs = require("fs");
const path = require("path");

const DEFAULTS = {
  chat: {
    mode: "agent",
    /** @deprecated use chat.mode — kept for migration from L3 */
    fastMode: false,
  },
};

function settingsPath(app) {
  return path.join(app.getPath("userData"), "config.json");
}

function normalizeChatSettings(chat = {}) {
  let mode = chat.mode;
  if (mode !== "fast" && mode !== "agent") {
    mode = chat.fastMode === true ? "fast" : "agent";
  }
  return {
    mode,
    fastMode: mode === "fast",
  };
}

function loadAppSettings(app) {
  const filePath = settingsPath(app);
  if (!fs.existsSync(filePath)) {
    return {
      chat: { ...DEFAULTS.chat },
    };
  }
  try {
    const raw = JSON.parse(fs.readFileSync(filePath, "utf8"));
    const chat = normalizeChatSettings({ ...DEFAULTS.chat, ...(raw.chat || {}) });
    return { chat };
  } catch {
    return {
      chat: { ...DEFAULTS.chat },
    };
  }
}

function saveAppSettings(app, settings) {
  const filePath = settingsPath(app);
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, `${JSON.stringify(settings, null, 2)}\n`, "utf8");
}

function setChatMode(app, mode) {
  const settings = loadAppSettings(app);
  const normalized = mode === "fast" ? "fast" : "agent";
  settings.chat.mode = normalized;
  settings.chat.fastMode = normalized === "fast";
  saveAppSettings(app, settings);
  return settings.chat;
}

/** @deprecated L3 — prefer setChatMode */
function setChatFastMode(app, enabled) {
  return setChatMode(app, enabled ? "fast" : "agent");
}

module.exports = {
  DEFAULTS,
  settingsPath,
  loadAppSettings,
  saveAppSettings,
  normalizeChatSettings,
  setChatMode,
  setChatFastMode,
};
