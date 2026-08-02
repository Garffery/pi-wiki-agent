<p align="center">
  <h1 align="center">pi-wiki-agent</h1>
  <p align="center"><strong>VCS-driven wiki documentation agent — keep your wiki in sync with your code, automatically.</strong></p>
</p>

<p align="center">
  <a href="#features">Features</a> •
  <a href="#quick-start">Quick Start</a> •
  <a href="#how-it-works">How It Works</a> •
  <a href="#architecture">Architecture</a> •
  <a href="#desktop-app">Desktop App</a> •
  <a href="#evaluation">Evaluation</a> •
  <a href="#development">Development</a>
</p>

---

## Features

- **VCS-driven sync** — every commit triggers a 3-stage LLM workflow (Analyze → Plan → Write) that updates wiki pages to reflect code changes. No manual documentation effort.
- **DAG-parallel execution** — Wiki pages are updated in topological order with maximum parallelism. LLM declares task dependencies; the engine resolves and executes them concurrently.
- **Quality auto-fix** — Built-in quality checker finds broken links, stale content, empty sections, and structural defects. One-click or cron-triggered fix workflow repairs them automatically.
- **Reverse-index traceability** — Every wiki section carries a `**source**` link back to the file that generated it. Changes propagate bidirectionally: code → wiki and wiki → code.
- **YAML → AST workflow compiler** — Workflows are defined in YAML and compiled to Python AST nodes (not string templates). Type-safe, statically analyzable, and extensible.
- **Checkpoint & resume** — Every phase persists to disk. Failed runs resume from the last successful checkpoint, not from scratch.
- **Desktop app + SSE streaming** — Vue 3 frontend with real-time agent progress, tool call visualization, model management, and cron scheduling.
- **Pluggable models** — Built-in catalog of 739 models across 22 providers. Add custom providers via the UI or `~/.pi/agent/models.json`.
- **Evaluation framework** — Structured test harness with diff-based test cases, pass@k metrics, LLM-as-Judge scoring, and Markdown reporting.

---

## Quick Start

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) package manager
- An LLM API key (DeepSeek, Anthropic, Gemini, or OpenAI)

### Installation

```bash
git clone https://github.com/openxjarvis/pi-wiki-agent.git
cd pi-wiki-agent

# Install all dependencies
uv sync
```

### Configuration

```bash
# .env — at least one API key required
ANTHROPIC_API_KEY=sk-ant-xxx    # or GEMINI_API_KEY, OPENAI_API_KEY, DEEPSEEK_API_KEY...

# Optional: add custom models via the desktop UI or by editing:
# ~/.pi/agent/models.json
# ~/.pi/agent/auth.json
```

### Launch

```bash
# Start the desktop server
uv run pi-wiki-desktop
# → http://127.0.0.1:8899

# Or run the sync workflow programmatically
python -c "
import asyncio
from pi_wiki_agent.core.workflow_sync import execute_workflow_sync

result = asyncio.run(execute_workflow_sync(
    project_path='D:/project/wiki-demo-taskman',
    changed_files=['src/taskman/cli.py'],
    commit_message='feat: add export command',
    diff=open('diff.txt').read(),
    revision='my-commit-hash',
    script=open('sync.yaml').read(),
    model='deepseek:deepseek-v4-flash',
))
print(result.result)
"
```

---

## How It Works

### Sync Workflow

```
┌──────────┐     ┌──────────┐     ┌──────────┐
│ Analyze  │ ──▶ │  Plan    │ ──▶ │  Write   │
│          │     │          │     │  (DAG)   │
│ diff →   │     │ file_tasks│    │ agent A  │
│ impact   │     │ + no_change│   │ agent B  │
│ analysis │     │ + schema  │    │ agent C  │
└──────────┘     └──────────┘     └──────────┘
```

1. **Analyze** — `diff-analyzer` agent reads each changed file's diff and explains the impact on wiki documentation.
2. **Plan** — `wiki-planner` agent consumes the analysis and outputs a structured JSON (`file_tasks` + `no_change_files`) via a `structured_output` tool. For each task, it specifies the target wiki page, section, action (create/update/delete), and precise instructions.
3. **Write** — `wiki-writer` agents execute tasks in parallel according to a DAG. The planner declares task dependencies; the engine topologically sorts and executes with maximum concurrency. Each agent reads the target wiki page, applies only the instructed changes, and preserves WIKI_SECTION markers and `**source**` traceability links.

### Fix Workflow

```
Quality Check → {issues} → Analyze → Plan → Fix (DAG)
```

`WikiQualityChecker` scans all `.wiki/*.md` pages for 9 types of defects across two priority tiers. The report feeds into a fix workflow that runs the same 3-stage pattern with quality-specific agents (`quality-analyzer`, `fix-planner`, `page-fixer`).

### Workflow Definition (YAML)

Workflows are defined in YAML and compiled to Python via AST:

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

See [workflow documentation](packages/wiki-agent/src/pi_wiki_agent/core/workflow/ast_compiler/DETAIL.html) for the full AST compiler architecture.

---

## Architecture

