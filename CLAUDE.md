# CLAUDE.md

本仓库是"五个 AI 玩家对局的阿瓦隆"。动手前先读：

- [docs/architecture.md](docs/architecture.md)：系统结构与模块职责
- [docs/rules.md](docs/rules.md)：游戏规则，代码行为以此为准
- [docs/decisions/](docs/decisions/)：改动设计前先看是否已有决策记录
- [docs/admin-console-design.md](docs/admin-console-design.md)：做网页界面前先读，管理员界面的设计稿与未决的技术问题

## 约定

- 术语与代码命名一一对应，见 rules.md 第一节：game、quest、proposal、speech、turn、leader、seat、team、phase。
- 所有面向模型的文字只放在 `avalon/prompts.py`。
- 规则函数放在 `avalon/rules.py`，必须是无状态纯函数。
- 玩家的私下分析绝不进入其他玩家的上下文。
- 改设计决策时新写一条 ADR，不修改旧的。
- 现状文档（rules.md、architecture.md）随代码改动同步更新。
- 文档文件名用英文小写加连字符，内容用中文；每份文档开头写 `> 起草日期：YYYY-MM-DD`。
- 设计稿画板由 `design/admin-console/build_screens.py` 生成，改稿改脚本再重新生成，不直接改生成出的 `.dc.html`。

## 命令

```bash
uv sync
uv run pytest                          # 全部不联网
uv run avalon --random-players --seed 1  # 不联网自检整局
uv run avalon --seed 42                  # 真实模型，隐藏思考关闭时一局约 3 到 5 分钟
```

.env 含 API key，已 gitignore，不要提交、不要打印其内容。
