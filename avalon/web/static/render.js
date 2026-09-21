// 画面渲染：纯函数，输入状态返回 HTML 字符串。交互通过 data-act / data-arg 交给 app.js。

import { PIDS, QUEST_SIZES, STEPS, ACTION_ZH, ACTION_ING, STATUS_ZH, LIVE, TERMINAL, esc, roleZh, sideOf, sideZh, hiddenInfo, winReasonZh, fmtDuration, fmtSecs, fmtTime, fmtDate, fmtCost, fmtInt, fmtTokens, pct, icon, countCn, markdown } from "./util.js";
import { stepIndex, currentQuest, currentProposal, situationTitle, questStates, publicClues, pausedSeconds, askLog, stepIndexAt } from "./reduce.js";
import { SETTINGS } from "./settings.js";

let PRIVATE_DEFAULT = "latest";
/** 设置变更后由 app.js 调用，渲染函数据此决定默认展开行为。 */
export function applySettings(settings) { PRIVATE_DEFAULT = settings.privateDefault || "latest"; }

// ---------------------------------------------------------------- 小片段

const chip = (t) => `<span class="chip mono">${esc(t)}</span>`;
const tchip = (t) => `<span class="chip">${esc(t)}</span>`;
const sideChip = (side) => `<span class="side ${side}">${sideZh(side)}</span>`;
export function tag(text, kind = "muted") {
  const inner = kind === "leader" ? `${icon("crown", 11)}${esc(text)}` : kind === "active" ? `<span class="dot pulse"></span>${esc(text)}` : esc(text);
  return `<span class="tag ${kind}">${inner}</span>`;
}
const voteTag = (v) => (v === true ? tag("赞成", "yes") : v === false ? tag("反对", "no") : tag("投票中", "wait"));
function avatar(pid, m, size = "", dim = false) {
  const side = dim ? "dimmed" : sideOf(m.assignments[pid]);
  return `<div class="avatar ${size} ${side}">${pid}</div>`;
}
const nameOf = (pid, m) => `${pid} · ${roleZh(m.assignments[pid])}`;
function cells(votes, order = PIDS) {
  return `<div class="cells">${order.map((p) => { const v = votes[p]; const k = v === true ? "yes" : v === false ? "no" : "pending pulse"; return `<span class="cell ${k}">${p}</span>`; }).join("")}</div>`;
}
const cardChip = (pid, ok) => `<span class="card-chip ${ok == null ? "pending" : ok ? "success" : "fail"} mono">${pid} ${ok == null ? "待出" : ok ? "成功" : "失败"}</span>`;
const teamChips = (team, m) => team.map((p) => `<span class="team-chip mono">${p} ${roleZh(m.assignments[p])}</span>`).join("");
const qcircle = (state, size, small = false) => `<span class="qcircle ${state} ${small ? "small" : ""}">${size}</span>`;
const mono = (t) => `<span class="mono">${esc(t)}</span>`;
const dim = (t) => `<span class="dim">${esc(t)}</span>`;
const m2 = (t) => `<span class="mono">${t}</span>`;

function isOpen(ui, key, dflt = false) { return ui.expanded.has(key) ? ui.expanded.get(key) : dflt; }

function privateBlock(ui, key, text, dflt = false) {
  const n = countCn(text);
  if (!text) return "";
  const open = PRIVATE_DEFAULT === "all" ? true : PRIVATE_DEFAULT === "none" ? false : dflt;
  if (!isOpen(ui, key, open)) return `<div class="private-collapsed" data-act="toggle" data-arg="${key}">${icon("lock", 13)}<span>私下分析 · ${n} 字</span>${icon("chev-right", 12)}</div>`;
  return `<div class="private"><div class="phead" data-act="toggle" data-arg="${key}"><span class="plabel">${icon("lock", 13)}私下分析 · 仅裁判可见</span><span class="ptoggle">收起${icon("chev-up", 12)}</span></div><p class="ptext">${esc(text)}</p></div>`;
}
function reasoningBlock(ui, key, turn) {
  if (!turn.reasoning || !turn.reasoning.length) return "";
  const text = turn.reasoning.join("\n\n");
  if (!isOpen(ui, key)) return `<div class="private-collapsed" data-act="toggle" data-arg="${key}">${icon("eye", 13)}<span>隐藏推理 · ${countCn(text)} 字</span>${icon("chev-right", 12)}</div>`;
  return `<div class="private"><div class="phead" data-act="toggle" data-arg="${key}"><span class="plabel">${icon("eye", 13)}隐藏推理 · 接口返回的原文，不进玩家线程</span><span class="ptoggle">收起${icon("chev-up", 12)}</span></div><div class="reasoning">${esc(text)}</div></div>`;
}
function turnMeta(turn) {
  const parts = [fmtTime(turn.ts)];
  if (turn.calls.length) parts.push(fmtSecs(turn.latency), `输出 ${fmtInt(turn.tokensOut)} token`);
  if (turn.attempt > 1) parts.push(`第 ${turn.attempt} 次尝试`);
  if (turn.fallback) parts.push("裁判兜底");
  return parts.join(" · ");
}
function invalidNote(turn) {
  if (!turn.invalids.length) return "";
  return turn.invalids.map((i) => `<div class="control-note red">第 ${i.attempt} 次答案不合法：${esc(i.reason || "")}${turn.fallback ? "" : "，退回重答后通过"}</div>`).join("");
}

function speechEntry(turn, m, ui, { leader = false, latest = false } = {}) {
  return `<div class="entry">${avatar(turn.pid, m)}<div class="body"><div class="head"><div class="row"><span class="name">${nameOf(turn.pid, m)}</span>${leader ? tag("队长", "leader") : ""}${turn.fallback ? tag("兜底", "wait") : ""}</div><span class="meta mono">${turnMeta(turn)}</span></div>${turn.team ? `<div class="row wrap" style="gap:10px"><span style="font-size:13px;color:var(--ink2)">队伍</span>${teamChips(turn.team, m)}</div>` : ""}<p class="text">${esc(turn.speech || "")}</p>${invalidNote(turn)}${privateBlock(ui, `priv:${turn.seq}`, turn.private, latest)}${reasoningBlock(ui, `reason:${turn.seq}`, turn)}</div></div>`;
}
function generatingEntry(pid, pending, m, now, widths = [92, 78, 46]) {
  const waited = Math.max(0, Math.round((now - Date.parse(pending.ts)) / 1000));
  const meta = `${fmtTime(pending.ts)} 起 · 已等待 <span data-tick="waited" data-ts="${pending.ts}">${waited}</span> 秒 · 第 ${pending.attempt} 次尝试`;
  return `<div class="entry">${avatar(pid, m)}<div class="body"><div class="head"><div class="row"><span class="name">${nameOf(pid, m)}</span>${tag(ACTION_ING[pending.action] || "正在生成", "active")}</div><span class="meta mono">${meta}</span></div><div class="bars">${widths.map((w) => `<div class="skeleton" style="width:${w}%"></div>`).join("")}</div></div></div>`;
}
function waitingEntry(pid, note, m) {
  return `<div class="entry waiting">${avatar(pid, m, "", true)}<div class="head"><span class="name dimmed">${nameOf(pid, m)}</span><span class="note">${esc(note)}</span></div></div>`;
}
function collapsedRow(ui, key, title, detail, inner, dflt = false) {
  const open = isOpen(ui, key, dflt);
  return `<div class="collapsed-row" data-act="toggle" data-arg="${key}"><div class="cleft"><span class="stepchip">${esc(title)}</span><span class="detail">${detail}</span></div><span class="toggle">${open ? "收起" : "展开"}${icon(open ? "chev-up" : "chev-down", 12)}</span></div>${open ? `<div class="nested">${inner}</div>` : ""}`;
}
function eventBlock(step, title, meta, inner, active = false) {
  return `<div class="block"><div class="bhead"><div class="row" style="gap:10px"><span class="stepchip ${active ? "active" : ""}">${esc(step)}</span><span class="btitle">${title}</span></div><span class="meta mono">${esc(meta)}</span></div>${inner}</div>`;
}
function panel(title, subtitle, right, inner) {
  return `<div class="panel"><div class="panel-head"><div><span class="ptitle">${esc(title)}</span>${subtitle ? `<span class="psub">${subtitle}</span>` : ""}</div><span class="pright mono">${right}</span></div><div class="panel-body">${inner}</div></div>`;
}
function statsCard(title, right, rows, links = "") {
  return `<div class="stats-card"><div class="shead"><span class="stitle">${esc(title)}</span><span class="sright mono">${right}</span></div><div class="kv">${rows.map(([k, v]) => `<span class="k">${esc(k)}</span><span class="v">${v}</span>`).join("")}</div>${links ? `<div class="links">${links}</div>` : ""}</div>`;
}
const nav = (hash, text, cls = "") => `<a class="${cls}" data-act="nav" data-arg="${hash}">${text}</a>`;
const fileLink = (id, name, text, download = true) => `<a href="/api/games/${id}/files/${name}${download ? "?download=1" : ""}" ${download ? "download" : 'target="_blank"'}>${text}</a>`;

