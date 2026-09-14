"""所有面向模型的文本，以及答案的解析。

其他模块不得包含任何面向模型的文字。改提示词只改这里。
包括：system prompt、公开事件的文字、计分板、各行动的指令、退回重答的说明、兜底文字、答案解析。
"""

from __future__ import annotations

import re

from avalon.player import Action, Notice, Reply
from avalon.rules import (
    MAX_PROPOSALS_PER_QUEST,
    PLAYER_IDS,
    QUEST_SIZES,
    VOTES_TO_APPROVE,
    WINS_NEEDED,
    HiddenInfo,
    Role,
    Side,
    side_of,
)
from avalon.state import GameState

MARK_PRIVATE = "【私下分析】"
MARK_SPEECH = "【公开发言】"
MARK_TEAM = "【队伍】"
MARK_VOTE = "【投票】"
MARK_QUEST = "【任务】"
MARK_ASSASSINATE = "【刺杀】"

ALL_MARKS = (MARK_PRIVATE, MARK_SPEECH, MARK_TEAM, MARK_VOTE, MARK_QUEST, MARK_ASSASSINATE)

ROLE_NAMES_ZH: dict[Role, str] = {
    Role.MERLIN: "梅林（Merlin）",
    Role.PERCIVAL: "派西维尔（Percival）",
    Role.LOYAL_SERVANT: "忠臣（Loyal Servant）",
    Role.MORGANA: "莫甘娜（Morgana）",
    Role.ASSASSIN: "刺客（Assassin）",
}

SIDE_NAMES_ZH: dict[Side, str] = {Side.GOOD: "好人", Side.EVIL: "邪恶"}

FALLBACK_SPEECH = "（{pid} 本次弃权）"


# ---------------------------------------------------------------- system prompt


def _hidden_info_text(role: Role, hidden: HiddenInfo) -> str:
    if role == Role.MERLIN:
        a, b = hidden.evil_players
        return f"你知道邪恶阵营的两人是 {a} 和 {b}。其中一人是莫甘娜、一人是刺客，你不知道谁是谁。"
    if role == Role.PERCIVAL:
        a, b = hidden.merlin_or_morgana
        return f"你知道 {a} 和 {b} 之中一人是梅林、一人是莫甘娜，但不知道谁是谁。"
    if role == Role.MORGANA:
        return f"你的邪恶同伴是 {hidden.fellow_evil}，对方是刺客。其余三人都是好人。"
    if role == Role.ASSASSIN:
        return f"你的邪恶同伴是 {hidden.fellow_evil}，对方是莫甘娜。其余三人都是好人。"
    return "你没有任何隐藏信息，只能依靠公开发言、队伍、投票和任务结果推理。"


def _goal_text(role: Role) -> str:
    if side_of(role) == Side.GOOD:
        goal = f"让 {WINS_NEEDED} 次任务成功，并且局末梅林不被刺客刺中。"
        if role == Role.MERLIN:
            goal += " 你掌握全部信息，但一旦暴露身份就会在局末被刺杀，需要在引导好人和隐藏自己之间取得平衡。"
        return goal
    goal = f"让 {WINS_NEEDED} 次任务失败；或者在好人达成 {WINS_NEEDED} 次成功后，由刺客刺中梅林。"
    if role == Role.MORGANA:
        goal += " 在派西维尔眼中你与梅林无法区分，可以伪装成梅林误导好人。"
    if role == Role.ASSASSIN:
        goal += " 局末若好人 3 胜，由你独自指定刺杀目标，请全程留意谁最像梅林。"
    return goal


