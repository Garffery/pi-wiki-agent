# pi-wiki-agent

> Python port of the [pi-mono](../pi-mono) TypeScript monorepo — three packages with aligned code, logic, algorithms, and folder structure.
>
> **[中文 README →](README_CN.md)**

| TypeScript | Python | Description |
|---|---|---|
| `@mariozechner/pi-ai` | `pi_ai` | Unified LLM streaming layer (Google, Anthropic, OpenAI, Bedrock, …) |
| `@mariozechner/pi-agent-core` | `pi_agent` | Agent loop, tool execution, state management |
| `@mariozechner/pi-coding-agent` | `pi_coding_agent` | Coding agent CLI with file tools: read, write, edit, bash, grep, find, ls |

---

## Installation

### Prerequisites

- **Python 3.11+** — Check with `python3 --version`
- **[uv](https://docs.astral.sh/uv/)** — Fast Python package manager

Install `uv` if you don't have it:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Clone and Install

```bash
git clone https://github.com/openxjarvis/pi-wiki-agent.git
cd pi-wiki-agent

# Install all packages and their dependencies in one step
uv sync
```

---

## Quick Start

### 1. Configure API Keys

Create `.env` in the project root:

```bash
# Google Gemini (recommended default)
GEMINI_API_KEY=your_key_here

# Optional — add whichever providers you need
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
GOOGLE_API_KEY=        # alternative to GEMINI_API_KEY
AWS_ACCESS_KEY_ID=     # for AWS Bedrock
AWS_SECRET_ACCESS_KEY=
```

> **Important:** `.env` is loaded automatically at runtime. **Never commit it to git.**

### 2. Run the Agent

```bash
uv run --package pi-coding-agent pi --print "your prompt here"
```

### 3. Try a Simple Task

```bash
uv run --package pi-coding-agent pi --print "Create a Python function to calculate fibonacci numbers"
```

The agent will write the code and output it to stdout.

---

## Common Use Cases

### Single Prompt (Non-Interactive)

For scripting or quick tasks:

```bash
uv run --package pi-coding-agent pi --print "Write a quicksort in Python"
```

The agent's response prints to stdout and exits.

### Switch Models

```bash
# Use a specific model
uv run --package pi-coding-agent pi --model gemini-2.5-pro-preview

# Use a provider + model name
uv run --package pi-coding-agent pi --provider google --model gemini-2.0-flash

# List all available models
uv run --package pi-coding-agent pi --list-models
```

### Resume Previous Sessions

```bash
# Continue the most recent session
uv run --package pi-coding-agent pi --continue

# Pick from a list of previous sessions
uv run --package pi-coding-agent pi --resume
```

### Full CLI Help

```bash
uv run --package pi-coding-agent pi --help
```

---

## Running Tests

### All tests

```bash
uv run pytest
```

### Per-package

```bash
uv run pytest packages/ai/tests/           # AI providers
uv run pytest packages/agent/tests/        # Agent core
uv run pytest packages/coding-agent/tests/ # CLI + coding agent
```

### Live API tests (requires `GEMINI_API_KEY`)

```bash
uv run pytest packages/ai/tests/ --live -v

# Or via environment variable
LIVE_TESTS=1 uv run pytest packages/ai/tests/ -v
```

> All tests run against mocks by default — no API key required, no quota consumed.

---

## Test Status

| Package | Tests | Status |
|---------|-------|--------|
| `pi_ai` + `pi_agent` | 156 | ✅ passed (7 skipped = live-only) |
| `pi_coding_agent` | 287 | ✅ passed |
| **Total** | **443** | **✅ all passing** |

---

## Extension System

pi supports a dynamic extension system. Extensions can register custom tools, slash commands, and event handlers.

### Built-in Extension: Todo Manager

The todo extension (`extensions/todos.py`) provides file-based task management:

- **Storage**: Each todo is a `.md` file under `.pi/todos/` (or `$PI_TODO_PATH`) with JSON frontmatter + markdown body
- **Fields**: `id`, `title`, `tags`, `status` (open/closed/done), `created_at`, `assigned_to_session`
- **Settings**: `.pi/todos/settings.json` — `gc` (auto-cleanup) and `gcDays` (age threshold)

#### Todo Tool Actions

| Action | Description |
|--------|-------------|
| `list` | Show open + assigned todos |
| `list-all` | Show all todos including closed |
| `get` | View a single todo by ID |
| `create` | Create a new todo (auto-generates ID) |
| `update` | Modify title/status/tags/body |
| `delete` | Remove a todo |
| `claim` | Assign a todo to the current session |
| `release` | Unassign a todo |

#### Usage

```bash
# List todos (via the coding agent)
uv run --package pi-coding-agent pi --print "Show me my open todos"

# Manual file operations
ls .pi/todos/
cat .pi/todos/<id>.md
```

### Writing Your Own Extension

Extensions live in the `extensions/` directory. To create one:

```python
# extensions/my_extension.py
def extension_factory(pi):
    # Register a tool
    pi.register_tool(
        name="my_tool",
        description="My custom tool",
        parameters={...},
        execute=my_async_function,
    )

    # Register a slash command
    pi.register_command(
        name="mycommand",
        description="Description for /mycommand",
        handler=my_handler_function,
    )

    # Listen to events
    pi.on("session_start", on_session_start)
```

---

## Windows Support

pi is fully compatible with Windows. See [WINDOWS_FIXES.md](WINDOWS_FIXES.md) for details on UTF-8 encoding support and troubleshooting.

Quick tips for Windows:

```powershell
# Fix encoding issues with Chinese characters
$env:PYTHONIOENCODING = "utf-8"
```

---

## Development Guide

### Prerequisites

- **Python 3.11+**
- **[uv](https://docs.astral.sh/uv/)** — Fast Python package manager
- **git**

### Setup

```bash
git clone https://github.com/openxjarvis/pi-wiki-agent.git
cd pi-wiki-agent
uv sync
```

### Code Style

This project uses [Ruff](https://docs.astral.sh/ruff/) for linting and formatting:

```bash
# Lint
uv run ruff check .

# Format
uv run ruff format .
```

Configuration is in `pyproject.toml`:
- Line length: 120
- Target: Python 3.11
- Rules: E, F, I, UP

### Adding Dependencies

```bash
uv add <package>                    # Add to a specific package
uv add --dev <package>              # Add dev dependency
uv sync                             # Update lockfile
```

### Creating a New Package

```bash
mkdir -p packages/my-package/src/my_package
mkdir packages/my-package/tests
```

Add to `[tool.uv.workspace]` members in `pyproject.toml`:

```toml
[tool.uv.workspace]
members = ["packages/ai", "packages/agent", "packages/coding-agent", "packages/my-package"]
```

### Testing

```bash
uv run pytest                    # All tests
uv run pytest -x                 # Stop on first failure
uv run pytest -k "test_name"     # Run specific test
uv run pytest --cov              # With coverage
uv run pytest --live -v          # Live API tests (requires GEMINI_API_KEY)
```

### Type Checking (future)

Type hints are used throughout. We recommend `pyright` or `mypy` for static analysis:

```bash
uv run pyright packages/
```

---

## Project Structure

```
pi-wiki-agent/
├── .env                          ← API keys (never commit)
├── pyproject.toml                ← uv workspace root
├── conftest.py                   ← global pytest config (.env loader)
└── packages/
    ├── ai/                       ← LLM provider layer
    │   └── src/pi_ai/
    │       ├── providers/        ← google.py, openai.py, anthropic.py, …
    │       ├── stream.py         ← unified stream_simple() / complete_simple()
    │       └── utils/            ← overflow detection, JSON parse, …
    ├── agent/                    ← core agent loop
    │   └── src/pi_agent/
    │       ├── agent.py          ← main run loop
    │       ├── tools/            ← tool registry & execution
    │       └── session.py        ← session state
    ├── coding-agent/             ← CLI entry point & extensions
    │   └── src/pi_coding_agent/
    │       ├── cli.py            ← `pi` command
    │       └── core/             ← AgentSession, system prompt, tools
```

---

---

## FAQ

| Problem | Solution |
|---------|----------|
| `uv: command not found` | Run the install script: `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| `GEMINI_API_KEY not set` | Add your key to `.env` |
| Tests are skipped | Add `--live` to run real API tests |
| `400 thought_signature` error | Upgrade to the latest version — this is fixed in the google provider |

---

## FAQ (Windows)

| Problem | Solution |
|---------|----------|
| Chinese characters garbled | Set `$env:PYTHONIOENCODING = "utf-8"` |
| `ModuleNotFoundError` with `uv run` | Run from project root with `uv sync` first |

---

## Related Projects

- **pi-mono TypeScript** — [github.com/badlogic/pi-mono](https://github.com/badlogic/pi-mono) — Upstream TypeScript monorepo
- **openclaw-python** — [github.com/openxjarvis/openclaw-python](https://github.com/openxjarvis/openclaw-python) — Complete AI gateway built on these packages (Telegram, Lark, Web UI, scheduling, multi-agent)

---

## License

MIT — See [LICENSE](LICENSE) for details.