function pillFor(st) {
  const s = st.summary.status;
  if (st.replaying) return `<span class="pill grey"><span class="dot"></span>回放中</span>${TERMINAL.has(s) ? `<button class="btn primary" data-act="live">回到结尾</button>` : `<button class="btn primary" data-act="live">回到实时</button>`}`;
  if (s === "running") return `<span class="pill live"><span class="dot pulse"></span>实时跟随</span>`;
  if (s === "pausing") return `<span class="pill gold"><span class="dot pulse"></span>暂停中 · 等 ${st.summary.inflight.length} 路调用返回</span>`;
  if (s === "paused") return `<span class="pill gold"><span class="dot"></span>已暂停</span>`;
  if (s === "terminating") return `<span class="pill red"><span class="dot pulse"></span>终止中</span>`;
  if (s === "terminated" || s === "error") return `<span class="pill red"><span class="dot"></span>${STATUS_ZH[s]}</span>`;
  return `<span class="pill grey"><span class="dot"></span>${s === "finished" ? "对局已结束" : STATUS_ZH[s] || s}</span>`;
}
function controlsFor(st) {
  const s = st.summary.status;
  if (!LIVE.has(s)) return "";
  const term = `<button class="btn danger" data-act="terminate" ${s === "terminating" ? "disabled" : ""}>${icon("stop", 12)}${s === "terminating" ? "终止中…" : "终止"}</button>`;
  if (s === "running") return `<div class="controls"><button class="btn outline" data-act="pause">${icon("pause", 12)}暂停</button>${term}</div>`;
  if (s === "pausing") return `<div class="controls"><button class="btn primary" data-act="pause" title="进行中的调用作废，稍后原样重发">${icon("bolt", 12)}立即掐断</button>${term}</div>`;
  if (s === "paused") return `<div class="controls"><button class="btn primary" data-act="resume">${icon("play", 12)}继续</button>${term}</div>`;
  return `<div class="controls">${term}</div>`;
}
const settingsLink = () => nav("#/settings", `<span class="btn ghost" title="设置">${icon("gear", 13)}</span>`);

function playback(st) {
  const total = st.steps.length, cur = st.stepIndex;
  const atStart = cur <= 1, atEnd = cur >= total;
  const btn = (name, act, disabled, active = false, title = "") => `<button data-act="${act}" ${disabled ? "disabled" : ""} class="${active ? "active" : ""}" title="${title}">${icon(name)}</button>`;
  const mid = st.replaying ? btn(st.playing ? "pause" : "play", "play", false, true, st.playing ? "暂停自动回放" : "自动回放") : btn("pause", "pause-follow", total === 0, true, "暂停跟随，进入回放");
  return `<div class="playback">${btn("skip-back", "skip-back", atStart, false, "回到开局")}${btn("step-back", "step-back", atStart, false, "上一条事件（←）")}${mid}${btn("step-fwd", "step-fwd", atEnd, false, "下一条事件（→）")}${btn("skip-fwd", "skip-fwd", atEnd, false, "跳到最新")}</div>`;
}

// ---------------------------------------------------------------- 对局页

export function renderGame(st) {
  const { summary, model: m } = st;
  const elapsed = st.elapsed;
  const top = `<div class="topbar"><div class="row" style="gap:18px"><div class="row" style="gap:10px">${nav("#/", icon("arrow-left", 16), "back")}<div class="title">阿瓦隆 · 裁判席</div></div><div class="row">${chip(`局号 ${summary.id}`)}${chip(`种子 ${summary.seed ?? "?"}`)}${chip(summary.random_players ? "随机玩家" : summary.model)}${tchip(`隐藏思考 ${summary.thinking ? "开" : "关"}`)}</div></div><div class="row" style="gap:18px">${pillFor(st)}${controlsFor(st)}${playback(st)}<span class="counter events mono" title="${st.settings.eventDetail === "detailed" ? "详细：一条原始事件一步" : "简略：一次行动一步，设置里可切换"}">事件 ${st.stepIndex} / ${st.steps.length}</span><span class="vsep"></span><span class="stat">用时 <span class="mono elapsed" data-tick="elapsed">${fmtDuration(elapsed)}</span></span><span class="stat">预计 <span class="mono cost">${fmtCost(m.stats.cost)}</span> 元</span>${settingsLink()}</div></div>`;
  if (!m.start) return top + `<div class="empty">${summary.status === "queued" ? "排队中，等前面的对局结束后自动开始。" : "尚无事件。"}</div>`;
  return top + strip(m) + `<div class="main"><div>${leftColumn(st)}</div><div>${rightColumn(st)}</div></div>`;
}

function strip(m) {
  const states = questStates(m);
  const labels = { success: "成功", fail: "失败", current: "进行中", upcoming: "未开始" };
  const circles = states.map((s, i) => `<div class="quest ${s}">${qcircle(s, QUEST_SIZES[i])}<span class="qlabel">${labels[s]}</span></div>`).join("");
  const q = currentQuest(m);
  const over = !!m.over || m.control.terminated || !!m.control.error;
  const rejections = q ? q.proposals.filter((p) => p.approved === false).length : 0;
  const rej = m.phase === "ASSASSINATION" || over || !q ? `<span class="dim" style="font-size:12px">${over ? "对局已结束" : "任务阶段已结束"}</span>` : `<div class="row"><span style="font-size:12px;color:var(--ink2)">本次任务否决</span><div class="pips">${[0, 1, 2, 3, 4].map((i) => `<span class="pip ${i < rejections ? "on" : ""}"></span>`).join("")}</div><span class="mono" style="font-size:12px;color:var(--ink2)">${rejections} / 5</span></div>`;
  const steps = [...STEPS];
  if (m.phase === "ASSASSINATION" || (m.over && m.assassination)) steps.push("刺杀");
  const active = stepIndex(m.phase);
  const stepsHtml = steps.map((s, i) => `<span class="step ${m.over ? "done" : i < active ? "done" : i === active ? "active" : ""}">${s}</span>`).join("");
  return `<div class="strip"><div class="left"><div class="row" style="gap:14px"><span class="label">任务进度<small>圈内为队伍人数</small></span><div class="quests">${circles}</div></div><span class="vsep tall"></span><div class="col" style="gap:6px"><span class="score">比分 <b class="g">好人 ${m.successCount}</b> <span class="dim">:</span> <b class="e">邪恶 ${m.failCount}</b></span>${rej}</div></div><div class="right"><div class="stitle">${esc(situationTitle(m))}</div><div class="steps">${stepsHtml}</div></div></div>`;
}

function seatTags(pid, m, p, q) {
  const tags = [];
  const pend = m.pending[pid];
  const role = m.assignments[pid];
  if (m.over) {
    const a = m.assassination;
    if (a && a.target === pid) tags.push(a.hit ? tag("被刺杀", "evil") : tag("刺杀未中", "good"));
    else if (a && a.assassin === pid) tags.push(a.hit ? tag("刺中梅林", "gold") : tag("刺杀未中", "wait"));
    else tags.push(tag(sideZh(sideOf(role)), sideOf(role) === "good" ? "good" : "evil-soft"));
    return tags;
  }
  if (m.phase === "ASSASSINATION") {
    if (role === "Assassin") tags.push(pend ? tag("正在选择刺杀目标", "active") : tag("刺客"));
    else if (sideOf(role) === "evil") tags.push(tag("刺客队友", "wait"));
    else { tags.push(tag("刺杀候选")); if (role === "Merlin") tags.push(tag("梅林真身", "gold")); }
    return tags;
  }
  if (!p) return tags;
  if (p.leader === pid) tags.push(tag("队长", "leader"));
  if (p.team.includes(pid)) tags.push(tag("队员", "member"));
  if (p.stage === "discussion") {
    const spoke = p.speeches.some((t) => t.pid === pid);
    if (pend) tags.push(tag(ACTION_ING[pend.action], "active"));
    else if (spoke) tags.push(tag("已发言"));
    else tags.push(tag("等待发言", "wait"));
  } else if (p.stage === "proposal") {
    if (pend) tags.push(tag(ACTION_ING[pend.action], "active"));
    else if (p.leader !== pid) tags.push(tag("已发言"));
  } else if (p.stage === "voting") {
    const t = p.voteTurns[pid];
    if (t) tags.push(voteTag(t.vote));
    else tags.push(pend ? tag("投票中", "active") : tag("等待投票", "wait"));
  } else if (p.stage === "execution" || p.stage === "result") {
    if (p.votesEvent) tags.push(voteTag(p.votes[pid]));
    if (p.team.includes(pid)) {
      const card = q && q.cards[pid];
      if (pend) tags.push(tag("正在出牌", "active"));
      else if (card === false) tags.push(tag("失败", "evil"));
      else if (card === true) tags.push(tag("成功", "good"));
      else if (sideOf(role) === "good") tags.push(tag("成功 · 裁判代出", "good"));
      else tags.push(tag("等待出牌", "wait"));
    } else if (!pend && p.stage !== "result") tags.push(tag("空闲"));
  } else if (p.stage === "done") {
    tags.push(voteTag(p.votes[pid]));
  }
  return tags;
}

