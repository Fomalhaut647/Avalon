"""所有面向模型的文本，以及答案的解析。

其他模块不得包含任何面向模型的文字。改提示词只改这里。
"""

from __future__ import annotations

from avalon.player import Action, Notice, Reply
from avalon.rules import HiddenInfo, Role

MARK_PRIVATE = "【私下分析】"
MARK_SPEECH = "【公开发言】"
MARK_TEAM = "【队伍】"
MARK_VOTE = "【投票】"
MARK_QUEST = "【任务】"
MARK_ASSASSINATE = "【刺杀】"


def system_prompt(player_id: str, role: Role, hidden: HiddenInfo) -> str:
    """规则摘要、座位、角色、隐藏信息、阵营目标、输出格式、发言风格要求。"""
    raise NotImplementedError


def render_notice(notice: Notice) -> str:
    """把 Notice 渲染为一条 user 消息。"""
    raise NotImplementedError


def parse_reply(text: str, action: Action) -> Reply:
    """按标记解析模型输出。格式不合法时抛 ValueError，由裁判决定退回重答。"""
    raise NotImplementedError
