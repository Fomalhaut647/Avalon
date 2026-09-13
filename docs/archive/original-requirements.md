> **归档说明**：本文是项目最初的需求提示词，原文件名 `阿瓦隆框架.md`，2026-09-13 归档，仅作历史参考。
> 当前有效的规则见 [rules.md](../rules.md)，架构见 [architecture.md](../architecture.md)，其中被替换的机制见 [roadmap.md](../roadmap.md) 与 [decisions/](../decisions/)。

---

请你为我实现一个“5 个 Agent 玩阿瓦隆”的最小可行版本项目。

技术要求：
- 编程语言：Python
- 环境管理：uv
- 先实现最小可行版本，重点是把流程和规则跑通，不要过早做复杂优化
- 不要假设任何未知信息；如果有任何实现细节不明确，先反问我，直到你完全弄清楚项目细节后再开始写代码

====================
一、术语定义
====================

请严格使用以下术语：

1. 一局游戏
指包含发身份、最多 5 次任务、直到胜负判定完成的完整游戏。

2. 一次任务
指从该次任务的讨论开始，到该次任务执行完毕并公布结果为止的完整过程。
一次任务中可能包含多次队长提案和多次投票。

3. 一轮对话
指讨论阶段中，一个玩家正式发言一次。

====================
二、目标
====================

实现一个由 1 个非 AI 裁判状态机 + 5 个 Agent 玩家组成的阿瓦隆框架。

裁判负责：
- 维护完整游戏状态
- 维护公开信息和私有信息
- 控制 phase 切换
- 校验所有工具调用是否合法
- 把当前状态和“当前可行动作”明确告知 Agent
- 记录日志和落盘文件

5 个 Agent 固定为：
- Merlin
- Percival
- Loyal Servant
- Morgana
- Assassin

先不实现“如何玩好某个身份”的复杂系统提示词，只先把流程跑通。

====================
三、文件格式与文件设计
====================

所有持久化文件必须使用 JSON，不使用 Markdown。

建议目录结构如下：

project_root/
  game/
    public/
      public_state.json
      group_chat.json
    players/
      P1/
        identity.json
        memory.json
      P2/
        identity.json
        memory.json
      P3/
        identity.json
        memory.json
      P4/
        identity.json
        memory.json
      P5/
        identity.json
        memory.json
    logs/
      events.jsonl
      tool_calls.jsonl
      game_result.json

含义如下：

1. public_state.json
记录本局可公开访问的结构化状态，例如：
- game_id
- player_ids
- round_index（第几次任务，1-5）
- proposal_index（当前这次任务中的第几次提案）
- leader_id
- current_phase
- current_team_size
- proposed_team
- vote_history
- quest_history
- consecutive_rejected_proposals_in_current_round
- success_count
- fail_count
- winner
- assassin_target
- current_allowed_actions_by_role_or_player

2. group_chat.json
只记录“当前这次任务”的完整公开发言，不保留历史任务的发言。
当一次任务执行结束后，裁判清空该文件。
建议结构：
{
  "round_index": 1,
  "messages": [
    {
      "turn_index": 1,
      "speaker": "P3",
      "content": "...",
      "timestamp": "..."
    }
  ]
}

3. identity.json（每个玩家一个）
记录该玩家的静态和半静态身份信息。
建议字段：
- player_id
- role
- side（good / evil）
- game_objective（本局目标）
- private_known_info（该玩家开局就知道的信息）
- trust_scores：对其他每个玩家的信任值，数值区间建议为 [-100, 100] 或 [0, 100]，由你选一个并统一
- speaking_willingness_cap：当前任务讨论阶段下，该玩家本次还能报出的发言意愿值上限

identity.json 中必须包含“对其他玩家的信任值”。

4. memory.json（每个玩家一个）
这是原先 Secret.md 的替代品。
只记录该玩家依据过往公开对话与公开结果总结出的“记忆”，不要记录冗长原始思维链。
例如应记录：
- 某玩家在某次任务的开场表态轮中声称自己是 Percival
- 某玩家在某次任务中强烈支持某个队伍
- 某次任务的队伍、投票、结果在自己视角下意味着什么
- 自己当前最重要的怀疑结论和理由摘要
- 自己需要记住的承诺、矛盾点、可疑点

memory.json 建议结构包含：
- player_id
- notes（按时间追加的结构化记忆条目）
- current_beliefs（当前对他人的简要判断）
- pending_agenda（下次若要发言，自己想推进的点，可选）

重要要求：
- 思考结果和发言意愿值是私密的，不得写入任何公共文件
- group_chat.json 只记录公开发言
- 一次任务结束后，裁判清空 group_chat.json
- 各个 Agent 需要自己把本次任务的重要信息总结进自己的 memory.json

====================
四、规则设定
====================

使用 5 人局配置：
- Good: Merlin, Percival, Loyal Servant
- Evil: Morgana, Assassin

5 次任务的人数固定为：
- Task 1: 2
- Task 2: 3
- Task 3: 2
- Task 4: 3
- Task 5: 3