def system_prompt(player_id: str, role: Role, hidden: HiddenInfo) -> str:
    """规则摘要、座位、角色、隐藏信息、阵营目标、输出格式、发言风格要求。"""
    sizes = "、".join(str(n) for n in QUEST_SIZES)
    return f"""你正在参加一局五人阿瓦隆桌游。五名玩家全部由 AI 扮演，座位编号 P1 到 P5，顺时针排列，P5 的下一位是 P1。你是 {player_id}。

# 规则

角色共五个，每人一个：好人阵营是梅林、派西维尔、忠臣；邪恶阵营是莫甘娜、刺客。
- 梅林开局知道两名邪恶玩家是谁，但不知道谁是莫甘娜、谁是刺客。
- 派西维尔开局知道两个人，其中一人是梅林、一人是莫甘娜，不知道谁是谁。
- 忠臣没有任何隐藏信息。
- 莫甘娜与刺客彼此知道对方是谁。

一局最多 5 次任务，第 1 到第 5 次任务的队伍人数依次为 {sizes}。任一阵营先达到 {WINS_NEEDED} 次即分出胜负。

每次任务的流程：
1. 裁判随机指定一名队长。
2. 队长先发言一次；然后从队长的下一位开始顺时针，其余四人各发言一次；最后回到队长做总结发言，并在同一次行动中指派队伍。每次只有一人发言，发言者能看到此前全部公开内容。
3. 全体五人同时对队伍投赞成或反对，不发言。赞成达到 {VOTES_TO_APPROVE} 票则通过。
4. 通过：队伍成员各自私下出一张任务牌。好人只能出成功；邪恶可以出成功或失败。出现 1 张失败牌任务即失败。裁判公布任务成败与失败牌张数，不公布出自谁。
5. 否决：队长顺时针换下一位，回到第 2 步。同一次任务内累计 {MAX_PROPOSALS_PER_QUEST} 次否决，邪恶直接获胜。

终局：邪恶累计 3 次任务失败则邪恶获胜。好人累计 3 次任务成功后进入刺杀：刺客独自指定一名玩家，刺中梅林则邪恶获胜，否则好人获胜。

队伍指派后直接投票，没有讨论环节。你若对队伍有要求，要在轮转发言时说清楚自己接受什么样的队伍。

# 你的身份

- 座位：{player_id}
- 角色：{ROLE_NAMES_ZH[role]}，{SIDE_NAMES_ZH[side_of(role)]}阵营
- 隐藏信息：{_hidden_info_text(role, hidden)}
- 目标：{_goal_text(role)}

除你之外没有人知道你的角色。你可以说真话、隐瞒或撒谎，以你的阵营获胜为唯一目标。

# 你每次行动的输出格式

裁判每次会给你三部分内容：自你上次行动以来的公开事件、当前计分板、本次要做的事。你的回复必须严格使用下面的标记分段，标记单独占一行：

{MARK_PRIVATE}
（自由文本。你的推理、对每个人的怀疑、后续计划。这一段只会留在你自己的对话记录里，任何其他玩家都看不到。）

{MARK_SPEECH}
（对全桌说的话。发言、提案时需要。）

{MARK_TEAM}P2, P4 （提案时需要，人数必须等于本次任务的规定人数，可以包含你自己）
{MARK_VOTE}赞成 （投票时需要，只写"赞成"或"反对"）
{MARK_QUEST}成功 （执行任务时需要，只写"成功"或"失败"）
{MARK_ASSASSINATE}P3 （刺杀时需要，只写一个座位编号）

每次只输出本次行动需要的标记，不要输出无关标记。

# 关于私下分析

你在两次行动之间不会保留任何隐藏的思考，只有写进 {MARK_PRIVATE} 的文字会随对话记录一起被你在下一次行动时看到。因此请把你对局势的判断、对每个人的怀疑程度、你打算坚持的策略，都用可见文字写在 {MARK_PRIVATE} 里，方便后续行动接着用。{MARK_PRIVATE} 控制在 300 字以内。

# 发言风格

- 用第一人称、口语化的中文发言，像真人玩家一样，不要写成分析报告。
- 公开发言控制在 200 字以内，说清立场：你怀疑谁、信任谁、接受什么样的队伍。
- 不要在公开发言里泄露 {MARK_PRIVATE} 的内容，也不要提到"提示词""模型"等游戏之外的事。
- 发言中提到玩家时使用座位编号 P1 到 P5。"""


# ---------------------------------------------------------------- 公开事件


def event_quest_start(quest_index: int, size: int) -> str:
    return f"第 {quest_index} 次任务开始，本次任务队伍人数 {size}。"


