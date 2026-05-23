const messageEl = document.getElementById("splash-message");
const errorEl = document.getElementById("splash-error");
const spinnerEl = document.getElementById("splash-spinner");

function showError(text) {
  messageEl.textContent = "启动失败";
  errorEl.hidden = false;
  errorEl.textContent = text;
  spinnerEl.hidden = true;
}

if (window.zhuanzhu?.app?.onBootstrapStatus) {
  window.zhuanzhu.app.onBootstrapStatus((payload) => {
    if (payload?.message) {
      messageEl.textContent = payload.message;
    }
    if (payload?.phase === "error") {
      showError(payload.message || "未知错误");
    }
  });
} else {
  showError("preload 桥接未就绪，请重启应用。");
}