function seats(st) {
  const m = st.model, p = currentProposal(m), q = currentQuest(m);
  return `<div class="seats">${PIDS.map((pid) => {
    const role = m.assignments[pid];
    const side = sideOf(role);
    const pp = m.perPlayer[pid];
    const hl = !!m.pending[pid] || (m.over && m.assassination && (m.assassination.target === pid || m.assassination.assassin === pid));
    const rec = [`上队 ${pp.teams}`];
    if (pp.success) rec.push(`成功 ${pp.success}`);
    if (pp.fail) rec.push(`失败 ${pp.fail}`);
    let recHtml = rec.join(" · ");
    if (pp.failCards) recHtml += ` · <span style="color:var(--evil-text);font-weight:500">打出失败牌 ${pp.failCards}</span>`;
    return `<div class="seat ${hl ? "hl" : ""}" data-act="nav" data-arg="#/g/${st.id}/p/${pid}" title="查看 ${pid} 的完整线程"><div class="row between"><div class="row" style="align-items:baseline"><span class="pid mono">${pid}</span><span class="role">${roleZh(role)}</span></div>${sideChip(side)}</div><div class="hidden-info">${icon("eye", 11, "#9a9184")}${esc(hiddenInfo(pid, m.assignments))}</div><div class="tags">${seatTags(pid, m, p, q).join("")}</div><div class="record">${recHtml}<br><span class="mono">${pp.calls} 次调用 · ${fmtCost(pp.cost)} 元</span></div></div>`;
  }).join("")}</div>`;
}

function proposalDiscussion(p, m, ui, now, live) {
  const spoken = new Set(p.speeches.map((t) => t.pid));
  const lastSeq = p.speeches.length ? p.speeches[p.speeches.length - 1].seq : 0;
  let html = "";
  let pendingSeen = null;
  for (const pid of p.order) {
    const turn = p.speeches.find((t) => t.pid === pid);
    if (turn) html += speechEntry(turn, m, ui, { leader: pid === p.leader, latest: turn.seq === lastSeq && p.stage === "discussion" });
    else if (m.pending[pid] && m.pending[pid].action === "speak" && live) { html += generatingEntry(pid, m.pending[pid], m, now); pendingSeen = pid; }
    else if (p.stage === "discussion" && live) { const prev = p.order[p.order.indexOf(pid) - 1]; html += waitingEntry(pid, prev ? `排在 ${prev} 之后发言` : "等待发言", m); }
  }
  if (!spoken.size && !pendingSeen && !live) html += `<div class="empty">这次提案没有发言记录。</div>`;
  return html;
}
function earlierProposals(q, m, ui) {
  const done = q.proposals.filter((p) => p.stage === "done");
  return done.map((p) => {
    const yes = Object.values(p.votes).filter(Boolean).length;
    const detail = `队长 ${mono(p.leader)} · 队伍 ${mono(p.team.join(" "))} · ${yes} : ${PIDS.length - yes} 否决`;
    const inner = proposalDiscussion(p, m, ui, 0, false) + (p.proposeTurn ? eventBlock("提案", `队长 ${p.leader} 提出队伍 ${p.team.join("、")}`, turnMeta(p.proposeTurn), `<p class="text" style="font-size:13px">${esc(p.proposeTurn.speech || "")}</p>${privateBlock(ui, `priv:${p.proposeTurn.seq}`, p.proposeTurn.private)}`) : "") + eventBlock("投票", `${yes} : ${PIDS.length - yes} 否决`, p.votesEvent ? fmtTime(p.votesEvent.ts) : "", voteRows(p, m, ui, 0, false));
    return collapsedRow(ui, `prop:${q.index}:${p.index}`, `提案 ${p.index}`, detail, inner);
  }).join("");
}
function voteRows(p, m, ui, now, live) {
  const asked = PIDS.filter((pid) => m.pending[pid] && m.pending[pid].action === "vote");
  return `<div class="col">${PIDS.map((pid) => {
    const t = p.voteTurns[pid];
    const pend = m.pending[pid];
    let mid, right;
    if (t) { mid = voteTag(t.vote); right = turnMeta(t); }
    else if (pend && pend.action === "vote" && live) { mid = voteTag(null); right = `${fmtTime(pend.ts)} 起 · 已等待 <span data-tick="waited" data-ts="${pend.ts}">${Math.max(0, Math.round((now - Date.parse(pend.ts)) / 1000))}</span> 秒`; }
    else if (p.votesEvent) { mid = voteTag(p.votes[pid]); right = ""; }
    else { mid = tag("等待", "wait"); right = ""; }
    const priv = t ? privateBlock(ui, `priv:${t.seq}`, t.private) + reasoningBlock(ui, `reason:${t.seq}`, t) : (live && !p.votesEvent ? `<div class="skeleton" style="width:160px;height:10px"></div>` : "");
    return `<div class="vote-row">${avatar(pid, m, "s")}<span class="name">${nameOf(pid, m)}</span><span>${mid}</span><div>${priv}</div><span class="meta mono">${right}</span></div>`;
  }).join("")}</div>${asked.length || !p.votesEvent ? `<div class="dim" style="font-size:12px;padding-top:8px">五人同时收到投票通知，回复各自独立；三人赞成即通过，否则否决并把队长换给下一位。</div>` : ""}`;
}
function proposeBlock(p, m, ui, now, live, active) {
  const q = currentQuest(m);
  if (p.proposeTurn) {
    const t = p.proposeTurn;
    const inner = `<div class="row wrap" style="gap:10px"><span style="font-size:13px;color:var(--ink2)">队伍</span>${teamChips(p.team, m)}<span class="dim" style="font-size:12px">${p.team.length} 人任务 · 合法</span></div><p class="text" style="font-size:13px">${esc(t.speech || "")}</p>${invalidNote(t)}${privateBlock(ui, `priv:${t.seq}`, t.private, active)}${reasoningBlock(ui, `reason:${t.seq}`, t)}`;
    return eventBlock("提案", `队长 ${p.leader} 提出队伍 ${p.team.join("、")}`, turnMeta(t), inner, active);
  }
  const pend = m.pending[p.leader];
  const inner = pend && pend.action === "propose" && live ? generatingEntry(p.leader, pend, m, now, [70, 40]) : live ? waitingEntry(p.leader, `等待队长指派 ${q ? q.size : ""} 人队伍`, m) : `<div class="dim" style="font-size:12px">队长尚未提出队伍。</div>`;
  return eventBlock("提案", `队长 ${p.leader} 指派队伍`, "", inner, active);
}
function executionBlock(p, q, m, ui, now, live, active) {
  const evil = p.team.filter((pid) => sideOf(m.assignments[pid]) === "evil");
  const good = p.team.filter((pid) => sideOf(m.assignments[pid]) !== "evil");
  const note = evil.length ? `好人队员由裁判自动出成功牌，不调用模型；邪恶队员被单独询问出哪张牌。本次队伍里${evil.length === 1 ? `只有 ${evil[0]} 需要决定` : `${evil.join("、")} 需要各自决定`}。` : "队伍里没有邪恶玩家，五张牌全由裁判代出，任务必然成功。";
  let entries = "";
  for (const pid of evil) {
    const t = p.execTurns[pid];
    if (t) entries += `<div class="entry" style="padding:8px 0">${avatar(pid, m)}<div class="body"><div class="head"><div class="row"><span class="name">${nameOf(pid, m)}</span>${t.card === false ? tag("出牌 失败", "evil") : tag("出牌 成功", "good")}</div><span class="meta mono">${turnMeta(t)}</span></div>${invalidNote(t)}${privateBlock(ui, `priv:${t.seq}`, t.private, active)}${reasoningBlock(ui, `reason:${t.seq}`, t)}</div></div>`;
    else if (m.pending[pid] && m.pending[pid].action === "execute_quest" && live) entries += generatingEntry(pid, m.pending[pid], m, now, [60, 40]);
    else if (live) entries += waitingEntry(pid, "等待出牌", m);
  }
  const auto = good.length ? `<div class="cards-line"><span style="color:var(--ink2)">裁判自动出牌</span>${good.map((pid) => cardChip(pid, true)).join("")}<span class="dim">· 未调用模型</span></div>` : "";
  return eventBlock("执行", "任务执行", p.execTurns && Object.keys(p.execTurns).length ? fmtTime(Object.values(p.execTurns)[0].ts) : "", `<div class="note">${note}</div>${entries}${auto}`, active);
}
function resultBlock(q, m, active, nextLeader) {
  const ok = q.succeeded;
  const cards = Object.values(q.cards);
  const desc = `翻开 ${cards.length} 张任务牌：${[...cards.filter((c) => c).map(() => "成功"), ...cards.filter((c) => !c).map(() => "失败")].join("、")}`;
  const box = `<div class="result-box ${ok ? "good" : "evil"}"><span class="big">第 ${q.index} 次任务${ok ? "成功" : "失败"}</span><span class="desc">${desc}</span><span class="score">比分 <b class="serif g" style="color:var(--good-text)">好人 ${m.successCount}</b> : <b class="serif e" style="color:var(--evil-text)">邪恶 ${m.failCount}</b></span></div>`;
  let after = "玩家只看到打乱顺序的牌面；谁打了失败牌只有裁判知道。";
  if (m.failCount >= 3) after += " 邪恶累计 3 次任务失败，游戏结束。";
  else if (m.successCount >= 3) after += " 好人达成 3 次成功，进入刺杀阶段。";
  else if (nextLeader) after += ` 第 ${q.index + 1} 次任务开始，队长顺时针轮转到 ${nextLeader}。`;
  return eventBlock("结算", "任务结果", q.resultEvent ? fmtTime(q.resultEvent.ts) : "", `${box}<div class="note">${after}</div>`, active);
}
function controlNotes(m) {
  if (m.control.terminated) return `<div class="control-note red">${icon("stop", 12)}对局已被管理员终止，此后不再有任何调用。</div>`;
  if (m.control.error) return `<div class="control-note red">${icon("x", 12)}对局出错中止：${esc(m.control.error)}</div>`;
  if (m.control.paused) return `<div class="control-note">${icon("pause", 12)}已暂停：下一份通知在继续后才会发出，玩家不知道发生了暂停。</div>`;
  if (m.control.pausing) return `<div class="control-note">${icon("pause", 12)}暂停中：等进行中的调用返回；再按一下"立即掐断"可作废它们。</div>`;
  return "";
}

