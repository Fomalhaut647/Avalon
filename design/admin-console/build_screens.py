"""生成管理员界面的全部画板（.dc.html）。

运行：python3 build_screens.py
所有画面共用同一套顶栏、态势条、座位卡、投票格等片段，示意数据来自同一局假想对局（种子 42）。
"""

from __future__ import annotations

from pathlib import Path

HERE = Path(__file__).parent

# ---------------------------------------------------------------- 颜色与字体

PAPER = "#f4f0e8"
STRIP = "#faf7f1"
CARD = "#fffdf8"
LINE = "#e2dbcd"
LINE2 = "#ede7db"
INK = "#211d18"
INK2 = "#6b6357"
INK3 = "#9a9184"
INK4 = "#4a443b"
GOOD = "#2f66ad"
GOOD_SOFT = "#e4ecf7"
GOOD_TEXT = "#24518a"
EVIL = "#b2403b"
EVIL_SOFT = "#f7e4e1"
EVIL_TEXT = "#8f312d"
GOLD_SOFT = "#f6ecd2"
GOLD_TEXT = "#8a6418"
GREEN = "#2f8a5b"
GREEN_SOFT = "#e6f2ea"
GREEN_TEXT = "#236b45"
DISABLED = "#b9b1a3"
DASH = "#cfc7b8"

FONT_LINK = (
    '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@600;700'
    "&family=Noto+Sans+SC:wght@400;500;700&family=JetBrains+Mono:wght@400;500&display=swap\">"
)

BASE_CSS = """    body { margin: 0; background: #f4f0e8; color: #211d18; font-family: "Noto Sans SC", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif; font-size: 14px; line-height: 1.6; -webkit-font-smoothing: antialiased; }
    a { color: #2f66ad; text-decoration: none; } a:hover { color: #24518a; text-decoration: underline; }
    .serif { font-family: "Noto Serif SC", "Songti SC", "STSong", "SimSun", serif; }
    .mono { font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace; font-variant-numeric: tabular-nums; }
    @keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.3; } 100% { opacity: 1; } }
    .pulse { animation: pulse 1.6s ease-in-out infinite; }
    @keyframes shimmer { 0% { background-position: -300px 0; } 100% { background-position: 300px 0; } }
    .skeleton { background: linear-gradient(90deg, #e9e3d7 0%, #f6f2ea 50%, #e9e3d7 100%); background-size: 600px 100%; animation: shimmer 1.8s linear infinite; border-radius: 3px; }"""


def page(body: str, height: int) -> str:
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <script src="./support.js"></script>
</head>
<body>
<x-dc>
<helmet>
  {FONT_LINK}
  <style>
{BASE_CSS}
  </style>
