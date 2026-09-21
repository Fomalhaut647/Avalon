// 入口：路由、状态、事件流、操作。画面由 render.js 生成，事件由 reduce.js 归约。

import { LIVE, TERMINAL, STATUS_ZH, fmtDuration } from "./util.js";
import { reduce, pausedSeconds, buildSteps, rawSteps, stepIndexAt } from "./reduce.js";
import { renderGame, renderLobby, renderThread, renderReport, renderSettings, applySettings } from "./render.js";
import { loadSettings, saveSettings } from "./settings.js";

const app = document.getElementById("app");
let view = null; // 当前页面的状态与清理函数
let serverOffset = 0; // 服务器时间 - 本地时间，毫秒
let settings = loadSettings();
applySettings(settings);

/**
 * 把新 HTML 合并进现有 DOM，而不是整块替换：正在拖的滑条、正在输入的框、正在点的按钮都还是原来那个节点。
 * 按位置逐个对比，同名节点只同步属性与文本；有焦点的输入框不改它的值。
 */
function morph(from, to) {
  const a = Array.from(from.childNodes), b = Array.from(to.childNodes);
  const n = Math.max(a.length, b.length);
  for (let i = 0; i < n; i++) {
    const x = a[i], y = b[i];
    if (!y) { x.remove(); continue; }
    if (!x) { from.appendChild(y); continue; }
    if (x.nodeType !== y.nodeType || x.nodeName !== y.nodeName) { from.replaceChild(y, x); continue; }
    if (x.nodeType === Node.TEXT_NODE || x.nodeType === Node.COMMENT_NODE) { if (x.data !== y.data) x.data = y.data; continue; }
    for (const attr of Array.from(x.attributes)) if (!y.hasAttribute(attr.name)) x.removeAttribute(attr.name);
    for (const attr of Array.from(y.attributes)) if (x.getAttribute(attr.name) !== attr.value) x.setAttribute(attr.name, attr.value);
    if ((x.tagName === "INPUT" || x.tagName === "SELECT" || x.tagName === "TEXTAREA") && x !== document.activeElement) {
      if (x.type === "checkbox" || x.type === "radio") { if (x.checked !== y.checked) x.checked = y.checked; }
      else if (x.value !== y.value) x.value = y.value;
    }
    morph(x, y);
  }
}
function render(html) {
  const tpl = document.createElement("div");
  tpl.innerHTML = html;
  morph(app, tpl);
}

const now = () => Date.now() + serverOffset;
function syncClock(summary) { if (summary && summary.server_now) serverOffset = Date.parse(summary.server_now) - Date.now(); }
/** 只接受更新的摘要：控制请求的回包可能比事件流里的状态更新还旧。 */
function newer(current, incoming) { return !current || !incoming.server_now || !current.server_now || Date.parse(incoming.server_now) >= Date.parse(current.server_now); }

async function api(path, opts = {}) {
  const r = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || (data.detail && JSON.stringify(data.detail)) || `HTTP ${r.status}`);
  return data;
}
function toast(text, err = false) {
  const el = document.createElement("div");
  el.className = `toast ${err ? "err" : ""}`;
  el.textContent = text;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 2600);
}

// ---------------------------------------------------------------- 路由

