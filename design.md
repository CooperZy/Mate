# Zeus VLM Agent 系统设计文档 v2.0

## 设计哲学

**一个 VLM，一个 KV Cache，三种呼吸节奏。**

Zeus 是一个以视觉语言模型为唯一大脑的智能代理系统。不依赖第三方视觉检测模块，不拆分多进程，通过控制输入的"问题粒度"来控制输出的"反应粒度"，通过 KV Cache 的分层复用让快速感知和深度推理在同一个模型上共存。

核心隐喻：VLM 的 KV Cache 就是 Zeus 的意识状态，Timeline 就是短期记忆，蒸馏就是记忆固化，Identity Stack 就是人格。

---

## 1. 系统概述

### 1.1 核心特性

- **三种呼吸节奏**：Heartbeat（快速感知）、正常推理（对话与工具调用）、Soulbeat（自省与记忆蒸馏）
- **统一 VLM 驱动**：所有感知、推理、反应均由同一个 VLM 完成，无外部 CV 依赖
- **KV Cache 分层复用**：稳定的 Identity + Timeline prefix 确保 Heartbeat 增量推理极快
- **Fire-and-Forget 工具执行**：VLM 发出工具调用后不等待，继续下一个 cycle
- **Timeline 全写入**：所有 Heartbeat 帧均写入 Timeline，保持视觉时间连续性
- **Identity Stack**：基于 Markdown 文件的分层身份配置，兼容 OpenClaw 生态
- **三层记忆系统**：Working Memory（KV Cache）→ Session Memory → Long-term Memory

### 1.2 与 v1.0 的核心差异

| 维度 | v1.0 (现有 Zeus) | v2.0 (VLM Agent) |
|------|-----------------|-----------------|
| 观察循环 | 固定 0.67Hz，每次完整推理 | 动态频率，Heartbeat 2-3Hz / 正常推理 0.67Hz |
| 快速反应 | 无（依赖下一个 cycle） | Heartbeat `<react/>` 触发即时推理 |
| Timeline | 8 条，满了整体 summarize | 24 条，滑动窗口蒸馏，全帧写入 |
| Prompt 管理 | prompts.yaml 硬编码 | Identity Stack (Markdown 文件栈) |
| 记忆 | 仅 VLM Summary | 三层：Working → Session → Long-term |
| 反应行为定义 | 无 | AGENT.md 自然语言指令，VLM 原生理解 |
| 蒸馏 | 简单 summarize | 结构化提取：facts / events / active / discard |

---

## 2. 系统架构

### 2.1 整体架构图

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ Zeus VLM Agent 系统架构                                                      │
└──────────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────────┐
│ 外部接口层 (Flask API)                                                       │
│ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌──────────┐ ┌──────────┐ │
│ │ /query  │ │ /camera │ │  /asr   │ │  /tts   │ │ /react   │ │ /status  │ │
│ │         │ │         │ │         │ │         │ │ /toggle  │ │ /health  │ │
│ └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘ └────┬─────┘ └────┬─────┘ │
└──────┼──────────┼──────────┼──────────┼──────────┼────────────┼───────────┘
       │          │          │          │          │            │
       ▼          ▼          ▼          ▼          ▼            ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ 核心处理层                                                                    │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐  │
│  │ UnifiedLoop (统一循环 — 三种呼吸节奏)                                    │  │
│  │                                                                        │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                    │  │
│  │  │  Heartbeat  │  │  正常推理   │  │  Soulbeat   │                    │  │
│  │  │  "△" 快速感知│  │  对话+工具  │  │  "◆" 自省蒸馏│                    │  │
│  │  │  2-3Hz      │  │  0.67Hz     │  │  每30s      │                    │  │
│  │  │  max_tok:50 │  │  max_tok:2k │  │  max_tok:1k │                    │  │
│  │  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘                    │  │
│  │         │                │                │                            │  │
│  │         └────────────────┼────────────────┘                            │  │
│  │                          ▼                                             │  │
│  │            ┌──────────────────────────┐                                │  │
│  │            │ LLMServer (VLM 推理)     │                                │  │
│  │            │ 共享 KV Cache Prefix     │                                │  │
│  │            └──────────────────────────┘                                │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────────────┐  │
│  │  Identity Loader  │  │   QueryBoard     │  │    ToolManager           │  │
│  │  (Markdown 栈)    │  │   (查询状态追踪) │  │    (工具发现与执行)      │  │
│  └──────────────────┘  └──────────────────┘  └──────────────────────────┘  │
│                                                                              │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────────────┐  │
│  │   TodoBoard      │  │  Session Memory  │  │    Timeline Manager      │  │
│  │   (工作流管理)    │  │  (蒸馏记忆持久化)│  │    (24条 滑动窗口)       │  │
│  └──────────────────┘  └──────────────────┘  └──────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────────┘
       │          │          │          │          │            │
       ▼          ▼          ▼          ▼          ▼            ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ 工具层 (Tools) — Fire-and-Forget                                             │
