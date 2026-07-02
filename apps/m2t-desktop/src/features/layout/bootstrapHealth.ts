export type BootstrapPhase = 'loading' | 'repairing' | 'error' | 'ready';

export type DoctorCheck = {
  name: string;
  ok: boolean;
  hint?: string;
  auto_repairable?: boolean;
};

export type HealthResponse = {
  ok?: boolean;
  doctor_ok?: boolean;
  checks?: DoctorCheck[];
};

export type RepairAction = {
  name: string;
  action?: string;
  ok: boolean;
  message?: string;
};

export type RepairResponse = HealthResponse & {
  repair_ok?: boolean;
  actions?: RepairAction[];
};

const BOOTSTRAP_REQUIRED = new Set(['ffmpeg', 'playwright_browser']);

export function needsEnvironmentRepair(checks: DoctorCheck[] | undefined): boolean {
  if (!checks?.length) return false;
  const byName = new Map(checks.map((c) => [c.name, c]));
  return [...BOOTSTRAP_REQUIRED].some((name) => !byName.get(name)?.ok);
}

function formatRepairFailure(checks: DoctorCheck[] | undefined, actions: RepairAction[] | undefined): string {
  const failedActions = (actions ?? []).filter((a) => !a.ok);
  const lines: string[] = [];
  if (failedActions.length) {
    for (const a of failedActions) {
      lines.push(`${a.name}: ${a.message ?? '修复失败'}`);
    }
  }
  const checksByName = new Map((checks ?? []).map((c) => [c.name, c]));
  for (const name of BOOTSTRAP_REQUIRED) {
    const c = checksByName.get(name);
    if (c && !c.ok) {
      const hint = c.hint ? `（${c.hint}）` : '';
      lines.push(`${name} 仍不可用${hint}`);
    }
  }
  return lines.length ? lines.join('\n') : '环境依赖未就绪';
}

function appendInstallHint(message: string): string {
  const lower = message.toLowerCase();
  const fromDmg =
    lower.includes('read-only') ||
    lower.includes('不可写') ||
    lower.includes('/volumes/');
  if (!fromDmg) return message;
  return `${message}\n\n提示：请勿从 DMG 卷直接运行。将「灵犀」拖到「应用程序」后打开；或删除 ~/Library/Application Support/dev.media2text.desktop/runtime/ 后重试以重新同步运行环境。`;
}

export async function pollApiHealth(
  baseUrl: string,
  options?: { fetchFn?: typeof fetch; maxAttempts?: number; intervalMs?: number },
): Promise<void> {
  const fetchFn = options?.fetchFn ?? fetch;
  const maxAttempts = options?.maxAttempts ?? 40;
  const intervalMs = options?.intervalMs ?? 250;
  const healthUrl = `${baseUrl.replace(/\/$/, '')}/api/health`;
  let lastError = '服务未就绪';

  for (let i = 0; i < maxAttempts; i += 1) {
    try {
      const res = await fetchFn(healthUrl, { method: 'GET' });
      if (res.ok) return;
      lastError = `健康检查 HTTP ${res.status}`;
    } catch (err) {
      const raw = err instanceof Error ? err.message : String(err);
      lastError =
        raw === 'Load failed' || raw === 'Failed to fetch'
          ? '无法连接本地 API（若为桌面窗口，请确认 sidecar 已启动；开发模式需 API 开启 CORS）'
          : raw;
    }
    await new Promise((r) => setTimeout(r, intervalMs));
  }

  throw new Error(lastError);
}

export async function ensureEnvironmentReady(
  baseUrl: string,
  options?: {
    fetchFn?: typeof fetch;
    onStatus?: (message: string) => void;
  },
): Promise<void> {
  const fetchFn = options?.fetchFn ?? fetch;
  const prefix = baseUrl.replace(/\/$/, '');

  options?.onStatus?.('正在检查运行环境…');
  const healthRes = await fetchFn(`${prefix}/api/health`, { method: 'GET' });
  if (!healthRes.ok) {
    throw new Error(`环境检查 HTTP ${healthRes.status}`);
  }
  const health = (await healthRes.json()) as HealthResponse;
  if (!needsEnvironmentRepair(health.checks)) return;

  options?.onStatus?.('正在安装缺失依赖（Chromium 首次下载可能需数分钟）…');
  const repairRes = await fetchFn(`${prefix}/api/doctor/repair`, { method: 'POST' });
  if (!repairRes.ok) {
    throw new Error(`环境修复 HTTP ${repairRes.status}`);
  }
  const repair = (await repairRes.json()) as RepairResponse;
  if (repair.repair_ok) return;

  throw new Error(appendInstallHint(formatRepairFailure(repair.checks, repair.actions)));
}

export async function runBootstrap(
  baseUrl: string,
  options?: {
    fetchFn?: typeof fetch;
    maxAttempts?: number;
    intervalMs?: number;
    onStatus?: (message: string) => void;
  },
): Promise<void> {
  await pollApiHealth(baseUrl, options);
  await ensureEnvironmentReady(baseUrl, options);
}
