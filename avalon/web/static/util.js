// 通用小工具：转义、格式化、图标、术语。

export const PIDS = ["P1", "P2", "P3", "P4", "P5"];
export const QUEST_SIZES = [2, 3, 2, 3, 3];
export const STEPS = ["讨论", "提案", "投票", "执行", "结算"];

export const ROLE_ZH = { Merlin: "梅林", Percival: "派西维尔", "Loyal Servant": "忠臣", Morgana: "莫甘娜", Assassin: "刺客" };
export const ROLE_SIDE = { Merlin: "good", Percival: "good", "Loyal Servant": "good", Morgana: "evil", Assassin: "evil" };
export const ACTION_ZH = { speak: "发言", propose: "提案", vote: "投票", execute_quest: "出牌", assassinate: "刺杀" };
export const ACTION_ING = { speak: "正在发言", propose: "正在指派队伍", vote: "投票中", execute_quest: "正在出牌", assassinate: "正在选择刺杀目标" };
export const STATUS_ZH = {
  queued: "排队中", running: "进行中", pausing: "暂停中 · 等调用返回", paused: "已暂停", terminating: "终止中",
  finished: "已结束", terminated: "已终止", error: "出错", interrupted: "已中断", cancelled: "已取消",
};
export const LIVE = new Set(["running", "pausing", "paused", "terminating"]);
export const TERMINAL = new Set(["finished", "terminated", "error", "interrupted"]);

export function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

export function roleZh(role) { return ROLE_ZH[role] || role || "?"; }
export function sideOf(role) { return ROLE_SIDE[role] || "unknown"; }
export function sideZh(side) { return side === "good" ? "好人" : side === "evil" ? "邪恶" : "未知"; }

/** 与 rules.hidden_info_for 一致的"开局所知"。 */
export function hiddenInfo(pid, assignments) {
  const role = assignments[pid];
  if (!role) return "";
  const evil = PIDS.filter((p) => ROLE_SIDE[assignments[p]] === "evil");
  if (role === "Merlin") return `看到 ${evil.join("、")} 是邪恶`;
  if (role === "Percival") {
    const pair = PIDS.filter((p) => assignments[p] === "Merlin" || assignments[p] === "Morgana");
    return `看到 ${pair.join("、")} 之一是梅林`;
  }
  if (ROLE_SIDE[role] === "evil") return `队友 ${evil.filter((p) => p !== pid).join("、")}`;
  return "无额外信息";
}

export function winReasonZh(reason, target) {
  switch (reason) {
    case "three_failures": return "邪恶累计 3 次任务失败";
    case "five_rejections": return "同一次任务内累计 5 次否决";
    case "merlin_assassinated": return `刺客刺中了梅林 ${target || ""}`;
    case "three_successes_and_merlin_safe": return `好人 3 次任务成功，刺客刺杀 ${target || ""} 未中梅林`;
    default: return reason || "";
  }
}

