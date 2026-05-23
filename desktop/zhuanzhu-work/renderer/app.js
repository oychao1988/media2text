const SESSION_KEY = "agent:main:main";

const AGENT_LABELS = {
  default: "默认协调",
  archive: "档案助手",
  wanzhan: "万战寻道",
  nuwa: "女娲蒸馏",
};

let currentAgent = "default";

const messagesEl = document.getElementById("messages");
const inputEl = document.getElementById("composer-input");
const sendBtn = document.getElementById("btn-send");
const statusBanner = document.getElementById("status-banner");
const sessionPill = document.getElementById("session-pill");

const archiveQueryEl = document.getElementById("archive-query");
const archiveSearchBtn = document.getElementById("btn-archive-search");
const archiveStatusEl = document.getElementById("archive-status");
const archiveResultsEl = document.getElementById("archive-results");

const doctorRefreshBtn = document.getElementById("btn-doctor-refresh");
const doctorStatusEl = document.getElementById("doctor-status");
const doctorChecksEl = document.getElementById("doctor-checks");
const doctorMetaEl = document.getElementById("doctor-meta");
const complianceBadgeEl = document.getElementById("compliance-badge");

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
    currentAgent = opts.agent;
  }

  document.querySelectorAll(".page").forEach((page) => {
    page.classList.toggle("active", page.id === `page-${viewId}`);
  });

  highlightNav(viewId);

  if (sessionPill) {
    const label = AGENT_LABELS[currentAgent] || currentAgent;
    sessionPill.textContent = `OpenClaw · ${SESSION_KEY} · ${label}`;
  }

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

async function sendMessage() {
  const message = inputEl.value.trim();
  if (!message) return;

  if (!window.zhuanzhu?.openclaw?.chat) {
    showBanner("preload 桥接未就绪，请重启应用。");
    return;
  }

  hideBanner();
  appendMessage("user", message);
  inputEl.value = "";
  setBusy(true);

  const pending = appendMessage("assistant", "思考中…", "pending");

  try {
    const result = await window.zhuanzhu.openclaw.chat({
      message,
      sessionKey: SESSION_KEY,
    });

    pending.remove();

    if (result.ok && result.content) {
      appendMessage("assistant", result.content);
    } else {
      const errText = result.error || "未知错误";
      showBanner(errText);
      appendMessage("error", errText, "error");
    }
  } catch (err) {
    pending.remove();
    const errText = err?.message || String(err);
    showBanner(errText);
    appendMessage("error", errText, "error");
  } finally {
    setBusy(false);
    inputEl.focus();
  }
}

function renderArchiveResults(hits) {
  archiveResultsEl.innerHTML = "";
  if (!hits?.length) {
    archiveResultsEl.innerHTML = '<p class="empty-hint">无命中结果</p>';
    return;
  }

  hits.forEach((hit) => {
    const card = document.createElement("article");
    card.className = "timeline-item";
    card.innerHTML = `
      <div class="meta">${escapeHtml(hit.creator_id || "")} · ${escapeHtml(hit.session_type || "")} · ${escapeHtml(hit.started_at || hit.session_id || "")}</div>
      <p class="excerpt">${escapeHtml(hit.excerpt || "")}</p>
      <code class="result-path">${escapeHtml(hit.transcript_path || hit.open_path || "")}</code>
    `;
    archiveResultsEl.appendChild(card);
  });
}

function escapeHtml(text) {
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
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
});

archiveSearchBtn.addEventListener("click", runArchiveSearch);
archiveQueryEl.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    runArchiveSearch();
  }
});

doctorRefreshBtn.addEventListener("click", refreshDoctor);

bindNavigation();

async function initMain() {
  showView("chat", { agent: "default", focusInput: false });

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

  appendMessage(
    "assistant",
    "转注 Work 已就绪。侧栏可切换智能体画廊与各能力页；档案检索与环境检查已接 media2text CLI。",
  );
  inputEl.focus();
}

initMain();
