const { app, BrowserWindow, ipcMain, shell } = require("electron");
const path = require("path");

const { assessOpenClawSetup, readGatewayToken } = require("./lib/config");
const {
  ensureGateway,
  killSpawnedGateway,
  gatewayUnreachableMessage,
} = require("./lib/gateway");
const { ensureAppConfig } = require("./lib/media2text-config");
const {
  archiveSearch,
  complianceAccept,
  complianceStatus,
  doctor,
  runMedia2text,
  resolveMedia2textBin,
} = require("./lib/media2text-sidecar");
const {
  acceptCompliance,
  isComplianceAccepted,
  openClawConfigDir,
  openClawConfigPath,
} = require("./lib/paths");

const DEFAULT_SESSION_KEY = "agent:main:main";
const GATEWAY_URL =
  process.env.OPENCLAW_GATEWAY_HTTP ||
  "http://127.0.0.1:18789/v1/chat/completions";

const APP_ROOT = __dirname;

function bundledResourcesRoot() {
  if (app.isPackaged) {
    return path.join(process.resourcesPath, "resources");
  }
  return path.join(APP_ROOT, "resources");
}
let mainWindow = null;

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

function bootstrapState() {
  const { configPath: media2textConfigPath, workspace } = ensureAppConfig(app);
  const complianceAccepted = isComplianceAccepted(app);
  const setup = assessOpenClawSetup();
  return {
    complianceAccepted,
    setup,
    configPath: openClawConfigPath(),
    configDir: openClawConfigDir(),
    workspace,
    media2textConfigPath,
    media2textBin: resolveMedia2textBin(app),
    needsWizard: !complianceAccepted || !setup.complete,
  };
}

async function openclawChat({ message, sessionKey }) {
  const trimmed = String(message || "").trim();
  if (!trimmed) {
    return { ok: false, error: "消息不能为空" };
  }

  let token;
  try {
    token = readGatewayToken();
  } catch (err) {
    const setup = assessOpenClawSetup();
    const hint = setup.complete
      ? err.message
      : `${err.message} 可在「${openClawConfigPath()}」完成配置。`;
    return { ok: false, error: hint, configIncomplete: !setup.complete };
  }

  const body = {
    model: "openclaw",
    stream: false,
    session_key: sessionKey || DEFAULT_SESSION_KEY,
    messages: [{ role: "user", content: trimmed }],
  };

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

    const choices = data?.choices || [];
    const content = choices[0]?.message?.content;
    if (typeof content === "string" && content.trim()) {
      return {
        ok: true,
        content: content.trim(),
        sessionKey: body.session_key,
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

async function runBootstrap() {
  sendBootstrap("bootstrap:status", {
    phase: "gateway",
    message: "正在启动 OpenClaw Gateway…",
  });

  const gateway = await ensureGateway(bundledResourcesRoot());
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
  ipcMain.handle("openclaw:chat", (_event, payload) => openclawChat(payload));

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
}

app.whenReady().then(async () => {
  ensureAppConfig(app);
  registerIpc();
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
