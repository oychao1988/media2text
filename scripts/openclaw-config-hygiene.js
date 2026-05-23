#!/usr/bin/env node
/** CLI: report OpenClaw config hygiene (agents.list size, skills symlinks). */

const {
  checkOpenClawHygiene,
} = require("../desktop/zhuanzhu-work/lib/openclaw-hygiene");

const dryRun = process.argv.includes("--dry-run");
const report = checkOpenClawHygiene();
if (dryRun) {
  report.dry_run = true;
}
console.log(JSON.stringify(report, null, 2));
process.exit(report.ok ? 0 : 2);