function leftColumn(st) {
  const m = st.model, ui = st.ui, now = st.now, live = !st.replaying || true;
  const q = currentQuest(m), p = currentProposal(m);
  let out = "";
  if (m.over) return gameOverLeft(st);
  if (m.control.terminated || m.control.error || (TERMINAL.has(st.summary.status) && !st.replaying)) {
    const s = m.control.terminated ? "对局已终止" : m.control.error ? "对局出错中止" : "对局已中断";
    const why = m.control.error ? esc(m.control.error) : m.control.terminated ? "管理员终止了对局，已落盘的内容完整保留，不计入胜负。" : "上次服务进程在这局跑完前退出了，记录停在最后一条事件；不支持从中恢复。";
    out += `<div class="banner grey"><div><div class="btitle">${s}</div><div class="bdesc">${why}</div></div><div class="actions">${fileLink(st.id, "transcript.md", `<span class="btn outline big">${icon("download", 14)}下载复盘稿</span>`)}${nav("#/", `<span class="btn ghost big">回到对局列表</span>`)}</div></div>`;
  }
  out += seats(st);
  const situ = p ? `第 ${q.index} 次任务 · 第 ${p.index} 次提案 · 队长 ${p.leader}` : q ? `第 ${q.index} 次任务` : "";
  if (m.phase === "ASSASSINATION") {
    const assassin = PIDS.find((pid) => m.assignments[pid] === "Assassin");
    const candidates = PIDS.filter((pid) => pid !== assassin);
    const goods = candidates.filter((pid) => sideOf(m.assignments[pid]) === "good");
    const pend = m.pending[assassin];
    const intro = `<div class="note">好人在第 ${q ? q.index : "?"} 次任务后达成 3 次成功。裁判向刺客 ${assassin} 发出刺杀通知：从 ${candidates.join("、")} 中选择一人，刺中梅林则邪恶反胜，否则好人获胜。</div>`;
    const act = m.assassination && m.assassination.turn ? speechEntry({ ...m.assassination.turn, speech: `刺杀 ${m.assassination.target}` }, m, ui, { latest: true }) : pend && pend.action === "assassinate" ? generatingEntry(assassin, pend, m, now, [88, 70, 82, 38]) : waitingEntry(assassin, "等待刺客", m);
    const clues = `<div class="dim" style="font-size:12px;margin-bottom:10px">下面是刺客在公开信息里能看到的线索，由裁判从对局记录汇总，供对照它的判断。</div><div class="clues">${goods.map((pid) => `<div class="clue"><div class="chead"><div class="row">${avatar(pid, m, "s")}<span class="cname">${nameOf(pid, m)}</span></div>${m.assignments[pid] === "Merlin" ? `<span class="truth">真身</span>` : ""}</div><div class="col" style="gap:3px">${publicClues(m, pid).map((r) => `<div class="cline">${esc(r)}</div>`).join("")}</div></div>`).join("")}</div>`;
    out += panel("刺杀阶段", "好人 3 胜 · 刺客一次机会", pend ? `等待 ${assassin}` : "", eventBlock("刺杀", "进入刺杀阶段", q && q.resultEvent ? fmtTime(q.resultEvent.ts) : "", intro) + act + eventBlock("线索", "刺客可见的公开线索", "裁判视角", clues) + controlNotes(m));
    return out;
  }
  if (!p) { out += panel("本轮进程", situ, "", `<div class="empty">等待第一任队长。</div>${controlNotes(m)}`); return out; }
  const earlier = earlierProposals(q, m, ui);
  const prevQuest = m.quests[m.quests.length - 2];
  const prevRow = prevQuest && prevQuest.resultEvent && !p.speeches.length && p.index === 1 ? collapsedRow(ui, `prevq:${q.index}`, "上次结算", `第 ${prevQuest.index} 次任务${prevQuest.succeeded ? "成功" : "失败"}${prevQuest.failCount ? ` · ${prevQuest.failCount} 张失败牌` : ""} · 比分 好人 ${m.successCount} : 邪恶 ${m.failCount}`, resultBlock(prevQuest, m, false, p.leader)) : "";
  if (p.stage === "discussion") {
    out += panel("本轮讨论", `${situ} · 从队长 ${p.leader} 起顺时针发言`, `${p.speeches.length} / ${PIDS.length} 已发言`, prevRow + earlier + proposalDiscussion(p, m, ui, now, live) + controlNotes(m));
    return out;
  }
  const disc = collapsedRow(ui, `disc:${q.index}:${p.index}`, "讨论", `${p.speeches.length} 条发言 · 队长 ${p.leader} 起顺时针`, proposalDiscussion(p, m, ui, now, false));
  let body = prevRow + earlier + disc;
  const yes = Object.values(p.votes).filter(Boolean).length, got = Object.keys(p.voteTurns).length;
  body += proposeBlock(p, m, ui, now, live, p.stage === "proposal");
  if (p.stage !== "proposal") {
    const vmeta = p.votesEvent ? `${fmtTime(p.votesEvent.ts)} · 5 人并行` : `已收到 ${got} / 5`;
    const vtitle = p.votesEvent ? `${yes} : ${PIDS.length - yes} ${p.approved ? "通过" : "否决"}` : "全体投票";
    const vinner = p.votesEvent && p.stage !== "voting" ? `<div class="row" style="gap:14px">${cells(p.votes)}<span style="font-size:12px;color:var(--ink2)">${PIDS.filter((pid) => p.votes[pid] === false).join("、") || "无人"}反对</span></div>${collapsedRow(ui, `votes:${q.index}:${p.index}`, "明细", "每人的投票与私下分析", voteRows(p, m, ui, now, false))}` : voteRows(p, m, ui, now, live);
    body += eventBlock("投票", vtitle, vmeta, vinner, p.stage === "voting");
  }
  if (p.stage === "execution" || p.stage === "result") body += executionBlock(p, q, m, ui, now, live, p.stage === "execution");
  if (p.stage === "result" && q.resultEvent) body += resultBlock(q, m, true, null);
  body += controlNotes(m);
  const right = p.stage === "voting" ? `投票 ${got} / 5` : p.stage === "execution" ? "执行中" : p.stage === "result" ? "已结算" : "";
  out += panel("本轮进程", situ, right, body);
  return out;
}