│ ┌────────┐ ┌────────┐ ┌──────────┐ ┌────────┐ ┌────────┐ ┌──────────────┐ │
│ │ speak  │ │ action │ │ file_read│ │  todo  │ │ times  │ │  web_search  │ │
│ └────────┘ └────────┘ └──────────┘ └────────┘ └────────┘ └──────────────┘ │
│ ┌────────┐ ┌────────┐ ┌──────────┐ ┌────────┐ ┌────────┐ ┌──────────────┐ │
│ │ memory │ │ timer  │ │video_call│ │  task  │ │ think  │ │request_teleop│ │
│ └────────┘ └────────┘ └──────────┘ └────────┘ └────────┘ └──────────────┘ │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 目录结构

```
zeus/
├── src/                          # 核心源代码
│   ├── unified_loop.py           # 主循环（三种呼吸节奏）
│   ├── llm_server.py             # LLM 服务封装（不变）
│   ├── query_board.py            # 查询状态追踪（不变）
│   ├── todo_board.py             # 工作流管理（不变）
│   ├── tool_manager.py           # 工具管理器
│   ├── identity_loader.py        # Identity Stack 加载（替代 prompt_loader）
│   ├── session_memory.py         # Session/Long-term Memory 管理
│   ├── timeline_manager.py       # Timeline 滑动窗口 + 蒸馏
│   ├── config_loader.py          # 配置加载（不变）
│   ├── document_manager.py       # 文档管理（不变）
│   ├── filter.py                 # 响应过滤（不变）
│   ├── text_tool_parser.py       # 响应解析（增加 △/◆ 标签）
│   └── gui/                      # GUI 相关
├── identity/                     # Identity Stack（替代 config/prompts.yaml）
│   ├── SOUL.md                   # 人格、价值观、交互风格
│   ├── AGENT.md                  # 观察模式、Heartbeat/Soulbeat 行为定义
│   ├── TOOLS.md                  # 工具调用格式约定
│   ├── KNOWLEDGE.md              # 领域知识、文档目录
│   └── USER.md                   # 用户画像（可由 VLM 通过 memory 工具更新）
├── memory/                       # 持久化记忆
│   ├── sessions/                 # Session Memory（按日期的 .md 文件）
│   │   ├── 2024-01-15.md
│   │   └── 2024-01-16.md
│   └── user_facts.md             # Long-term Memory（跨 session 的关键事实）
├── tools/                        # 工具模块（不变）
│   ├── speak/
│   ├── action/
│   ├── file_read/
│   ├── todo/
│   ├── times/
│   ├── timer/
│   ├── memory/
│   ├── web_search/
│   ├── video_call/
│   ├── request_teleop/
│   ├── think/
│   ├── task/
│   └── skills/                   # 组合技能（Markdown 定义）
│       ├── greet_visitor.md
│       └── daily_briefing.md
├── config/
│   ├── config.yaml               # 主配置（增加 heartbeat 相关参数）
│   └── prompts.yaml              # [废弃] 由 identity/ 替代
├── docs/
├── logs/
├── test/
└── cli.py
```

---

## 3. 三种呼吸节奏

### 3.1 概述

Zeus 的 UnifiedLoop 在同一个 VLM、同一个 KV Cache 上，以三种不同的"呼吸深度"运行：

| 节奏 | 符号 | 频率 | max_tokens | 用途 | KV Cache |
|------|------|------|-----------|------|----------|
| Heartbeat | △ | 2-3Hz | 50 | 快速感知：环境变化、手势、人物出入 | Prefix 全命中，只算尾部 |
| 正常推理 | — | ~0.67Hz | 2048 | 用户对话、工具调用、任务执行 | Prefix 全命中 |
| Soulbeat | ◆ | ~0.033Hz (30s) | 1024 | Timeline 蒸馏、记忆固化、主动任务检查 | Prefix 全命中 |

关键：三种模式**共享同一个 KV Cache Prefix**（Identity Stack + Pre-knowledge + VLM Summary + Timeline），只有尾部不同。Heartbeat 之所以快，是因为它的尾部极短（一张新图 + "△" ≈ 几百 tokens），而 prefix 全部命中缓存。

