<p align="center">
  <h1 align="center">pi-wiki-agent</h1>
  <p align="center"><strong>VCS 驱动的 Wiki 文档管理代理 — 代码变更时自动同步 Wiki，让文档始终与代码一致。</strong></p>
</p>

<p align="center">
  <a href="#核心特性">核心特性</a> •
  <a href="#快速开始">快速开始</a> •
  <a href="#工作原理">工作原理</a> •
  <a href="#项目架构">项目架构</a> •
  <a href="#桌面端">桌面端</a> •
  <a href="#评测框架">评测框架</a> •
  <a href="#开发指南">开发指南</a>
</p>

---

## 核心特性

- **VCS 驱动同步** — 每次代码提交自动触发 3 阶段 LLM 工作流（Analyze → Plan → Write），自动更新 Wiki 页面以反映代码变更。无需手动维护文档。
- **DAG 并行执行** — Wiki 页面按拓扑顺序并行更新。LLM 声明任务依赖关系，引擎负责拓扑排序和最大化并发。
- **质量自动修复** — 内置质量检查器发现断链、过期内容、空章节、结构缺陷。一键或定时触发修复工作流自动处理。
- **反向索引溯源** — 每个 Wiki 章节携带 `**source**` 链接，追溯到对应的源代码文件。代码 → Wiki、Wiki → 代码双向传播。
- **YAML → AST 工作流编译器** — 工作流用 YAML 定义，编译为 Python AST 节点（非字符串模板）。类型安全、可静态分析、可扩展。
- **断点续跑** — 每个阶段持久化到磁盘。失败后从最后一个成功阶段恢复，而非从头开始。
- **桌面端 + SSE 流式** — Vue 3 前端，支持实时 Agent 进度、工具调用可视化、模型管理和定时任务调度。
- **多模型支持** — 内置 739 个模型目录，覆盖 22 个 provider。通过 UI 或 `~/.pi/agent/models.json` 添加自定义模型。
- **评测框架** — 结构化测试框架，基于 Diff 的测试用例、pass@k 指标、LLM-as-Judge 评分、Markdown 报告。

---

## 为什么需要它

软件项目中最常见的问题是**代码变了，文档没变**。开发者提交代码后忘记同步 Wiki，导致文档描述与实际代码不一致。

pi-wiki-agent 的解决方式：

1. **自动发现变更** — 监控 Git/SVN 仓库的新提交
2. **反向索引定位** — 根据源码 → Wiki 章节的映射关系，精确找到需要更新的文档位置
3. **LLM 智能分析** — 调用大模型阅读 diff、理解变更意图、编辑 Wiki 页面
4. **质量保障** — 9 项自动化检测（P0 可追溯性 + P1 内容新鲜度）

---

## 快速开始

### 环境要求

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) 包管理器
- 至少一个 LLM API Key（DeepSeek / Anthropic / Gemini / OpenAI）

### 安装

```bash
git clone https://github.com/openxjarvis/pi-wiki-agent.git
cd pi-wiki-agent
uv sync
```

### 配置

```bash
# .env — 至少配置一个 API Key
DEEPSEEK_API_KEY=sk-xxx
# 或 ANTHROPIC_API_KEY=sk-ant-xxx
# 或 GEMINI_API_KEY=xxx
# 或 OPENAI_API_KEY=sk-xxx

# 可选：添加自定义模型
# 编辑 ~/.pi/agent/models.json（也可通过桌面端 UI 管理）
```

### 启动

```bash
# 启动桌面端服务器
uv run pi-wiki-desktop
# → 浏览器打开 http://127.0.0.1:8899

# 或编程调用
python -c "
import asyncio
from pi_wiki_agent.core.workflow_sync import execute_workflow_sync

result = asyncio.run(execute_workflow_sync(
    project_path='D:/project/wiki-demo-taskman',
    changed_files=['src/taskman/cli.py'],
    commit_message='feat: add export command',
    diff=open('diff.txt').read(),
    revision='HEAD',
    script=open('sync.yaml').read(),
    model='deepseek:deepseek-v4-flash',
))
print(result.result)
"
```

---

## 工作原理

### 同步工作流

```
┌──────────┐     ┌──────────┐     ┌──────────┐
│ Analyze  │ ──▶ │  Plan    │ ──▶ │  Write   │
│ 分析阶段 │     │ 规划阶段  │     │ 执行阶段  │
│          │     │          │     │  (DAG)   │
│ diff →   │     │ 生成     │     │ Agent A  │
│ 影响分析 │     │ 任务列表  │     │ Agent B  │
│          │     │ + schema │     │ Agent C  │
└──────────┘     └──────────┘     └──────────┘
```

