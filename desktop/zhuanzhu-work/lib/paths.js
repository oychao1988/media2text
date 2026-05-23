const fs = require("fs");
const os = require("os");
const path = require("path");

const COMPLIANCE_VERSION = "2026-05-22";
const COMPLIANCE_FILENAME = ".compliance-accepted";

function openClawConfigPath() {
  return (
    process.env.OPENCLAW_CONFIG_PATH ||
    path.join(os.homedir(), ".openclaw", "openclaw.json")
  );
}

function openClawConfigDir() {
  return path.dirname(openClawConfigPath());
}

/** media2text workspace: ~/Library/Application Support/转注Work/data (override ZHUANZU_WORKSPACE). */
function workspacePath(app) {
  if (process.env.ZHUANZU_WORKSPACE) {
    return path.resolve(process.env.ZHUANZU_WORKSPACE);
  }
  return path.join(app.getPath("userData"), "data");
}

function compliancePath(app) {
  return path.join(workspacePath(app), COMPLIANCE_FILENAME);
}

function isComplianceAccepted(app) {
  const filePath = compliancePath(app);
  if (!fs.existsSync(filePath)) return false;
  try {
    const payload = JSON.parse(fs.readFileSync(filePath, "utf8"));
    return (
      Boolean(payload.accepted_at) && payload.version === COMPLIANCE_VERSION
    );
  } catch {
    return false;
  }
}

function acceptCompliance(app) {
  const ws = workspacePath(app);
  fs.mkdirSync(ws, { recursive: true });
  const record = {
    accepted_at: new Date().toISOString(),
    version: COMPLIANCE_VERSION,
  };
  fs.writeFileSync(
    path.join(ws, COMPLIANCE_FILENAME),
    `${JSON.stringify(record, null, 2)}\n`,
    "utf8",
  );
  return record;
}

function gatewayLogPath() {
  if (process.platform === "darwin") {
    return path.join(
      os.homedir(),
      "Library",
      "Logs",
      "转注Work",
      "gateway.log",
    );
  }
  return path.join(os.homedir(), ".zhuanzhu-work", "gateway.log");
}

module.exports = {
  COMPLIANCE_VERSION,
  openClawConfigPath,
  openClawConfigDir,
  workspacePath,
  compliancePath,
  isComplianceAccepted,
  acceptCompliance,
  gatewayLogPath,
};
