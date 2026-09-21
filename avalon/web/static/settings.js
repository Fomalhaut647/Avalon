// 裁判席的本地设置：存在浏览器里，不进服务端。

const KEY = "avalon.settings";

export const SETTINGS = [
  {
    key: "eventDetail", title: "事件粒度", hint: "回放的步进与顶栏的事件计数按哪一档走。简略把一次行动的提问、模型返回与答案合成一步，五路并行的投票合成一步；详细一条原始事件一步。",
    options: [["simple", "简略"], ["detailed", "详细"]], default: "simple",
  },
  {
    key: "privateDefault", title: "私下分析默认状态", hint: "时间线里每条发言下的私下分析块。",
    options: [["latest", "只展开最新一条"], ["all", "全部展开"], ["none", "全部收起"]], default: "latest",
  },
  {
    key: "replaySpeed", title: "自动回放速度", hint: "回放中按播放键后每步停留的时间。",
    options: [["1.5", "慢 · 1.5 秒"], ["0.7", "中 · 0.7 秒"], ["0.3", "快 · 0.3 秒"]], default: "0.7",
  },
  {
    key: "showReasoning", title: "玩家线程页默认显示隐藏推理", hint: "开启隐藏思考的对局才有推理原文；这里只决定进入线程页时是否直接展开。",
    options: [["off", "关"], ["on", "开"]], default: "off",
  },
];

export function loadSettings() {
  const out = Object.fromEntries(SETTINGS.map((s) => [s.key, s.default]));
  try {
    const raw = JSON.parse(localStorage.getItem(KEY) || "{}");
    for (const s of SETTINGS) if (raw[s.key] != null && s.options.some(([v]) => v === String(raw[s.key]))) out[s.key] = String(raw[s.key]);
  } catch (e) { /* 存储不可用时用默认值 */ }
  return out;
}

export function saveSettings(patch) {
  const merged = { ...loadSettings(), ...patch };
  try { localStorage.setItem(KEY, JSON.stringify(merged)); } catch (e) { /* 忽略 */ }
  return merged;
}