1. **Analyze（分析）** — `diff-analyzer` Agent 阅读每个变更文件的 diff，输出对 Wiki 文档的影响分析。
2. **Plan（规划）** — `wiki-planner` Agent 基于分析结果，通过 `structured_output` 工具输出结构化 JSON（`file_tasks` + `no_change_files`）。每条 task 指定目标页面、章节、操作类型（create/update/delete）和精确指令。
3. **Write（执行）** — `wiki-writer` Agents 按 DAG 拓扑并行执行。Planner 声明任务依赖，引擎用 Kahn 算法拓扑排序，3 色 DFS 检测循环依赖。

### 修复工作流

```
质量检查 → 发现问题 → Analyze → Plan → Fix (DAG 并行修复)
```

`WikiQualityChecker` 扫描全部 `.wiki/*.md` 页面，检测 9 类缺陷（P0 可追溯性 5 项 + P1 新鲜度 4 项），生成结构化报告，触发自动修复流程。

| 优先级 | 检查项 | 严重度 |
|--------|--------|--------|
| P0 | `source_link_missing` — 溯源链接指向不存在文件 | error |
| P0 | `index_page_missing` — 反向索引指向不存在的页面 | error |
| P0 | `index_source_missing` — 反向索引指向不存在的源文件 | error |
| P0 | `orphan_page` — 页面不在反向索引中 | warning |
| P0 | `stale_index_entry` — 索引章节已从页面删除 | warning |
| P1 | `outdated_content` — 源文件修改时间晚于 Wiki 保存时间 | warning |
| P1 | `empty_section` — WIKI_SECTION 标记下无正文 | warning |
| P1 | `duplicate_section` — 同一页面重复章节名 | error |
| P1 | `html_entities` — HTML 实体残留（LLM 转义错误） | info |

### 工作流定义（YAML）

工作流用 YAML 定义，通过 AST 编译器编译为 Python 脚本：

```yaml
name: sync
phases:
  - title: Analyze
    steps:
      - agent: diff-analyzer
        prompt: |
          ## 提交信息
          ${commit_message}
          ## 变更文件
          ${join(changed_files, "- ${item}")}

  - title: Plan
    steps:
      - agent: wiki-planner
        output_schema:
          file_tasks:
            - file: str
              wiki_page: str
              action: {enum: [create, update, delete]}
              instructions: str

  - title: Write
    mode: dag
    for_each: ${outputs.Plan.file_tasks}
    steps:
      - agent: wiki-writer
```

支持 4 种执行模式：`serial`（串行）、`parallel`（并行）、`dag`（有向无环图）、`pipeline`（流水线）。完整架构见 [AST 编译器详解](packages/wiki-agent/src/pi_wiki_agent/core/workflow/ast_compiler/DETAIL.html)。

---

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
- `repowiki-metadata.json` — 反向索引，维护源文件 → Wiki 章节的映射关系

---

## 项目架构

```
pi-wiki-agent/
├── desktop/                         # FastAPI 后端 + Vue 3 前端
│   ├── src/pi_wiki_desktop/
│   │   ├── app.py                   # 服务入口 (uvicorn)
│   │   └── api/v1/endpoints/        # REST + SSE 端点
│   └── pyproject.toml
├── frontend/                        # Vue 3 SPA
│   ├── index.html
│   ├── app.js
│   └── style.css
├── packages/
│   ├── wiki-agent/                  # Wiki 管理核心引擎 ★
│   │   └── src/pi_wiki_agent/
│   │       ├── core/
│   │       │   ├── workflow/        # DAG 引擎 + AST 编译器
│   │       │   ├── workflow_sync.py # 同步编排器
│   │       │   ├── wiki_quality.py  # 质量检查器
│   │       │   └── agent_session.py # Agent 会话管理
│   │       ├── cases/               # 测试用例库 (8 个场景)
│   │       ├── eval/                # 评测框架
│   │       └── cron/                # 定时任务调度
│   ├── ai/                          # LLM provider 层 (739 个模型)
│   ├── agent/                       # Agent 循环 + 工具执行
│   ├── coding-agent/                # 文件编辑工具
│   └── tui/                         # 终端 UI 库
├── docs/                            # 设计文档 + 评测方案
├── .env                             # API Keys (gitignore)
└── pyproject.toml                   # uv workspace 根配置
```

---

## 桌面端

启动服务 `http://127.0.0.1:8899`：

```bash
uv run pi-wiki-desktop
```

**项目管理**
- 添加/删除项目，文件浏览器选择目录
- 每个项目维护 `.wiki/`（页面、反向索引、断点状态）

