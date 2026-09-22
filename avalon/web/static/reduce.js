// 把裁判事件流归约成画面模型。回放就是只喂前 N 条事件再归约一次。
// 事件种类见 docs/architecture.md 第六节；这里不依赖 public.json，一切都从 events.jsonl 推出。

import { DEFAULT_PLAYERS, seatIds, questSizes } from "./util.js";

function seatsFrom(leader, pids) {
  const i = pids.indexOf(leader);
  return i < 0 ? [...pids] : [...pids.slice(i), ...pids.slice(0, i)];
}

function newTurnState() {
  return { calls: [], invalids: [] };
}

function newPerPlayer() {
  return { calls: 0, cost: 0, promptTokens: 0, completionTokens: 0, teams: 0, success: 0, fail: 0, failCards: 0, leaderCount: 0, spoke: 0 };
}

/** 事件里没有座位名单的旧局按 5 人。 */
function playersOf(events) {
  const start = events.find((e) => e.kind === "game_start");
  const seats = start && Array.isArray(start.players) ? start.players.length : 0;
  return seats || DEFAULT_PLAYERS;
}

export function reduce(events) {
  const players = playersOf(events);
  const pids = seatIds(players);
  const m = {
    players,
    pids,
    questSizes: questSizes(players),
    start: null,
    assignments: {},
    quests: [],
    phase: "INIT",
    pending: {},
    assassination: null,
    over: null,
    control: { paused: false, pausing: false, terminating: false, terminated: false, error: null, voided: [], log: [] },
    stats: { calls: 0, promptTokens: 0, completionTokens: 0, reasoningTokens: 0, cacheHit: 0, cacheMiss: 0, cost: 0, latencies: [], maxLatency: null, invalid: 0, fallbacks: 0, voided: 0 },
    perPlayer: Object.fromEntries(pids.map((p) => [p, newPerPlayer()])),
    successCount: 0,
    failCount: 0,
    firstTs: null,
    lastTs: null,
    lastSeq: 0,
    lastEvent: null,
    speechCount: 0,
    proposalCount: 0,
    turns: [],
  };
  const acc = Object.fromEntries(pids.map((p) => [p, newTurnState()]));
  // 万一事件里出现名单之外的座位，补一份空记录，画面不至于崩。
  const ensure = (pid) => {
    if (!pid) return;
    if (!m.perPlayer[pid]) m.perPlayer[pid] = newPerPlayer();
    if (!acc[pid]) acc[pid] = newTurnState();
  };
  const quest = () => m.quests[m.quests.length - 1];
  const proposal = () => { const q = quest(); return q && q.proposals[q.proposals.length - 1]; };

  for (const e of events) {
    if (!m.firstTs) m.firstTs = e.ts;
    m.lastTs = e.ts;
    m.lastSeq = e.seq;
    m.lastEvent = e;
    ensure(e.player);
    switch (e.kind) {
      case "game_start":
        m.start = { seed: e.seed, seatModels: e.seat_models || {}, thinking: !!e.thinking, assignments: e.assignments || {}, ts: e.ts };
        m.assignments = e.assignments || {};
        break;
      case "quest_start":
        m.quests.push({ index: e.quest, size: e.size || m.questSizes[e.quest - 1], proposals: [], team: [], cards: {}, failCount: null, succeeded: null, startEvent: e, resultEvent: null });
        break;
      case "leader": {
        const q = quest();
        if (!q) break;
        ensure(e.leader);
        q.proposals.push({ index: e.proposal, leader: e.leader, rotated: !!e.rotated, leaderEvent: e, order: seatsFrom(e.leader, m.pids), speeches: [], proposeTurn: null, team: [], teamEvent: null, votes: {}, voteTurns: {}, approved: null, votesEvent: null, execTurns: {}, stage: "discussion" });
        m.perPlayer[e.leader].leaderCount += 1;
        m.proposalCount += 1;
        m.phase = "DISCUSSION";
        break;
      }
      case "ask":
        m.pending[e.player] = { event: e, action: e.action, attempt: e.attempt, ts: e.ts };
        if (e.action === "propose" && m.phase === "DISCUSSION") { m.phase = "PROPOSAL"; const p = proposal(); if (p) p.stage = "proposal"; }
        if (e.action === "assassinate") m.phase = "ASSASSINATION";
        break;
      case "llm_call": {
        const st = acc[e.player];
        st.calls.push(e);
        const s = m.stats, pp = m.perPlayer[e.player];
        s.calls += 1; pp.calls += 1;
        s.promptTokens += e.prompt_tokens || 0; pp.promptTokens += e.prompt_tokens || 0;
        s.completionTokens += e.completion_tokens || 0; pp.completionTokens += e.completion_tokens || 0;
        s.reasoningTokens += e.reasoning_tokens || 0;
        s.cacheHit += e.cache_hit_tokens || 0; s.cacheMiss += e.cache_miss_tokens || 0;
        s.cost += e.cost_cny || 0; pp.cost += e.cost_cny || 0;
        if (e.latency_s != null) {
          s.latencies.push(e.latency_s);
          if (!s.maxLatency || e.latency_s > s.maxLatency.v) s.maxLatency = { v: e.latency_s, pid: e.player, quest: quest() ? quest().index : null };
        }
        break;
      }
      case "invalid_reply":
        acc[e.player].invalids.push(e);
        m.stats.invalid += 1;
        delete m.pending[e.player];
        break;
      case "voided_call":
        m.stats.voided += 1;
        m.control.voided.push(e);
        delete m.pending[e.player];
        break;
      case "fallback":
        m.stats.fallbacks += 1;
        break;
      case "turn": {
        const st = acc[e.player];
        const turn = { event: e, seq: e.seq, ts: e.ts, pid: e.player, action: e.action, attempt: e.attempt, private: e.private_analysis || "", speech: e.speech || null, team: e.team || null, vote: e.vote ?? null, card: e.card ?? null, target: e.target ?? null, fallback: !!e.fallback, calls: st.calls, invalids: st.invalids, quest: e.quest, proposal: e.proposal };
        turn.latency = turn.calls.reduce((a, c) => a + (c.latency_s || 0), 0);
        turn.tokensOut = turn.calls.reduce((a, c) => a + (c.completion_tokens || 0), 0);
        turn.reasoning = turn.calls.map((c) => c.reasoning).filter(Boolean);
        acc[e.player] = newTurnState();
        delete m.pending[e.player];
        m.turns.push(turn);
        const p = proposal();
        if (e.action === "speak" && p) { p.speeches.push(turn); m.speechCount += 1; m.perPlayer[e.player].spoke += 1; if (p.speeches.length >= m.players) { m.phase = "PROPOSAL"; p.stage = "proposal"; } }
        else if (e.action === "propose" && p) { p.proposeTurn = turn; m.speechCount += 1; }
        else if (e.action === "vote" && p) { p.voteTurns[e.player] = turn; p.votes[e.player] = !!e.vote; }
        else if (e.action === "execute_quest" && p) { p.execTurns[e.player] = turn; const q = quest(); if (q) q.cards[e.player] = !!e.card; if (e.card === false) m.perPlayer[e.player].failCards += 1; }
        else if (e.action === "assassinate") { m.assassination = { ...(m.assassination || {}), assassin: e.player, target: e.target, turn }; }
        break;
      }
      case "team": {
        const p = proposal();
        if (!p) break;
        p.team = e.team || [];
        p.teamEvent = e;
        p.stage = "voting";
        m.phase = "VOTING";
        break;
      }
      case "votes": {
        const p = proposal(), q = quest();
        if (!p) break;
        p.votes = e.votes || {};
        p.approved = !!e.approved;
        p.votesEvent = e;
        if (p.approved) {
          p.stage = "execution";
          m.phase = "QUEST_EXECUTION";
          if (q) { q.team = p.team; for (const pid of p.team) m.perPlayer[pid].teams += 1; }
        } else {
          p.stage = "done";
          m.phase = "DISCUSSION";
        }
        break;
      }
      case "quest_result": {
        const q = quest(), p = proposal();
        if (!q) break;
        q.cards = e.cards || q.cards;
        q.failCount = e.fail_count;
        q.succeeded = !!e.succeeded;
        q.resultEvent = e;
        if (p) p.stage = "result";
        if (q.succeeded) { m.successCount += 1; for (const pid of q.team) m.perPlayer[pid].success += 1; }
        else { m.failCount += 1; for (const pid of q.team) m.perPlayer[pid].fail += 1; }
        m.phase = m.failCount >= 3 ? "QUEST_RESULT" : m.successCount >= 3 ? "ASSASSINATION" : "QUEST_RESULT";
        break;
      }
      case "assassination":
        m.assassination = { ...(m.assassination || {}), assassin: e.assassin, target: e.target, hit: !!e.hit, event: e };
        break;
      case "game_over":
        m.over = { winner: e.winner, reason: e.win_reason, target: e.assassination_target, event: e };
        if (e.assignments) m.assignments = e.assignments;
        m.phase = "GAME_OVER";
        break;
      case "pause_requested": m.control.pausing = true; m.control.log.push(e); break;
      case "pause_forced": m.control.log.push(e); break;
      case "paused": m.control.paused = true; m.control.pausing = false; m.control.log.push(e); break;
      case "resumed": m.control.paused = false; m.control.pausing = false; m.control.log.push(e); break;
      case "terminate_requested": m.control.terminating = true; m.control.log.push(e); break;
      case "terminated": m.control.terminated = true; m.control.terminating = false; m.control.paused = false; m.control.pausing = false; m.control.log.push(e); m.pending = {}; break;
      case "error": m.control.error = e.message || "未知错误"; m.control.log.push(e); m.pending = {}; break;
      default: break;
    }
  }
  return m;
}