### 3.2 Heartbeat (△) — 快速感知

#### 输入

```
[KV Cache Prefix: Identity + Timeline(含历史帧图像)]

尾部 (每次重算):
  [USER] [当前摄像头帧] "△"
  或
  [USER] [当前摄像头帧] "△ [pending: web_search done, result: '明天晴天']"
```

#### 预期输出（三种）

```xml
<!-- 1. 无显著变化 -->
<idle/>

<!-- 2. 检测到变化，记录但不行动 -->
<event type="motion">画面右侧有人走过</event>

<!-- 3. 需要立即反应 -->
<react/>
```

#### 关键设计

- **多帧时序感知**：VLM 在 Heartbeat 推理时，KV Cache 里已经编码了 Timeline 中前几帧的图像。它做的不是单帧分类，而是在已编码的视觉序列上做 attention，从中识别运动模式（如挥手：连续帧中手的往复运动）。
- **Timeline 全写入**：每次 Heartbeat 的帧和结果都写入 Timeline，保持视觉连续性。这是识别跨帧动作（挥手、走近、犹豫）的前提。
- **max_tokens=50**：Heartbeat 只负责判断"要不要 react"，不生成完整回复。`<idle/>` 约 3 tokens，`<react/>` 约 3 tokens，极快。
- **两段式 React**：若返回 `<react/>`，立即触发一次正常推理生成完整回应。延迟 budget：Heartbeat 判断 ~300ms + 正常推理 ~1-1.5s ≈ 1.5-2s 从检测到反应。
- **Pending Tool Results 顺便消费**：Heartbeat 的 prompt 中可附带 pending tool result 信息，VLM 在一次推理中同时处理视觉观察和工具结果。

### 3.3 正常推理 — 对话与工具调用

#### 触发条件

- 用户通过 `/query` API 发来查询
- Heartbeat 返回 `<react/>`（立即触发）
- Pending tool result 需要 followup（需要完整推理来决定下一步）

#### 输入

```
[KV Cache Prefix: Identity + Timeline]

尾部 (每次重算):
  [USER] [当前摄像头帧] "<用户查询>"
        "[Todo: step X | Queries: running]"
  或
  [USER] [当前摄像头帧] "你在 Heartbeat 中检测到了需要反应的变化，请回应。"
  或
  [USER] [当前摄像头帧] "[tool_result: web_search finished, result: ...]
         请根据工具结果回应用户。"
```

#### 行为

- 完全兼容现有 v1.0 的推理逻辑
- 支持文字回复 + `<tool_call>` 标签
- Fire-and-Forget 工具执行（不变）
- 结果写入 Timeline（含图像和完整回复）

### 3.4 Soulbeat (◆) — 自省与记忆蒸馏

#### 触发条件

- Timeline 条目数 >= 20（预留 4 条 buffer，总容量 24）
- 距上次 Soulbeat 超过 30 秒
- QueryBoard 中有长时间 running 的查询

#### 输入

```
[KV Cache Prefix: Identity + Timeline]

尾部:
  [USER] [当前摄像头帧] "◆"
```

#### 预期输出

```xml
<distill>
  <facts>用户名张三；桌上有红杯和蓝色笔记本</facts>
  <events>14:20 用户询问天气，已通过 web_search 回答</events>
  <active>用户正在等待 file_read 关于会议纪要的结果</active>
  <discard>14:15-14:19 连续 idle，场景无显著变化</discard>
</distill>
```

#### 蒸馏结果去向

| 分类 | 去向 | 说明 |
|------|------|------|
| facts | → `memory/user_facts.md` | 持久化，跨 session 可用 |
| events | → `memory/sessions/YYYY-MM-DD.md` | 当天记录 |
| active | → 保留在 Timeline 中 | 不清除，下次推理需要 |
| discard | → 丢弃 | 释放 Timeline 槽位 |

### 3.5 UnifiedLoop 循环调度

