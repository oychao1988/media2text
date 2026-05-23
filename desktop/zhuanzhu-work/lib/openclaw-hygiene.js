const fs = require("fs");
const os = require("os");
const path = require("path");

const { readOpenClawConfig } = require("./config");

const DEFAULT_AGENTS_WARN_THRESHOLD = 50;

function openClawSkillsRoot() {
  return path.join(os.homedir(), ".openclaw", "skills");
}

function listSkillsSymlinkIssues(limit = 25, skillsRoot = openClawSkillsRoot()) {
  const root = skillsRoot;
  const issues = [];
  if (!fs.existsSync(root)) {
    return issues;
  }

  for (const name of fs.readdirSync(root)) {
    const full = path.join(root, name);
    try {
      const stat = fs.lstatSync(full);
      if (!stat.isSymbolicLink()) continue;
      const target = fs.readlinkSync(full);
      const resolved = path.resolve(path.dirname(full), target);
      const rootResolved = path.resolve(root);
      if (
        resolved !== rootResolved &&
        !resolved.startsWith(`${rootResolved}${path.sep}`)
      ) {
        issues.push({ name, link: full, target, resolved });
      }
    } catch {
      // skip unreadable entries
    }
  }

  return issues.slice(0, limit);
}

function checkOpenClawHygiene(options = {}) {
  const threshold =
    Number(options.agentsWarnThreshold) || DEFAULT_AGENTS_WARN_THRESHOLD;
  const parsed = readOpenClawConfig();
  if (!parsed.ok) {
    return {
      ok: false,
      agents_list_count: null,
      agents_list_warn: false,
      skills_symlink_issues: 0,
      skills_symlink_samples: [],
      hints: [`无法读取 OpenClaw 配置：${parsed.configPath}`],
    };
  }

  const agents = parsed.config?.agents?.list;
  const count = Array.isArray(agents) ? agents.length : 0;
  const symlinkIssues = listSkillsSymlinkIssues();
  const hints = [];

  if (count > threshold) {
    hints.push(
      `agents.list 有 ${count} 条（建议 ≤${threshold}）：请备份 openclaw.json 后移除未使用的历史 agent 条目。`,
    );
  }
  if (symlinkIssues.length > 0) {
    hints.push(
      `${symlinkIssues.length} 个 skills symlink 指向 ~/.openclaw/skills 外，Gateway 每轮会 skip 扫描：请将 skill 复制到 ~/.openclaw/skills/ 或删除逃逸 symlink。`,
    );
  }

  return {
    ok: count <= threshold && symlinkIssues.length === 0,
    agents_list_count: count,
    agents_list_warn: count > threshold,
    skills_symlink_issues: symlinkIssues.length,
    skills_symlink_samples: symlinkIssues.map((item) => item.name).slice(0, 8),
    hints,
  };
}

module.exports = {
  DEFAULT_AGENTS_WARN_THRESHOLD,
  checkOpenClawHygiene,
  listSkillsSymlinkIssues,
};