function parseRoute() {
  const h = location.hash.replace(/^#\/?/, "");
  const parts = h.split("/").filter(Boolean);
  if (!parts.length) return { name: "lobby" };
  if (parts[0] === "g" && parts[1]) {
    if (parts[2] === "p" && parts[3]) return { name: "thread", id: parts[1], pid: parts[3] };
    if (parts[2] === "report") return { name: "report", id: parts[1] };
    return { name: "game", id: parts[1] };
  }
  if (parts[0] === "settings") return { name: "settings" };
  return { name: "lobby" };
}

let bootVersion = null;
/** 服务端前端文件的版本变了（我改了脚本或样式）就整页刷新，免得单页应用一直跑旧脚本。 */
function checkVersion() {
  api("/api/config").then((cfg) => {
    if (bootVersion === null) bootVersion = cfg.static_version;
    else if (cfg.static_version && cfg.static_version !== bootVersion) location.reload();
  }).catch(() => {});
}

function route() {
  checkVersion();
  if (view) { view.dead = true; if (view.teardown) view.teardown(); }
  const r = parseRoute();
  window.scrollTo(0, 0);
  if (r.name === "lobby") view = lobbyView();
  else if (r.name === "game") view = gameView(r.id);
  else if (r.name === "thread") view = threadView(r.id, r.pid);
  else if (r.name === "settings") view = settingsView();
  else view = reportView(r.id);
}
window.addEventListener("hashchange", route);

// ---------------------------------------------------------------- 对局列表

/** 与服务端 GameManager.stats 同一口径：胜负只算正常打完的局。 */
function computeStats(games) {
  const finished = games.filter((g) => g.status === "finished");
  const assassinations = finished.filter((g) => g.assassination_target);
  return {
    total: games.length, finished: finished.length,
    live: games.filter((g) => LIVE.has(g.status)).length, queued: games.filter((g) => g.status === "queued").length,
    good_wins: finished.filter((g) => g.winner === "good").length, evil_wins: finished.filter((g) => g.winner === "evil").length,
    assassinations: assassinations.length, assassination_hits: assassinations.filter((g) => g.win_reason === "merlin_assassinated").length,
    cost_cny: games.reduce((s, g) => s + (g.cost_cny || 0), 0), llm_calls: games.reduce((s, g) => s + (g.llm_calls || 0), 0),
    duration_s: finished.reduce((s, g) => s + (g.duration_s || 0), 0),
  };
}

const formDefaults = { seed: "", model: "", thinking: false, random: false, count: 1 };
let lobbyForm = { ...formDefaults };

function lobbyView() {
  const st = { games: [], stats: {}, capacity: { running: 0, max_concurrent: 8 }, config: null, filter: "all", form: lobbyForm, error: null, creating: false };
  let es = null;
  const self = { dead: false };
  const draw = () => { if (!self.dead) render(renderLobby(st)); };
  api("/api/config").then((cfg) => {
    st.config = cfg;
    if (!st.form.model) st.form.model = cfg.model;
    if (!st.form.touched) { st.form.thinking = !!cfg.thinking; if (cfg.api_key_present === false) st.form.random = true; }
    draw();
  }).catch((e) => { st.error = e.message; draw(); });
  const open = () => {
    es = new EventSource("/api/stream");
    es.addEventListener("games", (ev) => { const d = JSON.parse(ev.data); st.games = d.games; st.stats = d.stats; st.capacity = { running: d.running, max_concurrent: d.max_concurrent }; draw(); });
    es.addEventListener("game", (ev) => {
      const d = JSON.parse(ev.data);
      const i = st.games.findIndex((g) => g.id === d.game.id);
      if (i >= 0) st.games[i] = d.game; else st.games.unshift(d.game);
      st.games.sort((a, b) => (a.id < b.id ? 1 : -1));
      st.capacity = { running: d.running, max_concurrent: d.max_concurrent };
      refreshStats();
      draw();
    });
    es.addEventListener("removed", (ev) => { const d = JSON.parse(ev.data); st.games = st.games.filter((g) => g.id !== d.id); st.capacity = { running: d.running, max_concurrent: d.max_concurrent }; refreshStats(); draw(); });
  };
  const refreshStats = () => { st.stats = computeStats(st.games); };
  open();
  draw();
  const onClick = (act, arg, el) => {
    if (act === "filter") { st.filter = arg; draw(); }
    else if (act === "focus-form") { const f = document.querySelector(".form input"); if (f) f.focus(); }
    else if (act === "toggle-form") { st.form.touched = true; st.form[arg] = !st.form[arg]; if (arg === "random" && st.form.random) st.form.thinking = false; draw(); }
  };
  const onInput = (el) => { const k = el.dataset.form; if (k) { st.form.touched = true; st.form[k] = el.value; } };
  const onSubmit = async () => {
    st.error = null; st.creating = true; draw();
    const body = { seed: st.form.seed === "" ? null : Number(st.form.seed), thinking: !!st.form.thinking, model: st.form.model || "", random_players: !!st.form.random, random_delay_s: 1.5, count: Math.max(1, Number(st.form.count) || 1) };
    if (st.form.seed !== "" && !Number.isInteger(body.seed)) { st.error = "种子必须是整数"; st.creating = false; draw(); return; }
    try {
      const d = await api("/api/games", { method: "POST", body: JSON.stringify(body) });
      st.creating = false;
      if (d.ids.length === 1) location.hash = `#/g/${d.ids[0]}`;
      else { toast(`已开 ${d.ids.length} 局`); draw(); }
    } catch (e) { st.error = e.message; st.creating = false; draw(); }
  };
  return Object.assign(self, { onClick, onInput, onSubmit, teardown: () => { if (es) es.close(); } });
}

// ---------------------------------------------------------------- 对局页

/** 被点的折叠开关当前是展开态吗：展开态的私下分析块头部带 phead，展开态的折叠行后面跟着 nested 容器。 */
function currentlyOpen(el) {
  if (!el) return false;
  if (el.classList.contains("phead")) return true;
  if (el.classList.contains("collapsed-row")) return !!(el.nextElementSibling && el.nextElementSibling.classList.contains("nested"));
  if (el.classList.contains("expander")) return !!(el.previousElementSibling && !el.previousElementSibling.classList.contains("clamp"));
  return false;
}

function gameView(id) {
  const st = { id, summary: null, events: [], model: null, fullModel: null, cursor: null, cursorIndex: 0, steps: [], stepIndex: 0, settings, replaying: false, playing: false, ui: { expanded: new Map() }, now: now(), elapsed: 0, error: null };
  let es = null, tick = null, player = null, raf = 0;
  const seen = new Set();

  const compute = () => {
    st.now = now();
    st.settings = settings;
    st.fullModel = reduce(st.events);
    st.steps = settings.eventDetail === "detailed" ? rawSteps(st.events) : buildSteps(st.events);
    if (st.replaying && st.cursor != null) {
      const idx = st.events.findIndex((e) => e.seq > st.cursor);
      const slice = idx < 0 ? st.events : st.events.slice(0, idx);
      st.model = reduce(slice);
      st.cursorIndex = slice.length;
      st.stepIndex = stepIndexAt(st.steps, st.cursor);
      st.elapsed = st.model.firstTs ? (Date.parse(st.model.lastTs) - Date.parse(st.model.firstTs)) / 1000 - pausedSeconds(st.model.control.log, st.model.lastTs) : 0;
    } else {
      st.model = st.fullModel;
      st.cursorIndex = st.events.length;
      st.stepIndex = st.steps.length;
      const s = st.summary;
      if (!s) st.elapsed = 0;
      else if (s.status === "running" || s.status === "pausing" || s.status === "terminating") st.elapsed = (s.duration_s || 0) + Math.max(0, (st.now - Date.parse(s.server_now)) / 1000);
      else st.elapsed = s.duration_s || 0;
    }
  };
  const self = { dead: false };
  const draw = () => {
    cancelAnimationFrame(raf);
    raf = requestAnimationFrame(() => {
      if (self.dead) return;
      if (!st.summary) { render(st.error ? `<div class="empty">${st.error}</div>` : `<div class="loading">正在读取对局…</div>`); return; }
      compute();
      render(renderGame(st));
    });
  };
  const addEvents = (list) => { for (const e of list) { if (!seen.has(e.seq)) { seen.add(e.seq); st.events.push(e); } } st.events.sort((a, b) => a.seq - b.seq); };
  const openStream = () => {
    const since = st.events.length ? st.events[st.events.length - 1].seq : 0;
    es = new EventSource(`/api/games/${id}/stream?since=${since}`);
    es.addEventListener("game_event", (ev) => { addEvents([JSON.parse(ev.data)]); draw(); });
    es.addEventListener("status", (ev) => { const s = JSON.parse(ev.data); if (newer(st.summary, s)) st.summary = s; syncClock(s); if (TERMINAL.has(st.summary.status)) { es.close(); es = null; } draw(); });
    es.onerror = () => { /* EventSource 自动重连并带 Last-Event-ID */ };
  };
  api(`/api/games/${id}/events`).then((d) => {
    st.summary = d.game; syncClock(d.game); addEvents(d.events);
    if (!TERMINAL.has(d.game.status)) openStream();
    draw();
  }).catch((e) => { st.error = e.message; draw(); });
  // 每秒只更新用时与"已等待"数字，不整页重绘，免得正在点的按钮被换掉。
  tick = setInterval(() => {
    if (!st.summary || st.replaying || !LIVE.has(st.summary.status)) return;
    compute();
    const el = app.querySelector('[data-tick="elapsed"]');
    if (el) el.textContent = fmtDuration(st.elapsed);
    for (const w of app.querySelectorAll('[data-tick="waited"]')) w.textContent = String(Math.max(0, Math.round((st.now - Date.parse(w.dataset.ts)) / 1000)));
  }, 1000);

  const setCursor = (seq) => {
    const total = st.events.length;
    const max = total ? st.events[total - 1].seq : 0;
    seq = Math.max(1, Math.min(max, seq));
    if (seq >= max && !TERMINAL.has(st.summary.status)) { backLive(); return; }
    st.replaying = true; st.cursor = seq; st.stepIndex = stepIndexAt(st.steps, seq); st.playing = st.playing && seq < max; if (!st.playing) stopPlayer(); draw();
  };
  const backLive = () => { st.replaying = false; st.cursor = null; st.stepIndex = st.steps.length; st.playing = false; stopPlayer(); draw(); };
  const stopPlayer = () => { if (player) { clearInterval(player); player = null; } };
  const step = (d) => {
    if (!st.steps.length) return;
    const target = st.steps[Math.min(st.steps.length, Math.max(1, st.stepIndex + d)) - 1];
    if (!target) return;
    if (d > 0 && target.index === st.stepIndex) { if (!TERMINAL.has(st.summary.status)) backLive(); return; }
    setCursor(target.end);
  };
  const seekStep = (n) => { if (!st.steps.length) return; const target = st.steps[Math.min(st.steps.length, Math.max(1, Math.round(n))) - 1]; if (target) setCursor(target.end); };
  const control = async (verb) => {
    try { const s = await api(`/api/games/${id}/${verb}`, { method: "POST" }); if (newer(st.summary, s)) st.summary = s; syncClock(s); toast(`${{ pause: "暂停", resume: "继续", terminate: "终止" }[verb]}：${STATUS_ZH[s.status] || s.status}`); draw(); }
    catch (e) { toast(e.message, true); }
  };
  const onClick = (act, arg, el) => {
    if (act === "toggle") { st.ui.expanded.set(arg, !currentlyOpen(el)); draw(); }
    else if (act === "pause") control("pause");
    else if (act === "resume") control("resume");
    else if (act === "terminate") { if (confirm("终止这一局？进行中的调用会被掐断，记录保留，结果记为已终止、无胜方。")) control("terminate"); }
    else if (act === "live") backLive();
    else if (act === "pause-follow") { st.replaying = true; st.cursor = st.events.length ? st.events[st.events.length - 1].seq : 0; draw(); }
    else if (act === "skip-back") { if (st.steps.length) setCursor(st.steps[0].end); }
    else if (act === "skip-fwd") { if (TERMINAL.has(st.summary.status)) setCursor(st.events[st.events.length - 1].seq); else backLive(); }
    else if (act === "step-back") step(-1);
    else if (act === "step-fwd") step(1);
    else if (act === "play") { st.playing = !st.playing; if (st.playing) { player = setInterval(() => { if (!st.replaying) { stopPlayer(); st.playing = false; return; } if (st.stepIndex >= st.steps.length) { stopPlayer(); st.playing = false; draw(); return; } const target = st.steps[st.stepIndex]; st.cursor = target.end; draw(); }, Number(settings.replaySpeed) * 1000); } else stopPlayer(); draw(); }
    else if (act === "again") {
      const s = st.summary;
      api("/api/games", { method: "POST", body: JSON.stringify({ seed: s.seed, thinking: !!s.thinking, model: s.random_players ? "" : s.model, random_players: !!s.random_players, random_delay_s: 1.5, count: 1 }) })
        .then((d) => { location.hash = `#/g/${d.ids[0]}`; }).catch((e) => toast(e.message, true));
    }
  };
  const onInput = (el, type) => {
    if (el.dataset.act === "seek") seekStep(Number(el.value));
    else if (el.dataset.act === "seek-input" && type === "change") { seekStep(Number(el.value)); el.blur(); }
  };
  const onKey = (ev) => {
    if (ev.target && ["INPUT", "SELECT", "TEXTAREA"].includes(ev.target.tagName)) return;
    if (ev.key === "ArrowLeft") { ev.preventDefault(); step(-1); }
    else if (ev.key === "ArrowRight") { ev.preventDefault(); step(1); }
    else if (ev.key === " ") { ev.preventDefault(); if (st.replaying) backLive(); }
  };
  window.addEventListener("keydown", onKey);
  return Object.assign(self, { onClick, onInput, teardown: () => { if (es) es.close(); clearInterval(tick); stopPlayer(); cancelAnimationFrame(raf); window.removeEventListener("keydown", onKey); } });
}

// ---------------------------------------------------------------- 玩家线程

function threadView(id, pid) {
  const st = { id, pid, summary: null, messages: [], events: [], model: null, ui: { expanded: new Map() }, filter: "all", showReasoning: settings.showReasoning === "on", error: null };
  let es = null, timer = null;
  const self = { dead: false };
  const draw = () => {
    if (self.dead) return;
    if (!st.summary) { render(st.error ? `<div class="empty">${st.error}</div>` : `<div class="loading">正在读取线程…</div>`); return; }
    st.model = reduce(st.events);
    render(renderThread(st));
  };
  const load = async () => {
    const [ev, th] = await Promise.all([api(`/api/games/${id}/events`), api(`/api/games/${id}/players/${pid}`)]);
    st.summary = ev.game; st.events = ev.events; st.messages = th.messages; syncClock(ev.game);
    draw();
    if (LIVE.has(ev.game.status) && !es) {
      es = new EventSource(`/api/games/${id}/stream?since=${st.events.length ? st.events[st.events.length - 1].seq : 0}`);
      es.addEventListener("game_event", (e) => { const rec = JSON.parse(e.data); st.events.push(rec); if (rec.player === pid && (rec.kind === "turn" || rec.kind === "invalid_reply")) { clearTimeout(timer); timer = setTimeout(() => load().catch(() => {}), 300); } else draw(); });
      es.addEventListener("status", (e) => { st.summary = JSON.parse(e.data); if (TERMINAL.has(st.summary.status)) { es.close(); es = null; load().catch(() => {}); } });
    }
  };
  load().catch((e) => { st.error = e.message; draw(); });
  const onClick = (act, arg, el) => {
    if (act === "toggle") { st.ui.expanded.set(arg, !currentlyOpen(el)); draw(); }
    else if (act === "thread-filter") { st.filter = arg; draw(); }
    else if (act === "thread-reasoning") { st.showReasoning = !st.showReasoning; draw(); }
  };
  return Object.assign(self, { onClick, teardown: () => { if (es) es.close(); clearTimeout(timer); } });
}

// ---------------------------------------------------------------- 复盘稿

function reportView(id) {
  const st = { id, markdown: null };
  render(renderReport(st));
  fetch(`/api/games/${id}/files/transcript.md`).then(async (r) => { if (!r.ok) throw new Error("复盘稿尚未生成，对局结束后才有。"); st.markdown = await r.text(); render(renderReport(st)); }).catch((e) => { st.markdown = `> ${e.message}`; render(renderReport(st)); });
  return { onClick: () => {}, teardown: () => {} };
}

// ---------------------------------------------------------------- 设置

function settingsView() {
  const st = { settings };
  const draw = () => render(renderSettings(st));
  draw();
  const onClick = (act, arg) => {
    if (act === "set") { const i = arg.indexOf(":"); settings = saveSettings({ [arg.slice(0, i)]: arg.slice(i + 1) }); applySettings(settings); st.settings = settings; draw(); }
  };
  return { onClick, teardown: () => {} };
}

// ---------------------------------------------------------------- 事件委托

app.addEventListener("click", (ev) => {
  const el = ev.target.closest("[data-act]");
  if (!el || el.tagName === "INPUT") return;
  if (ev.target.closest("a[href]")) return; // 下载链接走浏览器默认行为
  const act = el.dataset.act, arg = el.dataset.arg;
  if (act === "nav") { ev.preventDefault(); location.hash = arg; return; }
  if (act === "create-form") return;
  // 点击卡片内部的可点元素时，只处理最内层的那个。
  ev.preventDefault();
  if (view && view.onClick) view.onClick(act, arg, el);
});
app.addEventListener("input", (ev) => { if (view && view.onInput) view.onInput(ev.target, "input"); });
app.addEventListener("change", (ev) => { if (view && view.onInput) view.onInput(ev.target, "change"); });
app.addEventListener("submit", (ev) => { ev.preventDefault(); if (view && view.onSubmit) view.onSubmit(); });

route();
