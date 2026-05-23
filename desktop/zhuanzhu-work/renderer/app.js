const SESSION_KEY = "agent:main:main";

const messagesEl = document.getElementById("messages");
const inputEl = document.getElementById("composer-input");
const sendBtn = document.getElementById("btn-send");
const statusBanner = document.getElementById("status-banner");

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

sendBtn.addEventListener("click", sendMessage);

inputEl.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    sendMessage();
  }
});

appendMessage(
  "assistant",
  "转注 Work 开发壳已就绪。请确保 OpenClaw Gateway 在 127.0.0.1:18789 运行，然后发送一条消息测试联调。",
);
inputEl.focus();
