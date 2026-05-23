const fs = require("fs");
const path = require("path");
const { workspacePath } = require("./paths");

function appConfigPath(app) {
  if (process.env.MEDIA2TEXT_CONFIG) {
    return path.resolve(process.env.MEDIA2TEXT_CONFIG);
  }
  return path.join(app.getPath("userData"), "config.yaml");
}

function ensureAppConfig(app) {
  const ws = workspacePath(app);
  fs.mkdirSync(ws, { recursive: true });
  for (const sub of ["sessions", "creators"]) {
    fs.mkdirSync(path.join(ws, sub), { recursive: true });
  }

  const configPath = appConfigPath(app);
  if (!fs.existsSync(configPath)) {
    const yaml = `workspace: ${JSON.stringify(ws)}\n`;
    fs.mkdirSync(path.dirname(configPath), { recursive: true });
    fs.writeFileSync(configPath, yaml, "utf8");
  }

  return { configPath, workspace: ws };
}

module.exports = {
  appConfigPath,
  ensureAppConfig,
};