/** 态势条与标题需要的"当前在第几步"。 */
export function stepIndex(phase) {
  return { INIT: -1, DISCUSSION: 0, PROPOSAL: 1, VOTING: 2, QUEST_EXECUTION: 3, QUEST_RESULT: 4, ASSASSINATION: 5, GAME_OVER: 6 }[phase] ?? -1;
}

export function currentQuest(m) { return m.quests[m.quests.length - 1] || null; }
export function currentProposal(m) { const q = currentQuest(m); return q ? q.proposals[q.proposals.length - 1] || null : null; }

/** 对局标题，如"第 3 次任务 · 第 1 次提案 · 队长 P1"。 */
export function situationTitle(m) {
  if (m.over) return m.over.winner === "good" ? "游戏结束 · 好人阵营获胜" : "游戏结束 · 邪恶阵营获胜";
  if (m.control.terminated) return "对局已终止";
  if (m.control.error) return "对局出错中止";
  if (m.phase === "ASSASSINATION") {
    const a = m.pids.find((p) => m.assignments[p] === "Assassin");
    return `刺杀阶段 · 刺客 ${a || "?"} 选择目标`;
  }
  const q = currentQuest(m), p = currentProposal(m);
  if (!q) return "开局";
  if (!p) return `第 ${q.index} 次任务`;
  return `第 ${q.index} 次任务 · 第 ${p.index} 次提案 · 队长 ${p.leader}`;
}

