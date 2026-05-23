const { spawn, spawnSync } = require("child_process");
const fs = require("fs");
const path = require("path");
const { gatewayLogPath, openClawConfigPath } = require("./paths");

const GATEWAY_HOST = "127.0.0.1";
const GATEWAY_PORT = 18789;
const GATEWAY_HEALTH_URL = `http://${GATEWAY_HOST}:${GATEWAY_PORT}/health`;
const GATEWAY_START_TIMEOUT_MS = 60_000;
const MIN_NODE = [22, 14, 0];

let spawnedGatewayPid = null;
let spawnedGatewayChild = null;

function parseNodeVersion(raw) {
  const match = String(raw || "").trim().match(/^v?(\d+)\.(\d+)\.(\d+)/);
  if (!match) return null;
  return [Number(match[1]), Number(match[2]), Number(match[3])];
}

function nodeMeetsMinimum(versionParts) {
  if (!versionParts) return false;
  for (let i = 0; i < 3; i += 1) {
    if (versionParts[i] > MIN_NODE[i]) return true;
    if (versionParts[i] < MIN_NODE[i]) return false;
  }
  return true;
}

function nodeVersionFromBinary(nodeBin) {
  const result = spawnSync(nodeBin, ["-v"], { encoding: "utf8" });
  if (result.status !== 0) return null;
  return parseNodeVersion(result.stdout || result.stderr);
}

function bundledNodeBin(appRoot) {
  const candidates = [
    path.join(appRoot, "resources", "node", "bin", "node"),
    path.join(appRoot, "resources", "node"),
  ];
  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) return candidate;
  }
  return null;
}

function resolveNodeBin(appRoot) {
  const bundled = bundledNodeBin(appRoot);
  if (bundled && nodeMeetsMinimum(nodeVersionFromBinary(bundled))) {
    return bundled;
  }

  const fromPath = spawnSync("which", ["node"], { encoding: "utf8" });
  if (fromPath.status === 0) {
    const nodeBin = fromPath.stdout.trim();
    if (nodeBin && nodeMeetsMinimum(nodeVersionFromBinary(nodeBin))) {
      return nodeBin;
    }
  }

  const nvmDir = process.env.NVM_DIR || path.join(process.env.HOME || "", ".nvm");
  const nvmNode = path.join(nvmDir, "versions", "node", process.version, "bin", "node");
  if (fs.existsSync(nvmNode) && nodeMeetsMinimum(nodeVersionFromBinary(nvmNode))) {
    return nvmNode;
  }

  throw new Error(
    "未找到 Node ≥22.14。请安装 nvm 并执行：source ~/.nvm/nvm.sh && nvm install 22",
  );
}

function buildGatewayEnv(nodeBin) {
  const nodeDir = path.dirname(nodeBin);
  const configPath = openClawConfigPath();
  return {
    ...process.env,
    OPENCLAW_CONFIG_PATH: configPath,
    PATH: `${nodeDir}${path.delimiter}${process.env.PATH || ""}`,
  };
}

function resolveOpenClawBin() {
  if (process.env.OPENCLAW_BIN) {
    return process.env.OPENCLAW_BIN;
  }
  const which = spawnSync("which", ["openclaw"], { encoding: "utf8" });
  if (which.status === 0 && which.stdout.trim()) {
    return which.stdout.trim();
  }
  return null;
}

async function probeGatewayHealth(timeoutMs = 2000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const resp = await fetch(GATEWAY_HEALTH_URL, { signal: controller.signal });
    if (!resp.ok) return false;
    const data = await resp.json().catch(() => ({}));
    return data?.ok === true || data?.status === "live";
  } catch {
    return false;
  } finally {
    clearTimeout(timer);
  }
}

function appendGatewayLog(line) {
  try {
    const logPath = gatewayLogPath();
    fs.mkdirSync(path.dirname(logPath), { recursive: true });
    fs.appendFileSync(logPath, `${line}\n`, "utf8");
  } catch {
    // optional logging
  }
}