function gameOverLeft(st) {
  const m = st.model, ui = st.ui;
  const o = m.over, a = m.assassination;
  const winnerGood = o.winner === "good";
  const desc = `${winReasonZh(o.reason, o.target)}。${a ? (a.hit ? `好人虽以 ${m.successCount} : ${m.failCount} 赢下任务，但梅林暴露。` : `好人以 ${m.successCount} : ${m.failCount} 赢下任务，梅林安全。`) : `任务比分 好人 ${m.successCount} : 邪恶 ${m.failCount}。`}`;
  const banner = `<div class="banner ${winnerGood ? "good" : "evil"}"><div><div class="btitle">${winnerGood ? "好人阵营获胜" : "邪恶阵营获胜"}</div><div class="bdesc">${esc(desc)}</div></div><div class="actions">${nav(`#/g/${st.id}/report`, `<span class="btn primary big">${icon("file", 14)}查看复盘稿</span>`)}<button class="btn outline big" data-act="again">再开一局 · 同种子 ${st.summary.seed}</button>${nav("#/", `<span class="btn ghost big">回到对局列表</span>`)}</div></div>`;
  let blocks = "";
  if (a && a.turn) {
    const t = a.turn;
    const cands = PIDS.filter((pid) => pid !== a.assassin);
    blocks += eventBlock("刺杀", "刺客的最后一手", turnMeta(t), `<div class="entry" style="padding:4px 0">${avatar(a.assassin, m)}<div class="body"><div class="head"><div class="row"><span class="name">${nameOf(a.assassin, m)}</span>${tag(`刺杀 ${a.target}`, "evil")}<span style="font-size:12px;color:var(--ink2)">候选 ${cands.join("、")}</span></div></div>${invalidNote(t)}${privateBlock(ui, `priv:${t.seq}`, t.private, true)}${reasoningBlock(ui, `reason:${t.seq}`, t)}</div></div>`);
  }
  const reveal = PIDS.map((pid) => `<div class="reveal">${avatar(pid, m, "s")}<span class="name">${nameOf(pid, m)}</span>${sideChip(sideOf(m.assignments[pid]))}<span class="info">开局所知：${esc(hiddenInfo(pid, m.assignments))}</span></div>`).join("");
  blocks += eventBlock("公布", "角色公布", fmtTime(o.event.ts), `<div class="col">${reveal}</div>`);
  const last = m.quests[m.quests.length - 1];
  if (last && last.resultEvent) blocks = collapsedRow(ui, "final-result", "最后一次结算", `第 ${last.index} 次任务${last.succeeded ? "成功" : "失败"}`, resultBlock(last, m, false, null)) + blocks;
  const recap = panel("全局回顾", `${m.quests.length} 次任务 · ${m.proposalCount} 次提案 · ${a ? 1 : 0} 次刺杀`, fmtDuration(st.elapsed), blocks + questsRecap(st));
  return banner + seats(st) + recap;
}
function questsRecap(st) {
  const m = st.model, ui = st.ui;
  return m.quests.map((q) => collapsedRow(ui, `recap:${q.index}`, `第 ${q.index} 次任务`, `${q.proposals.length} 次提案 · ${q.succeeded == null ? "未完成" : q.succeeded ? "成功" : `失败 · ${q.failCount} 张失败牌`}`, q.proposals.map((p) => {
    const yes = Object.values(p.votes).filter(Boolean).length;
    return `<div style="padding:8px 0"><div class="row" style="gap:10px;margin-bottom:6px"><span class="stepchip">提案 ${p.index}</span><span style="font-size:13px">队长 ${mono(p.leader)} · 队伍 ${mono(p.team.join(" ") || "—")} · ${p.approved == null ? "未投票" : `${yes} : ${PIDS.length - yes} ${p.approved ? "通过" : "否决"}`}</span></div>${proposalDiscussion(p, m, ui, 0, false)}${p.proposeTurn ? eventBlock("提案", `队长 ${p.leader} 提出队伍 ${p.team.join("、")}`, turnMeta(p.proposeTurn), `<p class="text" style="font-size:13px">${esc(p.proposeTurn.speech || "")}</p>${privateBlock(ui, `priv:${p.proposeTurn.seq}`, p.proposeTurn.private)}`) : ""}${p.votesEvent ? eventBlock("投票", `${yes} : ${PIDS.length - yes} ${p.approved ? "通过" : "否决"}`, fmtTime(p.votesEvent.ts), voteRows(p, m, ui, 0, false)) : ""}${p.approved ? executionBlock(p, q, m, ui, 0, false, false) : ""}</div>`;
  }).join(""))).join("");
}

