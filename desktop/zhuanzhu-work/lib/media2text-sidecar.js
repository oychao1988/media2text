const fs = require("fs");
const path = require("path");
const { spawn } = require("child_process");
const { spawnSync } = require("child_process");

const { ensureAppConfig } = require("./media2text-config");

const DEFAULT_TIMEOUT_MS = 120_000;
const APP_ROOT = path.join(__dirname, "..");

function repoRoot() {
  return path.resolve(APP_ROOT, "../..");
}

function resolveMedia2textBin(app) {
  if (process.env.MEDIA2TEXT_BIN) {
    return process.env.MEDIA2TEXT_BIN;
  }

  if (app?.isPackaged) {
    const bundled = path.join(
      process.resourcesPath,
      "resources",
      "media2text",
      "bin",
      "media2text",
    );
    if (fs.existsSync(bundled)) return bundled;
  }

  const venvBin = path.join(repoRoot(), ".venv", "bin", "media2text");
  if (fs.existsSync(venvBin)) return venvBin;

  const which = spawnSync("which", ["media2text"], { encoding: "utf8" });
  if (which.status === 0 && which.stdout.trim()) {
    return which.stdout.trim();
  }

  return null;
}

function parseJsonStdout(stdout) {
  const trimmed = String(stdout || "").trim();
  if (!trimmed) return null;
  const lines = trimmed.split("\n").filter(Boolean);
  for (let i = lines.length - 1; i >= 0; i -= 1) {
    try {
      return JSON.parse(lines[i]);
    } catch {
      // keep trying earlier lines
    }
  }
  try {
    return JSON.parse(trimmed);
  } catch {
    return null;
  }
}

function runMedia2text(app, argv, options = {}) {
  const bin = resolveMedia2textBin(app);
  if (!bin) {
    return Promise.resolve({
      ok: false,
      error:
        "未找到 media2text。开发态请在仓库根目录执行 pip install -e \".[dev]\"；发布态见 README（resources/media2text 占位）。",
      exitCode: null,
    });
  }

  const { appConfigPath } = require("./media2text-config");
  const configPath = appConfigPath(app);
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const cwd = options.cwd ?? repoRoot();

  return new Promise((resolve) => {
    const child = spawn(bin, argv, {
      cwd,
      env: {
        ...process.env,
        MEDIA2TEXT_CONFIG: configPath,
      },
      stdio: ["ignore", "pipe", "pipe"],
    });

    let stdout = "";
    let stderr = "";
    const timer = setTimeout(() => {
      child.kill("SIGTERM");
    }, timeoutMs);

    child.stdout.on("data", (chunk) => {
      stdout += chunk.toString();
    });
    child.stderr.on("data", (chunk) => {
      stderr += chunk.toString();
    });

    child.on("error", (err) => {
      clearTimeout(timer);
      resolve({
        ok: false,
        error: err.message,
        exitCode: null,
        stdout,
        stderr,
      });
    });

    child.on("close", (code) => {
      clearTimeout(timer);
      const data = parseJsonStdout(stdout);
      const ok = data != null ? Boolean(data.ok) : code === 0;
      resolve({
        ok,
        exitCode: code,
        data,
        stdout,
        stderr: stderr.trim() || undefined,
        error:
          data?.error ||
          (code !== 0 && !data
            ? stderr.trim() || `media2text 退出码 ${code}`
            : undefined),
        compliance_required: Boolean(data?.compliance_required),
      });
    });
  });
}

async function archiveSearch(app, query, options = {}) {
  const q = String(query || "").trim();
  if (!q) {
    return { ok: false, error: "请输入检索关键词" };
  }
  const argv = ["archive", "search", q, "--json"];
  if (options.creatorId) {
    argv.push("--creator", options.creatorId);
  }
  if (options.limit) {
    argv.push("--limit", String(options.limit));
  }
  return runMedia2text(app, argv, options);
}

async function doctor(app, options = {}) {
  return runMedia2text(app, ["doctor", "--json"], options);
}

async function complianceAccept(app, options = {}) {
  return runMedia2text(app, ["compliance", "accept", "--json"], options);
}

async function complianceStatus(app) {
  const result = await doctor(app, { timeoutMs: 15_000 });
  if (!result.ok && !result.data) {
    return {
      ok: false,
      error: result.error || "无法读取合规状态",
    };
  }
  return {
    ok: true,
    accepted: Boolean(result.data?.compliance_accepted),
    workspace: result.data?.workspace,
    raw: result.data,
  };
}

function listTranscriptRefs(app, options = {}) {
  const limit = Math.min(Number(options.limit) || 40, 100);
  const { workspace } = ensureAppConfig(app);
  const creatorsRoot = path.join(workspace, "creators");
  if (!fs.existsSync(creatorsRoot)) {
    return { ok: true, refs: [] };
  }

  const refs = [];
  const suffixes = [".transcript.md", ".transcript.json"];

  function walk(dir) {
    let entries;
    try {
      entries = fs.readdirSync(dir, { withFileTypes: true });
    } catch {
      return;
    }
    for (const entry of entries) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        walk(full);
        continue;
      }
      if (!entry.isFile()) continue;
      if (!suffixes.some((s) => entry.name.endsWith(s))) continue;
      let mtimeMs = 0;
      try {
        mtimeMs = fs.statSync(full).mtimeMs;
      } catch {
        // skip
      }
      const rel = path.relative(workspace, full);
      refs.push({
        path: rel.split(path.sep).join("/"),
        label: entry.name,
        mtimeMs,
      });
    }
  }

  walk(creatorsRoot);
  refs.sort((a, b) => b.mtimeMs - a.mtimeMs);

  return { ok: true, refs: refs.slice(0, limit) };
}

module.exports = {
  resolveMedia2textBin,
  runMedia2text,
  archiveSearch,
  doctor,
  complianceAccept,
  complianceStatus,
  listTranscriptRefs,
};
