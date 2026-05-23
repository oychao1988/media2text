const fs = require("fs");
const { openClawConfigPath } = require("./paths");

function readOpenClawConfig() {
  const configPath = openClawConfigPath();
  if (!fs.existsSync(configPath)) {
    return { ok: false, configPath, reason: "missing_file" };
  }
  try {
    const config = JSON.parse(fs.readFileSync(configPath, "utf8"));
    return { ok: true, configPath, config };
  } catch {
    return { ok: false, configPath, reason: "invalid_json" };
  }
}

function providerHasCredential(provider) {
  if (!provider || typeof provider !== "object") return false;
  return Boolean(
    provider.apiKey ||
      provider.api_key ||
      provider.key ||
      provider.token ||
      provider.accessToken,
  );
}

function hasProviderCredentials(config) {
  const buckets = [
    config?.providers,
    config?.models?.providers,
    config?.llm?.providers,
  ].filter(Boolean);

  for (const providers of buckets) {
    if (typeof providers !== "object") continue;
    if (Object.values(providers).some(providerHasCredential)) {
      return true;
    }
  }
  return false;
}

function assessOpenClawSetup() {
  const parsed = readOpenClawConfig();
  if (!parsed.ok) {
    return {
      complete: false,
      configPath: parsed.configPath,
      issues: [parsed.reason],
      missingToken: true,
      missingProvider: true,
    };
  }

  const { config, configPath } = parsed;
  const token = config?.gateway?.auth?.token;
  const missingToken = !token;
  const missingProvider = !hasProviderCredentials(config);
  const issues = [];
  if (missingToken) issues.push("missing_token");
  if (missingProvider) issues.push("missing_provider");

  return {
    complete: issues.length === 0,
    configPath,
    issues,
    missingToken,
    missingProvider,
    hasToken: Boolean(token),
  };
}

function readGatewayToken() {
  if (process.env.OPENCLAW_GATEWAY_TOKEN) {
    return process.env.OPENCLAW_GATEWAY_TOKEN;
  }
  const parsed = readOpenClawConfig();
  if (!parsed.ok) {
    throw new Error(
      `未找到 OpenClaw 配置：${parsed.configPath}。请完成首次向导或安装 OpenClaw。`,
    );
  }
  const token = parsed.config?.gateway?.auth?.token;
  if (!token) {
    throw new Error(
      `openclaw.json 中缺少 gateway.auth.token（${parsed.configPath}）`,
    );
  }
  return token;
}

module.exports = {
  assessOpenClawSetup,
  readGatewayToken,
  readOpenClawConfig,
};