```
┌──────────────────────────────────────────────────────────────────┐
│ UnifiedLoop._observation_cycle()                                 │
│ (动态频率)                                                       │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
               ┌──────────────────────────────┐
               │ 1. 检查 pending_tool_results  │
               └──────────────┬───────────────┘
                              │
                    ┌─────────┴─────────┐
                    │                   │
                    ▼                   ▼
          ┌──────────────┐    ┌─────────────────────────┐
          │ 有 pending   │    │ 无 pending              │
          │ 且需要完整   │    │                         │
          │ followup?    │    └────────────┬────────────┘
          └──────┬───────┘                 │
                 │ Yes                     ▼
                 ▼              ┌──────────────────────┐
          正常推理模式           │ 2. 检查 user_query   │
          (处理 tool result)   │    队列               │
                               └──────────┬───────────┘
                                          │
                                ┌─────────┴─────────┐
                                │                   │
                                ▼                   ▼
                      ┌──────────────┐    ┌──────────────────┐
                      │ 有 query     │    │ 无 query         │
                      └──────┬───────┘    └────────┬─────────┘
                             │                     │
                             ▼                     ▼
                       正常推理模式      ┌──────────────────────┐
                       (处理用户查询)   │ 3. 检查 soulbeat_due │
                                       └──────────┬───────────┘
                                                   │
                                         ┌─────────┴─────────┐
                                         │                   │
                                         ▼                   ▼
                                ┌──────────────┐   ┌──────────────┐
                                │ due          │   │ not due      │
                                └──────┬───────┘   └──────┬───────┘
                                       │                  │
                                       ▼                  ▼
                                 Soulbeat 模式      ┌──────────────┐
                                 ("◆" 蒸馏)        │ 4. Heartbeat │
                                                    │ ("△" 快速感知)│
                                                    └──────┬───────┘
                                                           │
                                                           ▼
                                              ┌─────────────────────┐
                                              │ 解析 Heartbeat 输出  │
                                              └──────────┬──────────┘
                                                         │
                                         ┌───────────────┼───────────────┐
                                         │               │               │
                                         ▼               ▼               ▼
                                    <idle/>         <event>...      <react/>
                                       │            </event>            │
                                       │               │                │
                                       ▼               ▼                ▼
                                    写入 timeline   写入 timeline   立即触发
                                    短休眠          短休眠          正常推理
                                    (~300ms)        (~300ms)        (完整回应)
                                       │               │                │
                                       └───────────────┴────────────────┘
                                                       │
                                                       ▼
                                              [下一个 cycle]
```

### 3.6 动态频率控制

```
上一次输出      → 下次 cycle 间隔
─────────────────────────────
<idle/>         → heartbeat_interval    (0.3-0.5s，实际 2-3Hz)
<event>         → heartbeat_interval    (继续快速观察)
<react/>        → 0 (立即触发正常推理)
正常推理完成     → heartbeat_interval    (回到快速观察)
Soulbeat 完成   → heartbeat_interval    (回到快速观察)
```

空闲时的实际节奏：
```
△ idle △ idle △ idle △ idle △ idle △ idle ...  (2-3Hz, 轻快)
                                          ↑ 检测到挥手
△ react → [正常推理 1.5s → speak "你好！"] → △ idle △ idle ...
```

---

## 4. KV Cache 策略

### 4.1 分层结构

