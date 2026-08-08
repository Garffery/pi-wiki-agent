"""
LLM Judge — 用带工具的 Agent 评测 wiki 内容质量。

评测流程:
  1. 准备临时目录，写入 diff/ 和 wiki/ 两个子目录
  2. 启动 AgentSession，只带 read/grep/ls/structured_output 工具
  3. Judge 自己决定读哪些文件
  4. 通过 structured_output 捕获结构化 JSON
"""
from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from pathlib import Path
from typing import Any

_log = logging.getLogger("pi_wiki_agent.judge")

def _debug(msg: str, *args) -> None:
    """开发调试打印，直接到 stdout。"""
    print(f"  [JUDGE] {msg % args if args else msg}", flush=True)


# ── diff 拆分 ──────────────────────────────────────────────────────────────────

def _split_diff(diff_text: str) -> dict[str, str]:
    """将 unified diff 按文件拆分为 {rel_path: diff_chunk}。"""
    result: dict[str, str] = {}
    current_file: str | None = None
    current_lines: list[str] = []

    for line in diff_text.split("\n"):
        if line.startswith("diff --git "):
            if current_file and current_lines:
                result[current_file] = "\n".join(current_lines)
            parts = line.split(" ")
            b_path = parts[-1] if parts else ""
            current_file = b_path[2:] if b_path.startswith("b/") else b_path
            current_lines = [line]
        elif current_file:
            current_lines.append(line)

    if current_file and current_lines:
        result[current_file] = "\n".join(current_lines)

    return result


def _split_svn_diff(diff_text: str) -> dict[str, str]:
    """将 SVN unified diff 按文件拆分为 {rel_path: diff_chunk}。"""
    result: dict[str, str] = {}
    current_file: str | None = None
    current_lines: list[str] = []

    for line in diff_text.split("\n"):
        if line.startswith("Index: "):
            if current_file and current_lines:
                result[current_file] = "\n".join(current_lines)
            current_file = line[len("Index: "):].strip()
            current_lines = [line]
        elif current_file:
            current_lines.append(line)

    if current_file and current_lines:
        result[current_file] = "\n".join(current_lines)

    return result


# ── 工作目录准备 ────────────────────────────────────────────────────────────────

def _pick_splitter(diff_text: str) -> Any:
    """根据 diff 首行判断 git 还是 SVN 格式，返回对应的拆分函数。"""
    for line in diff_text.split("\n")[:5]:
        if line.startswith("diff --git "):
            return _split_diff
        if line.startswith("Index: "):
            return _split_svn_diff
    return _split_diff  # fallback


def _write_per_file_diffs(diff_text: str, out_dir: str) -> list[str]:
    """将 diff 按文件拆分写入 out_dir/{name}.diff，返回文件名列表。"""
    os.makedirs(out_dir, exist_ok=True)
    splitter = _pick_splitter(diff_text)
    per_file = splitter(diff_text)

    filenames: list[str] = []
    for fname, chunk in per_file.items():
        safe = fname.replace("/", "_").replace("\\", "_")
        filepath = os.path.join(out_dir, f"{safe}.diff")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(chunk)
        filenames.append(fname)

    return filenames


