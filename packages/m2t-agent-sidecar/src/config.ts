import { existsSync, readFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

export type AgentConfig = {
  defaultSkills: string[];
  skillsDirs: string[];
};

const DEFAULT_CONFIG: AgentConfig = {
  defaultSkills: ['media2text'],
  skillsDirs: ['packages/agent-skills'],
};

export function resolveRepoRoot(): string {
  const fromEnv = process.env.M2T_REPO_ROOT?.trim();
  if (fromEnv && existsSync(fromEnv)) return resolve(fromEnv);

  let dir = dirname(fileURLToPath(import.meta.url));
  for (let i = 0; i < 8; i += 1) {
    if (existsSync(join(dir, 'pnpm-workspace.yaml'))) return dir;
    const parent = dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }
  return process.cwd();
}

export function loadAgentConfig(): AgentConfig {
  const configPath =
    process.env.M2T_AGENT_CONFIG?.trim() ||
    join(resolveRepoRoot(), 'apps/m2t-desktop/agent/agent.json');

  if (!existsSync(configPath)) return DEFAULT_CONFIG;

  try {
    const raw = JSON.parse(readFileSync(configPath, 'utf8')) as Partial<AgentConfig>;
    return {
      defaultSkills: raw.defaultSkills ?? DEFAULT_CONFIG.defaultSkills,
      skillsDirs: raw.skillsDirs ?? DEFAULT_CONFIG.skillsDirs,
    };
  } catch {
    return DEFAULT_CONFIG;
  }
}

export function resolveSkillsDirs(config: AgentConfig, repoRoot: string): string[] {
  const fromEnv = process.env.M2T_SKILLS_ROOT?.trim();
  if (fromEnv && existsSync(fromEnv)) return [fromEnv];

  return config.skillsDirs.map((dir) => {
    if (dir.startsWith('/')) return dir;
    return resolve(repoRoot, dir.replace(/^\.\.\/\.\.\//, ''));
  });
}

export function skillMdPath(skillsRoot: string, skillName: string): string | null {
  const path = join(skillsRoot, skillName, 'SKILL.md');
  return existsSync(path) ? path : null;
}

export function readSkillDescription(skillMd: string): string {
  const text = readFileSync(skillMd, 'utf8');
  const withoutFrontmatter = text.replace(/^---[\s\S]*?---\n?/, '');
  const title = withoutFrontmatter.match(/^#\s+(.+)/m)?.[1]?.trim();
  const firstPara = withoutFrontmatter
    .split('\n')
    .map((l) => l.trim())
    .find((l) => l && !l.startsWith('#'));
  return [title, firstPara].filter(Boolean).join(' — ') || skillMd;
}
