const SESSION_KEY = "agent:main:main";

const messagesEl = document.getElementById("messages");
const inputEl = document.getElementById("composer-input");
const sendBtn = document.getElementById("btn-send");
const statusBanner = document.getElementById("status-banner");

const navItems = document.querySelectorAll(".nav-item");
const viewPanels = {
  chat: document.getElementById("view-chat"),
  archive: document.getElementById("view-archive"),
  doctor: document.getElementById("view-doctor"),
};

const archiveQueryEl = document.getElementById("archive-query");
const archiveSearchBtn = document.getElementById("btn-archive-search");
const archiveStatusEl = document.getElementById("archive-status");
const archiveResultsEl = document.getElementById("archive-results");

const doctorRefreshBtn = document.getElementById("btn-doctor-refresh");
const doctorStatusEl = document.getElementById("doctor-status");
const doctorChecksEl = document.getElementById("doctor-checks");
const doctorMetaEl = document.getElementById("doctor-meta");

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

function switchView(view) {
  navItems.forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.view === view);
  });
  Object.entries(viewPanels).forEach(([name, panel]) => {
    if (!panel) return;
    const active = name === view;
    panel.hidden = !active;
    panel.classList.toggle("active", active);
  });
  if (view === "doctor") {
    refreshDoctor();
  }
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
    card.className = "result-card";
    card.innerHTML = `
      <div class="result-meta">${hit.creator_id || ""} · ${hit.session_type || ""} · ${hit.started_at || hit.session_id || ""}</div>
      <p class="result-excerpt">${escapeHtml(hit.excerpt || "")}</p>
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

navItems.forEach((btn) => {
  btn.addEventListener("click", () => switchView(btn.dataset.view));
});

archiveSearchBtn.addEventListener("click", runArchiveSearch);
archiveQueryEl.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    runArchiveSearch();
  }
});

doctorRefreshBtn.addEventListener("click", refreshDoctor);

async function initMain() {
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
        "未找到 media2text CLI。请在仓库根目录 pip install -e \".[dev]\" 或配置 PATH。",
        "warn",
      );
    }
  }

  appendMessage(
    "assistant",
    "转注 Work 已就绪。Gateway 由应用自动管理；侧栏可打开档案检索与环境检查。",
  );
  inputEl.focus();
}

initMain();
