"""用假玩家跑完整局：状态机能走到 GAME_OVER，每条终局路径都可达，私下分析不外泄，兜底可用。"""

import json
import random
from pathlib import Path

import pytest

from avalon import rules
from avalon.config import Config
from avalon.player import Action, InvalidReply, Notice, Player, RandomPlayer, Reply
from avalon.prompts import FALLBACK_SPEECH
from avalon.recorder import Recorder
from avalon.referee import Referee
from avalon.rules import PLAYER_IDS, Role, Side
from avalon.state import Phase


class ScriptedPlayer(Player):
    """固定策略：投票、任务牌、刺杀目标可配置；记录收到的每条通知。"""

    def __init__(self, pid, *, vote=True, card=True, target_index=0, rng=None):
        super().__init__(pid)
        self.vote = vote
        self.card = card
        self.target_index = target_index
        self.rng = rng or random.Random(0)
        self.notices: list[Notice] = []

    def brief(self, system_prompt):
        self.system_prompt = system_prompt

    def act(self, notice):
        self.notices.append(notice)
        secret = f"SECRET-{self.player_id}"
        if notice.action == Action.SPEAK:
            return Reply(secret, public_speech=f"{self.player_id} 说话")
        if notice.action == Action.PROPOSE:
            team = tuple(sorted(self.rng.sample(notice.candidates, notice.team_size)))
            return Reply(secret, public_speech=f"{self.player_id} 总结", team=team)
        if notice.action == Action.VOTE:
            return Reply(secret, vote=self.vote)
        if notice.action == Action.EXECUTE_QUEST:
            return Reply(secret, quest_success=self.card)
        if notice.action == Action.ASSASSINATE:
            return Reply(secret, target=notice.candidates[self.target_index])
        raise AssertionError(notice.action)


class BrokenPlayer(ScriptedPlayer):
    """永远给出不合法答案，逼出兜底。"""

    def act(self, notice):
        self.notices.append(notice)
        if notice.action == Action.PROPOSE:
            return Reply("x", public_speech="坏总结", team=("P1", "P1", "P2"))
        if notice.action == Action.ASSASSINATE:
            return Reply("x", target=self.player_id)
        raise InvalidReply("故意出错")


def run_game(tmp_path: Path, players: dict[str, Player], seed: int = 0) -> tuple[Referee, Recorder]:
    config = Config(api_key="", model="fake", seed=seed, games_dir=tmp_path, parallel=False)
    recorder = Recorder(tmp_path / f"game-{seed}")
    referee = Referee(players, config, recorder, random.Random(seed))
    referee.run()
    return referee, recorder


def check_invariants(referee: Referee) -> None:
    s = referee.state
    assert s.phase == Phase.GAME_OVER
    assert s.winner in (Side.GOOD, Side.EVIL)
    assert 1 <= len(s.quests) <= 5
    for q in s.quests:
        assert 1 <= len(q.proposals) <= rules.MAX_PROPOSALS_PER_QUEST
        for p in q.proposals:
            assert len(p.votes) == 5 and p.approved is not None
            assert rules.is_legal_team(p.team, q.size)
            # 每次提案恰好 6 次发言：队长首发、4 人轮转、队长总结。
            speeches = [sp for sp in s.speeches if sp.quest_index == q.index and sp.proposal_index == p.index]
            assert len(speeches) == 6
            order = rules.seats_from(p.leader)
            assert [sp.speaker for sp in speeches] == list(order) + [p.leader]
        approved = [p for p in q.proposals if p.approved]
        assert len(approved) <= 1
        if approved:
            assert q.team == approved[0].team
            assert set(q.cards) == set(q.team)
            good = [pid for pid in q.team if rules.side_of(s.assignments[pid]) == Side.GOOD]
            assert all(q.cards[pid] for pid in good), "好人必须自动出成功"
            assert q.succeeded is (q.fail_count == 0)
        else:
            assert q.succeeded is None
    # 队长按座位顺时针轮转：全局所有提案的队长连成一条顺时针链，跨任务也不断。
    leaders = [p.leader for q in s.quests for p in q.proposals]
    for a, b in zip(leaders, leaders[1:]):
        assert rules.next_seat(a) == b
    if s.win_reason == "five_rejections":
        assert s.quests[-1].rejections == 5 and s.winner == Side.EVIL
    elif s.win_reason == "three_failures":
        assert s.fail_count == 3 and s.winner == Side.EVIL
    elif s.win_reason == "merlin_assassinated":
        assert s.success_count == 3 and s.assignments[s.assassination_target] == Role.MERLIN
    elif s.win_reason == "three_successes_and_merlin_safe":
        assert s.success_count == 3 and s.assignments[s.assassination_target] != Role.MERLIN
    else:
        raise AssertionError(s.win_reason)


