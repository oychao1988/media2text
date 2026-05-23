const LENS_STORAGE_KEY = "zhuanzhu.currentLens";
const LENS_RECENT_KEY = "zhuanzhu.recentLenses";
const ARCHIVE_CONTEXT_LIMIT = 5;

const LENSES = window.ZHUANZHU_LENSES || {};
const LENS_ORDER = window.ZHUANZHU_LENS_ORDER || Object.keys(LENSES);

let currentAgent = loadStoredLens() || "default";
let attachedRefs = [];
let transcriptRefsCache = null;
let lastArchiveHits = [];

const messagesEl = document.getElementById("messages");
const inputEl = document.getElementById("composer-input");
const sendBtn = document.getElementById("btn-send");
const statusBanner = document.getElementById("status-banner");
const sessionPill = document.getElementById("session-pill");
const refChipsEl = document.getElementById("ref-chips");
const atPickerEl = document.getElementById("at-picker");

const archiveQueryEl = document.getElementById("archive-query");
const archiveSearchBtn = document.getElementById("btn-archive-search");
const archiveStatusEl = document.getElementById("archive-status");
const archiveResultsEl = document.getElementById("archive-results");

const doctorRefreshBtn = document.getElementById("btn-doctor-refresh");
const doctorStatusEl = document.getElementById("doctor-status");
const doctorChecksEl = document.getElementById("doctor-checks");
const doctorMetaEl = document.getElementById("doctor-meta");
const complianceBadgeEl = document.getElementById("compliance-badge");
const upgradeBtn = document.getElementById("btn-upgrade");

/** @type {{ status: string, version?: string | null, progress?: { percent?: number } | null, error?: string | null }} */
let updateState = { status: "idle" };

function getLens(agentId = currentAgent) {
  return LENSES[agentId] || LENSES.default;
}

function loadStoredLens() {
  try {
    const stored = localStorage.getItem(LENS_STORAGE_KEY);
    return stored && LENSES[stored] ? stored : null;
  } catch {
    return null;
  }
}

function persistLens(agentId) {
  try {
    localStorage.setItem(LENS_STORAGE_KEY, agentId);
    const recent = loadRecentLenses().filter((id) => id !== agentId);
    recent.unshift(agentId);
    localStorage.setItem(LENS_RECENT_KEY, JSON.stringify(recent.slice(0, LENS_ORDER.length)));
  } catch {
    /* ignore quota / private mode */
  }
}

