"""
真实 LLM 测试执行器 — 将合成 diff 直接写入磁盘，绕过 git，调用 run_workflow()。

与 cron/jobs.py 用同一套调用模式，不依赖 execute_workflow_sync 的 git 操作。
"""
from __future__ import annotations

import asyncio
import os
import shutil
from pathlib import Path
from typing import Any

from . import TestRunner
from .types import SuiteResult


def _write_per_file_diffs(project_path: str, changed_files: list[str],
                          diff_text: str, revision: str) -> str:
    """将完整 diff 按文件拆分并写入 .wiki/chain/diffs/<revision>/，返回 diffs_dir。"""
    diffs_dir = os.path.join(project_path, ".wiki", "chain", "diffs", revision)
    os.makedirs(diffs_dir, exist_ok=True)

    # 按文件拆分 unified diff
    per_file = _split_diff(diff_text)

    for fname in changed_files:
        safe = fname.replace("/", "_").replace("\\", "_")
        fdiff = per_file.get(fname, diff_text)  # 找不到则用完整 diff
        with open(os.path.join(diffs_dir, f"{safe}.diff"), "w", encoding="utf-8") as f:
            f.write(fdiff)

    return diffs_dir


def _split_diff(diff_text: str) -> dict[str, str]:
    """将 unified diff 按文件拆分为 {filename: diff_chunk}。"""
    result: dict[str, str] = {}
    current_file: str | None = None
    current_lines: list[str] = []

    for line in diff_text.split("\n"):
        if line.startswith("diff --git "):
            if current_file and current_lines:
                result[current_file] = "\n".join(current_lines)
            # 提取 b/ 路径
            parts = line.split(" ")
            b_path = parts[-1] if parts else ""
            if b_path.startswith("b/"):
                current_file = b_path[2:]
            else:
                current_file = b_path
            current_lines = [line]
        elif current_file:
            current_lines.append(line)

    if current_file and current_lines:
        result[current_file] = "\n".join(current_lines)

    return result


async def _real_workflow(inputs: dict[str, Any]) -> dict[str, Any]:
    """真实 LLM 执行 sync 工作流。与 execute_workflow_sync 内部逻辑一致，
    但 diff 直接写入磁盘而非通过 git 提取。"""
    from dotenv import load_dotenv
    load_dotenv()

    from pi_coding_agent.core.auth_storage import AuthStorage
    from pi_wiki_desktop.wiki_model_registry import WikiModelRegistry
    from pi_wiki_agent.core.workflow import WorkflowRunOptions, run_workflow
    from pi_wiki_agent.core.workflow.workflow_agent import WorkflowAgent
    from pi_wiki_agent.core.workflow_sync import (
        _load_workflow_agent_defs, _format_affected_sections,
        _resolve_model,
    )
    from pi_wiki_agent.indexer import WikiIndexer
    from pi_wiki_agent.core.wiki_quality import WikiQualityChecker
    from pi_wiki_agent.core.workflow.ast_compiler import compile_workflow_yaml

    project_path = inputs.get("project_path", "D:/project/wiki-demo-taskman")
    changed_files = inputs.get("changed_files", [])
    commit_message = inputs.get("commit_message", "")
    diff_text = inputs.get("diff", "")
    revision = inputs.get("revision", "eval")

    # ── 0. 质量检查 before ──
    checker = WikiQualityChecker(project_path)
    report_before = checker.run_checks()

    # ── 1. 反向索引 ──
    indexer = WikiIndexer(project_path)
    affected = indexer.get_affected_sections(changed_files) or {}
    affected_text = _format_affected_sections(affected)

    # ── 2. 写入 per-file diffs ──
    diffs_dir = _write_per_file_diffs(project_path, changed_files, diff_text, revision)

    # ── 3. 加载 agent 定义 + 编译脚本 ──
    agent_defs = _load_workflow_agent_defs(project_path)

    import pi_wiki_agent.core.workflow.scripts as _scripts
    yaml_path = Path(_scripts.__file__).parent / "sync.yaml"
    yaml_text = yaml_path.read_text(encoding="utf-8")
    script = compile_workflow_yaml(yaml_text)

    # ── 4. 模型 ──
    registry = WikiModelRegistry(auth_storage=AuthStorage())
    resolved_model = _resolve_model("deepseek:deepseek-v4-flash", registry)

    # ── 5. 执行 ──
    args = {
        "project_path": project_path,
        "changed_files": changed_files,
        "commit_message": commit_message,
        "diff": diff_text,
        "affected_sections": affected_text,
        "diffs_dir": diffs_dir,
        "revision": revision,
        "commit_hash": revision,
        "agent_defs": agent_defs,
        "keep_checkpoint": False,
    }

    agent = WorkflowAgent(
        cwd=project_path,
        model=resolved_model,
        model_registry=registry,
        auth_storage=AuthStorage(),
    )

    result = await run_workflow(
        script,
        WorkflowRunOptions(
            args=args,
            cwd=project_path,
            agent=agent,
            concurrency=8,
        ),
    )

    # ── 6. 质量检查 after ──
    report_after = checker.run_checks()

    # ── 7. 清理 diffs ──
    try:
        shutil.rmtree(diffs_dir, ignore_errors=True)
    except Exception:
        pass

    return {
        "phases": result.phases,
        "outputs": result.result,
        "agent_count": result.agent_count,
        "logs": result.logs,
        "errors_before": report_before.errors,
        "errors_after": report_after.errors,
        "warnings_before": report_before.warnings,
        "warnings_after": report_after.warnings,
        "pages_modified_before": report_before.total_pages,
        "pages_modified_after": report_after.total_pages,
    }


def make_runner(
    project_path: str,
    vcs: str = "git",
    enable_judge: bool = True,
) -> TestRunner:
    """创建真实 LLM 测试执行器"""
    def wrapper(inputs: dict) -> dict:
        inputs["project_path"] = project_path
        return asyncio.run(_real_workflow(inputs))
    return TestRunner(
        workflow_fn=wrapper,
        project_path=project_path,
        vcs=vcs,
        enable_judge=enable_judge,
    )


def run_real(project_path: str, cases_dir: str | Path, repeats: int = 1) -> SuiteResult:
    """便捷入口：一次调用运行全部用例"""
    runner = make_runner(project_path)
    return runner.run_all(Path(cases_dir), repeats=repeats)
