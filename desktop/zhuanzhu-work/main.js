const { app, BrowserWindow, ipcMain, shell } = require("electron");
const path = require("path");

const { assessOpenClawSetup } = require("./lib/config");
const { ensureGateway, killSpawnedGateway } = require("./lib/gateway");
const { ensureExtracted } = require("./lib/runtime-bundle");
const { ensureAppConfig } = require("./lib/media2text-config");
const { loadAppSettings, setChatFastMode } = require("./lib/app-settings");
const {
  archiveSearch,
  complianceAccept,
  complianceStatus,
  doctor,
  listTranscriptRefs,
  runMedia2text,
  resolveMedia2textBin,
} = require("./lib/media2text-sidecar");
const { createAutoUpdater } = require("./lib/auto-updater");
const { checkOpenClawHygiene } = require("./lib/openclaw-hygiene");
const { openclawChat, openclawChatStream } = require("./lib/openclaw-chat");
const {
  acceptCompliance,
  isComplianceAccepted,
  openClawConfigDir,
  openClawConfigPath,
} = require("./lib/paths");

const APP_ROOT = __dirname;

let mainWindow = null;
/** @type {ReturnType<typeof createAutoUpdater> | null} */
let autoUpdaterCtl = null;

function createShellWindow() {
  const win = new BrowserWindow({
    width: 1180,
    height: 780,
    minWidth: 900,
    minHeight: 600,
    title: "转注 Work",
    show: false,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  win.once("ready-to-show", () => win.show());
  return win;
}

function sendBootstrap(channel, payload) {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send(channel, payload);
  }
}

function chatFastModeEnabled() {
  return loadAppSettings(app).chat.fastMode;
}

function bootstrapState() {
  const { configPath: media2textConfigPath, workspace } = ensureAppConfig(app);
  const complianceAccepted = isComplianceAccepted(app);
  const setup = assessOpenClawSetup();
  const chatSettings = loadAppSettings(app).chat;
  const openclawConfigHygiene = checkOpenClawHygiene();
  return {
    complianceAccepted,
    setup,
    openclawConfigHygiene,
    configPath: openClawConfigPath(),
    configDir: openClawConfigDir(),
    workspace,
    media2textConfigPath,
    media2textBin: resolveMedia2textBin(app),
    chatFastMode: chatSettings.fastMode,
    needsWizard: !complianceAccepted || !setup.complete,
  };
}

async function runBootstrap() {
  sendBootstrap("bootstrap:status", {
    phase: "runtime",
    message: "正在准备运行环境…",
  });

  let runtimeRoot;
  try {
    runtimeRoot = await ensureExtracted(app, (progress) => {
      sendBootstrap("bootstrap:status", progress);
    });
  } catch (err) {
    sendBootstrap("bootstrap:status", {
      phase: "error",
      message: err?.message || String(err),
    });
    return;
  }

  sendBootstrap("bootstrap:status", {
    phase: "gateway",
    message: "正在启动 OpenClaw Gateway…",
  });

  const gateway = await ensureGateway(runtimeRoot);
  if (!gateway.ok) {
    sendBootstrap("bootstrap:status", {
      phase: "error",
      message: gateway.error,
    });
    return;
  }

  sendBootstrap("bootstrap:status", {
    phase: "ready",
    message: "Gateway 已就绪",
    spawned: gateway.spawned,
  });

  const state = bootstrapState();
  if (state.needsWizard) {
    mainWindow.loadFile(path.join(__dirname, "renderer", "wizard.html"));
  } else {
    mainWindow.loadFile(path.join(__dirname, "renderer", "index.html"));
  }
}

function registerIpc() {
  ipcMain.handle("openclaw:chat", (_event, payload) =>
    openclawChat({ ...payload, fastMode: chatFastModeEnabled() }),
  );

  ipcMain.handle("openclaw:chat-stream", async (event, payload) => {
    const streamId =
      payload?.streamId ||
      `stream-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    return openclawChatStream({
      ...payload,
      streamId,
      sender: event.sender,
      fastMode: chatFastModeEnabled(),
    });
  });

  ipcMain.handle("app:get-chat-settings", () => loadAppSettings(app).chat);

  ipcMain.handle("app:openclaw-hygiene", () => checkOpenClawHygiene());

  ipcMain.handle("app:set-chat-fast-mode", (_event, enabled) => ({
    ok: true,
    chat: setChatFastMode(app, enabled),
  }));

  ipcMain.handle("app:get-bootstrap", () => bootstrapState());

  ipcMain.handle("app:accept-compliance", async () => {
    ensureAppConfig(app);
    const record = acceptCompliance(app);
    const cli = await complianceAccept(app);
    return {
      ok: true,
      record,
      media2text: cli.data || { ok: cli.ok, error: cli.error },
    };
  });

  ipcMain.handle("media2text:run", (_event, payload) =>
    runMedia2text(app, payload?.argv || [], payload || {}),
  );

  ipcMain.handle("media2text:archive-search", (_event, payload) =>
    archiveSearch(app, payload?.query, payload || {}),
  );

  ipcMain.handle("media2text:list-transcript-refs", (_event, payload) =>
    listTranscriptRefs(app, payload || {}),
  );

  ipcMain.handle("media2text:doctor", () => doctor(app));

  ipcMain.handle("media2text:compliance-status", () => complianceStatus(app));

  ipcMain.handle("app:open-config-dir", async () => {
    const dir = openClawConfigDir();
    await shell.openPath(dir);
    return { ok: true, dir };
  });

  ipcMain.handle("app:enter-main", () => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.loadFile(path.join(__dirname, "renderer", "index.html"));
    }
    return { ok: true };
  });

  ipcMain.handle("app:get-version", () => app.getVersion());

  ipcMain.handle("app:is-packaged", () => app.isPackaged);

  ipcMain.handle("app:get-update-state", () =>
    autoUpdaterCtl ? autoUpdaterCtl.getState() : { status: "dev", currentVersion: app.getVersion() },
  );

  ipcMain.handle("app:check-updates", async () => {
    if (!autoUpdaterCtl) return { skipped: true, reason: "dev" };
    return autoUpdaterCtl.checkForUpdates();
  });

  ipcMain.handle("app:download-update", async () => {
    if (!autoUpdaterCtl) return { skipped: true, reason: "dev" };
    return autoUpdaterCtl.downloadUpdate();
  });

  ipcMain.handle("app:quit-and-install", () => {
    autoUpdaterCtl?.quitAndInstall();
    return { ok: true };
  });
}

app.whenReady().then(async () => {
  ensureAppConfig(app);
  registerIpc();
  mainWindow = createShellWindow();
  autoUpdaterCtl = createAutoUpdater(() => mainWindow);
  mainWindow.loadFile(path.join(__dirname, "renderer", "splash.html"));
  mainWindow.webContents.once("did-finish-load", () => {
    runBootstrap().catch((err) => {
      sendBootstrap("bootstrap:status", {
        phase: "error",
        message: err?.message || String(err),
      });
    });
  });

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      mainWindow = createShellWindow();
      mainWindow.loadFile(path.join(__dirname, "renderer", "splash.html"));
      mainWindow.webContents.once("did-finish-load", () => {
        runBootstrap().catch((err) => {
          sendBootstrap("bootstrap:status", {
            phase: "error",
            message: err?.message || String(err),
          });
        });
      });
    }
  });
});

app.on("before-quit", () => {
  killSpawnedGateway();
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
