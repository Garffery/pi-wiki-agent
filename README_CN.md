# pi-mono-python

[pi-mono](../pi-mono) TypeScript monorepo 的 Python 移植版本 — 四个包，代码、逻辑、算法和文件夹结构完全对齐。

| TypeScript | Python | 说明 |
|---|---|---|
| `@mariozechner/pi-ai` | `pi_ai` | 统一的 LLM 流式层（Google、Anthropic、OpenAI、Bedrock 等） |
| `@mariozechner/pi-agent-core` | `pi_agent` | 代理循环、工具执行、状态管理 |
| `@mariozechner/pi-coding-agent` | `pi_coding_agent` | 编码代理 CLI，包含文件工具：read、write、edit、bash、grep、find、ls |
| `@mariozechner/pi-tui` | `pi_tui` | 终端 UI 库，具备差异化渲染引擎 |

---

## 安装

### 前置要求

- **Python 3.11+** — 检查版本：`python3 --version`
- **[uv](https://docs.astral.sh/uv/)** — 快速的 Python 包管理器

如果没有安装 `uv`：

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 克隆和安装

```bash
git clone https://github.com/openxjarvis/pi-mono-python.git
cd pi-mono-python

# 一步安装所有四个包及其依赖
uv sync
```

---

## 快速开始

### 1. 配置 API 密钥

在项目根目录创建 `.env` 文件：

```bash
# Google Gemini（推荐默认）
GEMINI_API_KEY=your_key_here

# 可选 — 根据需要添加其他提供商
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
GOOGLE_API_KEY=        # GEMINI_API_KEY 的替代方案
AWS_ACCESS_KEY_ID=     # 用于 AWS Bedrock
AWS_SECRET_ACCESS_KEY=
```

> **重要：** `.env` 会在运行时自动加载。**永远不要提交到 git。**

### 2. 启动交互式 TUI

```bash
uv run --package pi-coding-agent pi
```

这会打开功能完整的终端 UI，你可以在其中与编码代理聊天。

**键盘快捷键：**

| 按键 | 操作 |
|-----|--------|
| `Enter` | 发送消息 |
| `Shift+Enter` | 在输入中换行 |
| `/` | 斜杠命令补全 |
| `@` | 文件路径补全 |
| `Ctrl+P` | 切换到下一个模型 |
| `Ctrl+C` / `Esc` | 退出 |

### 3. 尝试一个简单的任务

在终端中输入：

```
创建一个 Python 函数来计算斐波那契数列
```

代理会编写代码并将其保存到你的当前目录。

---

## 常见用法

### 单个提示（非交互式）

用于脚本或快速任务：

```bash
uv run --package pi-coding-agent pi --print "用 Python 写一个快速排序"
```

代理的响应会打印到标准输出并退出。

### 切换模型

```bash
# 使用特定模型
uv run --package pi-coding-agent pi --model gemini-2.5-pro-preview

# 使用提供商 + 模型名称
uv run --package pi-coding-agent pi --provider google --model gemini-2.0-flash

# 列出所有可用模型
uv run --package pi-coding-agent pi --list-models
```

### 恢复之前的会话

```bash
# 继续最近的会话
uv run --package pi-coding-agent pi --continue

# 从之前的会话列表中选择
uv run --package pi-coding-agent pi --resume
```

### TUI 中的斜杠命令

在交互式 TUI 中输入 `/` 查看可用命令：

| 命令 | 说明 |
|---------|-------------|
| `/model <name>` | 切换到不同的模型 |
| `/thinking <level>` | 设置思考详细程度：`minimal` · `low` · `medium` · `high` · `xhigh` |
| `/compact` | 压缩对话上下文以节省 token |
| `/session` | 显示会话统计（已使用的 token、成本估算） |
| `/tools` | 列出代理可用的所有工具 |

### 完整的 CLI 帮助

```bash
uv run --package pi-coding-agent pi --help
```

---

## 运行测试

### 所有测试

```bash
uv run pytest
```

### 按包测试

```bash
uv run pytest packages/tui/tests/          # TUI 组件
uv run pytest packages/ai/tests/           # AI 提供商
uv run pytest packages/agent/tests/        # 代理核心
uv run pytest packages/coding-agent/tests/ # CLI + 编码代理
```

### 实时 API 测试（需要 `GEMINI_API_KEY`）

```bash
uv run pytest packages/ai/tests/ --live -v

# 或通过环境变量
LIVE_TESTS=1 uv run pytest packages/ai/tests/ -v
```

> 默认情况下，所有测试都针对 mock 运行 — 不需要 API 密钥，不消耗配额。

---

## 测试状态

| 包 | 测试数 | 状态 |
|---------|-------|--------|
| `pi_tui` | 135 | ✅ 通过 |
| `pi_ai` + `pi_agent` | 156 | ✅ 通过（7 个跳过 = 仅实时测试） |
| `pi_coding_agent` | 287 | ✅ 通过 |
| **总计** | **578** | **✅ 全部通过** |

---

## 项目结构

```
pi-mono-python/
├── .env                          ← API 密钥（永远不要提交）
├── pyproject.toml                ← uv 工作区根
├── conftest.py                   ← 全局 pytest 配置（.env 加载器）
└── packages/
    ├── ai/                       ← LLM 提供商层
    │   └── src/pi_ai/
    │       ├── providers/        ← google.py、openai.py、anthropic.py 等
    │       ├── stream.py         ← 统一的 stream_simple() / complete_simple()
    │       └── utils/            ← 溢出检测、JSON 解析等
    ├── agent/                    ← 核心代理循环
    │   └── src/pi_agent/
    │       ├── agent.py          ← 主运行循环
    │       ├── tools/            ← 工具注册和执行
    │       └── session.py        ← 会话状态
    ├── coding-agent/             ← CLI 入口点和扩展
    │   └── src/pi_coding_agent/
    │       ├── cli.py            ← `pi` 命令
    │       ├── core/             ← AgentSession、系统提示、工具
    │       └── modes/interactive/← TUI 交互模式
    └── tui/                      ← 终端 UI 库
        └── src/pi_tui/
            ├── components/       ← Editor、SelectList、Markdown 等
            ├── tui.py            ← 差异化渲染引擎
            └── keys.py           ← Kitty 键盘协议解析器
```

---

## TypeScript → Python 映射

| TypeScript | Python |
|---|---|
| `interface X {}` | `class X(BaseModel):` 或 `@dataclass` |
| `type X = A \| B` | `X = Union[A, B]` |
| `async function f()` | `async def f()` |
| `AsyncIterable<T>` | `AsyncGenerator[T, None]` |
| `AbortSignal` | `asyncio.Event`（取消令牌） |
| `EventEmitter` | `dict[str, list[Callable]]` |
| TypeBox schema | `pydantic.BaseModel` |
| `vitest` | `pytest` + `pytest-asyncio` |

---

## 常见问题

| 问题 | 解决方案 |
|---------|----------|
| `uv: command not found` | 运行安装脚本：`curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| `GEMINI_API_KEY not set` | 将你的密钥添加到 `.env` |
| `ModuleNotFoundError: pi_tui` | 使用 `uv run --package pi-coding-agent pi` 而不是直接使用 `python` |
| TUI 显示乱码字符 | 确保你的终端支持 UTF-8（iTerm2、Warp 或任何现代终端） |
| 测试被跳过 | 添加 `--live` 来运行真实的 API 测试 |
| `400 thought_signature` 错误 | 升级到最新版本 — 此问题已在 google 提供商中修复 |

---

## 扩展系统

pi 支持动态扩展系统。扩展可以注册自定义工具、斜杠命令和事件处理器。

### 内置扩展：任务管理器（Todo）

任务管理扩展（`extensions/todos.py`）提供基于文件的任务管理：

- **存储方式**：每个任务是一个 `.md` 文件，位于 `.pi/todos/`（或 `$PI_TODO_PATH`），包含 JSON 前置元数据 + Markdown 正文
- **字段**：`id`、`title`、`tags`、`status`（open/closed/done）、`created_at`、`assigned_to_session`
- **设置**：`.pi/todos/settings.json` — `gc`（自动清理开关）和 `gcDays`（过期天数）

#### 任务工具动作

| 动作 | 说明 |
|--------|-------------|
| `list` | 显示打开 + 已分配的任务 |
| `list-all` | 显示所有任务（包括已关闭的） |
| `get` | 按 ID 查看单个任务 |
| `create` | 创建新任务（自动生成 ID） |
| `update` | 修改标题/状态/标签/正文 |
| `append` | 追加正文内容 |
| `delete` | 删除任务 |
| `claim` | 将任务分配给当前会话 |
| `release` | 取消任务分配 |

#### 使用方式

```bash
# 通过编码代理列出任务
uv run --package pi-coding-agent pi --print "显示我的待办任务"

# 手动文件操作
ls .pi/todos/
cat .pi/todos/<id>.md
```

### 编写自己的扩展

扩展文件放在 `extensions/` 目录下。创建一个扩展的示例：

```python
# extensions/my_extension.py
def extension_factory(pi):
    # 注册工具
    pi.register_tool(
        name="my_tool",
        description="我的自定义工具",
        parameters={...},
        execute=my_async_function,
    )

    # 注册斜杠命令
    pi.register_command(
        name="mycommand",
        description="/mycommand 的说明",
        handler=my_handler_function,
    )

    # 监听事件
    pi.on("session_start", on_session_start)
```

---

## Windows 支持

pi 完全兼容 Windows。详见 [WINDOWS_FIXES.md](WINDOWS_FIXES.md) 了解以下内容：

- 原生 Windows 控制台输入（使用 `msvcrt` 和 Win32 API）
- UTF-8 编码支持
- 故障排除环境变量（`PI_FORCE_READLINE`、`PYTHONIOENCODING`）

Windows 快速提示：

```powershell
# 如果 TUI 有问题，回退到 readline 模式
$env:PI_FORCE_READLINE = "1"
uv run --package pi-coding-agent pi

# 解决中文字符编码问题
$env:PYTHONIOENCODING = "utf-8"
```

---

## 开发指南

### 前置要求

- **Python 3.11+**
- **[uv](https://docs.astral.sh/uv/)** — 快速的 Python 包管理器
- **git**

### 设置开发环境

```bash
git clone https://github.com/openxjarvis/pi-mono-python.git
cd pi-mono-python
uv sync
```

### 代码风格

本项目使用 [Ruff](https://docs.astral.sh/ruff/) 进行代码检查和格式化：

```bash
# 检查
uv run ruff check .

# 格式化
uv run ruff format .
```

配置在 `pyproject.toml` 中：
- 行长度：120
- 目标：Python 3.11
- 规则：E, F, I, UP

### 添加依赖

```bash
uv add <package>                    # 添加到特定包
uv add --dev <package>              # 添加开发依赖
uv sync                             # 更新锁文件
```

### 创建新包

```bash
mkdir -p packages/my-package/src/my_package
mkdir packages/my-package/tests
```

在 `pyproject.toml` 的 `[tool.uv.workspace] members` 中添加：

```toml
[tool.uv.workspace]
members = ["packages/ai", "packages/agent", "packages/coding-agent", "packages/tui", "packages/my-package"]
```

### 测试

```bash
uv run pytest                    # 所有测试
uv run pytest -x                 # 遇到第一个失败即停止
uv run pytest -k "test_name"     # 运行特定测试
uv run pytest --cov              # 带覆盖率
uv run pytest --live -v          # 实时 API 测试（需要 GEMINI_API_KEY）
```

### 类型检查

项目全程使用类型提示。推荐使用 `pyright` 或 `mypy` 进行静态分析：

```bash
uv run pyright packages/
```

---

## 使用场景

### 作为独立的编码助手

直接使用 `pi` CLI 进行代码生成、文件编辑、bash 命令执行：

```bash
# 交互式对话
uv run --package pi-coding-agent pi

# 快速任务
uv run --package pi-coding-agent pi --print "分析当前目录的代码复杂度"
```

### 作为 openclaw-python 的依赖

[openclaw-python](https://github.com/openxjarvis/openclaw-python) 使用这些包构建完整的 AI 网关系统，支持：

- Telegram、飞书等多渠道接入
- Web UI 管理界面
- 定时任务调度
- 子代理系统
- 权限管理

如果你需要完整的 AI 助手网关，请查看 openclaw-python 项目。

---

## Windows 常见问题

| 问题 | 解决方案 |
|---------|----------|
| TUI 无法响应键盘输入 | 设置 `$env:PI_FORCE_READLINE = "1"` 使用 readline 模式 |
| 中文显示乱码 | 设置 `$env:PYTHONIOENCODING = "utf-8"` |
| `uv run` 报 `ModuleNotFoundError` | 确保在项目根目录运行，先执行 `uv sync` |

---

## 相关项目

- **pi-mono TypeScript** — [github.com/badlogic/pi-mono](https://github.com/badlogic/pi-mono) — 上游参考实现
- **openclaw-python** — [github.com/openxjarvis/openclaw-python](https://github.com/openxjarvis/openclaw-python) — 使用这些包构建的完整 AI 网关

---

## 许可证

MIT — 详见 [LICENSE](LICENSE)。