export function fmtDuration(s) {
  if (s == null || Number.isNaN(s)) return "—";
  s = Math.max(0, Math.round(s));
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), r = s % 60;
  if (h) return `${h} 时 ${m} 分`;
  if (m) return `${m} 分 ${String(r).padStart(2, "0")} 秒`;
  return `${r} 秒`;
}
export function fmtSecs(s) { return s == null ? "—" : `${Number(s).toFixed(1)} 秒`; }
export function fmtTime(ts) {
  if (!ts) return "";
  const d = new Date(ts);
  return d.toLocaleTimeString("zh-CN", { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" });
}
export function fmtDate(ts) {
  if (!ts) return "—";
  const d = new Date(ts);
  const p = (n) => String(n).padStart(2, "0");
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}
export function fmtCost(x, digits = 3) { return x == null ? "—" : Number(x).toFixed(digits); }
export function fmtInt(n) { return n == null ? "—" : Number(n).toLocaleString("en-US"); }
export function fmtTokens(n) {
  if (n == null) return "—";
  if (n >= 100000) return `${(n / 10000).toFixed(1)} 万 token`;
  return `${fmtInt(n)} token`;
}
export function pct(a, b) { return b ? `${Math.round((a / b) * 100)}%` : "—"; }

const PATHS = {
  crown: '<path d="M3 8l4.5 5L12 5l4.5 8L21 8l-2 11H5L3 8z"/>',
  lock: '<rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
  "chev-up": '<path d="M18 15l-6-6-6 6"/>', "chev-down": '<path d="M6 9l6 6 6-6"/>', "chev-right": '<path d="M9 6l6 6-6 6"/>',
  "skip-back": '<path d="M19 20L9 12l10-8v16z"/><path d="M5 19V5"/>', "step-back": '<path d="M15 18l-6-6 6-6"/>',
  "step-fwd": '<path d="M9 18l6-6-6-6"/>', "skip-fwd": '<path d="M5 4l10 8-10 8V4z"/><path d="M19 5v14"/>',
  play: '<path d="M7 4l12 8-12 8V4z"/>', download: '<path d="M12 4v11"/><path d="M7 10l5 5 5-5"/><path d="M4 19h16"/>',
  check: '<path d="M5 12l5 5L20 7"/>', dagger: '<path d="M12 3v13"/><path d="M8 16h8"/><path d="M10 16l2 5 2-5"/><path d="M9 6l3-3 3 3"/>',
  eye: '<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
  file: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/>',
  "arrow-left": '<path d="M19 12H5"/><path d="M11 18l-6-6 6-6"/>', stop: '<rect x="6" y="6" width="12" height="12" rx="1.5"/>',
  x: '<path d="M18 6L6 18"/><path d="M6 6l12 12"/>', bolt: '<path d="M13 2L4 14h7l-1 8 9-12h-7l1-8z"/>',
  gear: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
};
export function icon(name, size = 16, color) {
  if (name === "pause") return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="currentColor" stroke="none"><rect x="6" y="5" width="4" height="14" rx="1"/><rect x="14" y="5" width="4" height="14" rx="1"/></svg>`;
  const sw = name === "crown" ? 2.2 : 2;
  const stroke = color ? color : "currentColor";
  return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="${stroke}" stroke-width="${sw}" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0">${PATHS[name] || ""}</svg>`;
}

export function countCn(text) { return (text || "").replace(/\s/g, "").length; }

/** 一个极简的 markdown 转 HTML，只处理复盘稿用到的语法：标题、引用、加粗、列表、段落。 */
export function markdown(md) {
  const lines = md.split("\n");
  const out = [];
  let para = [], quote = [], list = [];
  const flushP = () => { if (para.length) { out.push(`<p>${inline(para.join(" "))}</p>`); para = []; } };
  const flushQ = () => { if (quote.length) { out.push(`<blockquote>${quote.map((l) => inline(l)).join("<br>")}</blockquote>`); quote = []; } };
  const flushL = () => { if (list.length) { out.push(`<ul>${list.map((l) => `<li>${inline(l)}</li>`).join("")}</ul>`); list = []; } };
  const inline = (s) => esc(s).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/`(.+?)`/g, "<code>$1</code>");
  for (const raw of lines) {
    const line = raw.replace(/\s+$/, "");
    const h = /^(#{1,6})\s+(.*)$/.exec(line);
    if (h) { flushP(); flushQ(); flushL(); out.push(`<h${h[1].length}>${inline(h[2])}</h${h[1].length}>`); continue; }
    if (/^>\s?/.test(line)) { flushP(); flushL(); quote.push(line.replace(/^>\s?/, "")); continue; }
    if (/^[-*]\s+/.test(line)) { flushP(); flushQ(); list.push(line.replace(/^[-*]\s+/, "")); continue; }
    if (line === "") { flushP(); flushQ(); flushL(); continue; }
    flushQ(); flushL(); para.push(line);
  }
  flushP(); flushQ(); flushL();
  return out.join("\n");
}

export function debounce(fn, ms) {
  let t = null;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}
