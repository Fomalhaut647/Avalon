# Avalon

五个 AI 玩家对局的阿瓦隆。一个非 AI 的裁判状态机主持，五个接入 API 的 chatbot 玩家参与，规则与真人阿瓦隆一致，v1 做了少量简化。

## 文档

- [docs/rules.md](docs/rules.md)：本项目采用的游戏规则，裁判与测试的唯一依据
- [docs/architecture.md](docs/architecture.md)：系统结构、信息流、模块职责、落盘内容
- [docs/decisions/](docs/decisions/)：设计决策记录，回答"为什么这样做"
- [docs/roadmap.md](docs/roadmap.md)：v1 刻意不做、日后可能做的方向
- [docs/archive/](docs/archive/)：最初的需求文档，仅历史参考

## 运行

```bash
uv sync
cp .env.example .env   # 填入 DEEPSEEK_API_KEY 与 DEEPSEEK_MODEL
uv run avalon --seed 42
```

一局结束后在 `games/<id>/transcript.md` 复盘。

## 测试

```bash
uv run pytest
```

## 状态

框架与文档已就位，游戏逻辑尚未实现。实施顺序：

1. `avalon/rules.py` 的规则函数，补齐 `tests/test_rules.py`。
2. `RandomPlayer` 与 `avalon/referee.py`，用假玩家跑通整局，补 `tests/test_referee.py`。
3. `avalon/prompts.py` 与 `avalon/llm.py`，接入真实模型。