function loadRecentLenses() {
  try {
    const raw = localStorage.getItem(LENS_RECENT_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed.filter((id) => LENSES[id]) : [];
  } catch {
    return [];
  }
}

function updateSessionPill() {
  if (!sessionPill) return;
  const lens = getLens();
  sessionPill.textContent = `${lens.label} · ${lens.sessionKey}`;
}

function clearChatMessages() {
  if (messagesEl) messagesEl.innerHTML = "";
}

function lensWelcome(agentId) {
  const lens = getLens(agentId);
  const hints = {
    archive: "可输入 /search 关键词 或直接 @ 引用转写路径。",
    wanzhan: "可粘贴转写片段，我会按万战寻道 lens 做节奏与兑现复盘。",
    nuwa: "描述想蒸馏的人名/主题，我会输出 SKILL.md 大纲。",
    default: "聊天支持 SSE 流式；@ 引用转写，/search 注入档案上下文。",
  };
  appendMessage(
    "assistant",
    `${lens.emoji} ${lens.label} 已就绪。${hints[lens.id] || hints.default}`,
  );
}

function applyLens(agentId, opts = {}) {
  const { resetChat } = opts;
  if (!LENSES[agentId]) agentId = "default";
  const changed = currentAgent !== agentId;
  currentAgent = agentId;
  persistLens(agentId);
  updateSessionPill();
  highlightNav("chat");
  const shouldReset = resetChat === true || (resetChat !== false && changed);
  if (shouldReset) {
    clearChatMessages();
    lensWelcome(agentId);
  }
}

function setBusy(busy) {
  inputEl.disabled = busy;
  sendBtn.disabled = busy;
}

function showBanner(text, kind = "error") {
  statusBanner.textContent = text;
  statusBanner.className = `status-banner visible ${kind}`;
}

function hideBanner() {
  statusBanner.className = "status-banner";
  statusBanner.textContent = "";
}

function appendMessage(role, text, extraClass = "") {
  const row = document.createElement("div");
  row.className = `msg ${role}${extraClass ? ` ${extraClass}` : ""}`;

  const avatar = document.createElement("div");
  avatar.className = "msg-av";
  avatar.textContent = role === "user" ? "O" : "🤖";

  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = text;

  row.append(avatar, bubble);
  messagesEl.appendChild(row);
  messagesEl.parentElement.scrollTop = messagesEl.parentElement.scrollHeight;
  return row;
}

function appendStreamingAssistant() {
  const row = document.createElement("div");
  row.className = "msg assistant streaming";

  const avatar = document.createElement("div");
  avatar.className = "msg-av";
  avatar.textContent = "🤖";

  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = "";

  row.append(avatar, bubble);
  messagesEl.appendChild(row);
  messagesEl.parentElement.scrollTop = messagesEl.parentElement.scrollHeight;
  return { row, bubble };
}

function highlightNav(viewId) {
  document.querySelectorAll(".nav-item[data-view]").forEach((el) => {
    const isSub = el.classList.contains("sub");
    const matches = el.dataset.view === viewId;
    if (isSub) {
      el.classList.toggle("active", matches);
    } else if (el.dataset.view === "agents") {
      el.classList.toggle("active", viewId === "agents");
    }
  });

  document.querySelectorAll('.nav-item[data-view="chat"][data-agent]').forEach((el) => {
    el.classList.toggle("active", viewId === "chat" && el.dataset.agent === currentAgent);
  });
}

function showView(viewId, opts = {}) {
  if (opts.agent) {
    applyLens(opts.agent, { resetChat: opts.resetChat });
  } else if (opts.newChat) {
    applyLens(currentAgent, { resetChat: true });
  }

  document.querySelectorAll(".page").forEach((page) => {
    page.classList.toggle("active", page.id === `page-${viewId}`);
  });

  highlightNav(viewId);
  updateSessionPill();

  if (viewId === "doctor") {
    refreshDoctor();
  }

  if (viewId === "chat" && opts.focusInput !== false) {
    inputEl?.focus();
  }
}

function bindNavigation() {
  document.body.addEventListener("click", (event) => {
    const trigger = event.target.closest("[data-view]");
    if (!trigger || trigger.disabled) return;

    const viewId = trigger.dataset.view;
    if (!viewId) return;

    const opts = {};
    if (trigger.dataset.agent) {
      opts.agent = trigger.dataset.agent;
    }
    if (trigger.dataset.newChat === "1") {
      opts.newChat = true;
    }

    showView(viewId, opts);
  });
}

function escapeHtml(text) {
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function renderRefChips() {
  if (!refChipsEl) return;
  refChipsEl.innerHTML = "";
  if (!attachedRefs.length) {
    refChipsEl.hidden = true;
    return;
  }
  refChipsEl.hidden = false;
  attachedRefs.forEach((ref, index) => {
    const chip = document.createElement("span");
    chip.className = "ref-chip";
    chip.innerHTML = `@${escapeHtml(ref.label || ref.path)} <button type="button" aria-label="移除">×</button>`;
    chip.querySelector("button").addEventListener("click", () => {
      attachedRefs.splice(index, 1);
      renderRefChips();
    });
    refChipsEl.appendChild(chip);
  });
}

function addAttachedRef(ref) {
  if (attachedRefs.some((r) => r.path === ref.path)) return;
  attachedRefs.push(ref);
  renderRefChips();
}

function buildArchiveContextBlock(keyword, hits) {
  const lines = hits.slice(0, ARCHIVE_CONTEXT_LIMIT).map((hit, i) => {
    const meta = [hit.creator_id, hit.session_type, hit.started_at || hit.session_id]
      .filter(Boolean)
      .join(" · ");
    const excerpt = (hit.excerpt || "").replace(/\s+/g, " ").trim();
    return `${i + 1}. (${meta}) ${excerpt}`;
  });
  return `[archive context keyword="${keyword}"]\n${lines.join("\n")}\n[/archive context]`;
}

function formatOutboundMessage(rawText) {
  const parts = [];
  const prefix = getLens().messagePrefix;
  if (prefix) parts.push(prefix);
  if (attachedRefs.length) {
    parts.push(attachedRefs.map((r) => `@file:${r.path}`).join("\n"));
  }
  const body = String(rawText || "").trim();
  if (body) parts.push(body);
  return parts.join("\n\n");
}

function parseSearchCommand(text) {
  const trimmed = text.trim();
  if (!trimmed.toLowerCase().startsWith("/search")) return null;
  const rest = trimmed.slice(7).trim();
  const spaceIdx = rest.indexOf(" ");
  if (spaceIdx === -1) {
    return { keyword: rest, question: "" };
  }
  return {
    keyword: rest.slice(0, spaceIdx).trim(),
    question: rest.slice(spaceIdx + 1).trim(),
  };
}

async function ensureTranscriptRefs() {
  if (transcriptRefsCache) return transcriptRefsCache;
  if (!window.zhuanzhu?.media2text?.listTranscriptRefs) {
    transcriptRefsCache = [];
    return transcriptRefsCache;
  }
  const result = await window.zhuanzhu.media2text.listTranscriptRefs({ limit: 40 });
  transcriptRefsCache = result.ok ? result.refs || [] : [];
  return transcriptRefsCache;
}

function hideAtPicker() {
  if (atPickerEl) atPickerEl.hidden = true;
}

function showAtPicker(filter = "") {
  if (!atPickerEl) return;
  ensureTranscriptRefs().then((refs) => {
    const q = filter.toLowerCase();
    const matches = refs.filter(
      (r) =>
        !q ||
        r.path.toLowerCase().includes(q) ||
        (r.label || "").toLowerCase().includes(q),
    );
    atPickerEl.innerHTML = "";
    if (!matches.length) {
      atPickerEl.hidden = true;
      return;
    }
    matches.slice(0, 8).forEach((ref) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "at-picker-item";
      btn.textContent = ref.path;
      btn.addEventListener("click", () => {
        addAttachedRef(ref);
        const value = inputEl.value;
        const atIdx = value.lastIndexOf("@");
        if (atIdx >= 0) {
          inputEl.value = `${value.slice(0, atIdx).trimEnd()} `;
        }
        hideAtPicker();
        inputEl.focus();
      });
      atPickerEl.appendChild(btn);
    });
    atPickerEl.hidden = false;
  });
}

function handleComposerInput() {
  const value = inputEl.value;
  const atIdx = value.lastIndexOf("@");
  if (atIdx < 0) {
    hideAtPicker();
    return;
  }
  const tail = value.slice(atIdx + 1);
  if (/\s/.test(tail)) {
    hideAtPicker();
    return;
  }
  showAtPicker(tail);
}

async function resolveSearchContext(parsed) {
  if (!window.zhuanzhu?.media2text?.archiveSearch) {
    return { ok: false, error: "media2text 桥接未就绪" };
  }
  const result = await window.zhuanzhu.media2text.archiveSearch(parsed.keyword);
  const data = result.data || {};
  if (data.compliance_required) {
    return {
      ok: false,
      error: data.error || "请先接受免责声明（compliance accept）",
      compliance_required: true,
    };
  }
  if (!result.ok) {
    return { ok: false, error: result.error || data.error || "档案检索失败" };
  }
  const hits = data.hits || [];
  if (!hits.length) {
    return { ok: false, error: `未找到「${parsed.keyword}」相关命中` };
  }
  const block = buildArchiveContextBlock(parsed.keyword, hits);
  const question = parsed.question || `请基于以上档案上下文，总结「${parsed.keyword}」相关要点。`;
  return { ok: true, message: `${block}\n\n${question}`, hits };
}

async function sendMessage() {
  const rawInput = inputEl.value.trim();
  if (!rawInput && !attachedRefs.length) return;

  if (!window.zhuanzhu?.openclaw?.chatStream && !window.zhuanzhu?.openclaw?.chat) {
    showBanner("preload 桥接未就绪，请重启应用。");
    return;
  }

  hideBanner();
  hideAtPicker();

  let displayText = rawInput;
  let outbound = formatOutboundMessage(rawInput);

  const searchCmd = parseSearchCommand(rawInput);
  if (searchCmd?.keyword) {
    setBusy(true);
    const ctx = await resolveSearchContext(searchCmd);
    if (!ctx.ok) {
      showBanner(ctx.error, ctx.compliance_required ? "warn" : "error");
      setBusy(false);
      return;
    }
    outbound = ctx.message;
    displayText = rawInput;
    lastArchiveHits = ctx.hits || [];
  }

  if (!outbound.trim()) {
    return;
  }

  appendMessage("user", displayText);
  inputEl.value = "";
  attachedRefs = [];
  renderRefChips();
  setBusy(true);

  const { row, bubble } = appendStreamingAssistant();
  let streamed = "";

  const lens = getLens();

  try {
    const chatStream = window.zhuanzhu.openclaw.chatStream;
    if (chatStream) {
      const result = await chatStream({
        message: outbound,
        sessionKey: lens.sessionKey,
        onDelta(delta) {
          streamed += delta;
          bubble.textContent = streamed;
          messagesEl.parentElement.scrollTop = messagesEl.parentElement.scrollHeight;
        },
      });
      row.classList.remove("streaming");
      if (result.fallback) {
        bubble.textContent = result.content || streamed;
      }
      if (!streamed && result.content) {
        bubble.textContent = result.content;
      }
    } else {
      const result = await window.zhuanzhu.openclaw.chat({
        message: outbound,
        sessionKey: lens.sessionKey,
      });
      row.remove();
      if (result.ok && result.content) {
        appendMessage("assistant", result.content);
      } else {
        const errText = result.error || "未知错误";
        showBanner(errText);
        appendMessage("error", errText, "error");
      }
    }
  } catch (err) {
    row.remove();
    const errText = err?.message || String(err);
    showBanner(errText);
    appendMessage("error", errText, "error");
  } finally {
    setBusy(false);
    inputEl.focus();
  }
}

function injectArchiveToChat(hits, keyword) {
  if (!hits?.length) return;
  lastArchiveHits = hits;
  const block = buildArchiveContextBlock(keyword, hits);
  showView("chat", { agent: "archive", resetChat: false });
  inputEl.value = `${block}\n\n请基于以上档案上下文回答：`;
  inputEl.focus();
}

function renderArchiveResults(hits) {
  archiveResultsEl.innerHTML = "";
  lastArchiveHits = hits || [];
  if (!hits?.length) {
    archiveResultsEl.innerHTML = '<p class="empty-hint">无命中结果</p>';
    return;
  }

  const keyword = archiveQueryEl.value.trim();

  hits.forEach((hit) => {
    const card = document.createElement("article");
    card.className = "timeline-item";
    card.innerHTML = `
      <div class="meta">${escapeHtml(hit.creator_id || "")} · ${escapeHtml(hit.session_type || "")} · ${escapeHtml(hit.started_at || hit.session_id || "")}</div>
      <p class="excerpt">${escapeHtml(hit.excerpt || "")}</p>
      <code class="result-path">${escapeHtml(hit.transcript_path || hit.open_path || "")}</code>
      <div class="result-actions">
        <button type="button" class="btn-secondary btn-send-chat">发送到聊天</button>
      </div>
    `;
    card.querySelector(".btn-send-chat").addEventListener("click", () => {
      injectArchiveToChat(hits, keyword);
    });
    archiveResultsEl.appendChild(card);
  });
}

async function runArchiveSearch() {
  const query = archiveQueryEl.value.trim();
  if (!query) {
    archiveStatusEl.textContent = "请输入关键词";
    archiveStatusEl.className = "panel-status warn";
    return;
  }

  if (!window.zhuanzhu?.media2text?.archiveSearch) {
    archiveStatusEl.textContent = "media2text 桥接未就绪";
    archiveStatusEl.className = "panel-status error";
    return;
  }

  archiveSearchBtn.disabled = true;
  archiveStatusEl.textContent = "检索中…";
  archiveStatusEl.className = "panel-status";

  try {
    const result = await window.zhuanzhu.media2text.archiveSearch(query);
    const data = result.data || {};

    if (data.compliance_required) {
      archiveStatusEl.textContent =
        data.error ||
        "请先接受免责声明：在首次向导中勾选，或运行 media2text compliance accept";
      archiveStatusEl.className = "panel-status warn";
      archiveResultsEl.innerHTML = "";
      return;
    }

    if (!result.ok) {
      archiveStatusEl.textContent = result.error || data.error || "检索失败";
      archiveStatusEl.className = "panel-status error";
      archiveResultsEl.innerHTML = "";
      return;
    }

    const hits = data.hits || [];
    archiveStatusEl.textContent = `共 ${hits.length} 条命中`;
    archiveStatusEl.className = "panel-status ok";
    renderArchiveResults(hits);
  } catch (err) {
    archiveStatusEl.textContent = err?.message || String(err);
    archiveStatusEl.className = "panel-status error";
  } finally {
    archiveSearchBtn.disabled = false;
  }
}

function renderDoctor(data) {
  doctorChecksEl.innerHTML = "";
  if (!data) {
    doctorStatusEl.textContent = "无数据";
    doctorStatusEl.className = "panel-status error";
    return;
  }

  doctorStatusEl.textContent = data.ok ? "环境就绪" : "存在未通过项";
  doctorStatusEl.className = `panel-status ${data.ok ? "ok" : "warn"}`;

  (data.checks || []).forEach((check) => {
    const li = document.createElement("li");
    li.className = check.ok ? "check-ok" : "check-fail";
    li.textContent = `${check.ok ? "✓" : "✗"} ${check.name}`;
    doctorChecksEl.appendChild(li);
  });

  const parts = [];
  parts.push(`合规：${data.compliance_accepted ? "已接受" : "未接受"}`);
  if (data.index_stale != null) {
    parts.push(`索引：${data.index_stale ? "需重建 (archive index)" : "正常"}`);
  }
  if (data.monitor_lock_pid) {
    parts.push(`monitor watch PID：${data.monitor_lock_pid}`);
  }
  doctorMetaEl.textContent = parts.join(" · ");

  if (complianceBadgeEl) {
    complianceBadgeEl.textContent = data.compliance_accepted ? "已接受免责声明" : "未接受免责声明";
    complianceBadgeEl.className = data.compliance_accepted ? "badge ok" : "badge warn";
  }
}

async function refreshDoctor() {
  if (!window.zhuanzhu?.media2text?.doctor) {
    doctorStatusEl.textContent = "media2text 桥接未就绪";
    doctorStatusEl.className = "panel-status error";
    return;
  }

  doctorRefreshBtn.disabled = true;
  doctorStatusEl.textContent = "检查中…";
  doctorStatusEl.className = "panel-status";

  try {
    const result = await window.zhuanzhu.media2text.doctor();
    if (!result.data && !result.ok) {
      doctorStatusEl.textContent = result.error || "doctor 失败";
      doctorStatusEl.className = "panel-status error";
      doctorChecksEl.innerHTML = "";
      doctorMetaEl.textContent = result.stderr || "";
      return;
    }
    renderDoctor(result.data);
  } catch (err) {
    doctorStatusEl.textContent = err?.message || String(err);
    doctorStatusEl.className = "panel-status error";
  } finally {
    doctorRefreshBtn.disabled = false;
  }
}

sendBtn.addEventListener("click", sendMessage);

inputEl.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    sendMessage();
  }
  if (event.key === "Escape") {
    hideAtPicker();
  }
});

