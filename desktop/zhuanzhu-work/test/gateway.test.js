const { test } = require("node:test");
const assert = require("node:assert/strict");

const gateway = require("../lib/gateway");

test("waitForGatewayReady fails fast when gateway child exited", async () => {
  gateway._resetGatewayStateForTests();
  gateway._setGatewayStartupFailureForTests({ code: 1, signal: null });

  const started = Date.now();
  const result = await gateway.waitForGatewayReady(60_000);
  const elapsed = Date.now() - started;

  assert.equal(result.ok, false);
  assert.equal(result.failFast, true);
  assert.match(result.error, /子进程已退出/);
  assert.ok(elapsed < 2_000, `expected fail-fast, took ${elapsed}ms`);
});
