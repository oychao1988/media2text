const complianceCheck = document.getElementById("compliance-check");
const continueBtn = document.getElementById("btn-continue");
const skipBtn = document.getElementById("btn-skip");
const openConfigBtn = document.getElementById("btn-open-config");
const configPathEl = document.getElementById("config-path");
const configSection = document.getElementById("config-section");
const errorEl = document.getElementById("wizard-error");

let bootstrap = null;

function showError(text) {
  errorEl.hidden = false;
  errorEl.textContent = text;
}

function updateContinueState() {
  continueBtn.disabled = !complianceCheck.checked;
}

async function finishWizard() {
  if (!complianceCheck.checked) {
    showError("请先勾选免责声明。");
    return;
  }
  try {
    await window.zhuanzhu.app.acceptCompliance();
    await window.zhuanzhu.app.enterMain();
  } catch (err) {
    showError(err?.message || String(err));
  }
}

async function init() {
  if (!window.zhuanzhu?.app?.getBootstrap) {
    showError("preload 桥接未就绪，请重启应用。");
    return;
  }

  bootstrap = await window.zhuanzhu.app.getBootstrap();
  if (configPathEl && bootstrap?.configPath) {
    configPathEl.textContent = bootstrap.configPath;
  }

  if (bootstrap?.setup?.complete) {
    configSection.hidden = true;
  }

  if (bootstrap?.complianceAccepted) {
    complianceCheck.checked = true;
    complianceCheck.disabled = true;
    updateContinueState();
  }
}

complianceCheck.addEventListener("change", updateContinueState);
continueBtn.addEventListener("click", () => finishWizard());
skipBtn.addEventListener("click", () => finishWizard());
openConfigBtn.addEventListener("click", () => {
  window.zhuanzhu.app.openConfigDir().catch((err) => {
    showError(err?.message || String(err));
  });
});

init();