胜利条件：
- Good 阵营先完成 3 次成功任务，则进入刺杀阶段
- Evil 阵营先完成 3 次失败任务，则 Evil 直接获胜
- 若某一次任务中，连续 5 次队伍提案均未通过，则 Evil 直接获胜
- 若 Good 先达成 3 次成功任务，则由 Assassin 执行刺杀
  - 若刺中 Merlin，则 Evil 获胜
  - 否则 Good 获胜

身份信息规则：
- Merlin 知道邪恶阵营玩家是谁
- Percival 知道 Merlin 和 Morgana 这两名玩家是谁，但不知道谁是谁
- Morgana 和 Assassin 互相知道彼此身份
- Loyal Servant 无额外隐藏信息

任务执行规则：
- 只有被选入队伍的玩家参与任务执行
- Good 阵营玩家执行任务时固定提交 success
- Evil 阵营玩家执行任务时可以选择 success 或 fail
- 5 人局中，任意任务只要出现 1 张 fail，即该任务失败

====================
五、Phase 设计
====================

请把游戏实现成明确的 phase 状态机。

建议 phase：
- INIT
- OPENING_STATEMENT
- DISCUSSION
- PROPOSAL
- VOTING
- QUEST_EXECUTION
- QUEST_RESULT
- ASSASSINATION
- GAME_OVER

含义：

1. INIT
裁判初始化整局游戏：
- 清空或重置所有文件
- 随机分配身份
- 写入每个玩家的 identity.json
- 初始化每个玩家的 memory.json
- 初始化 public_state.json
- 随机指定第一位队长
- 设定第 1 次任务人数为 2

2. OPENING_STATEMENT
这是“开场表态轮”。
每位玩家按固定顺序进行一次正式发言，用于给出第一轮简短看法。
注意：
- 不要把这一步描述为“报身份”
- 玩家可以选择简短表态，也可以选择“暂时不表态”
- 这一步属于公开发言，必须写入 group_chat.json

3. DISCUSSION
进入普通讨论阶段。
所有玩家根据上下文私下思考，然后调用“发言意愿值”工具提交一个整数。
裁判从中选择一位玩家发言。

意愿值规则：
- 普通玩家：每次提交的发言意愿值必须是 0-10 的整数
- 队长：每次提交的发言意愿值必须是 1-12 的整数
- 发言意愿值为 0 的玩家，不能被选中发言
- 队长的意愿值最低是 1，防止冷场
- 如果意愿值最高的玩家有多个，则随机选一个发言
- 禁止连续发言：上一轮对话刚发过言的玩家，下一轮对话不能再次发言
- 每次一个玩家成功正式发言后，该玩家本次任务讨论阶段的“发言意愿值上限”减 1
- 该上限需要记录在 identity.json 中，并在当前任务结束后重置为初始值
- 这个“发言意愿值上限递减 + 禁止连续发言”的机制用于限制对刷，不再额外设置单轮发言次数上限

发言长度规则：
- 在系统提示中告知所有玩家：发言要有信息密度
- 需要论述观点和方案时，不要吝啬字数
- 该简洁时不要输出无意义信息

4. PROPOSAL
只有当前队长可以进入该阶段。
队长应先进行一次正式发言，说明选人理由，然后调用“选人发车”工具提交队伍。
提交后进入 VOTING。

5. VOTING
所有玩家私下思考并调用“投票”工具提交 approve / reject。
裁判统一收集并公布投票结果，写入 public_state.json。
如果通过：
- 进入 QUEST_EXECUTION
如果不通过：
- 当前这次任务的提案失败次数 +1
- 若达到 5 次，Evil 直接获胜，进入 GAME_OVER
- 否则队长顺延给下一位玩家
- proposal_index +1
- 返回 DISCUSSION

6. QUEST_EXECUTION
只有被选入本次任务队伍的玩家允许执行任务。
- Good 玩家直接提交 success
- Evil 玩家私下思考后调用“执行任务”工具选择 success 或 fail
裁判收集结果并计算任务成败。

7. QUEST_RESULT
裁判更新：
- quest_history
- success_count / fail_count
- 当前任务的投票与执行结果
然后：
- 要求每个 Agent 基于本次任务的公开信息，把必要总结写入自己的 memory.json
- 清空 group_chat.json
- 若 Good 达到 3 次成功，进入 ASSASSINATION
- 若 Evil 达到 3 次失败，进入 GAME_OVER
- 否则进入下一次任务，更新 round_index、leader、team_size、proposal_index，并回到 DISCUSSION

8. ASSASSINATION
仅 Assassin 可以行动。
Assassin 私下思考后调用“刺杀”工具选择目标。
裁判判定最终胜负并进入 GAME_OVER。

9. GAME_OVER
裁判写入最终结果文件，包括：
- 全部真实身份
- 每次任务队伍
- 每次投票
- 每次任务结果
- 刺杀结果
- 最终胜方

====================
六、Agent 在每一步拿到的上下文
====================

每次轮到某个 Agent 思考或行动前，都只给它以下上下文：

1. identity.json 中的信息：
- 自己的身份
- 本局目标
- 对其他玩家的信任值
- 自己当前的发言意愿值上限