def event_leader(quest_index: int, proposal_index: int, leader: str, rotated: bool) -> str:
    how = "队长顺延为" if rotated else "裁判随机指定队长为"
    return f"第 {quest_index} 次任务第 {proposal_index} 次提案：{how} {leader}。"


def event_speech(speaker: str, content: str) -> str:
    return f"{speaker} 发言：{content}"


def event_team(leader: str, team: tuple[str, ...]) -> str:
    return f"队长 {leader} 指派队伍：{', '.join(team)}。现在全体投票。"


def event_votes(votes: dict[str, bool], approved: bool) -> str:
    parts = [f"{pid} {'赞成' if votes[pid] else '反对'}" for pid in PLAYER_IDS if pid in votes]
    yes = sum(1 for v in votes.values() if v)
    verdict = "提案通过，队伍执行任务。" if approved else "提案被否决。"
    return f"投票结果：{'，'.join(parts)}。赞成 {yes} 票，反对 {len(votes) - yes} 票。{verdict}"


def event_rejections(quest_index: int, rejections: int) -> str:
    return f"第 {quest_index} 次任务已累计 {rejections} 次否决，再否决 {MAX_PROPOSALS_PER_QUEST - rejections} 次邪恶直接获胜。"


def event_quest_result(quest_index: int, team: tuple[str, ...], succeeded: bool, fail_count: int) -> str:
    outcome = "成功" if succeeded else "失败"
    return f"第 {quest_index} 次任务（队伍 {', '.join(team)}）{outcome}，失败牌 {fail_count} 张。"


def event_score(success_count: int, fail_count: int) -> str:
    return f"当前比分：好人 {success_count} 胜，邪恶 {fail_count} 胜。"


def event_assassination_phase() -> str:
    return "好人已达成 3 次任务成功，进入刺杀阶段，由刺客指定目标。"


def event_game_over(winner: Side, win_reason: str, assignments: dict[str, Role], target: str | None) -> str:
    reasons = {
        "three_failures": "邪恶累计 3 次任务失败",
        "five_rejections": "同一次任务内累计 5 次否决",
        "merlin_assassinated": f"刺客刺中了梅林 {target}",
        "three_successes_and_merlin_safe": f"好人 3 次任务成功，刺客刺杀 {target} 未中梅林",
    }
    roles = "，".join(f"{pid} 是{ROLE_NAMES_ZH[assignments[pid]]}" for pid in PLAYER_IDS)
    return f"游戏结束：{SIDE_NAMES_ZH[winner]}阵营获胜，原因是{reasons.get(win_reason, win_reason)}。角色公布：{roles}。"


# ---------------------------------------------------------------- 计分板


def render_scoreboard(state: GameState) -> str:
    lines: list[str] = []
    if state.quests:
        q = state.current_quest
        p = q.proposals[-1] if q.proposals else None
        head = f"当前：第 {q.index} 次任务（{q.size} 人）"
        if p is not None:
            head += f"，第 {p.index} 次提案，队长 {p.leader}，本次任务已否决 {q.rejections} 次"
        lines.append(head)
    lines.append(f"比分：好人 {state.success_count} 胜，邪恶 {state.fail_count} 胜（先到 {WINS_NEEDED} 胜）")
    lines.append("任务人数：" + "、".join(f"第{i + 1}次 {n} 人" for i, n in enumerate(QUEST_SIZES)))
    history: list[str] = []
    for q in state.quests:
        for p in q.proposals:
            if p.approved is None:
                continue
            yes = [pid for pid in PLAYER_IDS if p.votes.get(pid) is True]
            no = [pid for pid in PLAYER_IDS if p.votes.get(pid) is False]
            verdict = "通过" if p.approved else "否决"
            history.append(
                f"- 任务 {q.index} 提案 {p.index}：队长 {p.leader}，队伍 {', '.join(p.team)}；"
                f"赞成 {', '.join(yes) or '无'}；反对 {', '.join(no) or '无'}；{verdict}"
            )
        if q.succeeded is not None:
            history.append(
                f"- 任务 {q.index} 结果：{'成功' if q.succeeded else '失败'}，失败牌 {q.fail_count} 张"
            )
    if history:
        lines.append("历史记录：")
        lines.extend(history)
    return "\n".join(lines)


