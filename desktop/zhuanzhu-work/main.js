const { app, BrowserWindow, ipcMain } = require("electron");
const fs = require("fs");
const os = require("os");
const path = require("path");

const DEFAULT_SESSION_KEY = "agent:main:main";
const GATEWAY_URL =
  process.env.OPENCLAW_GATEWAY_HTTP ||
  "http://127.0.0.1:18789/v1/chat/completions";

function readGatewayToken() {
  if (process.env.OPENCLAW_GATEWAY_TOKEN) {
    return process.env.OPENCLAW_GATEWAY_TOKEN;
  }
  const configPath =
    process.env.OPENCLAW_CONFIG_PATH ||
    path.join(os.homedir(), ".openclaw", "openclaw.json");
  if (!fs.existsSync(configPath)) {
    throw new Error(
      `未找到 OpenClaw 配置：${configPath}。请设置 OPENCLAW_GATEWAY_TOKEN 或安装 OpenClaw。`,
    );
  }
  const config = JSON.parse(fs.readFileSync(configPath, "utf8"));
  const token = config?.gateway?.auth?.token;
  if (!token) {
    throw new Error("openclaw.json 中缺少 gateway.auth.token");
  }
  return token;
}

function gatewayUnreachableMessage(cause) {
  const hint =
    "请先启动 Gateway：source ~/.nvm/nvm.sh && openclaw gateway run --port 18789 --bind loopback";
  if (cause?.code === "ECONNREFUSED" || cause?.cause?.code === "ECONNREFUSED") {
    return `无法连接 OpenClaw Gateway（127.0.0.1:18789）。${hint}`;
  }
  if (cause?.name === "AbortError") {
    return `Gateway 请求超时。${hint}`;
  }
  return cause?.message || String(cause);
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
    return { ok: false, error: err.message };
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
      return {
        ok: false,
        error: `Gateway 返回 ${resp.status}：${detail}`,
      };
    }

    const choices = data?.choices || [];
    const content = choices[0]?.message?.content;
    if (typeof content === "string" && content.trim()) {
      return { ok: true, content: content.trim(), sessionKey: body.session_key };
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

function createWindow() {
  const win = new BrowserWindow({
    width: 1180,
    height: 780,
    minWidth: 900,
    minHeight: 600,
    title: "转注 Work",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  win.loadFile(path.join(__dirname, "renderer", "index.html"));
}

app.whenReady().then(() => {
  ipcMain.handle("openclaw:chat", (_event, payload) => openclawChat(payload));

  createWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