function spawnGateway(appRoot) {
  if (process.env.ZHUANZHU_SKIP_SPAWN === "1") {
    return { skipped: true };
  }
  if (spawnedGatewayPid) {
    return { pid: spawnedGatewayPid, alreadyRunning: true };
  }

  const openclawBin = resolveOpenClawBin();
  if (!openclawBin) {
    throw new Error(
      "未找到 openclaw 命令。请安装 YonClaw 或执行：npm i -g openclaw",
    );
  }

  const nodeBin = resolveNodeBin(appRoot);
  const env = buildGatewayEnv(nodeBin);
  const logPath = gatewayLogPath();
  appendGatewayLog(
    `[${new Date().toISOString()}] spawning ${openclawBin} gateway run --port ${GATEWAY_PORT} --bind loopback`,
  );

  const child = spawn(
    openclawBin,
    ["gateway", "run", "--port", String(GATEWAY_PORT), "--bind", "loopback"],
    {
      env,
      detached: false,
      stdio: ["ignore", "pipe", "pipe"],
    },
  );

  spawnedGatewayPid = child.pid;
  spawnedGatewayChild = child;

  child.stdout?.on("data", (chunk) => {
    appendGatewayLog(chunk.toString().trimEnd());
  });
  child.stderr?.on("data", (chunk) => {
    appendGatewayLog(`[stderr] ${chunk.toString().trimEnd()}`);
  });
  child.on("exit", (code, signal) => {
    appendGatewayLog(
      `[${new Date().toISOString()}] gateway exited code=${code} signal=${signal}`,
    );
    if (spawnedGatewayPid === child.pid) {
      spawnedGatewayPid = null;
      spawnedGatewayChild = null;
    }
  });

  return { pid: child.pid, logPath };
}

async function waitForGatewayReady(timeoutMs = GATEWAY_START_TIMEOUT_MS) {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    if (await probeGatewayHealth(1500)) {
      return { ok: true, waitedMs: Date.now() - started };
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  return {
    ok: false,
    error: `OpenClaw Gateway 在 ${Math.round(timeoutMs / 1000)} 秒内未就绪。请检查 ~/.openclaw/openclaw.json 与日志：${gatewayLogPath()}`,
  };
}

async function ensureGateway(appRoot) {
  if (await probeGatewayHealth()) {
    return { ok: true, spawned: false };
  }
  if (process.env.ZHUANZHU_SKIP_SPAWN === "1") {
    const ready = await waitForGatewayReady();
    return ready.ok
      ? { ok: true, spawned: false }
      : { ok: false, error: ready.error };
  }

  try {
    spawnGateway(appRoot);
  } catch (err) {
    return { ok: false, error: err.message };
  }

  const ready = await waitForGatewayReady();
  if (!ready.ok) {
    return { ok: false, error: ready.error, spawned: true };
  }
  return { ok: true, spawned: true, pid: spawnedGatewayPid };
}

function killSpawnedGateway() {
  if (!spawnedGatewayChild || !spawnedGatewayPid) return;
  try {
    process.kill(spawnedGatewayPid, "SIGTERM");
  } catch {
    // already exited
  }
  spawnedGatewayPid = null;
  spawnedGatewayChild = null;
}

function gatewayUnreachableMessage(cause) {
  if (cause?.code === "ECONNREFUSED" || cause?.cause?.code === "ECONNREFUSED") {
    return "无法连接 OpenClaw Gateway（127.0.0.1:18789）。请重启应用或检查 Gateway 日志。";
  }
  if (cause?.name === "AbortError") {
    return "Gateway 请求超时。请检查 OpenClaw 配置与网络。";
  }
  return cause?.message || String(cause);
}

module.exports = {
  GATEWAY_HEALTH_URL,
  GATEWAY_PORT,
  ensureGateway,
  probeGatewayHealth,
  killSpawnedGateway,
  gatewayUnreachableMessage,
  resolveOpenClawBin,
};