inputEl.addEventListener("input", handleComposerInput);

archiveSearchBtn.addEventListener("click", runArchiveSearch);
archiveQueryEl.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    runArchiveSearch();
  }
});

doctorRefreshBtn.addEventListener("click", refreshDoctor);

function renderUpgradeButton() {
  if (!upgradeBtn) return;
  const { status, version, progress, error, currentVersion } = updateState;
  switch (status) {
    case "checking":
      upgradeBtn.textContent = "检查中…";
      upgradeBtn.disabled = true;
      break;
    case "available":
      upgradeBtn.textContent = version ? `下载 ${version}` : "下载更新";
      upgradeBtn.disabled = false;
      upgradeBtn.title = `发现新版本 ${version}`;
      break;
    case "downloading":
      upgradeBtn.textContent =
        progress?.percent != null ? `下载 ${Math.round(progress.percent)}%` : "下载中…";
      upgradeBtn.disabled = true;
      break;
    case "ready":
      upgradeBtn.textContent = "重启安装";
      upgradeBtn.disabled = false;
      upgradeBtn.title = version ? `已下载 ${version}，点击重启安装` : "点击重启安装";
      break;
    case "uptodate":
      upgradeBtn.textContent = "已是最新";
      upgradeBtn.disabled = true;
      upgradeBtn.title = currentVersion ? `当前 ${currentVersion}` : "已是最新";
      break;
    case "error":
      upgradeBtn.textContent = "重试";
      upgradeBtn.disabled = false;
      upgradeBtn.title = error || "检查更新失败";
      break;
    case "dev":
      upgradeBtn.textContent = "升级";
      upgradeBtn.disabled = true;
      upgradeBtn.title = "仅打包版可检查更新";
      break;
    default:
      upgradeBtn.textContent = "升级";
      upgradeBtn.disabled = !updateState.packaged;
      upgradeBtn.title = currentVersion ? `当前 ${currentVersion}` : "检查更新";
  }
}