/** 任务圆圈的状态列表（一局最多五次任务）。 */
export function questStates(m) {
  return m.questSizes.map((_, i) => {
    const q = m.quests[i];
    if (!q) return "upcoming";
    if (q.succeeded === true) return "success";
    if (q.succeeded === false) return "fail";
    return m.over || m.control.terminated || m.control.error ? "upcoming" : "current";
  });
}

/** 刺客在公开信息里能看到的线索，按候选人汇总。 */
export function publicClues(m, pid) {
  const rows = [];
  const teams = m.quests.filter((q) => q.team.includes(pid) && q.succeeded !== null);
  if (teams.length) {
    const ok = teams.filter((q) => q.succeeded).length;
    rows.push(ok === teams.length ? `上队 ${teams.length} 次，全部成功` : `上队 ${teams.length} 次，其中 ${teams.length - ok} 次任务失败`);
  } else rows.push("从未上队");
  const led = m.quests.flatMap((q) => q.proposals.filter((p) => p.leader === pid && p.team.length).map((p) => ({ q, p })));
  if (led.length) rows.push(`当队长 ${led.length} 次，提出的队伍 ${led.filter((x) => x.p.approved).length} 次通过`);
  const badYes = m.quests.flatMap((q) => q.proposals.filter((p) => p.approved && q.succeeded === false && p.votes[pid] === true)).length;
  const badNo = m.quests.flatMap((q) => q.proposals.filter((p) => p.approved && q.succeeded === false && p.votes[pid] === false)).length;
  if (badYes || badNo) rows.push(`对后来失败的队伍：赞成 ${badYes} 次，反对 ${badNo} 次`);
  rows.push(`发言 ${m.perPlayer[pid].spoke} 次`);
  return rows;
}