def _write_summary(out_dir: str, files: list[str], msg: str = "") -> None:
    """写 _summary.txt——变更文件列表 + commit message。"""
    lines = [f"变更文件 ({len(files)}):"]
    for f in files:
        lines.append(f"  {f}")
    if msg:
        lines.append(f"\ncommit: {msg}")
    with open(os.path.join(out_dir, "_summary.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def prepare_judge_dir(
    diff_text: str,
    wiki_diff_text: str,
    commit_message: str = "",
    tmp_dir: str | None = None,
) -> str:
    """
    准备 Judge 工作目录。

    目录结构:
      {tmp_dir}/
      ├── diff/           ← 源码变更，每个文件一个 .diff + _summary.txt
      └── wiki/           ← wiki 变更，每个页面一个 .diff + _summary.txt

    Returns: tmp_dir 路径
    """
    if tmp_dir is None:
        tmp_dir = tempfile.mkdtemp(prefix="wiki_judge_")

    _debug("step1: 准备临时目录: %s", tmp_dir)

    # diff/ 目录
    diff_dir = os.path.join(tmp_dir, "diff")
    diff_files = _write_per_file_diffs(diff_text, diff_dir)
    _write_summary(diff_dir, diff_files, commit_message)
    _debug("step1: diff/ 写入 %d 个文件: %s", len(diff_files), diff_files)

    # wiki/ 目录
    wiki_dir = os.path.join(tmp_dir, "wiki")
    wiki_files = _write_per_file_diffs(wiki_diff_text, wiki_dir)
    _write_summary(wiki_dir, wiki_files, "Agent 改动的 wiki 页面")
    _debug("step1: wiki/ 写入 %d 个文件: %s", len(wiki_files), wiki_files)

    return tmp_dir


# ── System prompt ──────────────────────────────────────────────────────────────

_JUDGE_SYSTEM_PROMPT = """\
你是一个 Wiki 文档质量评审员。你的任务是评估一个 AI Agent 自动生成的 Wiki 内容质量。

## 工作目录

{tmp_dir}/diff/     — 本次 commit 的源代码变更
{tmp_dir}/wiki/     — Agent 对 Wiki 的修改

两个目录格式一致：都是 unified diff，按文件拆分为 .diff 文件。
+ 行是新增/改动，- 行是删除。_summary.txt 包含文件列表概览。

**评测对象**: wiki/ 中 .diff 文件的 + 行内容（Agent 的增量），不是 wiki 的全部历史。

## 工作流程

1. 先读 diff/_summary.txt 和 wiki/_summary.txt，了解全局
2. 逐个读 diff/ 下 .diff 文件，提取所有需要记录的变更
3. 逐个读 wiki/ 下 .diff 文件，只审查 + 行内容
4. 输出评测结果 JSON

## 评测标准

### 1. 正确性（Correctness）
wiki 中 Agent 写的每条事实陈述必须与 diff 中的源码事实一致。

- CORRECT: 陈述与 diff 一致
- INCORRECT: 陈述与 diff 矛盾或编造了不存在的东西（幻觉）
- UNVERIFIABLE: diff 信息不足以验证（Agent 猜测了 diff 之外的细节）

正确性 = CORRECT / (CORRECT + INCORRECT + UNVERIFIABLE)

### 2. 完整性（Completeness）
diff 中需要记录到 wiki 的重要变更是否都被覆盖了。

以下不需要记录（Agent 不提是对的，不扣分）:
- 纯重构、变量重命名、格式调整、注释修改
- 单元测试、CI 配置
- 与现有 wiki 无关的微小改动

以下需要记录:
- 新增功能模块或全新系统
- 行为发生明显变化（API 参数、返回值、异常处理等）
- 与 wiki 现有描述冲突的代码变更
- 数据模型变更

完整性 = 已覆盖的重要变更 / 总重要变更

### 3. 精确性（Precision）
wiki 中 Agent 写的内容是否聚焦于本次 diff，无冗余、跑题、或过度展开。

- 背景说明、使用建议不算冗余（不超过 wiki 总篇幅 30%）
- Agent 编造 diff 之外的具体细节（如"支持 GitHub/Google/微信"但 diff 只写了 provider: str）扣分

精确性 = 相关句子数 / 总句子数

注意:
- claims 必须包含 wiki 中 Agent 写的每条事实陈述
- score 是 0.0 ~ 1.0 的浮点数
- reason 给出计算过程，引用具体的文件名或函数名
"""


def build_judge_prompt(tmp_dir: str) -> str:
    """构建 Judge 的 system prompt。"""
    # 用 replace 而非 format，因为 prompt 中包含 JSON 的 { }
    return _JUDGE_SYSTEM_PROMPT.replace("{tmp_dir}", tmp_dir)


# ── Judge 输出 JSON Schema ─────────────────────────────────────────────────────

_JUDGE_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "correctness": {
            "type": "object",
            "properties": {
                "score": {"type": "number", "minimum": 0, "maximum": 1},
                "reason": {"type": "string"},
            },
            "required": ["score", "reason"],
        },
        "completeness": {
            "type": "object",
            "properties": {
                "score": {"type": "number", "minimum": 0, "maximum": 1},
                "reason": {"type": "string"},
            },
            "required": ["score", "reason"],
        },
        "precision": {
            "type": "object",
            "properties": {
                "score": {"type": "number", "minimum": 0, "maximum": 1},
                "reason": {"type": "string"},
            },
            "required": ["score", "reason"],
        },
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "statement": {"type": "string"},
                    "verdict": {"type": "string", "enum": ["CORRECT", "INCORRECT", "UNVERIFIABLE"]},
                    "evidence": {"type": "string"},
                },
                "required": ["statement", "verdict", "evidence"],
            },
        },
    },
    "required": ["correctness", "completeness", "precision", "claims"],
}


