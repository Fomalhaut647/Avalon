"""裁判：状态机主循环。

推进阶段、决定轮到谁、组装 Notice、校验 Reply、兜底、把公开动作写入公开记录。
阶段与转移见 docs/architecture.md 第四节，规则见 docs/rules.md。
"""

from __future__ import annotations

import random
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from avalon import prompts, rules
from avalon.config import Config
from avalon.player import Action, InvalidReply, Notice, Player, Reply
from avalon.recorder import Recorder
from avalon.rules import PLAYER_IDS, Role, Side
from avalon.state import GameState, Phase, Proposal, Quest, Speech

Validator = Callable[[Reply], str | None]
"""返回 None 表示合法，否则返回退回给玩家的原因。"""


class Referee:
    def __init__(
        self,
        players: dict[str, Player],
        config: Config,
        recorder: Recorder,
        rng: random.Random,
        on_public: Callable[[str], None] | None = None,
        on_private: Callable[[str, str, str], None] | None = None,
    ) -> None:
        self.players = players
        self.config = config
        self.recorder = recorder
        self.rng = rng
        self.on_public = on_public
        self.on_private = on_private
        self.state = GameState(game_id=recorder.game_dir.name, seed=config.seed)
        self.public_log: list[str] = []
        """全部公开事件的文字，按时间排列。"""
        self.cursor: dict[str, int] = {pid: 0 for pid in PLAYER_IDS}
        """每名玩家已经收到的公开事件数。"""

    # ------------------------------------------------------------ 主循环

    def run(self) -> GameState:
        """跑完一局，返回终局状态。"""
        handlers = {
            Phase.INIT: self._init,
            Phase.DISCUSSION: self._discussion,
            Phase.PROPOSAL: self._proposal,
            Phase.VOTING: self._voting,
            Phase.QUEST_EXECUTION: self._quest_execution,
            Phase.QUEST_RESULT: self._quest_result,
            Phase.ASSASSINATION: self._assassination,
        }
        while self.state.phase != Phase.GAME_OVER:
            handlers[self.state.phase]()
            self.recorder.save_public(self.state)
        self._game_over()
        return self.state

    # ------------------------------------------------------------ 阶段

    def _init(self) -> None:
        s = self.state
        s.assignments = rules.assign_roles(self.rng)
        self.recorder.event(
            "game_start",
            game_id=s.game_id,
            seed=s.seed,
            seat_models=self.config.seat_models,
            assignments={pid: r.value for pid, r in s.assignments.items()},
        )
        for pid in PLAYER_IDS:
            hidden = rules.hidden_info_for(pid, s.assignments)
            self.players[pid].brief(prompts.system_prompt(pid, s.assignments[pid], hidden))
            self._save_thread(pid)
        self._start_quest()

    def _start_quest(self) -> None:
        s = self.state
        index = len(s.quests) + 1
        quest = Quest(index=index, size=rules.QUEST_SIZES[index - 1])
        s.quests.append(quest)
        self.recorder.event("quest_start", quest=index, size=quest.size)
        self._publish(prompts.event_quest_start(index, quest.size))
        self._start_proposal(self.rng.choice(PLAYER_IDS), rotated=False)

    def _start_proposal(self, leader: str, rotated: bool) -> None:
        quest = self.state.current_quest
        proposal = Proposal(index=len(quest.proposals) + 1, leader=leader)
        quest.proposals.append(proposal)
        self.recorder.event("leader", quest=quest.index, proposal=proposal.index, leader=leader, rotated=rotated)
        self._publish(prompts.event_leader(quest.index, proposal.index, leader, rotated))
        self.state.phase = Phase.DISCUSSION

    def _discussion(self) -> None:
        leader = self.state.current_proposal.leader
        for pid in rules.seats_from(leader):
            reply = self._ask(
                pid,
                Action.SPEAK,
                lambda: prompts.instruction(Action.SPEAK, is_leader=(pid == leader)),
                validate=lambda r: None if r.public_speech else prompts.reason_bad_speech(),
                fallback=lambda: Reply(private_analysis="", public_speech=prompts.FALLBACK_SPEECH.format(pid=pid)),
            )
            self._record_speech(pid, reply.public_speech or "")
        self.state.phase = Phase.PROPOSAL

    def _proposal(self) -> None:
        quest = self.state.current_quest
        proposal = self.state.current_proposal
        leader = proposal.leader

        def validate(r: Reply) -> str | None:
            if not r.public_speech:
                return prompts.reason_bad_speech()
            team = r.team or ()
            for pid in team:
                if pid not in PLAYER_IDS:
                    return prompts.reason_bad_team_member(pid)
            if not rules.is_legal_team(team, quest.size):
                return prompts.reason_bad_team_size(quest.size)
            return None

        def fallback() -> Reply:
            team = tuple(sorted(self.rng.sample(PLAYER_IDS, quest.size)))
            return Reply(private_analysis="", public_speech=prompts.FALLBACK_SPEECH.format(pid=leader), team=team)

        reply = self._ask(
            leader,
            Action.PROPOSE,
            lambda: prompts.instruction(Action.PROPOSE, team_size=quest.size, candidates=PLAYER_IDS),
            validate=validate,
            fallback=fallback,
            team_size=quest.size,
            candidates=PLAYER_IDS,
        )
        self._record_speech(leader, reply.public_speech or "")
        proposal.team = tuple(pid for pid in PLAYER_IDS if pid in (reply.team or ()))
        self.recorder.event("team", quest=quest.index, proposal=proposal.index, leader=leader, team=list(proposal.team))
        self._publish(prompts.event_team(leader, proposal.team))
        self.state.phase = Phase.VOTING

    def _voting(self) -> None:
        quest = self.state.current_quest
        proposal = self.state.current_proposal
        team = proposal.team

        def ask_vote(pid: str) -> tuple[str, bool]:
            reply = self._ask(
                pid,
                Action.VOTE,
                lambda: prompts.instruction(Action.VOTE, team=team),
                validate=lambda r: None if r.vote is not None else prompts.reason_missing_vote(),
                fallback=lambda: Reply(private_analysis="", vote=True),
            )
            return pid, bool(reply.vote)

        for pid, vote in self._collect(list(PLAYER_IDS), ask_vote):
            proposal.votes[pid] = vote
        proposal.approved = rules.is_approved(proposal.votes)
        self.recorder.event(
            "votes", quest=quest.index, proposal=proposal.index, votes=dict(proposal.votes), approved=proposal.approved
        )
        self._publish(prompts.event_votes(proposal.votes, proposal.approved))

        if proposal.approved:
            quest.team = team
            self.state.phase = Phase.QUEST_EXECUTION
            return
        if quest.rejections >= rules.MAX_PROPOSALS_PER_QUEST:
            self._finish(Side.EVIL, "five_rejections")
            return
        self._publish(prompts.event_rejections(quest.index, quest.rejections))
        self._start_proposal(rules.next_seat(proposal.leader), rotated=True)

    def _quest_execution(self) -> None:
        quest = self.state.current_quest
        evil_members = [pid for pid in quest.team if rules.side_of(self.state.assignments[pid]) == Side.EVIL]
        for pid in quest.team:
            if pid not in evil_members:
                quest.cards[pid] = True

        def ask_card(pid: str) -> tuple[str, bool]:
            reply = self._ask(
                pid,
                Action.EXECUTE_QUEST,
                lambda: prompts.instruction(Action.EXECUTE_QUEST, team=quest.team),
                validate=lambda r: None if r.quest_success is not None else prompts.reason_missing_card(),
                fallback=lambda: Reply(private_analysis="", quest_success=True),
            )
            return pid, bool(reply.quest_success)

        for pid, card in self._collect(evil_members, ask_card):
            quest.cards[pid] = card
        self.state.phase = Phase.QUEST_RESULT

    def _quest_result(self) -> None:
        s = self.state
        quest = s.current_quest
        quest.fail_count = sum(1 for v in quest.cards.values() if not v)
        quest.succeeded = not rules.quest_failed(quest.fail_count)
        self.recorder.event(
            "quest_result",
            quest=quest.index,
            team=list(quest.team),
            cards=dict(quest.cards),
            fail_count=quest.fail_count,
            succeeded=quest.succeeded,
        )
        self._publish(prompts.event_quest_result(quest.index, quest.team, quest.succeeded, quest.fail_count))
        self._publish(prompts.event_score(s.success_count, s.fail_count))

        if rules.winner_after_quests(s.success_count, s.fail_count) == Side.EVIL:
            self._finish(Side.EVIL, "three_failures")
        elif rules.good_reached_wins(s.success_count):
            self._publish(prompts.event_assassination_phase())
            s.phase = Phase.ASSASSINATION
        else:
            self._start_quest()

    def _assassination(self) -> None:
        s = self.state
        assassin = rules.player_with_role(s.assignments, Role.ASSASSIN)
        candidates = tuple(pid for pid in PLAYER_IDS if pid != assassin)

        def validate(r: Reply) -> str | None:
            if r.target not in candidates:
                return prompts.reason_bad_target(str(r.target), candidates)
            return None

        reply = self._ask(
            assassin,
            Action.ASSASSINATE,
            lambda: prompts.instruction(Action.ASSASSINATE, candidates=candidates),
            validate=validate,
            fallback=lambda: Reply(private_analysis="", target=self.rng.choice(candidates)),
            candidates=candidates,
        )
        target = str(reply.target)
        s.assassination_target = target
        winner = rules.winner_after_assassination(target, s.assignments)
        self.recorder.event("assassination", assassin=assassin, target=target, hit=(winner == Side.EVIL))
        self._finish(winner, "merlin_assassinated" if winner == Side.EVIL else "three_successes_and_merlin_safe")

    def _finish(self, winner: Side, reason: str) -> None:
        s = self.state
        s.winner = winner
        s.win_reason = reason
        s.phase = Phase.GAME_OVER

    def _game_over(self) -> None:
        s = self.state
        self.recorder.event(
            "game_over",
            winner=s.winner.value if s.winner else None,
            win_reason=s.win_reason,
            assignments={pid: r.value for pid, r in s.assignments.items()},
            assassination_target=s.assassination_target,
        )
        assert s.winner is not None and s.win_reason is not None
        self._publish(prompts.event_game_over(s.winner, s.win_reason, s.assignments, s.assassination_target))
        self.recorder.save_public(s)
        self.recorder.save_result(s)
        for pid in PLAYER_IDS:
            self._save_thread(pid)
        self.recorder.write_transcript(s)

    # ------------------------------------------------------------ 与玩家交互

    def _ask(
        self,
        pid: str,
        action: Action,
        make_instruction: Callable[[], str],
        *,
        validate: Validator,
        fallback: Callable[[], Reply],
        team_size: int | None = None,
        candidates: tuple[str, ...] = (),
    ) -> Reply:
        """向一名玩家发通知并收答案；不合法则退回重答，连续达到上限后兜底。"""
        player = self.players[pid]
        quest = self.state.current_quest if self.state.quests else None
        ctx = {
            "quest": quest.index if quest else None,
            "proposal": quest.proposals[-1].index if quest and quest.proposals else None,
        }
        reason: str | None = None
        for attempt in range(1, self.config.max_invalid_retries + 1):
            notice = self._notice(pid, action, make_instruction(), reason, team_size, candidates)
            reply: Reply | None
            try:
                reply = player.act(notice)
                error = validate(reply)
            except InvalidReply as e:
                reply, error = None, str(e)
            self._record_calls(pid)
            if error is None and reply is not None:
                self._record_turn(pid, action, reply, attempt, **ctx)
                return reply
            self.recorder.event("invalid_reply", player=pid, action=action.value, attempt=attempt, reason=error, **ctx)
            reason = error
        fb = fallback()
        value = fb.public_speech or fb.team or fb.target
        if fb.vote is not None:
            value = "赞成" if fb.vote else "反对"
        if fb.quest_success is not None:
            value = "成功" if fb.quest_success else "失败"
        self.recorder.event("fallback", player=pid, action=action.value, value=value, **ctx)
        self._record_turn(pid, action, fb, self.config.max_invalid_retries, fallback=True, **ctx)
        return fb

    def _notice(
        self,
        pid: str,
        action: Action,
        instruction: str,
        reason: str | None,
        team_size: int | None,
        candidates: tuple[str, ...],
    ) -> Notice:
        events = tuple(self.public_log[self.cursor[pid] :])
        self.cursor[pid] = len(self.public_log)
        return Notice(
            player_id=pid,
            action=action,
            public_events=events,
            scoreboard=prompts.render_scoreboard(self.state),
            instruction=instruction,
            team_size=team_size,
            candidates=candidates,
            rejection_reason=reason,
        )

    def _collect(self, pids: list[str], fn: Callable[[str], tuple[str, bool]]) -> list[tuple[str, bool]]:
        """向多名玩家同时提问。逻辑上同时，玩家互相看不到彼此的答案；实现上按配置并发或依次。"""
        if not pids:
            return []
        if self.config.parallel and len(pids) > 1:
            with ThreadPoolExecutor(max_workers=len(pids)) as pool:
                return list(pool.map(fn, pids))
        return [fn(pid) for pid in pids]

    # ------------------------------------------------------------ 记录

    def _publish(self, text: str) -> None:
        self.public_log.append(text)
        if self.on_public:
            self.on_public(text)

    def _record_speech(self, pid: str, content: str) -> None:
        quest = self.state.current_quest
        proposal = self.state.current_proposal
        self.state.speeches.append(Speech(pid, content, quest.index, proposal.index))
        self._publish(prompts.event_speech(pid, content))

    def _record_turn(self, pid: str, action: Action, reply: Reply, attempt: int, **extra: object) -> None:
        self.recorder.event(
            "turn",
            player=pid,
            action=action.value,
            attempt=attempt,
            private_analysis=reply.private_analysis,
            speech=reply.public_speech,
            team=list(reply.team) if reply.team else None,
            vote=reply.vote,
            card=reply.quest_success,
            target=reply.target,
            **extra,
        )
        if self.on_private and reply.private_analysis:
            self.on_private(pid, action.value, reply.private_analysis)
        self._save_thread(pid)

    def _record_calls(self, pid: str) -> None:
        for call in self.players[pid].drain_calls():
            self.recorder.event(
                "llm_call",
                player=pid,
                model=self.config.seat_models.get(pid),
                prompt_tokens=call.prompt_tokens,
                completion_tokens=call.completion_tokens,
                latency_s=round(call.latency_s, 2),
            )

    def _save_thread(self, pid: str) -> None:
        messages = self.players[pid].messages
        if messages:
            self.recorder.save_thread(pid, messages)