</helmet>
<div style="width: 1440px; min-height: {height}px; background: {PAPER}; display: flex; flex-direction: column; box-sizing: border-box;">
{body}
</div>
</x-dc>
</body>
</html>
"""


# ---------------------------------------------------------------- 对局数据（示意）

ROLES = {
    "P1": ("忠臣", "good", "无额外信息"),
    "P2": ("莫甘娜", "evil", "队友 P4"),
    "P3": ("梅林", "good", "看到 P2、P4 是邪恶"),
    "P4": ("刺客", "evil", "队友 P2"),
    "P5": ("派西维尔", "good", "看到 P2、P3 之一是梅林"),
}
PIDS = ["P1", "P2", "P3", "P4", "P5"]
GAME_ID = "20260914-1032-7f3a"

# 画面 0 到 6 用的假想对局是五人局。画面 7 专门讲人数：同一张牌桌坐满十人时的角色与隐藏信息。
# 十人局的角色构成见 docs/rules.md 第三节：梅林、派西维尔、忠臣 ×4、莫甘娜、刺客、奥伯伦、莫德雷德。
ROLES_TEN = {
    "P1": ("忠臣", "good", "无额外信息"),
    "P2": ("莫甘娜", "evil", "队友 P4、P10"),
    "P3": ("梅林", "good", "看到 P2、P4、P8 是邪恶，看不到莫德雷德"),
    "P4": ("刺客", "evil", "队友 P2、P10"),
    "P5": ("派西维尔", "good", "看到 P2、P3 之一是梅林"),
    "P6": ("忠臣", "good", "无额外信息"),
    "P7": ("忠臣", "good", "无额外信息"),
    "P8": ("奥伯伦", "evil", "不知同伴，同伴也不知他"),
    "P9": ("忠臣", "good", "无额外信息"),
    "P10": ("莫德雷德", "evil", "队友 P2、P4"),
}
PIDS_TEN = [f"P{i}" for i in range(1, 11)]

# 各人数的规则表，与 avalon/rules.py 一致。
BY_COUNT = {
    5: ((2, 3, 2, 3, 3), 3, "—"),
    6: ((2, 3, 4, 3, 4), 4, "—"),
    7: ((2, 3, 3, 4, 4), 4, "第 4 次任务 2 张"),
    8: ((3, 4, 4, 5, 5), 5, "第 4 次任务 2 张"),
    9: ((3, 4, 4, 5, 5), 5, "第 4 次任务 2 张"),
    10: ((3, 4, 4, 5, 5), 6, "第 4 次任务 2 张"),
}


def seat_columns(count: int) -> int:
    """座位卡一行摆几张：六人以内一行排开，再多就两行。与前端 seatColumns 一致。"""
    return count if count <= 6 else -(-count // 2)

# ---------------------------------------------------------------- 图标

SVG_ATTRS = 'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"'


def icon(name: str, size: int = 16, color: str | None = None) -> str:
    paths = {
        "crown": '<path d="M3 8l4.5 5L12 5l4.5 8L21 8l-2 11H5L3 8z"></path>',
        "lock": '<rect x="4" y="11" width="16" height="10" rx="2"></rect><path d="M8 11V7a4 4 0 0 1 8 0v4"></path>',
        "chev-up": '<path d="M18 15l-6-6-6 6"></path>',
        "chev-down": '<path d="M6 9l6 6 6-6"></path>',
        "chev-right": '<path d="M9 6l6 6-6 6"></path>',
        "skip-back": '<path d="M19 20L9 12l10-8v16z"></path><path d="M5 19V5"></path>',
        "step-back": '<path d="M15 18l-6-6 6-6"></path>',
        "step-fwd": '<path d="M9 18l6-6-6-6"></path>',
        "skip-fwd": '<path d="M5 4l10 8-10 8V4z"></path><path d="M19 5v14"></path>',
        "play": '<path d="M7 4l12 8-12 8V4z"></path>',
        "download": '<path d="M12 4v11"></path><path d="M7 10l5 5 5-5"></path><path d="M4 19h16"></path>',
        "check": '<path d="M5 12l5 5L20 7"></path>',
        "dagger": '<path d="M12 3v13"></path><path d="M8 16h8"></path><path d="M10 16l2 5 2-5"></path><path d="M9 6l3-3 3 3"></path>',
        "eye": '<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z"></path><circle cx="12" cy="12" r="3"></circle>',
        "file": '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"></path><path d="M14 3v5h5"></path>',
        "arrow-left": '<path d="M19 12H5"></path><path d="M11 18l-6-6 6-6"></path>',
    }
    stroke_width = "2.2" if name == "crown" else "2"
    attrs = SVG_ATTRS.replace('stroke-width="2"', f'stroke-width="{stroke_width}"')
    if color:
        attrs = attrs.replace('stroke="currentColor"', f'stroke="{color}"')
    if name == "pause":
        return f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="currentColor" stroke="none"><rect x="6" y="5" width="4" height="14" rx="1"></rect><rect x="14" y="5" width="4" height="14" rx="1"></rect></svg>'
    return f'<svg width="{size}" height="{size}" {attrs}>{paths[name]}</svg>'


# ---------------------------------------------------------------- 小片段


def mono_chip(text: str) -> str:
    return f'<span class="mono" style="font-size: 12px; padding: 3px 8px; border: 1px solid {LINE}; border-radius: 4px; color: {INK2}; background: {PAPER}; white-space: nowrap;">{text}</span>'


def text_chip(text: str) -> str:
    return f'<span style="font-size: 12px; padding: 3px 8px; border: 1px solid {LINE}; border-radius: 4px; color: {INK2}; background: {PAPER}; white-space: nowrap;">{text}</span>'


def side_chip(side: str) -> str:
    if side == "good":
        return f'<span style="font-size: 11px; padding: 2px 8px; border-radius: 999px; background: {GOOD_SOFT}; color: {GOOD_TEXT}; font-weight: 500;">好人</span>'
    return f'<span style="font-size: 11px; padding: 2px 8px; border-radius: 999px; background: {EVIL_SOFT}; color: {EVIL_TEXT}; font-weight: 500;">邪恶</span>'


def tag(text: str, kind: str = "muted") -> str:
    base = "font-size: 11px; padding: 2px 8px; border-radius: 4px; display: inline-flex; align-items: center; gap: 4px;"
    if kind == "leader":
        return f'<span style="{base} background: {GOLD_SOFT}; color: {GOLD_TEXT}; font-weight: 500;">{icon("crown", 11)}{text}</span>'
    if kind == "member":
        return f'<span style="{base} border: 1px solid {INK}; color: {INK}; font-weight: 500; background: {CARD};">{text}</span>'
    if kind == "active":
        return f'<span style="{base} gap: 6px; background: {INK}; color: {CARD}; font-weight: 500;"><span class="pulse" style="width: 6px; height: 6px; border-radius: 50%; background: {CARD}; display: inline-block;"></span>{text}</span>'
    if kind == "wait":
        return f'<span style="{base} border: 1px dashed {DASH}; color: {INK3};">{text}</span>'
    if kind == "good":
        return f'<span style="{base} background: {GOOD_SOFT}; color: {GOOD_TEXT}; font-weight: 500;">{text}</span>'
    if kind == "evil":
        return f'<span style="{base} background: {EVIL}; color: {CARD}; font-weight: 500;">{text}</span>'
    if kind == "evil-soft":
        return f'<span style="{base} background: {EVIL_SOFT}; color: {EVIL_TEXT}; font-weight: 500;">{text}</span>'
    if kind == "gold":
        return f'<span style="{base} background: {GOLD_SOFT}; color: {GOLD_TEXT}; font-weight: 500;">{text}</span>'
    if kind == "yes":
        return f'<span style="{base} background: {INK}; color: {CARD}; font-weight: 500;">{text}</span>'
    if kind == "no":
        return f'<span style="{base} border: 1px solid {INK}; color: {INK}; font-weight: 500; background: {CARD};">{text}</span>'
    return f'<span style="{base} border: 1px solid {LINE}; color: {INK2};">{text}</span>'


def vote_tag(v: bool | None) -> str:
    if v is True:
        return tag("赞成", "yes")
    if v is False:
        return tag("反对", "no")
    return tag("投票中", "wait")


def cells(votes: dict[str, bool | None], pids: list[str] | None = None) -> str:
    out = []
    for pid in pids or PIDS:
        v = votes.get(pid)
        common = "width: 30px; height: 22px; border-radius: 3px; display: inline-flex; align-items: center; justify-content: center; font-size: 11px; box-sizing: border-box;"
        if v is True:
            out.append(f'<span class="mono" style="{common} background: {INK}; color: {CARD};">{pid}</span>')
        elif v is False:
            out.append(f'<span class="mono" style="{common} border: 1px solid {INK}; color: {INK};">{pid}</span>')
        else:
            out.append(f'<span class="mono pulse" style="{common} border: 1px dashed {DASH}; color: {INK3};">{pid}</span>')
    return f'<div style="display: flex; gap: 4px;">{"".join(out)}</div>'


def card_chip(pid: str, result: str) -> str:
    if result == "success":
        return f'<span class="mono" style="font-size: 11px; padding: 1px 6px; border-radius: 3px; background: {GOOD_SOFT}; color: {GOOD_TEXT};">{pid} 成功</span>'
    return f'<span class="mono" style="font-size: 11px; padding: 1px 6px; border-radius: 3px; background: {EVIL}; color: {CARD}; font-weight: 500;">{pid} 失败</span>'


def avatar(pid: str, size: int = 40, dim: bool = False) -> str:
    _, side, _ = ROLES[pid]
    fs = 13 if size >= 36 else 11
    if dim:
        return f'<div class="mono" style="width: {size}px; height: {size}px; box-sizing: border-box; border-radius: 50%; border: 1px dashed {DASH}; color: {INK3}; display: flex; align-items: center; justify-content: center; font-size: {fs}px; flex-shrink: 0;">{pid}</div>'
    color, soft, text = (GOOD, GOOD_SOFT, GOOD_TEXT) if side == "good" else (EVIL, EVIL_SOFT, EVIL_TEXT)
    return f'<div class="mono" style="width: {size}px; height: {size}px; box-sizing: border-box; border-radius: 50%; border: 2px solid {color}; background: {soft}; color: {text}; display: flex; align-items: center; justify-content: center; font-size: {fs}px; font-weight: 500; flex-shrink: 0;">{pid}</div>'


def name_of(pid: str) -> str:
    return f"{pid} · {ROLES[pid][0]}"


# ---------------------------------------------------------------- 顶栏


def playback(mode: str) -> str:
    """mode: live | replay | over"""
    def btn(name: str, state: str, last: bool = False) -> str:
        color = {"on": INK2, "off": DISABLED, "active": INK}[state]
        bg = f" background: {PAPER};" if state == "active" else ""
        border = "" if last else f" border-right: 1px solid {LINE};"
        return f'<div style="width: 32px; height: 30px; display: flex; align-items: center; justify-content: center; color: {color};{border}{bg}">{icon(name)}</div>'

    if mode == "live":
        items = [btn("skip-back", "on"), btn("step-back", "on"), btn("pause", "active"), btn("step-fwd", "off"), btn("skip-fwd", "off", True)]
    elif mode == "replay":
        items = [btn("skip-back", "on"), btn("step-back", "on"), btn("play", "active"), btn("step-fwd", "on"), btn("skip-fwd", "on", True)]
    else:
        items = [btn("skip-back", "on"), btn("step-back", "on"), btn("play", "on"), btn("step-fwd", "off"), btn("skip-fwd", "off", True)]
    return f'<div style="display: flex; align-items: center; border: 1px solid {LINE}; border-radius: 6px; background: {CARD}; overflow: hidden;">{"".join(items)}</div>'


def live_pill(mode: str) -> str:
    if mode == "live":
        return f'<div style="display: flex; align-items: center; gap: 8px; padding: 4px 10px 4px 8px; border-radius: 999px; background: {GREEN_SOFT}; color: {GREEN_TEXT}; font-size: 12px; font-weight: 500;"><span class="pulse" style="width: 8px; height: 8px; border-radius: 50%; background: {GREEN}; display: inline-block;"></span><span>实时跟随</span></div>'
    if mode == "replay":
        return (
            f'<div style="display: flex; align-items: center; gap: 8px;">'
            f'<div style="display: flex; align-items: center; gap: 8px; padding: 4px 10px 4px 8px; border-radius: 999px; background: {LINE}; color: {INK2}; font-size: 12px; font-weight: 500; white-space: nowrap;"><span style="width: 8px; height: 8px; border-radius: 50%; background: {INK3}; display: inline-block;"></span><span>回放中</span></div>'
            f'<span style="font-size: 12px; padding: 4px 10px; border-radius: 4px; background: {INK}; color: {CARD}; font-weight: 500; white-space: nowrap;">回到实时</span>'
            f"</div>"
        )
    return f'<div style="display: flex; align-items: center; gap: 8px; padding: 4px 10px 4px 8px; border-radius: 999px; background: {LINE}; color: {INK2}; font-size: 12px; font-weight: 500;"><span style="width: 8px; height: 8px; border-radius: 50%; background: {INK3}; display: inline-block;"></span><span>对局已结束</span></div>'


def header(*, mode: str, events: str, elapsed: str, cost: str, thinking: str = "关") -> str:
    return f"""
  <div style="height: 60px; box-sizing: border-box; padding: 0 24px; display: flex; align-items: center; justify-content: space-between; gap: 24px; background: {CARD}; border-bottom: 1px solid {LINE};">
    <div style="display: flex; align-items: center; gap: 18px;">
      <div style="display: flex; align-items: center; gap: 10px;">
        <span style="color: {INK3}; display: inline-flex;">{icon("arrow-left", 16)}</span>
        <div class="serif" style="font-size: 19px; font-weight: 700; letter-spacing: 0.02em; color: {INK}; white-space: nowrap;">阿瓦隆 · 裁判席</div>
      </div>
      <div style="display: flex; align-items: center; gap: 8px;">
        {mono_chip(f"局号 {GAME_ID}")}
        {mono_chip("种子 42")}
        {mono_chip("deepseek-flash")}
        {text_chip(f"隐藏思考 {thinking}")}
      </div>
    </div>
    <div style="display: flex; align-items: center; gap: 18px;">
      {live_pill(mode)}
      {playback(mode)}
      <span class="mono" style="font-size: 12px; color: {INK2}; white-space: nowrap;">事件 {events}</span>
      <span style="width: 1px; height: 18px; background: {LINE};"></span>
      <span style="font-size: 13px; color: {INK}; white-space: nowrap;">用时 <span class="mono">{elapsed}</span></span>
      <span style="font-size: 13px; color: {INK}; white-space: nowrap;">预计 <span class="mono">{cost}</span> 元</span>
    </div>
  </div>"""


# ---------------------------------------------------------------- 态势条

QUEST_SIZES = (2, 3, 2, 3, 3)


def quest_circle(state: str, size: int, small: bool = False) -> str:
    d = 24 if small else 40
    fs = 12 if small else 15
    common = f"width: {d}px; height: {d}px; box-sizing: border-box; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center; font-size: {fs}px; font-weight: 500; flex-shrink: 0;"
    if state == "success":
        return f'<span class="mono" style="{common} background: {GOOD}; color: {CARD};">{size}</span>'
    if state == "fail":
        return f'<span class="mono" style="{common} background: {EVIL}; color: {CARD};">{size}</span>'
    if state == "current":
        return f'<span class="mono" style="{common} background: {CARD}; border: 2px solid {INK}; color: {INK};">{size}</span>'
    return f'<span class="mono" style="{common} border: 1px solid {DASH}; color: {INK3}; font-weight: 400;">{size}</span>'


def strip(*, quests: list[str], score: tuple[int, int], rejections: int | None, title: str, steps: list[str], active: int, done_all: bool = False) -> str:
    labels = {"success": ("成功", GOOD_TEXT, "400"), "fail": ("失败", EVIL_TEXT, "400"), "current": ("进行中", INK, "500"), "upcoming": ("未开始", INK3, "400")}
    circles = []
    for state, size in zip(quests, QUEST_SIZES):
        label, color, weight = labels[state]
        circles.append(
            f'<div style="display: flex; flex-direction: column; align-items: center; gap: 4px; width: 44px;">{quest_circle(state, size)}<span style="font-size: 11px; color: {color}; font-weight: {weight};">{label}</span></div>'
        )
    if rejections is None:
        rej = f'<span style="font-size: 12px; color: {INK3};">任务阶段已结束</span>'
    else:
        pips = "".join(
            f'<span style="width: 10px; height: 10px; border-radius: 50%; box-sizing: border-box; {"background: " + INK + ";" if i < rejections else "border: 1px solid " + DASH + ";"}"></span>'
            for i in range(5)
        )
        rej = f'<div style="display: flex; align-items: center; gap: 8px;"><span style="font-size: 12px; color: {INK2};">本次任务否决</span><div style="display: flex; gap: 4px;">{pips}</div><span class="mono" style="font-size: 12px; color: {INK2};">{rejections} / 5</span></div>'
    step_html = []
    for i, s in enumerate(steps):
        if done_all or i < active:
            step_html.append(f'<span style="font-size: 12px; padding: 4px 10px; border-radius: 4px; background: {LINE}; color: {INK2};">{s}</span>')
        elif i == active:
            step_html.append(f'<span style="font-size: 12px; padding: 4px 10px; border-radius: 4px; background: {INK}; color: {CARD}; font-weight: 500;">{s}</span>')
        else:
            step_html.append(f'<span style="font-size: 12px; padding: 4px 10px; border-radius: 4px; border: 1px solid {LINE}; color: {INK3};">{s}</span>')
    return f"""
  <div style="box-sizing: border-box; padding: 14px 24px; display: flex; align-items: center; justify-content: space-between; gap: 24px; background: {STRIP}; border-bottom: 1px solid {LINE};">
    <div style="display: flex; align-items: center; gap: 28px;">
      <div style="display: flex; align-items: center; gap: 14px;">
        <span style="font-size: 12px; color: {INK2}; white-space: nowrap;">任务进度<br><span style="color: {INK3};">圈内为队伍人数</span></span>
        <div style="display: flex; align-items: flex-start; gap: 10px;">{"".join(circles)}</div>
      </div>
      <span style="width: 1px; height: 40px; background: {LINE};"></span>
      <div style="display: flex; flex-direction: column; gap: 6px;">
        <span style="font-size: 12px; color: {INK2};">比分 <span class="serif" style="font-size: 15px; font-weight: 700; color: {GOOD_TEXT};">好人 {score[0]}</span> <span style="color: {INK3};">:</span> <span class="serif" style="font-size: 15px; font-weight: 700; color: {EVIL_TEXT};">邪恶 {score[1]}</span></span>
        {rej}
      </div>
    </div>
    <div style="display: flex; align-items: center; gap: 20px;">
      <div class="serif" style="font-size: 17px; font-weight: 700; color: {INK}; white-space: nowrap;">{title}</div>
      <div style="display: flex; align-items: center; gap: 6px;">{"".join(step_html)}</div>
    </div>
  </div>"""


STEPS = ["讨论", "提案", "投票", "执行", "结算"]


# ---------------------------------------------------------------- 座位


def seat(pid: str, *, tags: list[str], record: str, calls: str, highlight: bool = False, roles: dict | None = None) -> str:
    role, side, hidden = (roles or ROLES)[pid]
    border = f"2px solid {INK}" if highlight else f"1px solid {LINE}"
    pad = "13px 15px" if highlight else "14px 16px"
    return f"""
        <div style="background: {CARD}; border: {border}; border-radius: 6px; padding: {pad}; display: flex; flex-direction: column; gap: 9px; box-sizing: border-box;">
          <div style="display: flex; align-items: center; justify-content: space-between; gap: 8px;">
            <div style="display: flex; align-items: baseline; gap: 8px;">
              <span class="mono" style="font-size: 13px; color: {INK2};">{pid}</span>
              <span class="serif" style="font-size: 18px; font-weight: 700; color: {INK};">{role}</span>
            </div>
            {side_chip(side)}
          </div>
          <div style="font-size: 11px; color: {INK2}; display: inline-flex; align-items: center; gap: 5px;">{icon("eye", 11, INK3)}{hidden}</div>
          <div style="display: flex; gap: 6px; flex-wrap: wrap;">{"".join(tags)}</div>
          <div style="font-size: 11px; color: {INK3}; line-height: 1.5;">{record}<br><span class="mono">{calls}</span></div>
        </div>"""


def seats_row(cards: list[str], columns: int = 5) -> str:
    """座位卡网格。前端用 CSS 变量 --seat-cols 表达同一条规则，列数由 seat_columns 给出。"""
    return f'<div style="display: grid; grid-template-columns: repeat({columns}, minmax(0, 1fr)); gap: 12px;">{"".join(cards)}</div>'


# ---------------------------------------------------------------- 面板与时间线片段


def panel(title: str, subtitle: str, right: str, inner: str, pad_bottom: int = 6, gap: int = 0) -> str:
    sub = f'<span style="font-size: 12px; color: {INK2};">{subtitle}</span>' if subtitle else ""
    body_style = f"display: flex; flex-direction: column; gap: {gap}px;" if gap else ""
    return f"""
      <div style="background: {CARD}; border: 1px solid {LINE}; border-radius: 6px; padding: 18px 20px {pad_bottom}px; box-sizing: border-box;">
        <div style="display: flex; align-items: baseline; justify-content: space-between; gap: 16px; padding-bottom: 12px; border-bottom: 1px solid {LINE};">
          <div style="display: flex; align-items: baseline; gap: 12px;"><span class="serif" style="font-size: 17px; font-weight: 700; color: {INK};">{title}</span>{sub}</div>
          <span class="mono" style="font-size: 12px; color: {INK2};">{right}</span>
        </div>
        <div style="{body_style}">{inner}</div>
      </div>"""


def private_expanded(text: str) -> str:
    return f"""
            <div style="background: {PAPER}; border: 1px solid {LINE}; border-radius: 4px; padding: 10px 12px; display: flex; flex-direction: column; gap: 6px;">
              <div style="display: flex; align-items: center; justify-content: space-between;">
                <span style="display: inline-flex; align-items: center; gap: 6px; font-size: 12px; color: {INK2}; font-weight: 500;">{icon("lock", 13)}私下分析 · 仅裁判可见</span>
                <span style="display: inline-flex; align-items: center; gap: 2px; font-size: 12px; color: {INK3};">收起{icon("chev-up", 12)}</span>
              </div>
              <p style="margin: 0; font-size: 13px; line-height: 1.7; color: {INK4};">{text}</p>
            </div>"""


def private_collapsed(n: int) -> str:
    return f"""
            <div style="display: flex; align-items: center; gap: 6px; font-size: 12px; color: {INK2};">{icon("lock", 13)}<span>私下分析 · {n} 字</span>{icon("chev-right", 12, INK3)}</div>"""


def speech(pid: str, *, meta: str, text: str, private: str | int, leader: bool = False, last: bool = False) -> str:
    border = "" if last else f" border-bottom: 1px solid {LINE2};"
    leader_tag = tag("队长", "leader") if leader else ""
    priv = private_expanded(private) if isinstance(private, str) else private_collapsed(private)
    return f"""
        <div style="display: grid; grid-template-columns: 40px minmax(0, 1fr); gap: 14px; padding: 16px 0;{border}">
          {avatar(pid)}
          <div style="display: flex; flex-direction: column; gap: 8px; min-width: 0;">
            <div style="display: flex; align-items: center; justify-content: space-between; gap: 12px;">
              <div style="display: flex; align-items: center; gap: 8px;"><span class="serif" style="font-size: 15px; font-weight: 700; color: {INK};">{name_of(pid)}</span>{leader_tag}</div>
              <span class="mono" style="font-size: 11px; color: {INK3}; white-space: nowrap;">{meta}</span>
            </div>
            <p style="margin: 0; font-size: 14px; line-height: 1.75; color: {INK};">{text}</p>
            {priv}
          </div>
        </div>"""


def generating(pid: str, *, label: str, meta: str, last: bool = False, widths=(92, 78, 46)) -> str:
    border = "" if last else f" border-bottom: 1px solid {LINE2};"
    bars = "".join(f'<div class="skeleton" style="height: 12px; width: {w}%;"></div>' for w in widths)
    return f"""
        <div style="display: grid; grid-template-columns: 40px minmax(0, 1fr); gap: 14px; padding: 16px 0;{border}">
          {avatar(pid)}
          <div style="display: flex; flex-direction: column; gap: 10px; min-width: 0;">
            <div style="display: flex; align-items: center; justify-content: space-between; gap: 12px;">
              <div style="display: flex; align-items: center; gap: 8px;"><span class="serif" style="font-size: 15px; font-weight: 700; color: {INK};">{name_of(pid)}</span>{tag(label, "active")}</div>
              <span class="mono" style="font-size: 11px; color: {INK3}; white-space: nowrap;">{meta}</span>
            </div>
            <div style="display: flex; flex-direction: column; gap: 8px; padding-top: 2px;">{bars}</div>
          </div>
        </div>"""


def waiting(pid: str, *, note: str, last: bool = True) -> str:
    border = "" if last else f" border-bottom: 1px solid {LINE2};"
    return f"""
        <div style="display: grid; grid-template-columns: 40px minmax(0, 1fr); gap: 14px; padding: 16px 0 18px;{border}">
          {avatar(pid, dim=True)}
          <div style="display: flex; align-items: center; justify-content: space-between; gap: 12px;">
            <span class="serif" style="font-size: 15px; font-weight: 600; color: {INK3};">{name_of(pid)}</span>
            <span style="font-size: 12px; color: {INK3};">{note}</span>
          </div>
        </div>"""


def collapsed_row(title: str, detail: str) -> str:
    return f"""
        <div style="display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 12px 0; border-bottom: 1px solid {LINE2};">
          <div style="display: flex; align-items: center; gap: 10px;"><span style="font-size: 12px; padding: 2px 8px; border-radius: 4px; background: {LINE}; color: {INK2};">{title}</span><span style="font-size: 13px; color: {INK2};">{detail}</span></div>
          <span style="display: inline-flex; align-items: center; gap: 2px; font-size: 12px; color: {INK3};">展开{icon("chev-down", 12)}</span>
        </div>"""


def event_block(step: str, title: str, meta: str, inner: str, last: bool = False, active: bool = False) -> str:
    border = "" if last else f" border-bottom: 1px solid {LINE2};"
    step_style = f"background: {INK}; color: {CARD}; font-weight: 500;" if active else f"background: {LINE}; color: {INK2};"
    return f"""
        <div style="display: flex; flex-direction: column; gap: 10px; padding: 14px 0;{border}">
          <div style="display: flex; align-items: center; justify-content: space-between; gap: 12px;">
            <div style="display: flex; align-items: center; gap: 10px;"><span style="font-size: 12px; padding: 2px 8px; border-radius: 4px; {step_style}">{step}</span><span class="serif" style="font-size: 15px; font-weight: 700; color: {INK};">{title}</span></div>
            <span class="mono" style="font-size: 11px; color: {INK3}; white-space: nowrap;">{meta}</span>
          </div>
          {inner}
        </div>"""


def team_chips(team: list[str]) -> str:
    return "".join(f'<span class="mono" style="font-size: 12px; padding: 2px 8px; border-radius: 4px; border: 1px solid {INK}; color: {INK}; background: {CARD};">{pid} {ROLES[pid][0]}</span>' for pid in team)


def vote_row(pid: str, vote: bool | None, meta: str, private: int | None, last: bool = False) -> str:
    border = "" if last else f" border-bottom: 1px solid {LINE2};"
    if vote is None:
        right = f'<span class="mono" style="font-size: 11px; color: {INK3};">{meta}</span>'
        priv = f'<div class="skeleton" style="height: 10px; width: 160px;"></div>'
    else:
        right = f'<span class="mono" style="font-size: 11px; color: {INK3};">{meta}</span>'
        priv = private_collapsed(private or 0)
    return f"""
          <div style="display: grid; grid-template-columns: 28px 130px 72px minmax(0, 1fr) auto; gap: 12px; align-items: center; padding: 8px 0;{border}">
            {avatar(pid, 28)}
            <span class="serif" style="font-size: 14px; font-weight: 700; color: {INK};">{name_of(pid)}</span>
            <span>{vote_tag(vote)}</span>
            <div>{priv}</div>
            {right}
          </div>"""


# ---------------------------------------------------------------- 右栏：任务记录与统计


def proposal_rows(p: dict, gap_after: bool = True) -> str:
    verdict = p["verdict"]
    if verdict.startswith("通过"):
        vstyle = f"color: {GOOD_TEXT}; font-weight: 500;"
    elif verdict.startswith("投票中"):
        vstyle = f"color: {INK}; font-weight: 500;"
    else:
        vstyle = f"color: {INK2};"
    return f"""
            <div style="display: flex; flex-direction: column; gap: 6px;">
              <div style="display: flex; align-items: center; justify-content: space-between; gap: 8px; font-size: 12px; color: {INK4};">
                <span>提案 {p["index"]} · 队长 <span class="mono">{p["leader"]}</span> · 队伍 <span class="mono">{" ".join(p["team"])}</span></span>
                <span class="mono" style="{vstyle}">{verdict}</span>
              </div>
              {cells(p["votes"])}
            </div>"""


def quest_block(q: dict, last: bool = False) -> str:
    result = q["result"]
    if result == "success":
        badge = tag("成功", "good")
        circle = quest_circle("success", q["size"], small=True)
    elif result == "fail":
        badge = tag(q.get("fail_label", "失败"), "evil-soft")
        circle = quest_circle("fail", q["size"], small=True)
    else:
        badge = ""
        circle = quest_circle("current", q["size"], small=True)
    props = "".join(proposal_rows(p) for p in q.get("proposals", []))
    cards_html = ""
    if q.get("cards"):
        chips = "".join(card_chip(pid, r) for pid, r in q["cards"])
        cards_html = f'<div style="font-size: 12px; color: {INK4}; display: flex; align-items: center; gap: 6px; flex-wrap: wrap;"><span style="color: {INK2};">任务牌</span>{chips}</div>'
    note = f'<span style="font-size: 12px; color: {INK2};">{q["note"]}</span>' if q.get("note") else ""
    body = f'<div style="display: flex; flex-direction: column; gap: 12px; padding-left: 34px;">{props}{cards_html}</div>' if (props or cards_html) else ""
    sep = "" if last else f'<div style="height: 1px; background: {LINE2};"></div>'
    return f"""
        <div style="display: flex; flex-direction: column; gap: 10px;">
          <div style="display: flex; align-items: center; justify-content: space-between; gap: 8px;">
            <div style="display: flex; align-items: center; gap: 10px;">{circle}<span class="serif" style="font-size: 15px; font-weight: 700; color: {INK};">第 {q["index"]} 次任务</span>{note}</div>
            {badge}
          </div>
          {body}
        </div>{sep}"""


def quest_record(quests: list[dict], title: str = "任务记录") -> str:
    legend = f'<span style="font-size: 11px; color: {INK3}; display: inline-flex; align-items: center; gap: 6px;"><span style="display: inline-block; width: 16px; height: 14px; border-radius: 2px; background: {INK};"></span>赞成<span style="display: inline-block; width: 16px; height: 14px; border-radius: 2px; border: 1px solid {INK}; box-sizing: border-box; margin-left: 6px;"></span>反对</span>'
    blocks = "".join(quest_block(q, last=(i == len(quests) - 1)) for i, q in enumerate(quests))
    return f"""
      <div style="background: {CARD}; border: 1px solid {LINE}; border-radius: 6px; padding: 18px 20px; box-sizing: border-box; display: flex; flex-direction: column; gap: 16px;">
        <div style="display: flex; align-items: baseline; justify-content: space-between; gap: 12px; padding-bottom: 12px; border-bottom: 1px solid {LINE};">
          <span class="serif" style="font-size: 17px; font-weight: 700; color: {INK};">{title}</span>{legend}
        </div>
        {blocks}
      </div>"""


def stats_card(*, title: str, right: str, rows: list[tuple[str, str]], links: list[str] | None = None, label_w: int = 88) -> str:
    grid = "".join(f'<span style="color: {INK2};">{k}</span><span style="color: {INK};">{v}</span>' for k, v in rows)
    links_html = ""
    if links:
        links_html = f'<div style="display: flex; gap: 16px; padding-top: 8px; border-top: 1px solid {LINE2}; font-size: 12px; flex-wrap: wrap;">{"".join(f"<a href=\"#\">{l}</a>" for l in links)}</div>'
    return f"""
      <div style="background: {CARD}; border: 1px solid {LINE}; border-radius: 6px; padding: 18px 20px; box-sizing: border-box; display: flex; flex-direction: column; gap: 12px;">
        <div style="display: flex; align-items: baseline; justify-content: space-between; padding-bottom: 12px; border-bottom: 1px solid {LINE};">
          <span class="serif" style="font-size: 17px; font-weight: 700; color: {INK};">{title}</span>
          <span class="mono" style="font-size: 12px; color: {INK2};">{right}</span>
        </div>
        <div style="display: grid; grid-template-columns: {label_w}px minmax(0, 1fr); row-gap: 8px; column-gap: 12px; font-size: 13px;">{grid}</div>
        {links_html}
      </div>"""


def m(text: str) -> str:
    return f'<span class="mono">{text}</span>'


def dim(text: str) -> str:
    return f'<span style="color: {INK3};">{text}</span>'


def main_grid(left: str, right: str, right_w: int = 416) -> str:
    return f"""
  <div style="box-sizing: border-box; padding: 20px 24px 28px; display: grid; grid-template-columns: minmax(0, 1fr) {right_w}px; gap: 24px; align-items: start;">
    <div style="display: flex; flex-direction: column; gap: 20px; min-width: 0;">{left}</div>
    <div style="display: flex; flex-direction: column; gap: 20px; min-width: 0;">{right}</div>
  </div>"""


# ---------------------------------------------------------------- 各任务的历史数据

Q1 = {
    "index": 1, "size": 2, "result": "success",
    "proposals": [{"index": 1, "leader": "P2", "team": ["P2", "P5"], "votes": {"P1": False, "P2": True, "P3": False, "P4": True, "P5": True}, "verdict": "3 : 2 通过"}],
    "cards": [("P2", "success"), ("P5", "success")],
}
Q2 = {
    "index": 2, "size": 3, "result": "fail", "fail_label": "失败 · 1 张失败牌",
    "proposals": [
        {"index": 1, "leader": "P3", "team": ["P1", "P3", "P5"], "votes": {"P1": True, "P2": False, "P3": True, "P4": False, "P5": False}, "verdict": "2 : 3 否决"},
        {"index": 2, "leader": "P4", "team": ["P1", "P2", "P4"], "votes": {"P1": False, "P2": True, "P3": False, "P4": True, "P5": False}, "verdict": "2 : 3 否决"},
        {"index": 3, "leader": "P5", "team": ["P1", "P2", "P5"], "votes": {"P1": True, "P2": True, "P3": False, "P4": True, "P5": True}, "verdict": "4 : 1 通过"},
    ],
    "cards": [("P1", "success"), ("P2", "fail"), ("P5", "success")],
}
Q3_DISCUSSING = {"index": 3, "size": 2, "result": "current", "note": "提案 1 · 队长 <span class=\"mono\">P1</span> · 讨论中"}
Q3_VOTING = {
    "index": 3, "size": 2, "result": "current",
    "proposals": [{"index": 1, "leader": "P1", "team": ["P1", "P3"], "votes": {"P1": True, "P2": False, "P3": True, "P4": None, "P5": None}, "verdict": "投票中 3 / 5"}],
}
Q3_DONE = {
    "index": 3, "size": 2, "result": "success",
    "proposals": [{"index": 1, "leader": "P1", "team": ["P1", "P3"], "votes": {"P1": True, "P2": False, "P3": True, "P4": False, "P5": True}, "verdict": "3 : 2 通过"}],
    "cards": [("P1", "success"), ("P3", "success")],
}
Q4_DONE = {
    "index": 4, "size": 3, "result": "success",
    "proposals": [
        {"index": 1, "leader": "P2", "team": ["P1", "P2", "P4"], "votes": {"P1": False, "P2": True, "P3": False, "P4": True, "P5": False}, "verdict": "2 : 3 否决"},
        {"index": 2, "leader": "P3", "team": ["P1", "P3", "P5"], "votes": {"P1": True, "P2": False, "P3": True, "P4": False, "P5": True}, "verdict": "3 : 2 通过"},
    ],
    "cards": [("P1", "success"), ("P3", "success"), ("P5", "success")],
}

P1_SPEECH = "第 2 次任务只出了一张失败牌，队里 P1、P2、P5 三人中至少有一名坏人。我自己是好人，嫌疑落在 P2 和 P5 之间。P3 从第 1 次任务起就一直反对可疑的队伍，这轮我倾向带 P3。"
P1_PRIVATE = "我是忠臣，信息最少。P3 三次投票都反对含 P2 的队伍，很像梅林，至少是好人。P2 两次上队，第二次就出了失败牌，嫌疑最大。P5 提案带上 P2，可能是被误导的派西维尔，也可能是坏人。本轮我是队长，带 P3 最稳。"
P2_SPEECH = "P1 的推理漏了一点：第 2 次任务的队伍是 P5 提的，我只是被带上。如果我是坏人，第 1 次任务为什么打成功？两次都在队里的是 P5，我建议 P1 带 P5 验一验。"
P3_SPEECH = "我同意 P1 的判断。这轮带 P3 或带 P5 都可以，唯独不要带 P2：第 2 次任务 P2 一上队就出了失败牌，第 1 次任务的成功牌说明不了什么，两人队里的坏人也会打成功保身。"


# ================================================================ 画面一：讨论阶段（Main）


def screen_main() -> str:
    seats = seats_row([
        seat("P1", tags=[tag("队长", "leader"), tag("已发言")], record="上队 1 · 成功 1", calls="9 次调用 · 0.011 元"),
        seat("P2", tags=[tag("已发言")], record=f'上队 2 · 成功 1 · <span style="color: {EVIL_TEXT}; font-weight: 500;">失败 1</span>', calls="12 次调用 · 0.015 元"),
        seat("P3", tags=[tag("已发言")], record="上队 0", calls="10 次调用 · 0.012 元"),
        seat("P4", tags=[tag("正在发言", "active")], record="上队 0", calls="9 次调用 · 0.011 元", highlight=True),
        seat("P5", tags=[tag("等待发言", "wait")], record="上队 2 · 成功 2", calls="10 次调用 · 0.012 元"),
    ])
    timeline = panel(
        "本轮讨论", "第 3 次任务 · 第 1 次提案 · 从队长 P1 起顺时针发言", "3 / 5 已发言",
        speech("P1", meta="10:35:38 · 6.1 秒 · 输出 386 token", text=P1_SPEECH, private=P1_PRIVATE, leader=True)
        + speech("P2", meta="10:35:46 · 7.4 秒 · 输出 402 token", text=P2_SPEECH, private=116)
        + speech("P3", meta="10:35:53 · 5.6 秒 · 输出 351 token", text=P3_SPEECH, private=102)
        + generating("P4", label="正在生成", meta="10:35:59 起 · 已等待 12 秒 · 第 1 次尝试")
        + waiting("P5", note="排在 P4 之后发言"),
    )
    right = quest_record([Q1, Q2, Q3_DISCUSSING]) + stats_card(
        title="模型调用", right="50 次",
        rows=[
            ("输入", m("20.3 万 token") + dim(" · 缓存命中 86%")),
            ("输出", m("9,120 token")),
            ("延迟", m("平均 6.8 秒") + dim(" · 最慢 14.2 秒（P5，第 2 次任务）")),
            ("无效回复", "1 次" + dim(" · P5 缺少【投票】标记，重试后通过 · 兜底 0 次")),
            ("费用", m("0.061 元") + dim(" · 空闲时段价")),
        ],
        links=["查看裁判日志", "查看某位玩家的完整线程"],
    )
    body = (
        header(mode="live", events="47 / 47", elapsed="4 分 06 秒", cost="0.061")
        + strip(quests=["success", "fail", "current", "upcoming", "upcoming"], score=(1, 1), rejections=0, title="第 3 次任务 · 第 1 次提案 · 队长 P1", steps=STEPS, active=0)
        + main_grid(seats + timeline, right)
    )
    return page(body, 1200)


# ================================================================ 画面二：投票阶段


def screen_voting() -> str:
    seats = seats_row([
        seat("P1", tags=[tag("队长", "leader"), tag("队员", "member"), vote_tag(True)], record="上队 1 · 成功 1", calls="10 次调用 · 0.012 元"),
        seat("P2", tags=[vote_tag(False)], record=f'上队 2 · 成功 1 · <span style="color: {EVIL_TEXT}; font-weight: 500;">失败 1</span>', calls="14 次调用 · 0.017 元"),
        seat("P3", tags=[tag("队员", "member"), vote_tag(True)], record="上队 0", calls="12 次调用 · 0.014 元"),
        seat("P4", tags=[tag("投票中", "active")], record="上队 0", calls="11 次调用 · 0.013 元", highlight=True),
        seat("P5", tags=[tag("投票中", "active")], record="上队 2 · 成功 2", calls="12 次调用 · 0.014 元", highlight=True),
    ])
    proposal_inner = f"""
          <div style="display: flex; align-items: center; gap: 10px; flex-wrap: wrap;"><span style="font-size: 13px; color: {INK2};">队伍</span>{team_chips(["P1", "P3"])}<span style="font-size: 12px; color: {INK3};">2 人任务 · 合法</span></div>
          {private_expanded("P3 三次反对票都与失败队伍相反，最像梅林，至少是好人。两人任务带自己和 P3 是最安全的组合。P5 两次上队一次失败，先不带。P2 刚才急着把嫌疑推给 P5，更可疑了。")}"""
    votes_inner = f"""
          <div style="display: flex; flex-direction: column;">
            {vote_row("P1", True, "10:36:37 · 3.9 秒 · 输出 141 token", 54)}
            {vote_row("P2", False, "10:36:38 · 4.6 秒 · 输出 188 token", 77)}
            {vote_row("P3", True, "10:36:39 · 5.1 秒 · 输出 163 token", 61)}
            {vote_row("P4", None, "10:36:33 起 · 已等待 14 秒", None)}
            {vote_row("P5", None, "10:36:33 起 · 已等待 14 秒", None, last=True)}
          </div>
          <div style="font-size: 12px; color: {INK3};">五人同时收到投票通知，回复各自独立；三人赞成即通过，否则否决并把队长换给 P2。</div>"""
    timeline = panel(
        "本轮进程", "第 3 次任务 · 第 1 次提案 · 队长 P1", "投票 3 / 5",
        collapsed_row("讨论", "5 条发言 · P1 与 P3 倾向带 P3，P2 建议带 P5")
        + event_block("提案", "队长 P1 提出队伍 P1、P3", "10:36:31 · 5.2 秒 · 输出 298 token", proposal_inner)
        + event_block("投票", "全体投票", "10:36:33 发出通知 · 已收到 3 / 5", votes_inner, last=True, active=True),
        pad_bottom=14,
    )
    right = quest_record([Q1, Q2, Q3_VOTING]) + stats_card(
        title="模型调用", right="57 次",
        rows=[
            ("输入", m("23.6 万 token") + dim(" · 缓存命中 87%")),
            ("输出", m("10,470 token")),
            ("延迟", m("平均 6.5 秒") + dim(" · 最慢 14.2 秒（P5，第 2 次任务）")),
            ("无效回复", "1 次" + dim(" · 兜底 0 次")),
            ("费用", m("0.069 元") + dim(" · 空闲时段价")),
        ],
        links=["查看裁判日志", "查看某位玩家的完整线程"],
    )
    body = (
        header(mode="live", events="54 / 54", elapsed="4 分 42 秒", cost="0.069")
        + strip(quests=["success", "fail", "current", "upcoming", "upcoming"], score=(1, 1), rejections=0, title="第 3 次任务 · 第 1 次提案 · 队长 P1", steps=STEPS, active=2)
        + main_grid(seats + timeline, right)
    )
    return page(body, 1200)


# ================================================================ 画面三：任务执行与结算（回放）


def replay_card() -> str:
    marks = ""
    # 事件轴上的任务分段：任务 1 占 0 到 12，任务 2 占 12 到 31，任务 3 之后是实时
    segs = [("任务 1", 0, 25.5, GOOD), ("任务 2", 25.5, 66, EVIL), ("任务 3", 66, 100, DASH)]
    for label, a, b, color in segs:
        marks += f'<div style="position: absolute; left: {a}%; width: {b - a}%; top: 0; height: 100%; background: {color}; opacity: 0.35; border-right: 1px solid {CARD}; box-sizing: border-box;"></div>'
    return f"""
      <div style="background: {CARD}; border: 1px solid {LINE}; border-radius: 6px; padding: 18px 20px; box-sizing: border-box; display: flex; flex-direction: column; gap: 12px;">
        <div style="display: flex; align-items: baseline; justify-content: space-between; padding-bottom: 12px; border-bottom: 1px solid {LINE};">
          <span class="serif" style="font-size: 17px; font-weight: 700; color: {INK};">回放位置</span>
          <span class="mono" style="font-size: 12px; color: {INK2};">事件 31 / 47</span>
        </div>
        <div style="position: relative; height: 10px; border-radius: 5px; background: {LINE}; overflow: hidden;">{marks}</div>
        <div style="position: relative; height: 0;"><div style="position: absolute; left: 66%; top: -20px; width: 14px; height: 14px; margin-left: -7px; border-radius: 50%; background: {INK}; border: 2px solid {CARD}; box-shadow: 0 0 0 1px {INK}; box-sizing: border-box;"></div></div>
        <div style="display: flex; justify-content: space-between; font-size: 11px; color: {INK3};"><span>10:32:05 开局</span><span>任务 1</span><span>任务 2</span><span>实时 10:36:11</span></div>
        <div style="display: grid; grid-template-columns: 88px minmax(0, 1fr); row-gap: 8px; column-gap: 12px; font-size: 13px;">
          <span style="color: {INK2};">当前事件</span><span style="color: {INK};">第 2 次任务结算 <span class="mono" style="color: {INK3};">10:35:30</span></span>
          <span style="color: {INK2};">范围</span><span style="color: {INK};">只回放公开事件与私下分析，模型不会被重新调用</span>
          <span style="color: {INK2};">操作</span><span style="color: {INK};">左右键逐事件，空格回到实时</span>
        </div>
      </div>"""


def screen_quest_result() -> str:
    seats = seats_row([
        seat("P1", tags=[tag("队员", "member"), tag("成功", "good")], record="上队 1 · 成功 1", calls="8 次调用 · 0.009 元"),
        seat("P2", tags=[tag("队员", "member"), tag("失败", "evil")], record=f'上队 2 · 成功 1 · <span style="color: {EVIL_TEXT}; font-weight: 500;">失败 1</span>', calls="11 次调用 · 0.014 元", highlight=True),
        seat("P3", tags=[tag("空闲")], record="上队 0", calls="9 次调用 · 0.011 元"),
        seat("P4", tags=[tag("空闲")], record="上队 0", calls="8 次调用 · 0.010 元"),
        seat("P5", tags=[tag("队长", "leader"), tag("队员", "member"), tag("成功", "good")], record="上队 2 · 成功 2", calls="9 次调用 · 0.011 元"),
    ])
    exec_inner = f"""
          <div style="font-size: 13px; color: {INK2}; line-height: 1.7;">好人队员由裁判自动出成功牌，不调用模型；邪恶队员被单独询问出哪张牌。本次队伍里只有 P2 需要决定。</div>
          <div style="display: grid; grid-template-columns: 40px minmax(0, 1fr); gap: 14px; padding-top: 4px;">
            {avatar("P2")}
            <div style="display: flex; flex-direction: column; gap: 8px; min-width: 0;">
              <div style="display: flex; align-items: center; justify-content: space-between; gap: 12px;">
                <div style="display: flex; align-items: center; gap: 8px;"><span class="serif" style="font-size: 15px; font-weight: 700; color: {INK};">P2 · 莫甘娜</span>{tag("出牌 失败", "evil")}</div>
                <span class="mono" style="font-size: 11px; color: {INK3}; white-space: nowrap;">10:35:24 · 6.9 秒 · 输出 344 token</span>
              </div>
              {private_expanded("第 1 次任务我打了成功牌换信任，现在 P4 不在队里，这是唯一能由我制造失败的机会。三人队里出一张失败牌，嫌疑会分散到 P1 和 P5 身上；P5 是队长又主动带我，之后可以把矛头引向他。")}
            </div>
          </div>
          <div style="display: flex; align-items: center; gap: 8px; font-size: 12px; color: {INK4}; flex-wrap: wrap;"><span style="color: {INK2};">裁判自动出牌</span>{card_chip("P1", "success")}{card_chip("P5", "success")}<span style="color: {INK3};">· 未调用模型</span></div>"""
    result_inner = f"""
          <div style="display: flex; align-items: center; gap: 16px; padding: 12px 14px; border-radius: 6px; background: {EVIL_SOFT}; border: 1px solid #ebc9c5;">
            <span class="serif" style="font-size: 20px; font-weight: 700; color: {EVIL_TEXT};">第 2 次任务失败</span>
            <span style="font-size: 13px; color: {EVIL_TEXT};">翻开 3 张任务牌：成功、成功、失败</span>
            <span style="margin-left: auto; font-size: 13px; color: {INK};">比分 <span class="serif" style="font-weight: 700; color: {GOOD_TEXT};">好人 1</span> : <span class="serif" style="font-weight: 700; color: {EVIL_TEXT};">邪恶 1</span></span>
          </div>
          <div style="font-size: 13px; color: {INK2}; line-height: 1.7;">玩家只看到打乱顺序的牌面；谁打了失败牌只有裁判知道。第 3 次任务开始，队长顺时针轮转到 P1。</div>"""
    timeline = panel(
        "本轮进程", "第 2 次任务 · 第 3 次提案 · 队长 P5", "回放 · 事件 31",
        collapsed_row("讨论", "5 条发言 · P5 力主带 P2 证清白，P3 反对")
        + event_block("提案", "队长 P5 提出队伍 P1、P2、P5", "10:34:52 · 5.8 秒 · 输出 312 token",
                      f'<div style="display: flex; align-items: center; gap: 10px; flex-wrap: wrap;"><span style="font-size: 13px; color: {INK2};">队伍</span>{team_chips(["P1", "P2", "P5"])}</div>{private_collapsed(96)}')
        + event_block("投票", "4 : 1 通过", "10:35:02 · 5 人并行 · 最慢 14.2 秒（P5 重试 1 次）",
                      f'<div style="display: flex; align-items: center; gap: 14px;">{cells(Q2["proposals"][2]["votes"])}<span style="font-size: 12px; color: {INK2};">P3 反对</span></div>')
        + event_block("执行", "任务执行", "10:35:17 至 10:35:24", exec_inner)
        + event_block("结算", "任务结果", "10:35:30", result_inner, last=True, active=True),
        pad_bottom=14,
    )
    right = quest_record([Q1, Q2], title="任务记录 · 截至事件 31") + replay_card()
    body = (
        header(mode="replay", events="31 / 47", elapsed="4 分 06 秒", cost="0.061")
        + strip(quests=["success", "fail", "upcoming", "upcoming", "upcoming"], score=(1, 1), rejections=2, title="第 2 次任务 · 第 3 次提案 · 队长 P5", steps=STEPS, active=4)
        + main_grid(seats + timeline, right)
    )
    return page(body, 1200)


# ================================================================ 画面四：刺杀阶段


def clue_card(pid: str, rows: list[str], target_truth: bool = False) -> str:
    role, side, _ = ROLES[pid]
    truth = f'<span style="font-size: 11px; padding: 1px 6px; border-radius: 3px; background: {GOLD_SOFT}; color: {GOLD_TEXT}; font-weight: 500;">真身</span>' if target_truth else ""
    lines = "".join(f'<div style="font-size: 12px; color: {INK4};">{r}</div>' for r in rows)
    return f"""
            <div style="border: 1px solid {LINE}; border-radius: 6px; padding: 12px 14px; display: flex; flex-direction: column; gap: 8px; background: {CARD};">
              <div style="display: flex; align-items: center; justify-content: space-between; gap: 8px;">
                <div style="display: flex; align-items: center; gap: 8px;">{avatar(pid, 28)}<span class="serif" style="font-size: 14px; font-weight: 700; color: {INK};">{name_of(pid)}</span></div>{truth}
              </div>
              <div style="display: flex; flex-direction: column; gap: 3px;">{lines}</div>
            </div>"""


def screen_assassination() -> str:
    seats = seats_row([
        seat("P1", tags=[tag("刺杀候选")], record="上队 3 · 成功 3", calls="17 次调用 · 0.020 元"),
        seat("P2", tags=[tag("刺客队友 · 不可选", "wait")], record=f'上队 2 · 成功 1 · <span style="color: {EVIL_TEXT}; font-weight: 500;">失败 1</span>', calls="20 次调用 · 0.024 元"),
        seat("P3", tags=[tag("刺杀候选"), tag("梅林真身", "gold")], record="上队 2 · 成功 2", calls="18 次调用 · 0.021 元"),
        seat("P4", tags=[tag("正在选择刺杀目标", "active")], record="上队 0", calls="17 次调用 · 0.020 元", highlight=True),
        seat("P5", tags=[tag("刺杀候选")], record="上队 3 · 成功 3", calls="17 次调用 · 0.019 元"),
    ])
    intro = f"""
          <div style="font-size: 13px; color: {INK4}; line-height: 1.7;">好人在第 4 次任务后达成 3 次成功。裁判向刺客 P4 发出刺杀通知：从 P1、P3、P5 中选择一人，刺中梅林则邪恶反胜，否则好人获胜。P4 的队友 P2 不在候选之列，也不参与决定。</div>"""
    clues = f"""
          <div style="font-size: 12px; color: {INK2};">下面是刺客在公开信息里能看到的线索，由裁判从对局记录汇总，供裁判对照它的判断。</div>
          <div style="display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px;">
            {clue_card("P1", ["上队 3 次，全部成功", "第 3 次任务当队长，带了 P3", "首个点名 P2 可疑的人"])}
            {clue_card("P3", ["上队 2 次，全部成功", "当队长 2 次，第 4 次任务提出全好人队伍并通过", "含 P2 的队伍三次全投反对"], target_truth=True)}
            {clue_card("P5", ["上队 3 次，第 2 次任务带了 P2", "投票两次与失败队伍同向", "发言多次提到 P3 值得信任"])}
          </div>"""
    timeline = panel(
        "刺杀阶段", "好人 3 胜 · 刺客一次机会", "等待 P4",
        event_block("刺杀", "进入刺杀阶段", "10:40:03", intro)
        + generating("P4", label="正在选择目标", meta="10:40:03 起 · 已等待 9 秒 · 第 1 次尝试", widths=(88, 70, 82, 38))
        + event_block("线索", "刺客可见的公开线索", "裁判视角", clues, last=True),
        pad_bottom=14,
    )
    right = quest_record([Q1, Q2, Q3_DONE, Q4_DONE]) + stats_card(
        title="模型调用", right="89 次",
        rows=[
            ("输入", m("38.1 万 token") + dim(" · 缓存命中 88%")),
            ("输出", m("16,930 token")),
            ("延迟", m("平均 6.4 秒")),
            ("无效回复", "2 次" + dim(" · 兜底 0 次")),
            ("费用", m("0.104 元") + dim(" · 空闲时段价")),
        ],
        links=["查看裁判日志", "查看某位玩家的完整线程"],
    )
    body = (
        header(mode="live", events="71 / 71", elapsed="7 分 58 秒", cost="0.104")
        + strip(quests=["success", "fail", "success", "success", "upcoming"], score=(3, 1), rejections=None, title="刺杀阶段 · 刺客 P4 选择目标", steps=STEPS + ["刺杀"], active=5)
        + main_grid(seats + timeline, right)
    )
    return page(body, 1400)


# ================================================================ 画面五：终局


def screen_game_over() -> str:
    seats = seats_row([
        seat("P1", tags=[tag("好人", "good")], record="上队 3 · 成功 3", calls="17 次调用 · 0.020 元"),
        seat("P2", tags=[tag("邪恶", "evil-soft")], record=f'上队 2 · 成功 1 · <span style="color: {EVIL_TEXT}; font-weight: 500;">失败 1</span>', calls="20 次调用 · 0.024 元"),
        seat("P3", tags=[tag("被刺杀", "evil")], record="上队 2 · 成功 2", calls="18 次调用 · 0.021 元", highlight=True),
        seat("P4", tags=[tag("刺中梅林", "gold")], record="上队 0", calls="18 次调用 · 0.022 元", highlight=True),
        seat("P5", tags=[tag("好人", "good")], record="上队 3 · 成功 3", calls="17 次调用 · 0.019 元"),
    ])
    banner = f"""
      <div style="background: {CARD}; border: 1px solid #ebc9c5; border-radius: 6px; padding: 22px 24px; box-sizing: border-box; display: flex; align-items: center; justify-content: space-between; gap: 24px;">
        <div style="display: flex; flex-direction: column; gap: 6px;">
          <span class="serif" style="font-size: 30px; font-weight: 700; color: {EVIL_TEXT}; line-height: 1.2;">邪恶阵营获胜</span>
          <span style="font-size: 14px; color: {INK};">刺客 P4 刺中了梅林 P3。好人虽以 3 : 1 赢下任务，但梅林暴露。</span>
        </div>
        <div style="display: flex; gap: 10px;">
          <span style="font-size: 13px; padding: 8px 14px; border-radius: 6px; background: {INK}; color: {CARD}; font-weight: 500; display: inline-flex; align-items: center; gap: 6px;">{icon("download", 14)}下载复盘稿</span>
          <span style="font-size: 13px; padding: 8px 14px; border-radius: 6px; border: 1px solid {INK}; color: {INK}; font-weight: 500;">再开一局 · 同种子 42</span>
          <span style="font-size: 13px; padding: 8px 14px; border-radius: 6px; border: 1px solid {LINE}; color: {INK2};">回到对局列表</span>
        </div>
      </div>"""
    assassination_inner = f"""
          <div style="display: grid; grid-template-columns: 40px minmax(0, 1fr); gap: 14px;">
            {avatar("P4")}
            <div style="display: flex; flex-direction: column; gap: 8px; min-width: 0;">
              <div style="display: flex; align-items: center; justify-content: space-between; gap: 12px;">
                <div style="display: flex; align-items: center; gap: 8px;"><span class="serif" style="font-size: 15px; font-weight: 700; color: {INK};">P4 · 刺客</span>{tag("刺杀 P3", "evil")}<span style="font-size: 12px; color: {INK2};">候选 P1、P3、P5</span></div>
                <span class="mono" style="font-size: 11px; color: {INK3}; white-space: nowrap;">10:40:21 · 18.3 秒 · 输出 512 token</span>
              </div>
              {private_expanded("P3 是全场最像梅林的人：含 P2 的队伍它三次全反对，第 4 次任务当队长直接提出全好人队伍，一次通过。P1 只是跟着 P3 的判断走，P5 还带过 P2，显然看不清。P3 的发言一直含糊地附和别人却从不出错，这是梅林在藏自己。刺 P3。")}
            </div>
          </div>"""
    reveal_rows = ""
    for pid in PIDS:
        role, side, hidden = ROLES[pid]
        reveal_rows += f"""
            <div style="display: grid; grid-template-columns: 28px 120px 60px minmax(0, 1fr); gap: 12px; align-items: center; padding: 7px 0; border-bottom: 1px solid {LINE2};">
              {avatar(pid, 28)}<span class="serif" style="font-size: 14px; font-weight: 700; color: {INK};">{name_of(pid)}</span>{side_chip(side)}<span style="font-size: 12px; color: {INK2};">开局所知：{hidden}</span>
            </div>"""
    recap = panel(
        "全局回顾", "4 次任务 · 7 次提案 · 1 次刺杀", "8 分 29 秒",
        event_block("刺杀", "刺客的最后一手", "10:40:21", assassination_inner)
        + event_block("公布", "角色公布", "10:40:34", f'<div style="display: flex; flex-direction: column;">{reveal_rows}</div>', last=True),
        pad_bottom=14,
    )
    right = quest_record([Q1, Q2, Q3_DONE, Q4_DONE]) + stats_card(
        title="对局统计", right="结束于 10:40:34",
        rows=[
            ("用时", m("8 分 29 秒")),
            ("模型调用", m("90 次") + dim(" · 隐藏思考关")),
            ("输入", m("38.7 万 token") + dim(" · 缓存命中 88%")),
            ("输出", m("17,440 token")),
            ("无效回复", "2 次" + dim(" · 均重试通过 · 兜底 0 次")),
            ("费用", m("0.106 元") + dim(" · 空闲时段价")),
        ],
    ) + stats_card(
        title="产物", right="games/" + GAME_ID + "/",
        rows=[
            ("复盘稿", m("transcript.md") + dim(" · 含私下分析")),
            ("裁判日志", m("referee.jsonl") + dim(" · 每次调用的 usage 与费用")),
            ("公开状态", m("public.json")),
            ("结果", m("result.json")),
            ("玩家线程", m("threads/P1.json … P5.json")),
        ],
        links=["下载全部", "打开目录"],
    )
    body = (
        header(mode="over", events="74 / 74", elapsed="8 分 29 秒", cost="0.106")
        + strip(quests=["success", "fail", "success", "success", "upcoming"], score=(3, 1), rejections=None, title="游戏结束 · 邪恶阵营获胜", steps=STEPS + ["刺杀"], active=6, done_all=True)
        + main_grid(banner + seats + recap, right)
    )
    return page(body, 1640)


# ================================================================ 画面六：玩家线程


def msg_block(kind: str, index: int, title: str, meta: str, inner: str, last: bool = False) -> str:
    border = "" if last else f" border-bottom: 1px solid {LINE2};"
    if kind == "system":
        badge = f'<span style="font-size: 11px; padding: 2px 8px; border-radius: 4px; background: {GOLD_SOFT}; color: {GOLD_TEXT}; font-weight: 500;">系统</span>'
    elif kind == "user":
        badge = f'<span style="font-size: 11px; padding: 2px 8px; border-radius: 4px; background: {LINE}; color: {INK2}; font-weight: 500;">裁判通知</span>'
    else:
        badge = f'<span style="font-size: 11px; padding: 2px 8px; border-radius: 4px; background: {EVIL_SOFT}; color: {EVIL_TEXT}; font-weight: 500;">P2 回复</span>'
    return f"""
        <div style="display: grid; grid-template-columns: 36px minmax(0, 1fr); gap: 14px; padding: 14px 0;{border}">
          <span class="mono" style="font-size: 11px; color: {INK3}; padding-top: 3px;">#{index}</span>
          <div style="display: flex; flex-direction: column; gap: 8px; min-width: 0;">
            <div style="display: flex; align-items: center; justify-content: space-between; gap: 12px;">
              <div style="display: flex; align-items: center; gap: 8px;">{badge}<span style="font-size: 13px; color: {INK}; font-weight: 500;">{title}</span></div>
              <span class="mono" style="font-size: 11px; color: {INK3}; white-space: nowrap;">{meta}</span>
            </div>
            {inner}
          </div>
        </div>"""


def notice_box(lines: list[str]) -> str:
    body = "<br>".join(lines)
    return f'<div class="mono" style="font-size: 12px; line-height: 1.7; color: {INK4}; background: {PAPER}; border: 1px solid {LINE}; border-radius: 4px; padding: 10px 12px; white-space: normal;">{body}</div>'


def reply_box(sections: list[tuple[str, str, bool]]) -> str:
    """sections: (marker, text, private)"""
    parts = []
    for marker, text, private in sections:
        if private:
            parts.append(f'<div style="display: flex; flex-direction: column; gap: 4px; background: {PAPER}; border: 1px solid {LINE}; border-radius: 4px; padding: 8px 12px;"><span style="display: inline-flex; align-items: center; gap: 6px; font-size: 12px; color: {INK2}; font-weight: 500;">{icon("lock", 12)}{marker}<span style="color: {INK3}; font-weight: 400;">· 未进入任何人的公开事件</span></span><span style="font-size: 13px; color: {INK4}; line-height: 1.7;">{text}</span></div>')
        else:
            parts.append(f'<div style="display: flex; flex-direction: column; gap: 4px; padding: 0 12px;"><span style="font-size: 12px; color: {INK2}; font-weight: 500;">{marker}</span><span style="font-size: 13px; color: {INK}; line-height: 1.7;">{text}</span></div>')
    return f'<div style="display: flex; flex-direction: column; gap: 8px;">{"".join(parts)}</div>'


def screen_player_thread() -> str:
    head = f"""
  <div style="height: 60px; box-sizing: border-box; padding: 0 24px; display: flex; align-items: center; justify-content: space-between; gap: 24px; background: {CARD}; border-bottom: 1px solid {LINE};">
    <div style="display: flex; align-items: center; gap: 14px;">
      <span style="color: {INK3}; display: inline-flex;">{icon("arrow-left", 16)}</span>
      <div style="display: flex; align-items: center; gap: 8px; font-size: 13px; color: {INK2};"><span>对局列表</span><span style="color: {INK3};">/</span><span class="mono">{GAME_ID}</span><span style="color: {INK3};">/</span><span class="serif" style="font-size: 17px; font-weight: 700; color: {INK};">P2 · 莫甘娜 的完整线程</span></div>
    </div>
    <div style="display: flex; align-items: center; gap: 18px;">
      <div style="display: flex; align-items: center; gap: 6px;">
        {"".join(f'<span class="mono" style="font-size: 12px; padding: 3px 9px; border-radius: 4px; {"background: " + INK + "; color: " + CARD + ";" if pid == "P2" else "border: 1px solid " + LINE + "; color: " + INK2 + ";"}">{pid}</span>' for pid in PIDS)}
      </div>
      <span style="width: 1px; height: 18px; background: {LINE};"></span>
      <span class="mono" style="font-size: 12px; color: {INK2};">25 条消息 · 12 次调用 · 线程 1.62 万 token</span>
      <span style="font-size: 12px; padding: 4px 10px; border-radius: 4px; border: 1px solid {INK}; color: {INK}; font-weight: 500; display: inline-flex; align-items: center; gap: 6px;">{icon("download", 13)}导出 P2.json</span>
    </div>
  </div>"""
    role, side, hidden = ROLES["P2"]
    subhead = f"""
  <div style="box-sizing: border-box; padding: 14px 24px; display: flex; align-items: center; justify-content: space-between; gap: 24px; background: {STRIP}; border-bottom: 1px solid {LINE};">
    <div style="display: flex; align-items: center; gap: 14px;">
      {avatar("P2", 36)}
      <div style="display: flex; flex-direction: column; gap: 2px;">
        <div style="display: flex; align-items: center; gap: 8px;"><span class="serif" style="font-size: 17px; font-weight: 700; color: {INK};">P2 · 莫甘娜</span>{side_chip("evil")}<span style="font-size: 12px; color: {INK2}; display: inline-flex; align-items: center; gap: 5px;">{icon("eye", 11, INK3)}{hidden}</span></div>
        <span style="font-size: 12px; color: {INK3};">每条裁判通知只包含它自己尚未看过的公开事件；这条线程从开局起从未清空，可见的私下分析是它唯一的跨轮记忆。</span>
      </div>
    </div>
    <div style="display: flex; align-items: center; gap: 6px;">
      <span style="font-size: 12px; padding: 4px 10px; border-radius: 4px; background: {INK}; color: {CARD}; font-weight: 500;">全部</span>
      <span style="font-size: 12px; padding: 4px 10px; border-radius: 4px; border: 1px solid {LINE}; color: {INK2};">只看回复</span>
      <span style="font-size: 12px; padding: 4px 10px; border-radius: 4px; border: 1px solid {LINE}; color: {INK2};">只看私下分析</span>
      <span style="font-size: 12px; padding: 4px 10px; border-radius: 4px; border: 1px solid {LINE}; color: {INK3};">隐藏推理 · 本局关闭</span>
    </div>
  </div>"""
    messages = (
        msg_block("system", 0, "系统提示 · 规则、身份与格式", "1,180 token · 只发一次",
                  f'<div style="font-size: 13px; color: {INK4}; line-height: 1.7;">你是一局五人阿瓦隆中的玩家 P2……角色：莫甘娜（Morgana），邪恶阵营。你知道的额外信息：你的邪恶队友是 P4……回复必须依次包含【私下分析】【公开发言】……</div><span style="display: inline-flex; align-items: center; gap: 2px; font-size: 12px; color: {INK3};">展开全文{icon("chev-down", 12)}</span>')
        + msg_block("user", 1, "第 1 次任务 · 请发言", "10:32:05 · 412 token",
                    notice_box(["# 公开事件", "第 1 次任务开始，需要 2 人。裁判随机指定第一任队长为 P2。", "", "# 计分板", "当前：第 1 次任务（2 人），第 1 次提案，队长 P2，本次任务已否决 0 次", "比分：好人 0 胜，邪恶 0 胜（先到 3 胜）", "", "# 你的行动", "轮到你发言。请先写【私下分析】，再写【公开发言】（不超过 200 字）。"]))
        + msg_block("assistant", 2, "回复 · 发言", "6.2 秒 · 输出 398 token · 缓存命中 0",
                    reply_box([
                        ("【私下分析】", "我是莫甘娜，队友是 P4。我是第一任队长，可以直接把自己放进两人队伍，再带一个好人当掩护。P4 不能带，两个坏人同队太容易暴露。带 P5 比较自然，它坐在我旁边。第一次任务我先打成功牌换信任。", True),
                        ("【公开发言】", "第一轮没有任何信息，我作为队长打算带自己和 P5，两人队伍风险最小。大家看牌面说话，如果这轮成功，说明我们两个都可信。", False),
                    ]))
        + msg_block("user", 3, "第 1 次任务 · 请提出队伍", "10:33:00 · 266 token",
                    notice_box(["# 公开事件", "P3 发言：……", "P4 发言：……", "P5 发言：……", "P1 发言：……", "", "# 你的行动", "你是队长，请从 P1、P2、P3、P4、P5 中选出 2 人组成队伍，写在【队伍】后。"]))
        + msg_block("assistant", 4, "回复 · 提案", "4.4 秒 · 输出 176 token · 缓存命中 1,984",
                    reply_box([("【私下分析】", "按计划带自己和 P5。P3 发言时对我略有怀疑，之后要留意它。", True), ("【队伍】", "P2、P5", False)]))
        + f"""
        <div style="display: flex; align-items: center; gap: 12px; padding: 12px 0; border-bottom: 1px solid {LINE2};">
          <span style="flex: 1; height: 1px; background: {LINE};"></span>
          <span style="font-size: 12px; color: {INK3}; display: inline-flex; align-items: center; gap: 4px;">中间 18 条消息已折叠 · 第 1 次任务投票与出牌、第 2 次任务三次提案{icon("chev-down", 12)}</span>
          <span style="flex: 1; height: 1px; background: {LINE};"></span>
        </div>"""
        + msg_block("user", 23, "第 3 次任务 · 请发言", "10:35:44 · 588 token",
                    notice_box(["# 公开事件", "第 2 次任务结果：失败，3 张任务牌中有 1 张失败。", "比分：好人 1 胜，邪恶 1 胜。", "第 3 次任务开始，需要 2 人。队长轮转到 P1。", "P1 发言：第 2 次任务只出了一张失败牌，队里 P1、P2、P5 三人中至少有一名坏人……", "", "# 计分板", "当前：第 3 次任务（2 人），第 1 次提案，队长 P1，本次任务已否决 0 次", "……", "", "# 你的行动", "轮到你发言。请先写【私下分析】，再写【公开发言】（不超过 200 字）。"]))
        + msg_block("assistant", 24, "回复 · 发言", "7.4 秒 · 输出 402 token · 缓存命中 14,592",
                    reply_box([
                        ("【私下分析】", "第 2 次任务的失败牌是我打的，现在必须把嫌疑引到 P5 身上。P3 连续反对含我的队伍，很可能是梅林，之后要提醒 P4。本轮绝不能让 P1 带 P3，否则好人再赢一次就进入刺杀阶段。", True),
                        ("【公开发言】", P2_SPEECH, False),
                    ]), last=True)
    )
    left = panel("消息线程", "发给 API 的 messages 原样展示，顺序即发送顺序", "25 条", messages, pad_bottom=8)
    call_rows = [
        ("1", "发言", "6.2", "1,592 / 0", "398", "0.0032"),
        ("2", "提案", "4.4", "1,984 / 284", "176", "0.0010"),
        ("3", "投票", "3.8", "2,304 / 112", "131", "0.0007"),
        ("4", "出牌", "4.1", "2,496 / 96", "142", "0.0007"),
        ("5", "发言", "6.9", "2,688 / 604", "411", "0.0023"),
        ("6", "投票", "3.5", "3,776 / 88", "124", "0.0006"),
        ("7", "发言", "7.1", "3,904 / 512", "377", "0.0020"),
        ("8", "投票", "4.0", "4,864 / 92", "138", "0.0007"),
        ("9", "发言", "6.4", "5,056 / 476", "366", "0.0020"),
        ("10", "投票", "3.7", "5,952 / 90", "129", "0.0006"),
        ("11", "出牌", "6.9", "6,144 / 118", "344", "0.0015"),
        ("12", "发言", "7.4", "14,592 / 588", "402", "0.0025"),
    ]
    rows_html = "".join(
        f'<div class="mono" style="display: grid; grid-template-columns: 28px 44px 52px minmax(0, 1fr) 56px 64px; gap: 8px; font-size: 11px; color: {INK4}; padding: 5px 0; border-bottom: 1px solid {LINE2};"><span style="color: {INK3};">{a}</span><span style="font-family: inherit;">{b}</span><span>{c} 秒</span><span>{d}</span><span>{e}</span><span>{f}</span></div>'
        for a, b, c, d, e, f in call_rows
    )
    calls_table = f"""
      <div style="background: {CARD}; border: 1px solid {LINE}; border-radius: 6px; padding: 18px 20px; box-sizing: border-box; display: flex; flex-direction: column; gap: 10px;">
        <div style="display: flex; align-items: baseline; justify-content: space-between; padding-bottom: 12px; border-bottom: 1px solid {LINE};">
          <span class="serif" style="font-size: 17px; font-weight: 700; color: {INK};">调用明细</span>
          <span class="mono" style="font-size: 12px; color: {INK2};">12 次 · 0.0178 元</span>
        </div>
        <div class="mono" style="display: grid; grid-template-columns: 28px 44px 52px minmax(0, 1fr) 56px 64px; gap: 8px; font-size: 11px; color: {INK3}; padding-bottom: 4px;"><span>#</span><span>行动</span><span>延迟</span><span>输入 命中 / 未命中</span><span>输出</span><span>费用 元</span></div>
        {rows_html}
        <div style="font-size: 12px; color: {INK3}; line-height: 1.6; padding-top: 4px;">输入里的"命中"是前缀缓存命中的 token，只按十分之一以下计价。线程越长，命中占比越高。</div>
      </div>"""
    size_card = stats_card(
        title="线程规模", right="至第 25 条",
        rows=[
            ("系统提示", m("1,180 token")),
            ("累计输入", m("55.4 万 token") + dim(" · 命中 91%")),
            ("累计输出", m("3,138 token")),
            ("最新一次", m("15,180 token") + dim(" · 约占上下文窗口 12%")),
            ("私下分析", "12 段" + dim(" · 均未外泄")),
        ],
        links=["查看 P2 收到的每条通知的公开事件游标", "在裁判日志中定位"],
    )
    body = head + subhead + main_grid(left, calls_table + size_card, right_w=440)
    return page(body, 1900)


# ================================================================ 画面零：对局列表


def dots(states: list[str]) -> str:
    color = {"success": GOOD, "fail": EVIL, "current": None, "upcoming": None}
    out = []
    for s in states:
        if s == "success" or s == "fail":
            out.append(f'<span style="width: 10px; height: 10px; border-radius: 50%; background: {color[s]}; display: inline-block;"></span>')
        elif s == "current":
            out.append(f'<span class="pulse" style="width: 10px; height: 10px; border-radius: 50%; border: 2px solid {INK}; box-sizing: border-box; display: inline-block;"></span>')
        else:
            out.append(f'<span style="width: 10px; height: 10px; border-radius: 50%; border: 1px solid {DASH}; box-sizing: border-box; display: inline-block;"></span>')
    return f'<div style="display: inline-flex; gap: 4px; align-items: center;">{"".join(out)}</div>'


def screen_lobby() -> str:
    head = f"""
  <div style="height: 60px; box-sizing: border-box; padding: 0 24px; display: flex; align-items: center; justify-content: space-between; gap: 24px; background: {CARD}; border-bottom: 1px solid {LINE};">
    <div style="display: flex; align-items: center; gap: 18px;">
      <div class="serif" style="font-size: 19px; font-weight: 700; letter-spacing: 0.02em; color: {INK}; white-space: nowrap;">阿瓦隆 · 裁判席</div>
      <span style="font-size: 13px; color: {INK2};">对局列表</span>
    </div>
    <div style="display: flex; align-items: center; gap: 14px;">
      <span class="mono" style="font-size: 12px; color: {INK2};">games/ 共 10 局 · 累计 5.34 元</span>
      <span style="font-size: 13px; padding: 7px 14px; border-radius: 6px; background: {INK}; color: {CARD}; font-weight: 500;">新开一局</span>
    </div>
  </div>"""
    cols = "grid-template-columns: 170px 90px 176px 88px minmax(0, 1fr) 84px 56px 52px;"
    head_row = f'<div class="mono" style="display: grid; {cols} gap: 10px; font-size: 11px; color: {INK3}; padding: 0 16px 8px; border-bottom: 1px solid {LINE};"><span>局号</span><span>开始</span><span>人数 · 模型 · 隐藏思考</span><span>任务</span><span>状态与结果</span><span>用时</span><span>费用 元</span><span></span></div>'
    games = [
        (GAME_ID, "09-14 10:32", 5, "deepseek-flash", "关", ("current", "第 3 次任务 · 讨论"), ["success", "fail", "current", "upcoming", "upcoming"], ("", "进行中 · 好人 1 : 邪恶 1"), "4 分 06 秒", "0.061", "进入"),
        ("20260914-1004-b3d5", "09-14 10:04", 10, "deepseek-flash", "开", ("over", "已结束"), ["success", "fail", "fail", "success", "fail"], ("evil", "邪恶胜 · 累计 3 次任务失败"), "31 分 12 秒", "2.06", "复盘"),
        ("20260913-2214-c1e9", "09-13 22:14", 5, "deepseek-flash", "开", ("over", "已结束"), ["success", "fail", "success", "success", "upcoming"], ("evil", "邪恶胜 · 刺中梅林 P2"), "12 分 40 秒", "0.83", "复盘"),
        ("20260913-2213-a0d4", "09-13 22:13", 7, "deepseek-flash", "开", ("over", "已结束"), ["success", "success", "fail", "success", "upcoming"], ("evil", "邪恶胜 · 刺中梅林 P5"), "19 分 51 秒", "1.24", "复盘"),
        ("20260913-2213-5b77", "09-13 22:13", 5, "deepseek-flash", "开", ("over", "已结束"), ["success", "fail", "success", "success", "upcoming"], ("good", "好人胜 · 刺杀 P1 未中"), "8 分 03 秒", "0.52", "复盘"),
        ("20260913-2140-e812", "09-13 21:40", 6, "deepseek-flash", "关", ("over", "已结束"), ["success", "success", "fail", "success", "upcoming"], ("evil", "邪恶胜 · 刺中梅林 P3"), "2 分 58 秒", "0.14", "复盘"),
        ("20260913-2140-91f0", "09-13 21:40", 5, "deepseek-flash", "关", ("over", "已结束"), ["success", "fail", "success", "fail", "success"], ("evil", "邪恶胜 · 刺中梅林 P4"), "3 分 22 秒", "0.13", "复盘"),
        ("20260913-2140-3c2a", "09-13 21:40", 5, "deepseek-flash", "关", ("over", "已结束"), ["fail", "success", "fail", "fail", "upcoming"], ("evil", "邪恶胜 · 累计 3 次任务失败"), "1 分 47 秒", "0.09", "复盘"),
        ("20260913-1905-d6e1", "09-13 19:05", 5, "deepseek-flash", "关", ("over", "已结束"), ["success", "success", "success", "upcoming", "upcoming"], ("evil", "邪恶胜 · 刺中梅林 P1"), "2 分 31 秒", "0.12", "复盘"),
        ("20260913-1858-7a19", "09-13 18:58", 8, "deepseek-flash", "关", ("over", "已结束"), ["success", "fail", "success", "success", "upcoming"], ("evil", "邪恶胜 · 刺中梅林 P2"), "3 分 05 秒", "0.15", "复盘"),
    ]
    rows = ""
    for gid, start, count, model, thinking, (st, st_text), quests, (winner, result), elapsed, cost, action in games:
        if st == "current":
            res = f'<span style="display: inline-flex; align-items: center; gap: 6px; font-size: 12px; color: {GREEN_TEXT}; font-weight: 500; white-space: nowrap;"><span class="pulse" style="width: 8px; height: 8px; border-radius: 50%; background: {GREEN}; display: inline-block;"></span>进行中 · {st_text} · 好人 1 : 邪恶 1</span>'
            bg = f" background: {STRIP};"
        elif winner == "evil":
            res = f'<span style="font-size: 12px; color: {EVIL_TEXT}; font-weight: 500; white-space: nowrap;">{result}</span>'
            bg = ""
        else:
            res = f'<span style="font-size: 12px; color: {GOOD_TEXT}; font-weight: 500; white-space: nowrap;">{result}</span>'
            bg = ""
        act = f'<span style="font-size: 12px; padding: 3px 10px; border-radius: 4px; {"background: " + INK + "; color: " + CARD + ";" if action == "进入" else "border: 1px solid " + LINE + "; color: " + INK2 + ";"} font-weight: 500; text-align: center; white-space: nowrap;">{action}</span>'
        rows += f"""
          <div style="display: grid; {cols} gap: 10px; align-items: center; padding: 11px 16px; border-bottom: 1px solid {LINE2}; font-size: 13px; color: {INK};{bg}">
            <span class="mono" style="font-size: 12px; white-space: nowrap;">{gid}</span>
            <span class="mono" style="font-size: 12px; color: {INK2}; white-space: nowrap;">{start}</span>
            <span class="mono" style="font-size: 12px; color: {INK2}; white-space: nowrap;">{count} 人 · {model} · {thinking}</span>
            {dots(quests)}
            {res}
            <span class="mono" style="font-size: 12px; color: {INK2}; white-space: nowrap;">{elapsed}</span>
            <span class="mono" style="font-size: 12px;">{cost}</span>
            {act}
          </div>"""
    table = f"""
      <div style="background: {CARD}; border: 1px solid {LINE}; border-radius: 6px; padding: 16px 0 4px; box-sizing: border-box;">
        <div style="display: flex; align-items: center; justify-content: space-between; padding: 0 16px 14px;">
          <div style="display: flex; align-items: center; gap: 6px;">
            <span style="font-size: 12px; padding: 4px 10px; border-radius: 4px; background: {INK}; color: {CARD}; font-weight: 500;">全部 10</span>
            <span style="font-size: 12px; padding: 4px 10px; border-radius: 4px; border: 1px solid {LINE}; color: {INK2};">进行中 1</span>
            <span style="font-size: 12px; padding: 4px 10px; border-radius: 4px; border: 1px solid {LINE}; color: {INK2};">已结束 9</span>
          </div>
          <span style="font-size: 12px; color: {INK3};">按开始时间倒序 · 数据来自每局的 result.json 与 public.json</span>
        </div>
        {head_row}
        {rows}
      </div>"""
    def field(label: str, control: str, hint: str = "") -> str:
        h = f'<span style="font-size: 11px; color: {INK3};">{hint}</span>' if hint else ""
        return f'<div style="display: flex; flex-direction: column; gap: 6px;"><span style="font-size: 12px; color: {INK2}; font-weight: 500;">{label}</span>{control}{h}</div>'
    def input_box(text: str, mono: bool = True, placeholder: bool = False) -> str:
        cls = ' class="mono"' if mono else ""
        color = INK3 if placeholder else INK
        return f'<div{cls} style="height: 36px; box-sizing: border-box; border: 1px solid {LINE}; border-radius: 6px; padding: 0 12px; display: flex; align-items: center; font-size: 13px; color: {color}; background: {CARD};">{text}</div>'
    def select_box(text: str) -> str:
        return f'<div class="mono" style="height: 36px; box-sizing: border-box; border: 1px solid {LINE}; border-radius: 6px; padding: 0 12px; display: flex; align-items: center; justify-content: space-between; font-size: 13px; color: {INK}; background: {CARD};"><span>{text}</span>{icon("chev-down", 14, INK3)}</div>'
    def toggle(on: bool, label_on: str, label_off: str) -> str:
        knob_left = "18px" if on else "2px"
        bg = INK if on else LINE
        return f'<div style="display: flex; align-items: center; gap: 10px;"><span style="position: relative; width: 36px; height: 20px; border-radius: 10px; background: {bg}; display: inline-block;"><span style="position: absolute; top: 2px; left: {knob_left}; width: 16px; height: 16px; border-radius: 50%; background: {CARD};"></span></span><span style="font-size: 13px; color: {INK};">{label_on if on else label_off}</span></div>'
    new_game = f"""
      <div style="background: {CARD}; border: 1px solid {LINE}; border-radius: 6px; padding: 18px 20px; box-sizing: border-box; display: flex; flex-direction: column; gap: 16px;">
        <div style="display: flex; align-items: baseline; justify-content: space-between; padding-bottom: 12px; border-bottom: 1px solid {LINE};">
          <span class="serif" style="font-size: 17px; font-weight: 700; color: {INK};">新开一局</span>
          <span style="font-size: 12px; color: {INK3};">等同命令行参数</span>
        </div>
        {field("种子", input_box("留空则随机", placeholder=True), "同一种子重放同样的角色分配与第一任队长")}
        {field("人数", select_box("5 人"), "可选 5 到 10；任务人数 2、3、2、3、3，提案需 3 票通过。改人数时这行提示跟着变")}
        {field("模型", select_box("deepseek-flash（V4.1 Flash）"), "所有座位使用同一模型；分座位配置留待玩家界面阶段")}
        {field("隐藏思考", toggle(False, "开", "关 · 一局约 3 到 5 分钟"), "打开后输出 token 约 10 倍，一局 4 到 20 分钟")}
        {field("投票与出牌并行", toggle(True, "开", "关"))}
        <span style="font-size: 13px; padding: 9px 14px; border-radius: 6px; background: {INK}; color: {CARD}; font-weight: 500; text-align: center;">开始对局并进入裁判席</span>
        <div style="font-size: 12px; color: {INK3}; line-height: 1.6; padding-top: 8px; border-top: 1px solid {LINE2};">开始后浮现裁判席页面，每位玩家先各收到一份系统提示，随后从第 1 次任务的讨论开始。中途关闭页面不影响对局，随时可以回来接着看。</div>
      </div>"""
    body = head + f"""
  <div style="box-sizing: border-box; padding: 20px 24px 28px; display: grid; grid-template-columns: minmax(0, 1fr) 320px; gap: 24px; align-items: start;">
    <div style="display: flex; flex-direction: column; gap: 20px; min-width: 0;">{table}</div>
    <div style="display: flex; flex-direction: column; gap: 20px; min-width: 0;">{new_game}</div>
  </div>"""
    return page(body, 760)


# ================================================================ 画面七：人数与座位排布


def _seat_demo(pid: str, roles: dict) -> str:
    return seat(pid, tags=[], record="上队 0", calls="0 次调用 · 0.000 元", roles=roles)


def _panel(title: str, note: str, inner: str) -> str:
    return f"""
      <div style="background: {CARD}; border: 1px solid {LINE}; border-radius: 6px; padding: 18px 20px; box-sizing: border-box; display: flex; flex-direction: column; gap: 14px;">
        <div style="display: flex; align-items: baseline; justify-content: space-between; gap: 16px; padding-bottom: 12px; border-bottom: 1px solid {LINE};">
          <span class="serif" style="font-size: 17px; font-weight: 700; color: {INK};">{title}</span>
          <span style="font-size: 12px; color: {INK3};">{note}</span>
        </div>
        {inner}
      </div>"""


SEAT_TABLE_COLS = "grid-template-columns: 56px 92px minmax(0, 1fr) 150px 84px 108px 150px;"
SEAT_TABLE_EXTRA = {
    5: "五人局底牌",
    6: "+忠臣",
    7: "+忠臣 +奥伯伦",
    8: "+2 忠臣 +爪牙",
    9: "+3 忠臣 +莫德雷德",
    10: "+3 忠臣 +奥伯伦 +莫德雷德",
}


def screen_seat_layout() -> str:
    """专讲人数：座位卡在 5 到 10 人下怎么摆，十人局的角色与隐藏信息，各人数的规则表。"""
    title_bar = f"""
  <div style="height: 60px; box-sizing: border-box; padding: 0 24px; display: flex; align-items: center; justify-content: space-between; gap: 24px; background: {CARD}; border-bottom: 1px solid {LINE};">
    <div style="display: flex; align-items: center; gap: 18px;">
      <div class="serif" style="font-size: 19px; font-weight: 700; letter-spacing: 0.02em; color: {INK}; white-space: nowrap;">阿瓦隆 · 裁判席</div>
      <span style="font-size: 13px; color: {INK2};">人数与座位排布</span>
    </div>
    <span style="font-size: 12px; color: {INK3};">一局 5 到 10 人，开局时选定，整局不变</span>
  </div>"""

    label_five = f'<div style="font-size: 12px; color: {INK3};">5 人 · 一行 5 列 · 用画面 0 到 6 那局的角色</div>'
    label_ten = f'<div style="font-size: 12px; color: {INK3}; padding-top: 6px;">10 人 · 两行 5 列 · 另一局，角色与隐藏信息按十人局重算</div>'
    rule = f"""<div style="font-size: 13px; color: {INK2}; line-height: 1.8;">
          列数规则：六人以内一行排开；七人及以上折成两行，列数取人数的一半向上取整，即七人 4 列、八人 4 列、九人 5 列、十人 5 列。
          前端用 CSS 变量 <span class="mono">--seat-cols</span> 表达同一条规则，卡片本身不改尺寸。
        </div>"""
    layout_inner = (
        label_five
        + seats_row([_seat_demo(pid, ROLES) for pid in PIDS], seat_columns(5))
        + label_ten
        + seats_row([_seat_demo(pid, ROLES_TEN) for pid in PIDS_TEN], seat_columns(10))
        + rule
    )
    layout = _panel("座位卡：五人一行，十人两行", "卡片尺寸不随人数变，只变列数", layout_inner)

    ten_votes = cells(
        {"P1": True, "P2": False, "P3": True, "P4": None, "P5": None, "P6": True, "P7": True, "P8": False, "P9": True, "P10": None},
        PIDS_TEN,
    )
    parallel_inner = f"""<div style="display: flex; align-items: center; gap: 14px; flex-wrap: wrap;">
          {ten_votes}
          <span style="font-size: 12px; color: {INK2};">已收到 7 / 10 · 10 人并行</span>
        </div>
        <div style="font-size: 13px; color: {INK2}; line-height: 1.8;">
          投票格一人一格横向排开，不折行。面板右上角的进度与提示语都写本局人数，不写死"五人""三人赞成"。
          十人局提案需 6 票赞成才通过，平票按否决处理。
        </div>"""
    parallel = _panel("投票格与并行提示", "十人局的一次投票", parallel_inner)

    head_cells = "".join(
        f'<span style="font-size: 11px; color: {INK3};">{h}</span>'
        for h in ("人数", "座位", "角色构成", "任务人数", "通过票数", "每次提案发言", "失败牌门槛")
    )
    rows = ""
    for count, (sizes, votes, threshold) in BY_COUNT.items():
        bg = f" background: {STRIP};" if count == 10 else ""
        sizes_text = "、".join(str(n) for n in sizes)
        rows += f"""
          <div style="display: grid; {SEAT_TABLE_COLS} gap: 10px; align-items: center; padding: 9px 0; border-bottom: 1px solid {LINE2}; font-size: 13px; color: {INK};{bg}">
            <span class="mono">{count} 人</span>
            <span class="mono" style="font-size: 12px; color: {INK2};">P1–P{count}</span>
            <span style="font-size: 12px; color: {INK2};">{SEAT_TABLE_EXTRA[count]}</span>
            <span class="mono" style="font-size: 12px;">{sizes_text}</span>
            <span class="mono" style="font-size: 12px;">{votes} 票</span>
            <span class="mono" style="font-size: 12px;">{count + 1} 次</span>
            <span style="font-size: 12px; color: {INK2};">{threshold}</span>
          </div>"""
    table_inner = f"""<div style="display: grid; {SEAT_TABLE_COLS} gap: 10px; padding-bottom: 8px; border-bottom: 1px solid {LINE};">{head_cells}</div>
        {rows}
        <div style="font-size: 13px; color: {INK2}; line-height: 1.8; padding-top: 4px;">
          角色构成以五人局的梅林、派西维尔、忠臣、莫甘娜、刺客为底逐级追加，管理员只选人数，不逐张挑身份牌。
          梅林看不到莫德雷德、能看到奥伯伦，奥伯伦不知同伴、同伴也不知他；这两条在座位卡的"开局所知"一行里直接写出来。
        </div>"""
    table = _panel("各人数的规则表", "与 docs/rules.md 第三、四、七节一致", table_inner)

    body = title_bar + f"""
  <div style="box-sizing: border-box; padding: 20px 24px 28px; display: flex; flex-direction: column; gap: 20px;">
    {layout}
    {parallel}
    {table}
  </div>"""
    return page(body, 1460)


# ================================================================ 输出

SCREENS = {
    "Lobby.dc.html": screen_lobby,
    "Main.dc.html": screen_main,
    "Voting.dc.html": screen_voting,
    "QuestResult.dc.html": screen_quest_result,
    "Assassination.dc.html": screen_assassination,
    "GameOver.dc.html": screen_game_over,
    "PlayerThread.dc.html": screen_player_thread,
    "SeatLayout.dc.html": screen_seat_layout,
}

if __name__ == "__main__":
    for name, fn in SCREENS.items():
        (HERE / name).write_text(fn(), encoding="utf-8")
        print("wrote", name)
