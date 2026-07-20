# pi-wiki-agent — 智能 Wiki 文档管理代理

**一句话介绍**：监听 Git/SVN 代码提交，利用 LLM 自动同步更新项目的 Wiki 文档，确保文档与代码保持一致。

## 为什么需要它

软件项目中最常见的文档问题是**代码变了，文档没变**。开发者在代码变更后会忘记同步更新 Wiki，导致文档描述的功能与实际代码不一致。

pi-wiki-agent 通过以下方式解决这个问题：

1. **自动发现代码变更** — 监控 Git/SVN 仓库的新提交
2. **反向索引定位** — 根据源码→Wiki 章节的映射关系，精确找到需要更新的文档位置
3. **LLM 智能更新** — 调用大模型阅读 diff，理解变更意图，编辑 Wiki 页面
4. **质量保障** — 自动校验 Wiki 的结构完整性和内容时效性

## 架构总览

```
┌─────────────────────────────────────────────────────────┐
│                    桌面端 (Web UI)                        │
│  Frontend (Vue.js)  ←→  Desktop (FastAPI + uvicorn)     │
├─────────────────────────────────────────────────────────┤
│                     Wiki Agent 核心                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────────┐  │
│  │ 单Agent  │  │  Chain   │  │  Quality Checker     │  │
│  │ 同步模式 │  │ 链式模式  │  │  质量检查 (P0+P1)     │  │
│  └──────────┘  └──────────┘  └──────────────────────┘  │
│  ┌──────────────────────────────────────────────────┐  │
│  │  Extension System (扩展系统)                       │  │
│  │  · LightGuard — 结构化守卫 (防止标记被破坏)        │  │
│  │  · WikiToolGuard — 文件访问控制                    │  │
│  │  · 外部扩展加载 (三层发现 + manifest)              │  │
│  └──────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────┐  │
│  │  VCS Monitor (Git/SVN 变更监控)                    │  │
│  │  Wiki Indexer (反向索引: 源文件↔Wiki章节)          │  │
│  │  Structure Validator (Wiki 结构校验, 13项检查)     │  │
│  └──────────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────────────┤
│              底层 Agent 框架                             │
│  pi-agent (Agent 循环/工具) ← pi-ai (LLM 统一层)        │
└─────────────────────────────────────────────────────────┘
```

## 核心工作流

### 1. 标准同步（单 Agent 模式）

```
Git 提交 → VCS Monitor → Wiki Indexer 反向索引 → LLM Agent → 编辑 Wiki 页面
```

一个 Agent 直接分析 diff、定位受影响章节、执行编辑。快速直接。

### 2. Chain 链式同步（多 Agent 协作）

```
Git 提交
  → 反向索引查找受影响章节
    → Step 1: diff-analyzer  生成变更分析
    → Step 2: wiki-planner   制定更新计划
    → Step 3: wiki-writer    执行精确编辑
```

每个 Agent 专注一个子任务，`{previous}` 模板传递上下文。更可靠、更可观测。

### 3. 质量检查

```
逐页扫描 .wiki/**/*.md
  → P0 溯源: source 链接有效性、反向索引一致性、孤儿页面
  → P1 时效: 源文件时间戳对比、空章节、重复章节名、HTML 残留
  → 生成 QualityReport
```

## Wiki 文档格式

被管理的 Wiki 页面使用特殊标记实现精确的章节定位：

```markdown
---
title: 系统架构
date: 2026-07-11
tags: [design]
---

<!-- WIKI_SECTION:模块划分 -->
## 模块划分
**source**:[src/taskman/cli.py](file://src/taskman/cli.py)

模块说明...
<!-- WIKI_SECTION_END -->
```

- `<!-- WIKI_SECTION:xxx -->` / `<!-- WIKI_SECTION_END -->` — 标记章节边界
- `**source**:[文件名](file://路径)` — 溯源行，记录章节对应的源代码
- `repowiki-metadata.json` — 反向索引，维护源文件→Wiki 章节的映射

## 技术特性

| 特性 | 说明 |
|------|------|
| **双模式同步** | 单 Agent（快速）/ Chain 链式（多 Agent 分步协作） |
| **VCS 支持** | Git（完整）、SVN（基础） |
| **LLM 兼容** | OpenAI / Anthropic / Google / DeepSeek / 自定义 API |
| **扩展系统** | 三层发现（全局/项目/显式路径），支持 pyproject.toml manifest |
| **结构化守卫** | LightGuard 防止 LLM 破坏标记和溯源行 |
| **Streaming** | SSE 实时推送 Agent 工具调用和文本生成 |
| **质量检查** | 9 项自动化检查（溯源 + 时效） |
| **Agent 自定义** | Markdown + YAML frontmatter 定义 Agent 角色 |