# ── Judge 执行 ─────────────────────────────────────────────────────────────────

async def run_judge_session(
    tmp_dir: str,
    model: Any,
    model_registry: Any = None,
    auth_storage: Any = None,
) -> dict:
    """
    启动 AgentSession 作为 Judge，使用 structured_output 强制输出 JSON。

    Args:
        tmp_dir: prepare_judge_dir() 返回的工作目录
        model: pi_ai Model 对象
        model_registry: ModelRegistry 实例（可选，自动创建）
        auth_storage: AuthStorage 实例（可选，自动创建）

    Returns: Judge 输出的 dict（通过 structured_output 捕获）
    """
    from dotenv import load_dotenv
    load_dotenv()

    from pi_coding_agent.core.agent_session import AgentSession
    from pi_coding_agent.core.auth_storage import AuthStorage
    from pi_coding_agent.core.model_registry import ModelRegistry
    from pi_coding_agent.core.session_manager import SessionManager
    from pi_coding_agent.core.settings_manager import Settings
    from pi_wiki_agent.core.workflow.structured_output import (
        StructuredOutputCapture,
        create_structured_output_tool,
    )

    if model_registry is None:
        model_registry = ModelRegistry(auth_storage=AuthStorage())
    if auth_storage is None:
        auth_storage = AuthStorage()

    settings = Settings(
        thinking_level="off",
        model_id=model.id if model else None,
        provider=model.provider if model else None,
    )

    # structured_output 捕获
    capture = StructuredOutputCapture()
    so_tool = create_structured_output_tool(_JUDGE_OUTPUT_SCHEMA, capture)
    _debug("step2: 创建 structured_output 工具, schema 有 %d 个顶层字段",
             len(_JUDGE_OUTPUT_SCHEMA["required"]))

    session = AgentSession(
        cwd=tmp_dir,
        model=model,
        settings=settings,
        session_manager=SessionManager.in_memory(tmp_dir),
        auth_storage=auth_storage,
        model_registry=model_registry,
        extra_tools=[so_tool],
    )

    session.set_active_tools_by_name(["read", "grep", "ls", "structured_output"])
    _debug(" step2: AgentSession 创建完成, model=%s/%s, cwd=%s",
             model.provider, model.id, tmp_dir)

    system_prompt = build_judge_prompt(tmp_dir)
    system_prompt += (
        "\n\n评测完成后，必须调用 structured_output 工具提交结果。"
        "不要输出任何其他文本。"
    )
    session._agent.set_system_prompt(system_prompt)
    _debug(" step2: system_prompt 长度=%d chars, 激活工具=%s",
             len(system_prompt), ["read", "grep", "ls", "structured_output"])

    task_prompt = (
        "请评测 diff/ 中源代码变更对应的 wiki/ 中 Agent 生成的 Wiki 内容质量。"
        "先读 _summary.txt 了解全局，再逐个审查具体文件。"
    )
    _debug(" step3: 发送 task_prompt, 长度=%d chars", len(task_prompt))

    try:
        await session.prompt(task_prompt)
        _debug(" step4: session.prompt 返回")

        # 输出 Judge 的消息历史（工具调用记录）—— 容错，不影响主流程
        try:
            msgs = session._agent.state.messages
            tool_calls = 0
            for msg in msgs:
                content = getattr(msg, "content", [])
                if isinstance(content, list):
                    for part in content:
                        if hasattr(part, "name") and getattr(part, "name", None):
                            tool_calls += 1
                            args_str = str(getattr(part, "arguments", "") if hasattr(part, "arguments") else "")[:80]
                            _debug(" step4: tool_call #%d: %s(%s)", tool_calls, part.name, args_str)
            _debug(" step4: 共 %d 次工具调用, %d 条消息", tool_calls, len(msgs))
        except Exception:
            _debug(" step4: 消息统计失败 (non-critical)")

        if capture.called:
            _debug(" step5: structured_output 捕获成功, claims=%d 条",
                     len(capture.value.get("claims", [])) if isinstance(capture.value, dict) else 0)
            return capture.value
        # fallback
        text = _last_assistant_text(session)
        if text:
            _debug("WARN: step5: structured_output 未调用, fallback 解析文本 (%d chars)", len(text))
            return parse_judge_response(text)
        raise RuntimeError("Judge did not produce any output")
    finally:
        session.dispose()
        _debug(" step6: session 已释放")