```
┌─────────────────────────────────────────────────────────────────────┐
│ 稳定前缀 (CACHED) — 三种呼吸模式共享                                 │
│─────────────────────────────────────────────────────────────────────│
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │ Layer 0: Identity Stack (几乎永不失效)                        │  │
│  │                                                               │  │
│  │   SOUL.md 内容                                                │  │
│  │   + AGENT.md 内容 (含 Heartbeat/Soulbeat 行为定义)            │  │
│  │   + TOOLS.md 内容 (工具调用格式规则)                           │  │
│  │   + KNOWLEDGE.md 内容 (文档目录)                               │  │
│  │   + 活跃 Todo 指令 (仅工作流进行中)                            │  │
│  │                                                               │  │
│  │   → 只在配置文件被修改时才重算                                  │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │ Layer 1: Context (慢变)                                       │  │
│  │                                                               │  │
│  │   <pre_knowledge>                                             │  │
│  │     <current_time>2024-01-15 14:30:00 (Monday)</current_time> │  │
│  │     <disabled_tools>websearch, preparation</disabled_tools>   │  │
│  │     <available_tools>speak, file_read, action, ...</tools>    │  │
│  │     <self_identification>名字: 小叶子...</self_identification>│  │
│  │     <user_context>USER.md 关键内容</user_context>             │  │
│  │   </pre_knowledge>                                            │  │
│  │                                                               │  │
│  │   → 每分钟更新一次时间，或状态变更时更新                        │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │ Layer 2: VLM Summary (累积蒸馏摘要)                            │  │
│  │                                                               │  │
│  │   [USER] "Previous context summary: 14:15-14:28 期间，         │  │
│  │          用户张三来访，询问了天气和会议安排..."                   │  │
│  │   [ASST] "Understood."                                        │  │
│  │                                                               │  │
│  │   → 每次 Soulbeat 蒸馏后更新（累积追加）                       │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │ Layer 3: Timeline (最多 24 条，含图像，全帧写入)               │  │
│  │                                                               │  │
│  │   Entry 1:  [USER] "△" + IMG_1   [ASST] <idle/>              │  │
│  │   Entry 2:  [USER] "△" + IMG_2   [ASST] <idle/>              │  │
│  │   Entry 3:  [USER] "△" + IMG_3   [ASST] <event>有人出现</>   │  │
│  │   Entry 4:  [USER] "你好" + IMG_4 [ASST] "你好！..." + speak │  │
│  │   Entry 5:  [USER] "△" + IMG_5   [ASST] <idle/>              │  │
│  │   ...                                                         │  │
│  │   Entry 24: [USER] "△" + IMG_24  [ASST] <idle/>              │  │
│  │                                                               │  │
│  │   → 每次 cycle 追加（稳定增长，只在 Soulbeat 时批量清理）      │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│ 变化尾部 (RECOMPUTED) — 每次 cycle 替换                              │
│─────────────────────────────────────────────────────────────────────│
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │ Layer 4: 当前观察                                              │  │
│  │                                                               │  │
│  │   Heartbeat:  [USER] [IMG_new] "△"                            │  │
│  │   正常推理:   [USER] [IMG_new] "<用户查询>" + 状态摘要         │  │
│  │   Soulbeat:   [USER] [IMG_new] "◆"                            │  │
│  │                                                               │  │
│  │   ← 模型在此生成响应                                          │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 4.2 Cache 命中分析

| 场景 | Layer 0-2 | Layer 3 | Layer 4 | 增量计算量 |
|------|-----------|---------|---------|-----------|
| 连续 Heartbeat | ✅ 命中 | ✅ 前 N-1 条命中，最后 1 条新增 | ❌ 重算 | ~1 image + 几 tokens |
| Heartbeat → 正常推理 | ✅ 命中 | ✅ 命中 | ❌ 重算 | ~1 image + query tokens |
| 正常推理 → Heartbeat | ✅ 命中 | ✅ 前 N-1 条命中 | ❌ 重算 | ~1 image + 几 tokens |
| Soulbeat 后 | ✅ 命中 | ⚠️ 部分失效（条目被清理） | ❌ 重算 | 需重算清理后的 timeline |

### 4.3 Heartbeat 条目的 Token 成本

```
正常交互条目:
  [USER] "请帮我查一下明天的天气" + [IMAGE]     ~20 tokens + image tokens
  [ASST] "好的。<tool_call>{...}</tool_call>"   ~50 tokens
  合计: ~70 text tokens + image tokens

Heartbeat idle 条目:
  [USER] "△" + [IMAGE]                          ~2 tokens + image tokens
  [ASST] "<idle/>"                               ~3 tokens
  合计: ~5 text tokens + image tokens
```

Heartbeat 条目的文本成本几乎为零，**边际成本全在图像上**。而图像无论是否写入 timeline 都要编码（VLM 需要看当前帧），所以全写入的额外成本 = 在 KV Cache 中多保留这些已编码的图像 KV，这是内存成本而非计算成本。

---

## 5. Timeline 管理

### 5.1 滑动窗口蒸馏

```
Timeline 容量: 24 条

正常运行: 持续追加
  [1] [2] [3] ... [20] [21] [22] [23] [24]
                        ↑ 达到 20 条，触发 Soulbeat

Soulbeat 蒸馏:
  ┌─── 最老的 16 条 ──────────────┐  ┌─── 保留最新 8 条 ──┐
  [1] [2] [3] ... [14] [15] [16]    [17] [18] ... [24]
           │                                  │
           ▼                                  │
  VLM Summary (累积追加):                      │
  "旧 summary + 这 16 条的蒸馏"                │
                                              │
  Timeline 重置为:                              │
  [17] [18] [19] [20] [21] [22] [23] [24]    ← 从 8 条继续增长
```

### 5.2 蒸馏 Prompt

Soulbeat 时，VLM 收到的指令（定义在 AGENT.md 中）：

```
收到 "◆" 时，回顾 Timeline 中的交互历史，进行结构化蒸馏：

<distill>
  <facts>提取关键事实（人物身份、物品位置、用户偏好等）</facts>
  <events>按时间顺序记录重要事件</events>
  <active>当前仍在进行中的任务或等待</active>
  <discard>可以安全丢弃的信息（连续 idle、无变化时段）</discard>
</distill>