function rightColumn(st) {
  const m = st.model;
  let out = "";
  if (st.replaying) out += replayCard(st);
  out += questRecord(st);
  if (m.over || m.control.terminated || m.control.error) {
    const s = m.stats;
    out += statsCard("对局统计", m.lastTs ? `结束于 ${fmtTime(m.lastTs)}` : "", [
      ["用时", m2(fmtDuration(st.elapsed)) + (pausedSeconds(m.control.log, m.lastTs) >= 1 ? dim(` · 另有暂停 ${fmtDuration(pausedSeconds(m.control.log, m.lastTs))}`) : "")],
      ["模型调用", m2(`${s.calls} 次`) + dim(` · 隐藏思考${st.summary.thinking ? "开" : "关"}`)],
      ["输入", m2(fmtTokens(s.promptTokens)) + dim(` · 缓存命中 ${pct(s.cacheHit, s.promptTokens)}`)],
      ["输出", m2(fmtTokens(s.completionTokens)) + (s.reasoningTokens ? dim(` · 其中推理 ${fmtTokens(s.reasoningTokens)}`) : "")],
      ["无效回复", `${s.invalid} 次` + dim(` · 兜底 ${s.fallbacks} 次 · 掐断 ${s.voided} 次`)],
      ["费用", m2(`${fmtCost(s.cost)} 元`) + dim(" · 空闲时段价")],
    ]);
    out += statsCard("产物", `games/${st.id}/`, [
      ["复盘稿", fileLink(st.id, "transcript.md", mono("transcript.md")) + dim(" · 含私下分析")],
      ["裁判日志", fileLink(st.id, "events.jsonl", mono("events.jsonl")) + dim(" · 每次调用的 usage 与费用")],
      ["公开状态", fileLink(st.id, "public.json", mono("public.json"))],
      ["结果", fileLink(st.id, "result.json", mono("result.json"))],
      ["玩家线程", PIDS.map((pid) => nav(`#/g/${st.id}/p/${pid}`, mono(pid))).join(" ")],
    ]);
  } else {
    out += modelStats(st);
  }
  return out;
}
function modelStats(st) {
  const m = st.model, s = m.stats;
  const avg = s.latencies.length ? s.latencies.reduce((a, b) => a + b, 0) / s.latencies.length : null;
  const slow = s.maxLatency ? dim(` · 最慢 ${fmtSecs(s.maxLatency.v)}（${s.maxLatency.pid}，第 ${s.maxLatency.quest} 次任务）`) : "";
  return statsCard("模型调用", `${s.calls} 次`, [
    ["输入", m2(fmtTokens(s.promptTokens)) + dim(` · 缓存命中 ${pct(s.cacheHit, s.promptTokens)}`)],
    ["输出", m2(fmtTokens(s.completionTokens)) + (s.reasoningTokens ? dim(` · 其中推理 ${fmtTokens(s.reasoningTokens)}`) : "")],
    ["延迟", avg == null ? "—" : m2(`平均 ${fmtSecs(avg)}`) + slow],
    ["无效回复", `${s.invalid} 次` + dim(` · 兜底 ${s.fallbacks} 次${s.voided ? ` · 掐断 ${s.voided} 次` : ""}`)],
    ["费用", m2(`${fmtCost(s.cost)} 元`) + dim(" · 空闲时段价")],
  ], `${fileLink(st.id, "events.jsonl", "下载裁判日志")}${nav(`#/g/${st.id}/report`, "复盘稿")}<span class="dim">玩家线程</span>${PIDS.map((pid) => nav(`#/g/${st.id}/p/${pid}`, pid)).join(" ")}`);
}
function questRecord(st) {
  const m = st.model;
  const legend = `<span class="legend"><span class="sw yes"></span>赞成<span class="sw no"></span>反对</span>`;
  const blocks = m.quests.map((q, qi) => {
    const state = q.succeeded === true ? "success" : q.succeeded === false ? "fail" : "current";
    const badge = state === "success" ? tag("成功", "good") : state === "fail" ? tag(`失败 · ${q.failCount} 张失败牌`, "evil-soft") : "";
    const p = q.proposals[q.proposals.length - 1];
    const stageZh = { discussion: "讨论中", proposal: "队长指派中", voting: "投票中", execution: "执行中", result: "已结算", done: "已否决" };
    const note = state === "current" && p && !m.over ? `<span class="qnote">提案 ${p.index} · 队长 ${mono(p.leader)} · ${stageZh[p.stage] || ""}</span>` : "";
    const props = q.proposals.filter((pp) => pp.team.length || pp.votesEvent).map((pp) => {
      const yes = Object.values(pp.votes).filter(Boolean).length, got = Object.keys(pp.voteTurns).length;
      const verdict = pp.votesEvent ? `<span class="verdict mono ${pp.approved ? "ok" : ""}">${yes} : ${PIDS.length - yes} ${pp.approved ? "通过" : "否决"}</span>` : `<span class="verdict mono live">投票中 ${got} / 5</span>`;
      const votes = pp.votesEvent ? pp.votes : Object.fromEntries(Object.entries(pp.voteTurns).map(([k, t]) => [k, t.vote]));
      return `<div class="prow"><div class="phead"><span>提案 ${pp.index} · 队长 ${mono(pp.leader)} · 队伍 ${mono(pp.team.join(" "))}</span>${verdict}</div>${cells(votes)}</div>`;
    }).join("");
    let cards = "";
    if (q.team.length && (Object.keys(q.cards).length || p.stage === "execution")) {
      cards = `<div class="cards-line"><span style="color:var(--ink2)">任务牌</span>${q.team.map((pid) => cardChip(pid, q.resultEvent ? q.cards[pid] : q.cards[pid] ?? (sideOf(m.assignments[pid]) === "good" ? true : null))).join("")}</div>`;
    }
    const body = props || cards ? `<div class="qbody">${props}${cards}</div>` : "";
    return `<div class="qblock"><div class="qhead"><div class="row" style="gap:10px">${qcircle(state, q.size, true)}<span class="qtitle">第 ${q.index} 次任务</span>${note}</div>${badge}</div>${body}</div>${qi < m.quests.length - 1 ? `<div class="qsep"></div>` : ""}`;
  }).join("");
  return `<div class="qrecord"><div class="panel-head" style="padding-bottom:12px"><span class="ptitle">任务记录${st.replaying ? ` · 截至事件 ${st.stepIndex}` : ""}</span>${legend}</div>${blocks || `<div class="empty">尚未开始任务。</div>`}</div>`;
}
function replayCard(st) {
  const steps = st.steps, total = steps.length;
  const full = st.fullModel;
  const colors = { success: "var(--good)", fail: "var(--evil)", current: "var(--dash)" };
  const pos = (seq) => (total ? stepIndexAt(steps, seq) / total : 0);
  const segs = full.quests.map((q, i) => {
    const a = pos(q.startEvent.seq - 1), next = full.quests[i + 1];
    const b = next ? pos(next.startEvent.seq - 1) : 1;
    return `<div class="seg" style="left:${a * 100}%;width:${(b - a) * 100}%;background:${colors[q.succeeded === true ? "success" : q.succeeded === false ? "fail" : "current"]}"></div>`;
  }).join("");
  const cur = steps[st.stepIndex - 1];
  const detailed = st.settings.eventDetail === "detailed";
  return `<div class="stats-card"><div class="shead"><span class="stitle">回放位置</span><span class="sright mono">事件 ${st.stepIndex} / ${total}</span></div><div class="replay-bar">${segs}</div><input class="replay-range" type="range" min="1" max="${Math.max(1, total)}" value="${st.stepIndex}" data-act="seek" aria-label="回放位置"><div class="replay-ticks"><span>${fmtTime(st.events[0].ts)} 开局</span>${full.quests.map((q) => `<span>任务 ${q.index}</span>`).join("")}<span>${TERMINAL.has(st.summary.status) ? "结尾" : "实时"} ${fmtTime(st.events[st.events.length - 1].ts)}</span></div><div class="seek-row"><span>跳到第</span><input class="input seek-input mono" type="number" min="1" max="${Math.max(1, total)}" value="${st.stepIndex}" data-act="seek-input" aria-label="跳到第几个事件"><span>个事件，回车确认</span></div><div class="kv"><span class="k">当前事件</span><span class="v">${esc(cur ? cur.title : "")} <span class="mono dim">${fmtTime(cur && st.events.find((e) => e.seq === cur.end)?.ts)}</span></span><span class="k">粒度</span><span class="v">${detailed ? "详细：一条原始事件一步" : "简略：一次行动一步"} · ${nav("#/settings", "去设置里切换")}</span><span class="k">范围</span><span class="v">只回放公开事件与私下分析，模型不会被重新调用</span><span class="k">操作</span><span class="v">左右键逐事件，空格回到实时，拖动或点击进度条跳转</span></div></div>`;
}

// ---------------------------------------------------------------- 对局列表

export function renderLobby(st) {
  const games = st.games || [];
  const stats = st.stats || {};
  const filters = [["all", `全部 ${games.length}`], ["live", `进行中 ${games.filter((g) => LIVE.has(g.status) || g.status === "queued").length}`], ["finished", `已结束 ${games.filter((g) => g.status === "finished").length}`], ["other", `其他 ${games.filter((g) => ["terminated", "error", "interrupted"].includes(g.status)).length}`]];
  const shown = games.filter((g) => st.filter === "all" || (st.filter === "live" ? LIVE.has(g.status) || g.status === "queued" : st.filter === "finished" ? g.status === "finished" : ["terminated", "error", "interrupted"].includes(g.status)));
  const top = `<div class="topbar"><div class="row" style="gap:18px"><div class="title">阿瓦隆 · 裁判席</div><span style="font-size:13px;color:var(--ink2)">对局列表</span></div><div class="row" style="gap:14px"><span class="counter mono">games/ 共 ${games.length} 局 · 累计 ${fmtCost(stats.cost_cny, 2)} 元</span><span class="counter mono">同时进行 ${st.capacity.running} / ${st.capacity.max_concurrent}</span><button class="btn primary big" data-act="focus-form">新开一局</button>${settingsLink()}</div></div>`;
  const tiles = [
    ["已完成", stats.finished ?? 0, `共 ${games.length} 局`],
    ["好人胜", stats.good_wins ?? 0, stats.finished ? pct(stats.good_wins, stats.finished) : "—"],
    ["邪恶胜", stats.evil_wins ?? 0, stats.finished ? pct(stats.evil_wins, stats.finished) : "—"],
    ["刺杀命中", `${stats.assassination_hits ?? 0} / ${stats.assassinations ?? 0}`, stats.assassinations ? pct(stats.assassination_hits, stats.assassinations) : "—"],
    ["总费用", `${fmtCost(stats.cost_cny, 2)} 元`, `${fmtInt(stats.llm_calls)} 次调用`],
    ["平均用时", stats.finished ? fmtDuration(stats.duration_s / stats.finished) : "—", "只算正常打完的局"],
  ].map(([l, v, s]) => `<div class="stat-tile"><span class="tl">${l}</span><span class="tv">${v}</span><span class="ts">${s}</span></div>`).join("");
  const rows = shown.map((g) => lobbyRow(g)).join("") || `<div class="empty">${games.length ? "这个筛选下没有对局。" : "还没有对局，右侧新开一局。"}</div>`;
  const table = `<div class="table"><div class="thead-tools"><div class="filters">${filters.map(([k, t]) => `<button class="filter ${st.filter === k ? "on" : ""}" data-act="filter" data-arg="${k}">${t}</button>`).join("")}</div><span class="dim" style="font-size:12px">按开始时间倒序 · 进行中的局实时刷新</span></div><div class="trow head"><span>局号</span><span>开始</span><span>模型 · 隐藏思考</span><span>任务</span><span>状态与结果</span><span>用时</span><span>费用 元</span><span></span></div>${rows}</div>`;
  return top + `<div class="main lobby"><div><div class="stats-strip">${tiles}</div>${table}</div><div>${newGameForm(st)}</div></div>`;
}
function lobbyRow(g) {
  const dots = QUEST_SIZES.map((_, i) => { const q = g.quests[i]; const k = !q ? "" : q.succeeded === true ? "success" : q.succeeded === false ? "fail" : LIVE.has(g.status) ? "current pulse" : ""; return `<span class="${k}"></span>`; }).join("");
  const phaseZh = { INIT: "开局", DISCUSSION: "讨论", PROPOSAL: "提案", VOTING: "投票", QUEST_EXECUTION: "执行", QUEST_RESULT: "结算", ASSASSINATION: "刺杀", GAME_OVER: "结束" };
  const where = g.current_quest ? `第 ${g.current_quest} 次任务 · ${phaseZh[g.phase] || ""}` : "开局";
  const score = `好人 ${g.success_count} : 邪恶 ${g.fail_count}`;
  let res, cls = "grey", rowCls = "";
  if (g.status === "running") { res = `<span class="dot pulse"></span>进行中 · ${where} · ${score}`; cls = "live"; rowCls = "live"; }
  else if (g.status === "pausing" || g.status === "paused") { res = `${STATUS_ZH[g.status]} · ${where} · ${score}`; cls = "grey"; rowCls = "live"; }
  else if (g.status === "terminating") { res = `终止中 · ${where}`; cls = "red"; rowCls = "live"; }
  else if (g.status === "queued") { res = "排队中 · 等前面的对局结束"; }
  else if (g.status === "finished") { cls = g.winner === "good" ? "good" : "evil"; res = `${g.winner === "good" ? "好人胜" : "邪恶胜"} · ${winReasonZh(g.win_reason, g.assassination_target).replace(/^好人 3 次任务成功，/, "").replace(/^邪恶累计 /, "")}`; }
  else if (g.status === "terminated") { res = `已终止 · ${where} · ${score}`; }
  else if (g.status === "error") { res = `出错 · ${esc(g.error || "")}`; cls = "red"; }
  else { res = `已中断 · ${where}`; }
  const action = LIVE.has(g.status) || g.status === "queued" ? `<span class="btn primary" style="justify-content:center">进入</span>` : `<span class="btn ghost" style="justify-content:center">${g.status === "finished" ? "复盘" : "查看"}</span>`;
  return `<div class="trow ${rowCls}" data-act="nav" data-arg="#/g/${g.id}" style="cursor:pointer"><span class="c">${g.id}</span><span class="c dim">${fmtDate(g.started_at || g.created_at)}</span><span class="c dim">${g.random_players ? "随机玩家" : `${esc(g.model)} · ${g.thinking ? "开" : "关"}`}</span><span class="dots">${dots}</span><span class="res ${cls}" title="${esc(res.replace(/<[^>]+>/g, ""))}">${res}</span><span class="c dim">${fmtDuration(g.duration_s)}</span><span class="c">${fmtCost(g.cost_cny)}</span>${action}</div>`;
}
function newGameForm(st) {
  const f = st.form, cfg = st.config || {};
  const models = [...new Set([...(cfg.known_models || []), cfg.model].filter(Boolean))];
  const noKey = cfg.api_key_present === false;
  const toggle = (key, on, labelOn, labelOff, disabled = false) => `<div class="toggle ${on ? "on" : ""}" data-act="toggle-form" data-arg="${key}" style="${disabled ? "opacity:.5;pointer-events:none" : ""}"><span class="sw"></span><span class="tl">${on ? labelOn : labelOff}</span></div>`;
  const field = (label, control, hint = "") => `<div class="field"><label>${label}</label>${control}${hint ? `<span class="hint">${hint}</span>` : ""}</div>`;
  return `<form class="form" data-act="create-form"><div class="fhead"><span class="ftitle">新开一局</span><span class="fnote">等同命令行参数</span></div>
  ${field("种子", `<input class="input" name="seed" inputmode="numeric" placeholder="留空则随机" value="${esc(f.seed)}" data-form="seed">`, "同一种子重放同样的角色分配与第一任队长；开多局时依次加一")}
  ${field("模型", `<select class="select" name="model" data-form="model" ${f.random ? "disabled" : ""}>${models.map((mm) => `<option value="${esc(mm)}" ${f.model === mm ? "selected" : ""}>${esc(mm)}</option>`).join("")}</select>`, "五个座位使用同一模型")}
  ${field("隐藏思考", toggle("thinking", f.thinking, "开 · 一局 4 到 20 分钟", "关 · 一局约 3 到 5 分钟", f.random), "打开后输出 token 约 10 倍")}
  ${field("随机玩家", toggle("random", f.random, "开 · 不联网、零费用", "关 · 使用真实模型", noKey), noKey ? "未在 .env 里找到 DEEPSEEK_API_KEY，只能用随机玩家" : "用随机合法答案跑完整局，每次行动模拟 1.5 秒思考，用来试界面")}
  ${field("局数", `<input class="input" name="count" type="number" min="1" max="50" value="${esc(f.count)}" data-form="count">`, `同时最多 ${cfg.max_concurrent ?? 8} 局，多出的排队`)}
  ${st.error ? `<div class="error">${esc(st.error)}</div>` : ""}
  <button class="btn primary big" type="submit" style="justify-content:center" ${st.creating ? "disabled" : ""}>${st.creating ? "正在开局…" : Number(f.count) > 1 ? `开始 ${f.count} 局` : "开始对局并进入裁判席"}</button>
  <div class="foot">开始后五位玩家先各收到一份系统提示，随后从第 1 次任务的讨论开始。中途关闭页面不影响对局，随时可以回来接着看。</div></form>`;
}

// ---------------------------------------------------------------- 玩家线程

export function renderThread(st) {
  const { id, pid, summary, messages, model: m, events, ui } = st;
  const asks = askLog(events, pid);
  const calls = events.filter((e) => e.kind === "llm_call" && e.player === pid);
  const role = m.assignments[pid], side = sideOf(role);
  const lastPrompt = calls.length ? calls[calls.length - 1].prompt_tokens : 0;
  const top = `<div class="topbar"><div class="row" style="gap:14px">${nav(`#/g/${id}`, icon("arrow-left", 16), "back")}<div class="crumb">${nav("#/", "对局列表")}<span class="sep">/</span>${nav(`#/g/${id}`, `<span class="mono">${id}</span>`)}<span class="sep">/</span><span class="serif" style="font-size:17px;font-weight:700;color:var(--ink)">${nameOf(pid, m)} 的完整线程</span></div></div><div class="row" style="gap:18px"><div class="seatpick">${PIDS.map((p) => `<button class="${p === pid ? "on" : ""}" data-act="nav" data-arg="#/g/${id}/p/${p}">${p}</button>`).join("")}</div><span class="vsep"></span><span class="counter mono">${messages.length} 条消息 · ${calls.length} 次调用 · 线程 ${fmtTokens(lastPrompt)}</span>${fileLink(id, `players/${pid}.json`, `<span class="btn outline">${icon("download", 13)}导出 ${pid}.json</span>`)}</div></div>`;
  const filters = [["all", "全部"], ["replies", "只看回复"], ["private", "只看私下分析"]];
  const hasReasoning = calls.some((c) => c.reasoning);
  const sub = `<div class="subhead"><div class="who">${avatar(pid, m, "m")}<div class="col" style="gap:2px"><div class="row"><span class="wname">${nameOf(pid, m)}</span>${sideChip(side)}<span style="font-size:12px;color:var(--ink2);display:inline-flex;align-items:center;gap:5px">${icon("eye", 11, "#9a9184")}${esc(hiddenInfo(pid, m.assignments))}</span></div><span class="wnote">每条裁判通知只包含它自己尚未看过的公开事件；这条线程从开局起从未清空，可见的私下分析是它唯一的跨轮记忆。${summary.random_players ? "随机玩家不调用模型，线程为空。" : ""}</span></div></div><div class="filters">${filters.map(([k, t]) => `<button class="filter ${st.filter === k ? "on" : ""}" data-act="thread-filter" data-arg="${k}">${t}</button>`).join("")}<button class="filter ${st.showReasoning ? "on" : ""}" data-act="thread-reasoning" ${hasReasoning ? "" : "disabled"} title="${hasReasoning ? "" : "本局关闭隐藏思考"}">隐藏推理${hasReasoning ? "" : " · 本局关闭"}</button></div></div>`;
  let pairIdx = 0;
  const items = messages.map((msg, i) => {
    if (msg.role === "system") {
      if (st.filter !== "all") return "";
      const open = isOpen(ui, "sys");
      return `<div class="msg"><span class="idx">#${i}</span><div class="mbody"><div class="mhead"><div class="row"><span class="badge system">系统</span><span class="mtitle">系统提示 · 规则、身份与格式</span></div><span class="meta mono">${countCn(msg.content)} 字 · 只发一次</span></div><div class="sys-text ${open ? "" : "clamp"}">${esc(msg.content)}</div><span class="expander" data-act="toggle" data-arg="sys">${open ? "收起" : "展开全文"}${icon(open ? "chev-up" : "chev-down", 12)}</span></div></div>`;
    }
    if (msg.role === "user") {
      const a = asks[pairIdx];
      if (st.filter !== "all") return "";
      const title = a ? `${a.ask.quest ? `第 ${a.ask.quest} 次任务 · ` : ""}请${ACTION_ZH[a.ask.action] || "行动"}${a.ask.attempt > 1 ? "（重答）" : ""}` : "裁判通知";
      const meta = a ? `${fmtTime(a.ask.ts)}${a.call ? ` · 输入 ${fmtInt(a.call.prompt_tokens)} token` : ""}` : "";
      return `<div class="msg"><span class="idx">#${i}</span><div class="mbody"><div class="mhead"><div class="row"><span class="badge user">裁判通知</span><span class="mtitle">${esc(title)}</span></div><span class="meta mono">${meta}</span></div><div class="notice-box">${esc(msg.content)}</div></div></div>`;
    }
    const a = asks[pairIdx++];
    const sections = parseReply(msg.content);
    const priv = sections.find((s) => s.private);
    if (st.filter === "private" && !priv) return "";
    const shown = st.filter === "private" ? sections.filter((s) => s.private) : sections;
    const call = a && a.call;
    const meta = call ? `${fmtSecs(call.latency_s)} · 输出 ${fmtInt(call.completion_tokens)} token · 缓存命中 ${fmtInt(call.cache_hit_tokens)}` : "";
    const title = a ? `回复 · ${ACTION_ZH[a.ask.action] || ""}` : "回复";
    const invalid = a && a.invalid ? `<div class="control-note red">裁判判定不合法：${esc(a.invalid.reason || "")}，已退回重答</div>` : "";
    const reasoning = st.showReasoning && call && call.reasoning ? `<div class="reasoning">${esc(call.reasoning)}</div>` : "";
    const body = shown.length ? `<div class="reply">${shown.map((s) => s.private ? `<div class="section private"><span class="marker">${icon("lock", 12)}${esc(s.marker)}<span class="dim">· 未进入任何人的公开事件</span></span><span class="stext">${esc(s.text)}</span></div>` : `<div class="section"><span class="marker">${esc(s.marker)}</span><span class="stext">${esc(s.text)}</span></div>`).join("")}</div>` : `<div class="notice-box">${esc(msg.content)}</div>`;
    return `<div class="msg"><span class="idx">#${i}</span><div class="mbody"><div class="mhead"><div class="row"><span class="badge assistant ${side}">${pid} 回复</span><span class="mtitle">${esc(title)}</span></div><span class="meta mono">${meta}</span></div>${reasoning}${body}${invalid}</div></div>`;
  }).join("");
  const left = panel("消息线程", "发给 API 的 messages 原样展示，顺序即发送顺序", `${messages.length} 条`, items || `<div class="empty">${summary.random_players ? "随机玩家没有消息线程。" : "线程尚未建立。"}</div>`);
  const callRows = calls.map((c, i) => { const a = asks.find((x) => x.call === c); return `<div class="crow"><span>${i + 1}</span><span class="act">${a ? ACTION_ZH[a.ask.action] : ""}</span><span>${fmtSecs(c.latency_s)}</span><span>${fmtInt(c.cache_hit_tokens)} / ${fmtInt(c.cache_miss_tokens)}</span><span>${fmtInt(c.completion_tokens)}</span><span>${c.cost_cny == null ? "—" : c.cost_cny.toFixed(4)}</span></div>`; }).join("");
  const cost = calls.reduce((s, c) => s + (c.cost_cny || 0), 0);
  const callsTable = `<div class="stats-card"><div class="shead"><span class="stitle">调用明细</span><span class="sright mono">${calls.length} 次 · ${cost.toFixed(4)} 元</span></div><div class="calls"><div class="crow head"><span>#</span><span class="act">行动</span><span>延迟</span><span>输入 命中 / 未命中</span><span>输出</span><span>费用 元</span></div>${callRows || `<div class="empty">无调用。</div>`}</div><div class="dim" style="font-size:12px;line-height:1.6">输入里的"命中"是前缀缓存命中的 token，只按十分之一以下计价。线程越长，命中占比越高。</div></div>`;
  const promptSum = calls.reduce((s, c) => s + (c.prompt_tokens || 0), 0), hitSum = calls.reduce((s, c) => s + (c.cache_hit_tokens || 0), 0), outSum = calls.reduce((s, c) => s + (c.completion_tokens || 0), 0);
  const privCount = messages.filter((x) => x.role === "assistant" && parseReply(x.content).some((s) => s.private)).length;
  const size = statsCard("线程规模", `至第 ${Math.max(0, messages.length - 1)} 条`, [
    ["系统提示", m2(`${countCn(messages[0] ? messages[0].content : "")} 字`)],
    ["累计输入", m2(fmtTokens(promptSum)) + dim(` · 命中 ${pct(hitSum, promptSum)}`)],
    ["累计输出", m2(fmtTokens(outSum))],
    ["最新一次", m2(fmtTokens(lastPrompt))],
    ["私下分析", `${privCount} 段` + dim(" · 均未外泄")],
  ], `${nav(`#/g/${id}`, "回到裁判席")}${fileLink(id, "events.jsonl", "下载裁判日志")}`);
  return top + sub + `<div class="main wide-right"><div>${left}</div><div>${callsTable}${size}</div></div>`;
}
const MARKS = ["【私下分析】", "【公开发言】", "【队伍】", "【投票】", "【任务】", "【刺杀】"];
export function parseReply(text) {
  const re = new RegExp(`(${MARKS.join("|")})`, "g");
  const parts = text.split(re);
  const out = [];
  for (let i = 1; i < parts.length; i += 2) {
    const marker = parts[i], body = (parts[i + 1] || "").trim();
    out.push({ marker, text: body, private: marker === "【私下分析】" });
  }
  if (!out.length && text.trim()) out.push({ marker: "原文", text: text.trim(), private: false });
  return out;
}

// ---------------------------------------------------------------- 复盘稿

export function renderReport(st) {
  const top = `<div class="topbar"><div class="row" style="gap:14px">${nav(`#/g/${st.id}`, icon("arrow-left", 16), "back")}<div class="crumb">${nav("#/", "对局列表")}<span class="sep">/</span>${nav(`#/g/${st.id}`, `<span class="mono">${st.id}</span>`)}<span class="sep">/</span><span class="serif" style="font-size:17px;font-weight:700;color:var(--ink)">复盘稿</span></div></div><div class="row" style="gap:12px"><span class="counter mono">transcript.md</span>${fileLink(st.id, "transcript.md", `<span class="btn outline">${icon("download", 13)}下载</span>`)}</div></div>`;
  return top + `<div class="main" style="grid-template-columns:minmax(0,1fr)"><div class="panel md">${st.markdown == null ? `<div class="empty">正在读取…</div>` : markdown(st.markdown)}</div></div>`;
}

// ---------------------------------------------------------------- 设置

export function renderSettings(st) {
  const top = `<div class="topbar"><div class="row" style="gap:14px">${nav("#/", icon("arrow-left", 16), "back")}<div class="crumb">${nav("#/", "对局列表")}<span class="sep">/</span><span class="serif" style="font-size:17px;font-weight:700;color:var(--ink)">设置</span></div></div><span class="counter mono">只存在这台浏览器里</span></div>`;
  const rows = SETTINGS.map((s) => `<div class="setting"><div class="shead2"><span class="stitle2">${esc(s.title)}</span><span class="hint">${esc(s.hint)}</span></div><div class="filters">${s.options.map(([v, label]) => `<button class="filter ${String(st.settings[s.key]) === v ? "on" : ""}" data-act="set" data-arg="${s.key}:${v}">${esc(label)}</button>`).join("")}</div></div>`).join("");
  return top + `<div class="main" style="grid-template-columns:minmax(0,720px)"><div>${panel("裁判席设置", "改动立即生效，只影响这台浏览器", "", `<div class="settings">${rows}</div>`)}</div></div>`;
}