async function bindAutoUpdater() {
  if (!upgradeBtn || !window.zhuanzhu?.app) return;

  window.zhuanzhu.app.onUpdateStatus((payload) => {
    updateState = payload || { status: "idle" };
    renderUpgradeButton();
  });

  try {
    const [version, packaged, state] = await Promise.all([
      window.zhuanzhu.app.getVersion(),
      window.zhuanzhu.app.isPackaged(),
      window.zhuanzhu.app.getUpdateState(),
    ]);
    updateState = { ...state, currentVersion: version, packaged };
    renderUpgradeButton();
    if (packaged) {
      await window.zhuanzhu.app.checkForUpdates();
    }
  } catch {
    renderUpgradeButton();
  }

  upgradeBtn.addEventListener("click", async () => {
    if (!window.zhuanzhu?.app) return;
    try {
      if (updateState.status === "ready") {
        await window.zhuanzhu.app.quitAndInstall();
        return;
      }
      if (updateState.status === "available") {
        upgradeBtn.disabled = true;
        await window.zhuanzhu.app.downloadUpdate();
        return;
      }
      await window.zhuanzhu.app.checkForUpdates();
    } catch (err) {
      showBanner(err?.message || String(err), "warn");
    }
  });
}

bindNavigation();

async function initMain() {
  showView("chat", { agent: currentAgent, resetChat: true, focusInput: false });

  if (window.zhuanzhu?.app?.getBootstrap) {
    const state = await window.zhuanzhu.app.getBootstrap();
    if (!state.setup?.complete) {
      showBanner(
        `OpenClaw 配置未完成，请在 ${state.configPath} 中设置 gateway.auth.token 与模型 API Key。`,
        "warn",
      );
    }
    if (!state.media2textBin) {
      showBanner(
        '未找到 media2text CLI。请在仓库根目录 pip install -e ".[dev]" 或配置 PATH。',
        "warn",
      );
    }
  }

  inputEl.focus();
  bindAutoUpdater();
}

initMain();