蒸馏时注意保留视觉场景的变化描述，即使图像将被释放。
例如："14:30 时桌上有红色杯子和蓝色笔记本" — 这样即使丢失了图像，
后续推理仍然知道场景状态。
```

### 5.3 VLM Summary 的累积

```
第一次蒸馏后:
  Summary: "14:15-14:27 期间，环境无人。14:27 用户出现并挥手打招呼。"

第二次蒸馏后:
  Summary: "14:15-14:27 期间，环境无人。14:27 用户出现并挥手打招呼。
           14:27-14:39 用户询问了天气（已回答：明天晴天）和会议安排
           （正在查询中）。桌面上有红杯和笔记本。"

第三次蒸馏后:
  Summary: (在上述基础上继续追加...)
```

Summary 会越来越长。当超过 ~1000 tokens 时，可以在 Soulbeat 中要求 VLM 对 Summary 本身进行再压缩。

---

## 6. Identity Stack

### 6.1 文件层级与优先级

```
优先级 (高→低):
  SOUL.md  →  AGENT.md  →  TOOLS.md  →  KNOWLEDGE.md  →  USER.md
  (人格)      (行为规则)    (工具约定)    (领域知识)       (用户画像)
```

### 6.2 SOUL.md — 人格定义

```markdown
# 小叶子

## 核心身份
我是小叶子，一个视觉智能助手。我通过摄像头观察环境，通过对话和工具帮助用户。

## 性格特质
- 友善、主动、适度幽默
- 观察敏锐，会注意到环境变化并适时提及
- 诚实，不确定时会说明

## 交互风格
- 日常对话用中文，技术讨论可中英混用
- 回复简洁，避免冗长
- 主动但不打扰：有事说事，没事不废话

## 身份边界
- 如果被问"是千问/Qwen/GPT吗"，回答：不是，我是小叶子
- 不假装有物理感受（饥饿、疲倦等）
```

### 6.3 AGENT.md — 行为规则

```markdown
# 行为规则

## Heartbeat 模式 (收到 "△" 时)

你会同时看到 Timeline 中最近多帧画面。利用跨帧对比进行判断：

### 关注的变化类型
**跨帧运动** (对比前几帧和当前帧):
- 人物手部运动模式：挥手(往复摆动)、招手、指向、竖大拇指
- 人物进出画面
- 物品位置改变（被拿走、放下、移动）
- 人物朝向/注意力方向变化

**长时序模式** (需要观察 5 秒以上的趋势):
- 用户在画面中停留超过 5 秒但没有说话 → 考虑主动问好
- 用户反复看向某个方向 → 注意记录
- 场景逐渐变化（光线、物品累积变化）

### 输出规则
- 无显著变化 → `<idle/>`
- 检测到变化但不需要行动 → `<event type="...">简短描述</event>`
- 需要立即反应 → `<react/>`

保持判断极度简洁，不要过度分析。"△" 是快速扫描，不是深度思考。

### Pending Tool Results
如果 "△" 后附带了 pending tool result，在同一次判断中考虑是否需要将结果
告知用户。如果用户在场且结果重要，返回 `<react/>`。

## Soulbeat 模式 (收到 "◆" 时)

回顾 Timeline 中的交互历史，进行结构化蒸馏。输出格式：

<distill>
  <facts>关键事实</facts>
  <events>时序事件</events>
  <active>进行中的任务</active>
  <discard>可安全丢弃的信息</discard>
</distill>

蒸馏时保留视觉场景的文字描述，确保即使图像被释放，场景状态仍可理解。

## 正常推理模式

### Fire-and-Forget 规则
- 发出 tool_call 后立即继续，不等待结果
- tool result 会在后续 cycle 中返回
- 可以在同一次回复中发出多个 tool_call

### 观察模式
- 如果没有需要说或做的事情，回复 `<idle>`
- 不要为了说话而说话

### 工具调用格式
使用 <tool_call> 标签：
<tool_call>
{"name": "工具名", "arguments": {参数}}
</tool_call>
```

### 6.4 与 OpenClaw 生态的兼容

Zeus 的 Identity Stack 采用与 OpenClaw 相同的 Markdown 文件格式：

- **SOUL.md** 格式兼容 OpenClaw 社区的 persona 模板
- **USER.md** 格式兼容 OpenClaw 的用户画像格式
- **TOOLS.md** 中的工具定义可参考 OpenClaw 的 YAML frontmatter 约定
- 未来可考虑接入 ClawHub 的 skill/persona 注册表

### 6.5 热加载

Identity Loader 监控 `identity/` 目录的文件变更：

- 文件修改 → 重新读取 → 标记 KV Cache prefix 需要重算
- 下一次 cycle 时自动重算 prefix
- 无需重启系统

---

## 7. 三层记忆系统

### 7.1 架构

```
┌────────────────────────────────────────────────────┐
│ Working Memory (KV Cache)                          │
│                                                    │
│ 内容: Timeline 中最近 24 条（含图像）               │
│       + VLM Summary (累积蒸馏)                     │
│ 容量: 受 KV Cache 大小限制                          │
│ 生命周期: 当前 session                              │
│ 访问速度: 即时（已在 cache 中）                     │
└───────────────────────┬────────────────────────────┘
                        │ Soulbeat 蒸馏
                        ▼