/** 到某一时刻为止的暂停秒数（只算"没有任何调用在跑"的时间，与 recorder.paused_seconds 一致）。 */
export function pausedSeconds(log, untilTs) {
  let total = 0, since = null;
  for (const e of log) {
    if (e.kind === "paused" && since === null) since = Date.parse(e.ts);
    else if (e.kind === "resumed" && since !== null) { total += (Date.parse(e.ts) - since) / 1000; since = null; }
  }
  if (since !== null && untilTs) total += Math.max(0, (Date.parse(untilTs) - since) / 1000);
  return total;
}

/** 每名玩家收到的通知序列：第 k 条非作废的提问 ↔ 线程里第 k 对 user/assistant 消息。 */
export function askLog(events, pid) {
  const asks = [];
  for (const e of events) {
    if (e.player !== pid) continue;
    if (e.kind === "ask") asks.push({ ask: e, call: null, turn: null, invalid: null, voided: false });
    else if (!asks.length) continue;
    else if (e.kind === "voided_call") asks[asks.length - 1].voided = true;
    else if (e.kind === "llm_call") asks[asks.length - 1].call = e;
    else if (e.kind === "turn") asks[asks.length - 1].turn = e;
    else if (e.kind === "invalid_reply") asks[asks.length - 1].invalid = e;
  }
  return asks.filter((a) => !a.voided);
}

/** 一条事件的一句话描述，回放卡片用。 */
export function describeEvent(e) {
  if (!e) return "";
  const who = e.player || "";
  switch (e.kind) {
    case "game_start": return "开局，分配角色";
    case "quest_start": return `第 ${e.quest} 次任务开始（${e.size} 人）`;
    case "leader": return `第 ${e.quest} 次任务 · 第 ${e.proposal} 次提案 · 队长 ${e.leader}`;
    case "ask": return `裁判向 ${who} 发出${{ speak: "发言", propose: "提案", vote: "投票", execute_quest: "出牌", assassinate: "刺杀" }[e.action] || ""}通知`;
    case "llm_call": return `${who} 的模型返回（${e.latency_s} 秒）`;
    case "turn": return `${who} ${{ speak: "发言", propose: "提出队伍", vote: e.vote ? "投赞成" : "投反对", execute_quest: e.card ? "出成功牌" : "出失败牌", assassinate: `刺杀 ${e.target}` }[e.action] || ""}`;
    case "invalid_reply": return `${who} 的答案不合法，退回重答`;
    case "fallback": return `${who} 连续不合法，裁判兜底`;
    case "team": return `队长 ${e.leader} 提出队伍 ${(e.team || []).join("、")}`;
    case "votes": return `投票${e.approved ? "通过" : "否决"}`;
    case "quest_result": return `第 ${e.quest} 次任务${e.succeeded ? "成功" : "失败"}`;
    case "assassination": return `刺客 ${e.assassin} 刺杀 ${e.target}，${e.hit ? "命中" : "未中"}`;
    case "game_over": return `游戏结束，${e.winner === "good" ? "好人" : "邪恶"}获胜`;
    case "voided_call": return `${who} 的一次调用被掐断`;
    case "pause_requested": return "管理员请求暂停";
    case "pause_forced": return "管理员掐断进行中的调用";
    case "paused": return "对局已暂停";
    case "resumed": return "对局继续";
    case "terminate_requested": return "管理员请求终止";
    case "terminated": return "对局已终止";
    case "error": return `出错：${e.message || ""}`;
    default: return e.kind;
  }
}

// ---------------------------------------------------------------- 事件的粗细两档

