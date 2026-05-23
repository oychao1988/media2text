const { app } = require("electron");
const { autoUpdater } = require("electron-updater");

/** @typedef {'idle'|'checking'|'available'|'downloading'|'ready'|'uptodate'|'error'|'dev'} UpdateStatus */

/**
 * @param {import('electron').BrowserWindow | null} getMainWindow
 */
function createAutoUpdater(getMainWindow) {
  /** @type {{ status: UpdateStatus, version: string | null, progress: object | null, error: string | null }} */
  const state = {
    status: "idle",
    version: null,
    progress: null,
    error: null,
  };

  function broadcast() {
    const win = getMainWindow();
    if (win && !win.isDestroyed()) {
      win.webContents.send("app:update-status", {
        ...state,
        currentVersion: app.getVersion(),
        packaged: app.isPackaged,
      });
    }
  }

  if (!app.isPackaged) {
    state.status = "dev";
    return {
      checkForUpdates: async () => ({ skipped: true, reason: "dev" }),
      downloadUpdate: async () => ({ skipped: true, reason: "dev" }),
      quitAndInstall: () => {},
      getState: () => ({ ...state, currentVersion: app.getVersion(), packaged: false }),
    };
  }

  autoUpdater.autoDownload = false;
  autoUpdater.autoInstallOnAppQuit = true;
  autoUpdater.allowDowngrade = false;

  autoUpdater.on("checking-for-update", () => {
    state.status = "checking";
    state.error = null;
    broadcast();
  });

  autoUpdater.on("update-available", (info) => {
    state.status = "available";
    state.version = info?.version || null;
    broadcast();
  });

  autoUpdater.on("update-not-available", () => {
    state.status = "uptodate";
    state.version = null;
    broadcast();
    setTimeout(() => {
      if (state.status === "uptodate") {
        state.status = "idle";
        broadcast();
      }
    }, 4000);
  });

  autoUpdater.on("error", (err) => {
    state.status = "error";
    state.error = err?.message || String(err);
    broadcast();
  });

  autoUpdater.on("download-progress", (progress) => {
    state.status = "downloading";
    state.progress = progress;
    broadcast();
  });

  autoUpdater.on("update-downloaded", (info) => {
    state.status = "ready";
    state.version = info?.version || state.version;
    state.progress = null;
    broadcast();
  });

  setTimeout(() => {
    autoUpdater.checkForUpdates().catch(() => {});
  }, 8000);

  return {
    checkForUpdates: () => autoUpdater.checkForUpdates(),
    downloadUpdate: () => autoUpdater.downloadUpdate(),
    quitAndInstall: () => {
      autoUpdater.quitAndInstall(false, true);
    },
    getState: () => ({
      ...state,
      currentVersion: app.getVersion(),
      packaged: true,
    }),
  };
}

module.exports = { createAutoUpdater };
