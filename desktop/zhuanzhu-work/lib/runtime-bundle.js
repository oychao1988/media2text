const { spawnSync } = require("child_process");
const fs = require("fs");
const path = require("path");

const APP_ROOT = path.join(__dirname, "..");
const MIN_FREE_BYTES = 600 * 1024 * 1024;

function bundledResourcesRoot(app) {
  if (app?.isPackaged) {
    return path.join(process.resourcesPath, "resources");
  }
  return path.join(APP_ROOT, "resources");
}

function archivePaths(resourcesRoot) {
  return {
    tar: path.join(resourcesRoot, "runtime-bundle.tar.gz"),
    version: path.join(resourcesRoot, "runtime-bundle.version"),
  };
}

function useArchiveLayout(app, resourcesRoot) {
  const mode = process.env.ZHUANZHU_RUNTIME_MODE || "";
  if (mode === "expanded") return false;
  if (mode === "archive") return true;

  const { tar, version } = archivePaths(resourcesRoot);
  if (!fs.existsSync(tar) || !fs.existsSync(version)) {
    return false;
  }
  if (app?.isPackaged) return true;

  const expandedNode = path.join(resourcesRoot, "node", "bin", "node");
  return !fs.existsSync(expandedNode);
}

function readBundleHash(resourcesRoot) {
  const { version } = archivePaths(resourcesRoot);
  try {
    return fs.readFileSync(version, "utf8").trim();
  } catch {
    return null;
  }
}

function runtimeExtractDir(app, hash) {
  return path.join(app.getPath("userData"), "runtime", hash);
}

function runtimeReady(dir) {
  const node = path.join(dir, "node", "bin", "node");
  const openclaw = path.join(dir, "openclaw", "node_modules", ".bin", "openclaw");
  return fs.existsSync(node) && fs.existsSync(openclaw);
}

async function freeBytesForPath(dirPath) {
  try {
    const stats = await fs.promises.statfs(dirPath);
    return (stats.bavail ?? stats.bfree) * stats.bsize;
  } catch {
    return Number.MAX_SAFE_INTEGER;
  }
}

function extractTar(tarPath, destDir) {
  fs.mkdirSync(destDir, { recursive: true });
  const result = spawnSync("tar", ["-xzf", tarPath, "-C", destDir], {
    encoding: "utf8",
  });
  if (result.status !== 0) {
    const detail = (result.stderr || result.stdout || "").trim();
    throw new Error(
      detail
        ? `解压运行环境失败：${detail}`
        : "解压运行环境失败（tar 退出码非 0）",
    );
  }
}

/**
 * @param {import('electron').App} app
 * @param {(payload: { message: string; phase?: string }) => void} [onProgress]
 */
async function ensureExtracted(app, onProgress) {
  const resourcesRoot = bundledResourcesRoot(app);
  if (!useArchiveLayout(app, resourcesRoot)) {
    return resourcesRoot;
  }

  const hash = readBundleHash(resourcesRoot);
  if (!hash) {
    throw new Error("缺少 runtime-bundle.version，请重新执行 npm run prepare-bundle。");
  }

  const { tar } = archivePaths(resourcesRoot);
  if (!fs.existsSync(tar)) {
    throw new Error("缺少 runtime-bundle.tar.gz，请重新执行 npm run prepare-bundle。");
  }

  const dest = runtimeExtractDir(app, hash);
  if (runtimeReady(dest)) {
    onProgress?.({ phase: "runtime", message: "运行环境已就绪" });
    return dest;
  }

  onProgress?.({
    phase: "runtime",
    message: "正在解压运行环境（首次约 1 分钟）…",
  });

  const userData = app.getPath("userData");
  fs.mkdirSync(userData, { recursive: true });
  const free = await freeBytesForPath(userData);
  if (free < MIN_FREE_BYTES) {
    const needMb = Math.round(MIN_FREE_BYTES / (1024 * 1024));
    const freeMb = Math.round(free / (1024 * 1024));
    throw new Error(
      `磁盘空间不足：需要至少 ${needMb} MB 可用空间解压运行环境（当前约 ${freeMb} MB）。请清理磁盘后重试。`,
    );
  }

  const parent = path.dirname(dest);
  fs.mkdirSync(parent, { recursive: true });
  if (fs.existsSync(dest)) {
    fs.rmSync(dest, { recursive: true, force: true });
  }
  fs.mkdirSync(dest, { recursive: true });

  extractTar(tar, dest);

  if (!runtimeReady(dest)) {
    throw new Error("运行环境解压不完整，请删除应用数据目录后重试。");
  }

  onProgress?.({ phase: "runtime", message: "运行环境解压完成" });
  return dest;
}

/**
 * @param {import('electron').App} app
 */
function resolveRuntimeRoot(app) {
  const resourcesRoot = bundledResourcesRoot(app);
  if (!useArchiveLayout(app, resourcesRoot)) {
    return resourcesRoot;
  }
  const hash = readBundleHash(resourcesRoot);
  if (!hash) return resourcesRoot;
  const dest = runtimeExtractDir(app, hash);
  if (runtimeReady(dest)) return dest;
  return resourcesRoot;
}

module.exports = {
  APP_ROOT,
  MIN_FREE_BYTES,
  bundledResourcesRoot,
  useArchiveLayout,
  readBundleHash,
  runtimeExtractDir,
  ensureExtracted,
  resolveRuntimeRoot,
};