const PARALLEL = new Set(["vote", "execute_quest"]);
const CONTROL = new Set(["pause_requested", "pause_forced", "paused", "resumed", "terminate_requested", "terminated"]);
const ACTION_KINDS = new Set(["ask", "llm_call", "invalid_reply", "fallback", "voided_call", "turn"]);

/**
 * 简略版事件（"步"）：把同一次行动的提问、模型返回、答案合成一步，五路并行的投票合成一步，
 * 任务开始与队长指定合成一步，连续的暂停类操作合成一步。每步记录它包含的原始事件序号，
 * 以最后一条的序号作为落点。行动可以被暂停类事件打断，所以一步的事件不一定连续。
 */
export function buildSteps(events) {
  const players = playersOf(events);
  const steps = [];
  const open = {}; // 行动的键 -> 未结束的步
  let questStep = null, controlStep = null;
  const push = (step) => { steps.push(step); return step; };
  const keyOf = (e) => (PARALLEL.has(e.action) ? `${e.action}` : `${e.player}:${e.action}`);
  const finish = (step) => { step.done = true; };

  for (const e of events) {
    if (e.kind !== "leader") questStep = null;
    if (!CONTROL.has(e.kind)) controlStep = null;
    if (e.kind === "game_start") { push({ kind: "game_start", seqs: [e.seq], events: [e], done: true }); continue; }
    if (e.kind === "quest_start") { questStep = push({ kind: "quest", seqs: [e.seq], events: [e], done: true }); continue; }
    if (e.kind === "leader") {
      if (questStep) { questStep.seqs.push(e.seq); questStep.events.push(e); questStep = null; }
      else push({ kind: "leader", seqs: [e.seq], events: [e], done: true });
      continue;
    }
    if (ACTION_KINDS.has(e.kind)) {
      const action = e.action || (e.kind === "llm_call" ? guessAction(open, e.player) : null);
      const key = PARALLEL.has(action) ? action : `${e.player}:${action}`;
      let step = open[key];
      if (!step) step = open[key] = push({ kind: "action", action, players: [], seqs: [], events: [], done: false });
      if (e.player && !step.players.includes(e.player)) step.players.push(e.player);
      step.seqs.push(e.seq); step.events.push(e);
      // 发言在答案处收尾；提案要等随后的 team 事件，投票与出牌等收齐，刺杀等裁判判定。
      if (e.kind === "turn" && action === "speak") { finish(step); delete open[key]; }
      continue;
    }
    if (e.kind === "team") { const key = `${e.leader}:propose`; const step = open[key]; if (step) { step.seqs.push(e.seq); step.events.push(e); finish(step); delete open[key]; } else push({ kind: "team", seqs: [e.seq], events: [e], done: true }); continue; }
    if (e.kind === "votes") { const step = open["vote"]; if (step) { step.seqs.push(e.seq); step.events.push(e); finish(step); delete open["vote"]; } else push({ kind: "votes", seqs: [e.seq], events: [e], done: true }); continue; }
    if (e.kind === "quest_result") { const step = open["execute_quest"] || push({ kind: "action", action: "execute_quest", players: [], seqs: [], events: [], done: false }); step.seqs.push(e.seq); step.events.push(e); finish(step); delete open["execute_quest"]; continue; }
    if (e.kind === "assassination") { const key = `${e.assassin}:assassinate`; const step = open[key]; if (step) { step.seqs.push(e.seq); step.events.push(e); finish(step); delete open[key]; } else push({ kind: "assassination", seqs: [e.seq], events: [e], done: true }); continue; }
    if (CONTROL.has(e.kind)) {
      if (controlStep && !(e.kind === "resumed") && !(controlStep.events.some((x) => x.kind === "resumed"))) { controlStep.seqs.push(e.seq); controlStep.events.push(e); }
      else controlStep = push({ kind: "control", seqs: [e.seq], events: [e], done: true });
      continue;
    }
    push({ kind: e.kind, seqs: [e.seq], events: [e], done: true });
  }
  // 每步以最后一条事件为落点，按落点排序、编号。
  for (const s of steps) { s.end = Math.max(...s.seqs); s.start = Math.min(...s.seqs); }
  steps.sort((a, b) => a.end - b.end);
  steps.forEach((s, i) => { s.index = i + 1; s.title = stepTitle(s, players); });
  return steps;
}

