/** @typedef {{ id: string, label: string, emoji: string, sessionKey: string, messagePrefix: string | null }} Lens */

/** @type {Record<string, Lens>} */
window.ZHUANZHU_LENSES = {
  default: {
    id: "default",
    label: "默认协调",
    emoji: "⚙",
    sessionKey: "agent:main:main",
    messagePrefix: null,
  },
  archive: {
    id: "archive",
    label: "档案助手",
    emoji: "📁",
    sessionKey: "agent:main:archive",
    messagePrefix:
      "[lens:archive] 你是转注 Work 档案助手。帮用户在 media2text 本地转写与 manifest 中检索、对齐时间线；引用时注明 creator、场次与时间戳。不提供荐股或买卖建议。",
  },
  wanzhan: {
    id: "wanzhan",
    label: "万战寻道",
    emoji: "📈",
    sessionKey: "agent:main:wanzhan",
    messagePrefix:
      "[lens:wanzhan] 你是万战寻道短线交易复盘 lens：关注节奏、背离、兑现与仓位纪律。引用转写时带时间戳出处；不构成投资建议。",
  },
  nuwa: {
    id: "nuwa",
    label: "女娲蒸馏",
    emoji: "🧬",
    sessionKey: "agent:main:nuwa",
    messagePrefix:
      "[lens:nuwa] 你是女娲蒸馏助手：从人名/主题调研并生成可运行 SKILL.md 大纲。先澄清输入，再输出结构化 skill 草稿，不臆造来源。",
  },
};

window.ZHUANZHU_LENS_ORDER = ["default", "archive", "wanzhan", "nuwa"];