## 项目结构

```
pi-wiki-agent/
├── packages/
│   ├── ai/                 # LLM 统一抽象层
│   ├── agent/              # Agent 循环与工具执行
│   ├── coding-agent/       # 编码 Agent CLI
│   ├── wiki-agent/         # Wiki 管理核心 ★
│   │   ├── agents/         # 内置 Agent 定义
│   │   └── src/pi_wiki_agent/core/
│   │       ├── chain/              # Chain 链式执行
│   │       ├── extensions/         # 扩展系统
│   │       ├── wiki_quality.py     # 质量检查
│   │       └── structure_validator.py
│   └── tui/                # 终端 UI 库
├── desktop/                # 桌面端 Web 后端 (FastAPI)
├── frontend/               # 浏览器前端 (Vue.js)
├── extensions/             # 内置扩展
└── docs/                   # 设计文档
```

## 快速开始

### 1. 安装依赖

```bash
git clone <repo-url> && cd pi-wiki-agent
uv sync
```

### 2. 配置 API Key

```bash
cp .env.example .env
# 编辑 .env，填入 LLM API Key
```

### 3. 启动桌面端

```bash
uv run pi-wiki-desktop
# 服务启动在 http://127.0.0.1:8899
```

### 4. 使用

打开浏览器 → 添加项目（需包含 `.wiki` 目录）→ 选择提交 → 选择同步模式 → 点击同步

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查 |
| GET/POST/DELETE | `/api/projects[/{name}]` | 项目管理 |
| GET | `/api/projects/{name}/commits` | 待处理提交 |
| GET | `/api/projects/{name}/commits/{rev}` | 提交详情（含受影响章节） |
| POST | `/api/projects/{name}/sync/{rev}` | 单 Agent 同步 |
| POST | `/api/projects/{name}/sync/{rev}/stream` | 单 Agent 同步 (SSE) |
| POST | `/api/projects/{name}/chain-sync/{rev}` | Chain 链式同步 |
| POST | `/api/projects/{name}/chain-sync/{rev}/stream` | Chain 同步 (SSE) |
| POST | `/api/projects/{name}/sync-all` | 全部同步 |
| POST | `/api/projects/{name}/quality-check` | 质量检查 |
| GET/POST | `/api/models` | 模型管理 |
| GET/POST/DELETE | `/api/projects/{name}/filters` | 过滤规则 |

## 自定义 Agent

在 `~/.pi/wiki-agent/agents/` 或 `<project>/.pi/agents/` 下创建 `.md` 文件：

```markdown
---
name: my-reviewer
description: 代码审查 Agent
tools: [read, grep, find, ls]
thinking: medium
---

你是一个代码审查专家。你的任务是...
```

| 字段 | 说明 |
|------|------|
| `name` | Agent 名称（必填） |
| `description` | 描述 |
| `tools` | 可用工具列表 |
| `model` | 模型（格式: `provider:model_id`） |
| `thinking` | 思考级别: `off` / `low` / `medium` / `high` |
| `output` | 默认输出文件名 |
| `reads` | 默认读取的文件列表 |

正文部分为 system prompt，会替换默认的 Wiki 管理 prompt。

## 编写扩展

```python
# extensions/my_ext.py
def extension_factory(api):
    api.register_tool(
        name="my_tool",
        description="我的自定义工具",
        parameters={"type": "object", "properties": {}},
        execute=my_async_function,
    )

    api.on("session_start", on_session_start)
```

扩展发现路径（优先级从低到高）：
1. `<package>/extensions/` — 内置
2. `~/.pi/wiki-agent/extensions/` — 用户级
3. `<project>/.pi/extensions/` — 项目级
4. `settings.json` 中的显式路径

## 依赖要求

- Python >= 3.11
- [uv](https://docs.astral.sh/uv/) 包管理器
- Git 或 SVN
- 至少一个 LLM API Key (DeepSeek / OpenAI / Anthropic / Google)

## 相关项目

- [pi-mono](https://github.com/badlogic/pi-mono) — TypeScript 上游参考实现
- [pi-subagents](https://github.com/agwab/pi-subagents) — 子代理 Chain 系统（设计参考）
- [pi-workflow](https://github.com/agwab/pi-workflow) — DAG 工作流系统（设计参考）

## 许可证

MIT
