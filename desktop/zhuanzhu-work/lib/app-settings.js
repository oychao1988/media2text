const fs = require("fs");
const path = require("path");

const DEFAULTS = {
  chat: {
    fastMode: false,
  },
};

function settingsPath(app) {
  return path.join(app.getPath("userData"), "config.json");
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
    return {
      chat: { ...DEFAULTS.chat, ...(raw.chat || {}) },
    };
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

function setChatFastMode(app, enabled) {
  const settings = loadAppSettings(app);
  settings.chat.fastMode = Boolean(enabled);
  saveAppSettings(app, settings);
  return settings.chat;
}

module.exports = {
  DEFAULTS,
  settingsPath,
  loadAppSettings,
  saveAppSettings,
  setChatFastMode,
};
