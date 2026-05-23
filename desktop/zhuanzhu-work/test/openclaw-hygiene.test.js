const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const os = require("os");
const path = require("path");

const {
  checkOpenClawHygiene,
  listSkillsSymlinkIssues,
} = require("../lib/openclaw-hygiene");
const config = require("../lib/config");

test("listSkillsSymlinkIssues detects symlink outside skills root", () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "oc-skills-"));
  const outside = fs.mkdtempSync(path.join(os.tmpdir(), "oc-out-"));
  const skillLink = path.join(tmp, "demo-skill");
  fs.symlinkSync(outside, skillLink);

  const issues = listSkillsSymlinkIssues(10, tmp);
  assert.equal(issues.length, 1);
  assert.equal(issues[0].name, "demo-skill");

  fs.rmSync(tmp, { recursive: true, force: true });
  fs.rmSync(outside, { recursive: true, force: true });
});

test("checkOpenClawHygiene warns when agents.list exceeds threshold", () => {
  const parsed = config.readOpenClawConfig();
  if (!parsed.ok) {
    assert.ok(true);
    return;
  }
  const report = checkOpenClawHygiene({ agentsWarnThreshold: 0 });
  assert.equal(typeof report.agents_list_count, "number");
  assert.equal(report.agents_list_warn, report.agents_list_count > 0);
  assert.ok(Array.isArray(report.hints));
});