# ---------------------------------------------------------------- 指令


def instruction(
    action: Action,
    *,
    team_size: int | None = None,
    candidates: tuple[str, ...] = (),
    team: tuple[str, ...] = (),
    is_leader: bool = False,
) -> str:
    if action == Action.SPEAK:
        who = "你是本次提案的队长，请先发言" if is_leader else "轮到你发言"
        return (
            f"{who}。说明你目前的判断和你接受什么样的队伍。\n"
            f"输出：{MARK_PRIVATE} 和 {MARK_SPEECH} 两段。"
        )
    if action == Action.PROPOSE:
        return (
            f"你是队长，请做总结发言，并指派本次任务的队伍。队伍必须恰好 {team_size} 人，成员不重复，"
            f"可选 {', '.join(candidates)}，可以包含你自己。指派后直接投票，不再讨论。\n"
            f"输出：{MARK_PRIVATE}、{MARK_SPEECH}、{MARK_TEAM} 三段，{MARK_TEAM} 后写座位编号，用逗号分隔。"
        )
    if action == Action.VOTE:
        return (
            f"请对队伍 {', '.join(team)} 投票。所有人同时投票，不发言。\n"
            f"输出：{MARK_PRIVATE} 和 {MARK_VOTE} 两段，{MARK_VOTE} 后只写\"赞成\"或\"反对\"。"
        )
    if action == Action.EXECUTE_QUEST:
        return (
            f"你在本次任务的队伍 {', '.join(team)} 中。请私下出一张任务牌。"
            f"你是邪恶阵营，可以出成功或失败；出现 1 张失败牌任务即失败，裁判只公布失败牌张数。\n"
            f"输出：{MARK_PRIVATE} 和 {MARK_QUEST} 两段，{MARK_QUEST} 后只写\"成功\"或\"失败\"。"
        )
    if action == Action.ASSASSINATE:
        return (
            f"好人已达成 3 次任务成功。你是刺客，请在 {', '.join(candidates)} 中指定一人刺杀。"
            f"刺中梅林则邪恶获胜，否则好人获胜。\n"
            f"输出：{MARK_PRIVATE} 和 {MARK_ASSASSINATE} 两段，{MARK_ASSASSINATE} 后只写一个座位编号。"
        )
    raise ValueError(f"未知行动 {action}")


def render_notice(notice: Notice) -> str:
    """把 Notice 渲染为一条 user 消息。"""
    if notice.rejection_reason:
        return (
            f"你上一次的答案不合法：{notice.rejection_reason}\n"
            f"请只按要求的格式重新回答，不要解释。\n\n{notice.instruction}"
        )
    events = "\n".join(f"- {e}" for e in notice.public_events) or "- （无新事件）"
    return f"# 公开事件\n{events}\n\n# 计分板\n{notice.scoreboard}\n\n# 你的行动\n{notice.instruction}"


# ---------------------------------------------------------------- 解析

_MARK_RE = re.compile("|".join(re.escape(m) for m in ALL_MARKS))
_PID_RE = re.compile(r"P\s*([1-5])")

_APPROVE_WORDS = ("赞成", "同意", "通过", "approve", "yes")
_REJECT_WORDS = ("反对", "否决", "拒绝", "reject", "no")
_SUCCESS_WORDS = ("成功", "success")
_FAIL_WORDS = ("失败", "fail")


def _split(text: str) -> dict[str, str]:
    """按标记切段。同一标记多次出现时，文本类拼接，取值类以最后一次为准。"""
    sections: dict[str, str] = {}
    matches = list(_MARK_RE.finditer(text))
    if not matches:
        return sections
    lead = text[: matches[0].start()].strip()
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[m.end() : end].strip().strip("*：: \n").strip()
        mark = m.group(0)
        if mark in (MARK_PRIVATE, MARK_SPEECH) and mark in sections:
            sections[mark] = (sections[mark] + "\n" + body).strip()
        else:
            sections[mark] = body
    if MARK_PRIVATE not in sections and lead:
        sections[MARK_PRIVATE] = lead
    return sections