@pytest.mark.parametrize("seed", range(40))
def test_random_players_reach_game_over(tmp_path, seed):
    rng = random.Random(seed)
    players = {pid: RandomPlayer(pid, random.Random(rng.randrange(2**31))) for pid in PLAYER_IDS}
    referee, _ = run_game(tmp_path, players, seed)
    check_invariants(referee)


def test_random_players_are_reproducible(tmp_path):
    def play(sub):
        rng = random.Random(3)
        players = {pid: RandomPlayer(pid, random.Random(rng.randrange(2**31))) for pid in PLAYER_IDS}
        referee, _ = run_game(tmp_path / sub, players, 3)
        return referee.public_log

    assert play("a") == play("b")


def test_five_rejections_path(tmp_path):
    players = {pid: ScriptedPlayer(pid, vote=False) for pid in PLAYER_IDS}
    referee, _ = run_game(tmp_path, players)
    check_invariants(referee)
    s = referee.state
    assert s.win_reason == "five_rejections"
    assert len(s.quests) == 1 and len(s.quests[0].proposals) == 5
    leaders = [p.leader for p in s.quests[0].proposals]
    for a, b in zip(leaders, leaders[1:]):
        assert rules.next_seat(a) == b


def test_three_failures_path(tmp_path):
    players = {pid: ScriptedPlayer(pid, vote=True, card=False) for pid in PLAYER_IDS}
    # 随机队长每次都可能挑到没有邪恶的队伍，所以多试几个种子直到邪恶三败。
    for seed in range(20):
        referee, _ = run_game(tmp_path / str(seed), players, seed)
        check_invariants(referee)
        if referee.state.win_reason == "three_failures":
            assert referee.state.fail_count == 3
            return
    raise AssertionError("20 个种子内都没有出现邪恶三败")


def test_assassination_both_outcomes(tmp_path):
    outcomes = set()
    for seed in range(30):
        players = {pid: ScriptedPlayer(pid, vote=True, card=True, target_index=0) for pid in PLAYER_IDS}
        referee, _ = run_game(tmp_path / str(seed), players, seed)
        check_invariants(referee)
        assert referee.state.success_count == 3 and len(referee.state.quests) == 3
        outcomes.add(referee.state.win_reason)
    assert outcomes == {"merlin_assassinated", "three_successes_and_merlin_safe"}


def test_private_analysis_never_reaches_other_players(tmp_path):
    players = {pid: ScriptedPlayer(pid, vote=True, card=True) for pid in PLAYER_IDS}
    referee, recorder = run_game(tmp_path, players, seed=5)
    for pid, p in players.items():
        assert "SECRET" not in p.system_prompt
        for n in p.notices:
            blob = "\n".join(n.public_events) + n.scoreboard + n.instruction + (n.rejection_reason or "")
            assert "SECRET" not in blob
    public = json.loads((recorder.game_dir / "public.json").read_text())
    assert "SECRET" not in json.dumps(public, ensure_ascii=False)
    # 裁判日志与复盘稿要有。
    assert "SECRET-P1" in (recorder.game_dir / "events.jsonl").read_text()
    assert "SECRET-P1" in (recorder.game_dir / "transcript.md").read_text()