```
pi-wiki-agent/
├── desktop/                         # FastAPI backend + Vue 3 frontend
│   ├── src/pi_wiki_desktop/
│   │   ├── app.py                   # Server entry point (uvicorn)
│   │   ├── api/v1/endpoints/        # REST + SSE endpoints
│   │   └── wiki_model_registry.py   # Persistent model CRUD
│   └── pyproject.toml
├── frontend/                        # Vue 3 SPA
│   ├── index.html
│   ├── app.js
│   └── style.css
├── packages/
│   ├── wiki-agent/                  # Core engine
│   │   └── src/pi_wiki_agent/
│   │       ├── core/
│   │       │   ├── workflow/        # DAG engine + AST compiler
│   │       │   ├── workflow_sync.py # Sync orchestrator
│   │       │   ├── wiki_quality.py  # Quality checker
│   │       │   └── agent_session.py # Agent session management
│   │       ├── cases/               # Test case library
│   │       ├── eval/                # Evaluation framework
│   │       └── cron/                # Scheduled jobs
│   ├── ai/                          # LLM provider layer (739 models)
│   ├── agent/                       # Agent loop + tool execution
│   ├── coding-agent/                # File tools (read/write/edit/bash)
│   └── tui/                         # Terminal UI library
├── docs/                            # Design docs + evaluation plans
│   └── test/                        # Test framework documentation
├── .env                             # API keys (gitignored)
└── pyproject.toml                   # uv workspace root
```

---

## Desktop App

Launch the server at `http://127.0.0.1:8899`:

```bash
uv run pi-wiki-desktop
```

**Project Management**
- Add/remove projects with file browser
- Each project stores `.wiki/` (pages, reverse-index, checkpoint state)

**Commit Sync**
- Three modes: **Single Agent** (sequential), **Chain** (pipeline), **Workflow** (DAG-parallel)
- Select pending commits, preview file changes, trigger sync
- **Real-time SSE streaming** of agent progress per phase

**Quality Dashboard**
- Run quality checks across all wiki pages
- **Auto-fix workflow** with live progress per check type
- Issues categorized by severity (error / warning / info)

**Settings**
- **Model Management** — add custom providers + models via UI
- **Filter Rules** — path/author/message patterns to skip commits
- **Cron Jobs** — schedule quality checks and auto-fix on a timer

---

## Evaluation

The project includes a structured test framework for evaluating the sync agent:

```bash
# Dry-run (no LLM, validates pipeline logic)
python -m pi_wiki_agent.eval \
    --cases packages/wiki-agent/src/pi_wiki_agent/cases \
    --dry-run \
    --report docs/test/reports/report.md

# Real LLM run
python -m pi_wiki_agent.eval \
    --cases packages/wiki-agent/src/pi_wiki_agent/cases \
    --report docs/test/reports/report.md
```

**Test cases** are YAML-free — each case is a directory of `diff.txt` + `args.json` + `expected.json`:

```
cases/
├── case_01_new_feature/       ← Agent adds new wiki content
├── case_02_modify_behavior/   ← Agent updates existing descriptions
├── case_03_remove_refactor/   ← Agent removes stale content
├── case_04_doc_only/          ← Agent correctly does nothing
├── case_05_multi_file/        ← Agent handles multi-file changes
├── case_06_new_feature_2/     ← Cross-validation
├── case_07_modify_behavior_2/ ← Cross-validation
└── case_08_large_diff/        ← Stress test (50-line diff)
```

**Metrics** follow the SWE-bench methodology: `pass@k` (probability of at least 1 success in k attempts), `pass^k` (all k succeed), quality deltas, latency, and token cost. See [Evaluation Plan](docs/test/EVALUATION_PLAN.md) for full details.

---

## Development

### Setup

```bash
git clone https://github.com/openxjarvis/pi-wiki-agent.git
cd pi-wiki-agent
uv sync
```

### Run Tests

```bash
uv run pytest                              # All tests (578 passing)
uv run pytest packages/wiki-agent/tests/   # Wiki-agent specific
uv run pytest --live -v                    # Live API tests (needs API key)
```

### Code Quality

```bash
uv run ruff check .   # Lint
uv run ruff format .  # Format
```

### Underlying Packages

| Package | Description | Tests |
|---------|-------------|-------|
| `pi_ai` | Unified LLM streaming (Google, Anthropic, OpenAI, …) | 156 |
| `pi_agent` | Agent loop, tool execution, state management | — |
| `pi_coding_agent` | Coding agent with file tools | 287 |
| `pi_tui` | Terminal UI library | 135 |
| `pi_wiki_agent` | Wiki sync engine, workflow, quality checker | — |
| **Total** | | **578** |

---

## FAQ

| Question | Answer |
|----------|--------|
| What does it sync? | Any wiki page in `.wiki/*.md` with `WIKI_SECTION` markers and a reverse index |
| What VCS are supported? | Git (SVN in progress) |
| Can I add custom LLM models? | Yes — via the desktop UI or `~/.pi/agent/models.json` |
| Does it work without an API key? | Most tests run with mocks. Real sync requires at least one API key |
| How are diffs provided? | Workflows accept raw diff strings; the CLI reads from git. See [test cases](packages/wiki-agent/src/pi_wiki_agent/cases/) for synthetic examples |
| Can I define custom workflows? | Yes — write a YAML file with phases/steps/modes, place it in `.wiki/workflows/` |
| Checkpoint resume? | Every phase checkpoints to `.wiki/checkpoints/<hash>/`. Failed runs resume from the last successful phase |

---

## License

MIT — See [LICENSE](LICENSE) for details.