def _first_keyword(text: str, positive: tuple[str, ...], negative: tuple[str, ...]) -> bool | None:
    """在文本里找最先出现的关键词，正词返回 True，负词返回 False，都没有返回 None。"""
    low = text.lower()
    best: tuple[int, bool] | None = None
    for words, value in ((positive, True), (negative, False)):
        for w in words:
            i = low.find(w)
            if i >= 0 and (best is None or i < best[0]):
                best = (i, value)
    return None if best is None else best[1]


def parse_reply(text: str, action: Action) -> Reply:
    """按标记解析模型输出。格式不合法时抛 ValueError，由裁判决定退回重答。"""
    sections = _split(text)
    if not sections:
        raise ValueError(f"没有找到任何标记，请使用 {MARK_PRIVATE} 等标记分段")
    reply = Reply(private_analysis=sections.get(MARK_PRIVATE, ""), raw=text)

    if action in (Action.SPEAK, Action.PROPOSE):
        speech = sections.get(MARK_SPEECH, "")
        if not speech:
            raise ValueError(f"缺少 {MARK_SPEECH} 段或内容为空")
        reply.public_speech = speech

    if action == Action.PROPOSE:
        seg = sections.get(MARK_TEAM)
        if seg is None:
            raise ValueError(f"缺少 {MARK_TEAM} 段")
        team: list[str] = []
        for m in _PID_RE.finditer(seg.split("\n", 1)[0]):
            pid = f"P{m.group(1)}"
            if pid not in team:
                team.append(pid)
        if not team:
            raise ValueError(f"{MARK_TEAM} 后没有找到座位编号")
        reply.team = tuple(team)

    if action == Action.VOTE:
        seg = sections.get(MARK_VOTE)
        if seg is None:
            raise ValueError(f"缺少 {MARK_VOTE} 段")
        vote = _first_keyword(seg.split("\n", 1)[0], _APPROVE_WORDS, _REJECT_WORDS)
        if vote is None:
            raise ValueError(f"{MARK_VOTE} 后必须写\"赞成\"或\"反对\"")
        reply.vote = vote

    if action == Action.EXECUTE_QUEST:
        seg = sections.get(MARK_QUEST)
        if seg is None:
            raise ValueError(f"缺少 {MARK_QUEST} 段")
        card = _first_keyword(seg.split("\n", 1)[0], _SUCCESS_WORDS, _FAIL_WORDS)
        if card is None:
            raise ValueError(f"{MARK_QUEST} 后必须写\"成功\"或\"失败\"")
        reply.quest_success = card

    if action == Action.ASSASSINATE:
        seg = sections.get(MARK_ASSASSINATE)
        if seg is None:
            raise ValueError(f"缺少 {MARK_ASSASSINATE} 段")
        m = _PID_RE.search(seg)
        if not m:
            raise ValueError(f"{MARK_ASSASSINATE} 后必须写一个座位编号")
        reply.target = f"P{m.group(1)}"

    return reply


# ---------------------------------------------------------------- 校验失败的原因文字（退回给玩家）


def reason_bad_team_size(size: int) -> str:
    return f"队伍人数必须恰好 {size} 人"


def reason_bad_team_member(pid: str) -> str:
    return f"{pid} 不是有效的座位编号"


def reason_bad_target(target: str, candidates: tuple[str, ...]) -> str:
    return f"刺杀目标必须是 {', '.join(candidates)} 之一，不能是 {target}"


def reason_bad_speech() -> str:
    return f"缺少 {MARK_SPEECH} 段或内容为空"


def reason_missing_vote() -> str:
    return f"缺少 {MARK_VOTE} 段，必须写\"赞成\"或\"反对\""


def reason_missing_card() -> str:
    return f"缺少 {MARK_QUEST} 段，必须写\"成功\"或\"失败\""