┌────────────────────────────────────────────────────┐
│ Session Memory (Markdown 文件)                     │
│                                                    │
│ 位置: memory/sessions/YYYY-MM-DD.md                │
│ 内容: 当天的 events 蒸馏记录                        │
│ 格式: 时间戳 + 事件描述                             │
│ 生命周期: 按天存储，可配置保留天数                    │
│ 访问方式: 通过 file_read 工具或 VLM 直接读取         │
└───────────────────────┬────────────────────────────┘
                        │ facts 提取
                        ▼
┌────────────────────────────────────────────────────┐
│ Long-term Memory (Markdown 文件)                   │
│                                                    │
│ 位置: memory/user_facts.md + USER.md               │
│ 内容: 跨 session 的关键事实和用户偏好               │
│ 格式: 分类的事实列表                                │
│ 生命周期: 持久化                                    │
│ 访问方式: 启动时加载到 Identity Stack (USER.md)     │
│          或通过 memory 工具查询                     │
└────────────────────────────────────────────────────┘
```

### 7.2 Session 启动时的记忆恢复

```
Zeus 启动 / 新 session 开始:
  1. 读取 identity/ 栈 (含 USER.md 长期记忆)
  2. 读取最近的 session memory 文件
  3. 将关键上下文注入到 VLM Summary 位置:
     "上次 session (2024-01-14): 用户询问了项目进度，
      待办事项还剩3项未完成。"
  4. 开始正常的 Heartbeat 循环
```

---

## 8. Fire-and-Forget 工具执行（不变）

### 8.1 执行流程

```
VLM 发出 tool_call
       │
       ▼
┌─────────────────────────────┐
│ 添加到 QueryBoard            │
│ query_board.add_tool_call() │
└─────────────────────────────┘
       │
       ├── "speak" 工具? ─── Yes ──→ 同步执行 speak_callback()
       │
       No
       │
       ▼
┌─────────────────────────────┐
│ 提交到 ThreadPoolExecutor    │
│ (4 workers)                 │
│ 立即返回 {"status":          │
│          "executing"}       │
└─────────────────────────────┘
       │ (后台执行)
       ▼
┌─────────────────────────────┐
│ 执行完成                     │
│ 更新 QueryBoard              │
│ 有额外信息? → 加入           │
│ _pending_tool_results       │
└─────────────────────────────┘
       │
       ▼
  下次 Heartbeat/正常推理时消费
```

### 8.2 与 Heartbeat 的协同

```
cycle N:     正常推理 → 发出 web_search tool_call → fire-and-forget
cycle N+1:   Heartbeat △ → <idle/> (工具还在执行)
cycle N+2:   Heartbeat △ → <idle/> (工具还在执行)
cycle N+3:   Heartbeat △ [pending: web_search done, result: ...]
             → VLM 判断: 用户在场 + 结果重要 → <react/>
cycle N+3.1: 正常推理 → speak "查到了，明天晴天！"
```

**效果**: Tool result 被消费的延迟从原来的 ~1.5s 降到 ~300-500ms。

---

## 9. 跨帧手势识别示例

### 9.1 挥手识别的工作原理

```
Timeline 中的连续帧 (Heartbeat 2Hz):

  t=0.0s  [IMG] 人站着，手在身侧          → <idle/>
  t=0.5s  [IMG] 人站着，右手举起            → <idle/>
  t=1.0s  [IMG] 人站着，右手偏右            → <idle/>
  t=1.5s  [IMG] 人站着，右手偏左            → <event type="gesture">手部运动</event>
  t=2.0s  [IMG] 人站着，右手偏右（往复）    → <react/>
                                                ↓
                                          立即正常推理
                                          VLM 看到最近 5 帧的运动模式
                                          判断: 挥手打招呼
                                          → speak "你好！有什么需要帮忙的吗？"