function guessAction(open, pid) {
  for (const key of Object.keys(open)) {
    if (key.startsWith(`${pid}:`)) return key.split(":")[1];
    if (PARALLEL.has(key) && open[key].players.includes(pid)) return key;
  }
  return null;
}

/** 详细版：一条原始事件一步。 */
export function rawSteps(events) {
  return events.map((e, i) => ({ kind: e.kind, seqs: [e.seq], events: [e], done: true, end: e.seq, start: e.seq, index: i + 1, title: describeEvent(e) }));
}

/** 序号 seq 处于第几步（落点 ≤ seq 的步数）。 */
export function stepIndexAt(steps, seq) {
  let n = 0;
  for (const s of steps) { if (s.end <= seq) n = s.index; else break; }
  return n;
}

const ACT = { speak: "发言", propose: "提案", vote: "投票", execute_quest: "出牌", assassinate: "刺杀" };

export function stepTitle(step, players = DEFAULT_PLAYERS) {
  const ev = step.events, last = ev[ev.length - 1];
  const has = (k) => ev.some((e) => e.kind === k);
  switch (step.kind) {
    case "game_start": return "开局，分配角色";
    case "quest": { const q = ev.find((e) => e.kind === "quest_start"); const l = ev.find((e) => e.kind === "leader"); return `第 ${q.quest} 次任务开始（${q.size} 人）${l ? `，队长 ${l.leader}` : ""}`; }
    case "leader": return `第 ${last.quest} 次任务 · 第 ${last.proposal} 次提案，队长顺延到 ${last.leader}`;
    case "control": {
      if (has("terminated") || has("terminate_requested")) return has("terminated") ? "管理员终止了对局" : "管理员请求终止";
      if (has("resumed")) return "管理员继续了对局";
      if (has("pause_forced")) return has("paused") ? "管理员掐断进行中的调用并暂停" : "管理员掐断进行中的调用";
      return has("paused") ? "管理员暂停了对局" : "管理员请求暂停";
    }
    case "action": {
      const a = step.action;
      const turns = ev.filter((e) => e.kind === "turn");
      const retries = ev.filter((e) => e.kind === "invalid_reply").length;
      const voided = ev.filter((e) => e.kind === "voided_call").length;
      const extra = [retries ? `重答 ${retries} 次` : "", voided ? `被掐断 ${voided} 次` : "", ev.some((e) => e.kind === "fallback") ? "兜底" : ""].filter(Boolean);
      const suffix = extra.length ? `（${extra.join("，")}）` : "";
      if (a === "speak") { const t = turns[0]; return t ? `${t.player} 发言${suffix}` : `${step.players[0] || ""} 正在发言${suffix}`; }
      if (a === "propose") { const t = turns[0]; const team = ev.find((e) => e.kind === "team"); return t ? `队长 ${t.player} 提出队伍 ${(team ? team.team : t.team || []).join("、")}${suffix}` : `队长 ${step.players[0] || ""} 正在指派队伍${suffix}`; }
      if (a === "vote") { const v = ev.find((e) => e.kind === "votes"); if (v) { const yes = Object.values(v.votes).filter(Boolean).length; return `全体投票：${yes} : ${Object.keys(v.votes).length - yes} ${v.approved ? "通过" : "否决"}${suffix}`; } return `全体投票中，已收到 ${turns.length} / ${players}${suffix}`; }
      if (a === "execute_quest") { const r = ev.find((e) => e.kind === "quest_result"); if (r) return `第 ${r.quest} 次任务执行与结算：${r.succeeded ? "成功" : `失败，${r.fail_count} 张失败牌`}${suffix}`; return `任务执行中，${step.players.join("、")} 出牌${suffix}`; }
      if (a === "assassinate") { const r = ev.find((e) => e.kind === "assassination"); if (r) return `刺客 ${r.assassin} 刺杀 ${r.target}，${r.hit ? "命中梅林" : "未中"}${suffix}`; return `刺客 ${step.players[0] || ""} 正在选择目标${suffix}`; }
      return describeEvent(last);
    }
    default: return describeEvent(last);
  }
}
