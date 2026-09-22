# Avalon

AI 玩家对局的阿瓦隆，一局 5 到 10 人。一个非 AI 的裁判状态机主持，每个座位是一个接入 API 的 chatbot 玩家，规则与真人阿瓦隆一致，v1 做了少量简化。

## 文档

- [docs/rules.md](docs/rules.md)：本项目采用的游戏规则，裁判与测试的唯一依据
- [docs/architecture.md](docs/architecture.md)：系统结构、信息流、模块职责、落盘内容
- [docs/decisions/](docs/decisions/)：设计决策记录，回答"为什么这样做"
- [docs/roadmap.md](docs/roadmap.md)：v1 刻意不做、日后可能做的方向
- [docs/experiments.md](docs/experiments.md)：真实模型对局的记录与观察
- [docs/admin-console-design.md](docs/admin-console-design.md)：管理员网页界面的设计稿说明与画布链接；技术方案见 architecture.md 第十节
- [docs/archive/](docs/archive/)：最初的需求文档，仅历史参考

## 运行

```bash
uv sync
cp .env.example .env   # 填入 DEEPSEEK_API_KEY，模型默认 deepseek-flash
uv run avalon --seed 42            # 默认五人局
uv run avalon --seed 42 --players 10
```

一局结束后在 `games/<id>/transcript.md` 复盘。模型的隐藏思考默认开启，一局约 5 到 20 分钟；在 `.env` 里写 `DEEPSEEK_THINKING=off` 可关闭，快数倍、便宜十倍以上，但模型只剩可见的私下分析可用。

## 网页裁判席

```bash
uv run avalon serve
```

打开 <http://127.0.0.1:8000/>：新开一局或一次开多局（同时最多 8 局，每局可选 5 到 10 人）、实时看每个座位的角色、发言、私下分析、投票与任务牌，暂停、掐断进行中的调用、终止，回放到任一事件（简略或详细两档粒度），读复盘稿，看每名玩家发给模型的完整线程；显示偏好在设置页里改，只存在浏览器本地。没有 API key 时可以用"随机玩家"零成本试界面。默认只监听本机。

## 测试

```bash
uv run pytest
```

不想联网时可以用随机玩家自检整条流程：

```bash
uv run avalon --random-players --seed 1
uv run avalon --random-players --seed 1 --players 10
```

## 状态

v1 已完成：规则（5 到 10 人局，含奥伯伦、莫德雷德、爪牙）、裁判状态机、DeepSeek 玩家、落盘与复盘稿、管理员网页界面（裁判席）均已实现，测试全部不联网。玩家界面暂缓。后续方向见 [docs/roadmap.md](docs/roadmap.md)。