def test_hidden_info_in_brief_matches_roles(tmp_path):
    players = {pid: ScriptedPlayer(pid) for pid in PLAYER_IDS}
    referee, _ = run_game(tmp_path, players, seed=11)
    assignments = referee.state.assignments
    for pid, role in assignments.items():
        text = players[pid].system_prompt
        assert f"你是 {pid}" in text
        if role == Role.MERLIN:
            for evil in rules.players_with_side(assignments, Side.EVIL):
                assert evil in text
        if role == Role.LOYAL_SERVANT:
            assert "没有任何隐藏信息" in text


def test_notices_carry_incremental_events_only(tmp_path):
    players = {pid: ScriptedPlayer(pid, vote=True, card=True) for pid in PLAYER_IDS}
    referee, _ = run_game(tmp_path, players, seed=2)
    for pid, p in players.items():
        seen: list[str] = []
        for n in p.notices:
            if n.rejection_reason:
                continue
            seen.extend(n.public_events)
        # 每名玩家收到的事件是"公开记录去掉自己的发言"的一个前缀，不重复、不乱序。
        expected = [e.text for e in referee.public_log if e.skip_for != pid]
        assert seen == expected[: len(seen)]
        # 自己的发言一条都没收到，别人的发言一条不少。
        assert not any(s.startswith(f"{pid} 发言：") for s in seen)
        assert sum(1 for s in seen if " 发言：" in s) == len(referee.state.speeches) - sum(
            1 for sp in referee.state.speeches if sp.speaker == pid
        )
        # 至少能看到全部投票、任务结果（游戏结束公告除外，不再发通知）。
        assert len(expected) - len(seen) <= 6


def test_fallback_speech_is_sent_back_to_its_author(tmp_path):
    players = {pid: BrokenPlayer(pid) for pid in PLAYER_IDS}
    referee, _ = run_game(tmp_path, players, seed=1)
    for pid, p in players.items():
        own = FALLBACK_SPEECH.format(pid=pid)
        seen = [e for n in p.notices for e in n.public_events]
        assert any(own in s for s in seen), "兜底发言不是玩家自己写的，应当发回给他"



def test_broken_players_fall_back_and_finish(tmp_path):
    players = {pid: BrokenPlayer(pid) for pid in PLAYER_IDS}
    referee, recorder = run_game(tmp_path, players, seed=1)
    check_invariants(referee)
    s = referee.state
    kinds = [e["kind"] for e in recorder.events]
    assert "fallback" in kinds and "invalid_reply" in kinds
    # 每次行动最多尝试 3 次，第 3 次不合法后兜底。
    invalid = [e for e in recorder.events if e["kind"] == "invalid_reply"]
    assert max(e["attempt"] for e in invalid) == rules.MAX_INVALID_RETRIES
    assert all(sp.content == FALLBACK_SPEECH.format(pid=sp.speaker) for sp in s.speeches)
    # 兜底投票全部赞成，任务牌全部成功，因此好人三胜进入刺杀，刺杀目标随机且合法。
    assert s.success_count == 3 and s.assassination_target is not None
    assassin = rules.player_with_role(s.assignments, Role.ASSASSIN)
    assert s.assassination_target != assassin
    # 退回重答的通知带原因。
    reasons = [n.rejection_reason for p in players.values() for n in p.notices if n.rejection_reason]
    assert reasons and all(reasons)


def test_output_files_exist(tmp_path):
    players = {pid: ScriptedPlayer(pid) for pid in PLAYER_IDS}
    _, recorder = run_game(tmp_path, players, seed=9)
    for name in ("public.json", "events.jsonl", "result.json", "transcript.md"):
        assert (recorder.game_dir / name).exists(), name
    result = json.loads((recorder.game_dir / "result.json").read_text())
    assert set(result["assignments"]) == set(PLAYER_IDS)
    assert result["winner"] in ("good", "evil")
