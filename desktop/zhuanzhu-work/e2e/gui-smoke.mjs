/**
 * 转注 Work GUI 冒烟测试（Playwright + Electron）。
 *
 * 用法：
 *   ZHUANZHU_SKIP_SPAWN=1 node e2e/gui-smoke.mjs
 *
 * 前提：127.0.0.1:18789 Gateway 可用（手动运行或由其他进程提供）。
 */
import { _electron as electron } from "playwright";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const appRoot = path.resolve(__dirname, "..");
const electronExecutable = require("electron");
const timeoutMs = Number(process.env.ZHUANZHU_E2E_TIMEOUT_MS || 120_000);

process.env.ZHUANZHU_SKIP_SPAWN = process.env.ZHUANZHU_SKIP_SPAWN || "1";
delete process.env.ELECTRON_RUN_AS_NODE;

async function waitForChatReady(page) {
  await page.waitForSelector("#composer-input", { timeout: timeoutMs });
  await page.waitForFunction(
    () => !document.querySelector("#composer-input")?.disabled,
    undefined,
    { timeout: timeoutMs },
  );
}

async function main() {
  const childEnv = { ...process.env, ZHUANZHU_SKIP_SPAWN: process.env.ZHUANZHU_SKIP_SPAWN };
  delete childEnv.ELECTRON_RUN_AS_NODE;

  const electronApp = await electron.launch({
    executablePath: electronExecutable,
    cwd: appRoot,
    args: ["."],
    env: childEnv,
    timeout: timeoutMs,
  });

  try {
    const page = await electronApp.firstWindow();
    await page.waitForLoadState("domcontentloaded", { timeout: timeoutMs });

    const bodyText = await page.textContent("body");
    if (bodyText?.includes("启动失败")) {
      throw new Error(`应用启动失败：${bodyText.slice(0, 400)}`);
    }

    if (await page.locator("#compliance-check").count()) {
      await page.locator("#compliance-check").check();
      await page.locator("#btn-continue, #btn-skip").first().click();
    }

    await waitForChatReady(page);

    const prompt = process.env.ZHUANZHU_SMOKE_MESSAGE || "回复两个字：收到";
    const assistantCountBefore = await page
      .locator(".msg.assistant:not(.pending)")
      .count();

    await page.fill("#composer-input", prompt);
    await page.click("#btn-send");

    await page.waitForFunction(
      ({ before }) => {
        if (document.querySelector(".msg.assistant.streaming")) return false;
        const msgs = document.querySelectorAll(".msg.assistant:not(.pending) .bubble");
        if (msgs.length <= before) return false;
        const last = msgs[msgs.length - 1]?.textContent?.trim() || "";
        return last.length > 0 && !last.includes("思考") && !last.includes("已就绪");
      },
      { before: assistantCountBefore },
      { timeout: timeoutMs },
    );

    const replies = await page
      .locator(".msg.assistant:not(.pending) .bubble")
      .allTextContents();
    const lastReply = replies.at(-1)?.trim();
    console.log("assistant reply:", lastReply);

    if (!lastReply) {
      throw new Error("未收到 assistant 回复");
    }

    console.log("gui-smoke: OK");
  } finally {
    await electronApp.close();
  }
}

main().catch((err) => {
  console.error("gui-smoke: FAIL", err);
  process.exit(1);
});