**提交同步**
- 三种模式：**单 Agent**（串行）、**Chain**（链式管道）、**Workflow**（DAG 并行）
- 选择待处理提交、预览文件变更、触发同步
- **SSE 实时流式**展示 Agent 各阶段进度

**质量面板**
- 运行全站质量检查，按错误/警告/提示分类
- **自动修复工作流**，实时显示每类问题的修复进度

**设置页**
- **模型管理** — 添加自定义 Provider 和模型
- **过滤规则** — 按路径/作者/提交信息跳过特定提交
- **定时任务** — 配置 Cron 表达式，自动运行质量检查和修复

---

## 评测框架

项目包含结构化的 Agent 评测框架：

```bash
# Dry-run 模式（不调用 LLM，验证管道逻辑）
python -m pi_wiki_agent.eval \
    --cases packages/wiki-agent/src/pi_wiki_agent/cases \
    --dry-run \
    --report docs/test/reports/report.md

# 真实 LLM 运行
python -m pi_wiki_agent.eval \
    --cases packages/wiki-agent/src/pi_wiki_agent/cases \
    --report docs/test/reports/report.md
```

**测试用例**无需 YAML，每个用例是 `diff.txt` + `args.json` + `expected.json` 三个文件：

```
cases/
├── case_01_new_feature/       ← Agent 应为新增功能添加 Wiki 内容
├── case_02_modify_behavior/   ← Agent 应更新已有描述
├── case_03_remove_refactor/   ← Agent 应移除过时内容
├── case_04_doc_only/          ← Agent 正确判定无需修改
├── case_05_multi_file/        ← Agent 处理多文件变更
├── case_06_new_feature_2/     ← 交叉验证
├── case_07_modify_behavior_2/ ← 交叉验证
└── case_08_large_diff/        ← 压力测试（50 行变更）
```

**指标**遵循 SWE-bench 方法论：`pass@k`（k 次尝试至少 1 次成功概率）、`pass^k`（全部成功）、质量变化、延迟、Token 消耗。详见[评测方案](docs/test/EVALUATION_PLAN.md)。

---

## 开发指南

### 环境搭建

```bash
git clone https://github.com/openxjarvis/pi-wiki-agent.git
cd pi-wiki-agent
uv sync
```

### 运行测试

```bash
uv run pytest                              # 全部测试 (578 通过)
uv run pytest packages/wiki-agent/tests/   # Wiki-agent 测试
uv run pytest --live -v                    # 真实 API 测试（需要 API Key）
```

### 代码规范

```bash
uv run ruff check .   # Lint
uv run ruff format .  # Format
```

### 底层依赖包

| 包 | 说明 | 测试数 |
|---|------|--------|
| `pi_ai` | 统一 LLM 流式层 (Google, Anthropic, OpenAI, …) | 156 |
| `pi_agent` | Agent 循环、工具执行、状态管理 | — |
| `pi_coding_agent` | 编码 Agent，支持读写/编辑/bash 等文件工具 | 287 |
| `pi_tui` | 终端 UI 库 | 135 |
| `pi_wiki_agent` | Wiki 同步引擎、工作流、质量检查 ★ | — |
| **合计** | | **578** |

---

## 自定义 Agent

在 `.wiki/workflows/agents/` 下创建 `.md` 文件：

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
| `thinking` | 思考级别: `off` / `low` / `medium` / `high` / `xhigh` |

正文为 system prompt，会替换默认的 Wiki 管理 prompt。

---

## 常见问题

| 问题 | 解答 |
|------|------|
| 同步什么内容？ | `.wiki/*.md` 中带 `WIKI_SECTION` 标记且有反向索引的页面 |
| 支持哪些 VCS？ | Git（完整支持）、SVN（基础支持） |
| 如何添加自定义模型？ | 通过桌面端 UI 或编辑 `~/.pi/agent/models.json` |
| 没有 API Key 能用吗？ | 大部分测试用 Mock 运行。真实同步需要至少一个 API Key |
| Diff 如何提供？ | 工作流接受原始 diff 字符串，CLI 从 Git 自动提取 |
| 能自定义工作流吗？ | 可以。编写 YAML 文件放入 `.wiki/workflows/` 即可 |
| 断点续跑？ | 每个阶段 checkpoints 到 `.wiki/checkpoints/<hash>/`，失败后从最后成功阶段恢复 |

---

## 相关项目

- [pi-mono](https://github.com/badlogic/pi-mono) — TypeScript 上游参考实现
- [pi-workflow](https://github.com/agwab/pi-workflow) — DAG 工作流系统（设计参考）

## 许可证

MIT — 详见 [LICENSE](LICENSE)