总延迟: 2.0s (积累足够帧) + 0.3s (heartbeat) + 1.5s (正常推理) ≈ 3.8s
实际上 VLM 可能在 t=1.5s 就 react (3帧足够判断)，则 ≈ 1.5 + 0.3 + 1.5 = 3.3s
```

### 9.2 VLM 为什么能识别

VLM 在 Heartbeat 推理时：
1. KV Cache 中已编码了前几帧图像的 key-value
2. 当前帧编码后，通过 self-attention 与历史帧的 KV 交互
3. VLM 在"△"的 prompt 下被引导关注跨帧变化
4. 多帧中手部位置的系统性变化 → 运动模式识别

不需要 optical flow，不需要 MediaPipe — VLM 的 attention 机制本身就在做跨帧对比。AGENT.md 中的指令只是引导它关注什么类型的变化。

---

## 10. 配置系统

### 10.1 新增配置项 (config.yaml)

```yaml
# 呼吸节奏配置
breathing:
  heartbeat_interval: 0.4        # Heartbeat 间隔 (秒)，对应约 2.5Hz
  heartbeat_max_tokens: 50       # Heartbeat 最大输出 tokens
  soulbeat_interval: 30          # Soulbeat 最小间隔 (秒)
  soulbeat_max_tokens: 1024      # Soulbeat 最大输出 tokens
  soulbeat_timeline_threshold: 20 # Timeline 达到此数量时触发 Soulbeat

# Timeline 配置
timeline:
  max_entries: 24                # Timeline 最大条目数
  keep_after_distill: 8          # 蒸馏后保留的最新条目数
  max_summary_tokens: 1000       # VLM Summary 最大长度，超过则再压缩

# Identity Stack 配置
identity:
  directory: "identity/"          # Identity 文件目录
  hot_reload: true               # 是否监控文件变更并热加载

# 记忆配置
memory:
  session_dir: "memory/sessions/" # Session Memory 目录
  user_facts_file: "memory/user_facts.md"
  session_retention_days: 30      # Session 文件保留天数

# 模型配置 (不变)
model:
  base_url: "http://localhost:8000/v1"
  model: "Qwen/Qwen2.5-VL-72B"
  temperature: 0.7
  max_tokens: 2048
```

---

## 11. 改造量评估

### 11.1 模块改动清单

| 模块 | 改动程度 | 具体内容 |
|------|---------|---------|
| `unified_loop.py` | **中等** | cycle 调度加入模式判断（heartbeat/soulbeat/normal）、动态频率控制、两段式 react |
| `prompt_loader.py` → `identity_loader.py` | **重写** | 从读 YAML 改为读 Markdown 文件栈，支持热加载和文件监控 |
| `text_tool_parser.py` | **小改** | 增加 `<idle/>` `<event>` `<react/>` `<distill>` 标签解析 |
| `session_memory.py` | **新增** | 蒸馏结果存储、session 文件管理、启动时记忆恢复 |
| `timeline_manager.py` | **新增/重构** | 从 unified_loop 中提取 timeline 管理逻辑，实现滑动窗口蒸馏 |
| `llm_server.py` | **不变** | KV Cache 策略本身无需修改 |
| `query_board.py` | **不变** | Fire-and-Forget 逻辑完全保留 |
| `todo_board.py` | **不变** | |
| `tool_manager.py` | **小改** | 可选增加 skills/ 目录扫描 |
| `config.yaml` | **小改** | 增加 breathing / timeline / identity / memory 配置段 |
| `identity/` 目录 | **新增** | SOUL.md, AGENT.md, TOOLS.md, KNOWLEDGE.md, USER.md |
| `memory/` 目录 | **新增** | sessions/ 子目录, user_facts.md |
| `config/prompts.yaml` | **废弃** | 由 identity/ 替代 |

### 11.2 不变的核心组件

- LLMServer（VLM 推理封装）
- QueryBoard（查询状态追踪 + Fire-and-Forget）
- TodoBoard（工作流管理）
- ToolManager（工具发现与执行，核心逻辑不变）
- 所有工具实现（speak, action, file_read, web_search 等）
- Flask API 层（外部接口）
- 日志系统

---

## 12. 版本历史

| 版本 | 日期 | 描述 |
|------|------|------|
| 1.0 | 2024-01 | 初始版本 |
| 1.1 | 2024-02 | 添加 UnifiedLoop 合并架构 |
| 1.2 | 2024-02 | 添加 Timer 功能 |
| 2.0 | 2024-xx | VLM Agent 架构：三种呼吸节奏、Identity Stack、三层记忆、Timeline 全写入 + 滑动窗口蒸馏 |