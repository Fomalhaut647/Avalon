# Avalon

五个 AI 玩家对局的阿瓦隆。一个非 AI 的裁判状态机主持，五个接入 API 的 chatbot 玩家参与，规则与真人阿瓦隆一致，v1 做了少量简化。

## 文档

- [docs/rules.md](docs/rules.md)：本项目采用的游戏规则，裁判与测试的唯一依据
- [docs/architecture.md](docs/architecture.md)：系统结构、信息流、模块职责、落盘内容
- [docs/decisions/](docs/decisions/)：设计决策记录，回答"为什么这样做"
- [docs/roadmap.md](docs/roadmap.md)：v1 刻意不做、日后可能做的方向
- [docs/experiments.md](docs/experiments.md)：真实模型对局的记录与观察
- [docs/admin-console-design.md](docs/admin-console-design.md)：管理员网页界面的设计稿说明与画布链接
- [docs/archive/](docs/archive/)：最初的需求文档，仅历史参考

## 运行

```bash
uv sync
cp .env.example .env   # 填入 DEEPSEEK_API_KEY，模型默认 deepseek-flash
uv run avalon --seed 42
```

一局结束后在 `games/<id>/transcript.md` 复盘。默认关闭模型的隐藏思考，在 `.env` 里写 `DEEPSEEK_THINKING=on` 可开启，代价是一局慢数倍、贵数倍。

## 测试

```bash
uv run pytest
```

不想联网时可以用随机玩家自检整条流程：

```bash
uv run avalon --random-players --seed 1
```

## 状态

v1 已完成：规则、裁判状态机、DeepSeek 玩家、落盘与复盘稿均已实现，测试全部不联网。管理员网页界面已有设计稿，尚未开发。后续方向见 [docs/roadmap.md](docs/roadmap.md)。