def _last_assistant_text(session: Any) -> str:
    """从 session 消息中提取最后一个 assistant 文本回复。"""
    messages = session._agent.state.messages
    for msg in reversed(messages):
        role = getattr(msg, "role", "")
        if role != "assistant":
            continue
        content = getattr(msg, "content", [])
        if not isinstance(content, list):
            continue
        texts = []
        for part in content:
            if hasattr(part, "text"):
                texts.append(part.text)
            elif isinstance(part, dict) and part.get("type") == "text":
                texts.append(part["text"])
        text = "".join(texts).strip()
        if text:
            return text
    return ""


# ── JSON 解析 ──────────────────────────────────────────────────────────────────

def parse_judge_response(text: str) -> dict:
    """
    从 Judge 的响应中解析 JSON。

    处理常见的格式瑕疵：```json 包裹、前后空白、末尾逗号。
    Raises ValueError 如果无法解析。
    """
    # 去除可能的 markdown 代码块包裹
    text = text.strip()
    if text.startswith("```"):
        # 找到第一个 ``` 之后的换行
        idx = text.find("\n")
        if idx > 0:
            text = text[idx + 1:]
        # 去掉末尾的 ```
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:text.rstrip().rfind("```")]

    text = text.strip()

    # 尝试直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 尝试从文本中提取 JSON 对象
    match = re.search(r'\{[\s\S]*"correctness"[\s\S]*\}', text)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    raise ValueError(f"无法从 Judge 响应中解析 JSON: {text[:500]}")


# ── 顶层入口 ───────────────────────────────────────────────────────────────────

async def judge(
    diff_text: str,
    wiki_diff_text: str,
    commit_message: str = "",
    model: Any = None,
    tmp_dir: str | None = None,
) -> dict:
    """
    执行一次完整的 LLM Judge 评测。

    Args:
        diff_text: 源码变更的 unified diff
        wiki_diff_text: Agent 对 wiki 的变更（git diff -- .wiki/）
        commit_message: commit 信息
        model: pi_ai Model 对象。为 None 时自动解析默认模型
        tmp_dir: 可选，已有的临时工作目录

    Returns:
        {"correctness": {score, reason},
         "completeness": {score, reason},
         "precision": {score, reason},
         "claims": [{statement, verdict, evidence}, ...]}
    """
    # 准备目录
    tmp_dir = prepare_judge_dir(
        diff_text=diff_text,
        wiki_diff_text=wiki_diff_text,
        commit_message=commit_message,
        tmp_dir=tmp_dir,
    )

    # 解析模型 — 优先用 deepseek（项目中已有 key），claude 作为备选
    if model is None:
        from pi_coding_agent.core.auth_storage import AuthStorage
        from pi_coding_agent.core.model_registry import ModelRegistry
        registry = ModelRegistry(auth_storage=AuthStorage())
        model = registry.resolve_model(model_id="deepseek-v4-flash", provider="deepseek")
        if model is None:
            model = registry.resolve_model(model_id="claude-sonnet-4-6", provider="anthropic")
        if model is None:
            raise RuntimeError("No Judge model available. Please configure an API key.")

    # 执行（run_judge_session 通过 structured_output 直接返回 dict）
    return await run_judge_session(tmp_dir, model)