2. memory.json 中的信息：
- 自己总结出的过往信息

3. group_chat.json 中的信息：
- 当前这次任务从开始到现在的完整公开发言

4. 裁判当前通知：
- 当前 round_index / proposal_index / leader_id / current_phase
- 当前公开状态摘要
- 当前可用工具
- 当前不可用工具
- 若当前需要你行动，明确说明你现在应当做什么

重要要求：
- Agent 不得访问其他玩家的 identity.json 或 memory.json
- Agent 不得看到其他玩家的私有思考和发言意愿值
- 裁判必须把“当前可行动作”明确告诉 Agent

====================
七、工具设计
====================

请实现以下工具接口，并对所有工具做严格的 phase 校验和身份校验。
非法调用必须被裁判拒绝，并写入日志。

1. submit_willingness(value: int)
作用：
- 提交发言意愿值
约束：
- 仅在 DISCUSSION 阶段可用
- value 必须满足该玩家当前身份允许的整数范围
- value 不能超过该玩家当前的 speaking_willingness_cap
- value 为 0 的玩家不能被选中发言
- 队长最小值为 1
- 普通玩家最小值为 0

2. speak(content: str)
作用：
- 正式发言
约束：
- 仅在 OPENING_STATEMENT、DISCUSSION、PROPOSAL 阶段可用
- 只有被裁判明确选中允许发言的玩家，或当前处于开场表态轮中被轮到的玩家，才能调用
- 不允许连续发言
- 发言必须写入 group_chat.json

3. propose_team(members: list[str])
作用：
- 队长正式提交本次任务队伍
约束：
- 仅在 PROPOSAL 阶段可用
- 仅当前队长可用
- 队伍人数必须等于当前任务所需人数
- 成员不得重复
- 提交后进入 VOTING

4. vote(choice: "approve" | "reject")
作用：
- 对当前提案投票
约束：
- 仅在 VOTING 阶段可用
- 所有存活玩家都必须且只能投一次

5. execute_quest(choice: "success" | "fail")
作用：
- 执行任务
约束：
- 仅在 QUEST_EXECUTION 阶段可用
- 只有当前任务成员可用
- Good 玩家只能提交 success
- Evil 玩家可提交 success 或 fail

6. assassinate(target: str)
作用：
- 刺客选择刺杀对象
约束：
- 仅在 ASSASSINATION 阶段可用
- 仅 Assassin 可用
- target 必须是有效玩家 ID

7. update_memory(entry: object)
作用：
- 玩家把本次任务后的结构化总结写入自己的 memory.json
约束：
- 仅在 QUEST_RESULT 阶段可用
- 只能写自己的 memory.json
- 不能修改 identity.json 与 public_state.json

====================
八、发言选择机制
====================

DISCUSSION 阶段按以下流程运行：

1. 所有玩家并行或顺序私下思考
2. 所有玩家提交自己的发言意愿值
3. 裁判过滤掉：
- 意愿值为 0 的玩家
- 本轮禁止连续发言的玩家
- 非法提交的玩家
4. 从剩余玩家中选择意愿值最高者
5. 若最高者不唯一，则随机选择其中一人
6. 裁判显式通知该玩家：
- 你被选中发言
- 你当前可调用的工具只有 speak（以及如果你是队长且已进入 PROPOSAL，则可调用 propose_team）
7. 发言成功后：
- 该玩家本次任务讨论阶段的发言意愿值上限减 1
- 更新 identity.json
8. 重复上述流程，直到：
- 队长决定发车并提交队伍
- 或裁判根据流程需要强制进入 PROPOSAL，让队长表态并发车

这里不要再额外实现复杂抢话机制、回应权机制、多层心智机制。

====================
九、初始化与隐藏信息分发
====================

在 INIT 阶段，裁判需要把隐藏信息正确写入各玩家 identity.json：

- Merlin：知道 Morgana 和 Assassin 是邪恶阵营
- Percival：知道 Merlin 与 Morgana 这两位玩家，但不知道二者谁是谁
- Loyal Servant：无额外隐藏信息
- Morgana：知道 Assassin
- Assassin：知道 Morgana

同时要写入本局目标，例如：
- Good 目标：达成 3 次任务成功，并保护 Merlin 不被刺杀
- Evil 目标：达成 3 次任务失败，或在 Good 3 成功后刺杀 Merlin

====================
十、实现边界
====================

本版本先不要实现：
- 邪恶阵营内部额外通讯
- 更复杂的人格系统
- 更复杂的身份攻略提示词
- 多人更多角色扩展
- GUI
- 网络服务
- 数据库

先做一个本地可运行、可复盘的 Python 项目。

====================
十一、我期望你产出的内容
====================

请先给出：
1. 你对这个项目需求的结构化理解
2. 你计划创建的文件树
3. 关键数据结构与 JSON schema 设计
4. 状态机与主循环设计
5. 工具接口设计
6. 一个最小可行实现计划

在开始写代码之前，不要假设任何未知信息。请主动列出所有你仍不确定、需要我确认的问题，并向我追问，直到你完全弄清楚项目细节。