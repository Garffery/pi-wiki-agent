"""Wiki sync chain — leverages the reverse index for commit-driven wiki updates.

Standard workflow:
  1. diff-analyzer: reads the diff + affected wiki sections (from reverse index),
     produces a structured change analysis
  2. wiki-planner:  reads the analysis, inspects wiki pages, creates an update plan
  3. wiki-writer:   executes the plan, making precise edits to wiki pages

Large diffs are written to disk (chain_dir/commit.diff) rather than inlined
in the prompt, so agents read them via the `read` tool as needed.
"""

from __future__ import annotations

import os
from pathlib import Path

from ...logging import logger
from ...indexer import WikiIndexer
from .executor import execute_chain, ProgressCallback, SessionFactory
from .types import ChainConfig, ChainResult, ChainStep


async def execute_sync_chain(
    project_path: str,
    changed_files: list[str],
    commit_message: str,
    diff: str,
    revision: str = "",
    chain_dir: str | None = None,
    steps: list[ChainStep] | None = None,
    on_progress: ProgressCallback = None,
    session_factory: SessionFactory | None = None,
) -> ChainResult:
    """Run a commit-driven wiki sync chain with reverse index integration.

    Pre-computes affected wiki sections via WikiIndexer.get_affected_sections()
    and injects them as template variables into the chain's first step.

    Args:
        project_path: Project root directory.
        changed_files: List of changed files from the VCS commit.
        commit_message: The commit message.
        diff: The unified diff of the commit (used for affected-section analysis).
        revision: The commit revision (used by VCS monitor to generate per-file diffs).
        chain_dir: Optional working directory for the chain.
        steps: Optional custom chain steps. Defaults to the standard
               diff-analyzer → wiki-planner → wiki-writer pipeline.

    Returns:
        ChainResult with per-step results and aggregated output.
    """
    # ── Pre-compute affected wiki sections via reverse index ──────────────────
    indexer = WikiIndexer(project_path)
    affected = indexer.get_affected_sections(changed_files)
    affected_text = _format_affected_sections(affected)

    logger.info(
        "Sync chain: {} changed files → {} affected wiki pages",
        len(changed_files), len(affected),
    )

    # ── Ensure chain working directory exists (inside project so read tool can access) ─
    if chain_dir is None:
        chain_dir = os.path.join(project_path, ".wiki", "chain")
    os.makedirs(chain_dir, exist_ok=True)

    # ── Write per-file diffs via native VCS commands (avoids context overflow) ─
    from pi_wiki_agent.vcs import create_monitor
    diffs_dir = os.path.join(chain_dir, "diffs")
    monitor = create_monitor(project_path)
    diff_files = await monitor.write_file_diffs(revision, changed_files, diffs_dir)
    logger.info("{} per-file diffs written to {}", len(diff_files), diffs_dir)

    # ── Build chain config ────────────────────────────────────────────────────
    if steps is None:
        steps = [
            ChainStep(agent="diff-analyzer"),
            ChainStep(agent="wiki-planner"),
            ChainStep(agent="wiki-writer"),
        ]

    diff_list = "\n".join(f"- .wiki/chain/diffs/{f}" for f in diff_files)
    task = (
        f"## 提交信息\n{commit_message}\n\n"
        f"## 变更文件\n" + "\n".join(f"- {f}" for f in changed_files) + "\n\n"
        f"## 受影响的 Wiki 章节\n{affected_text}\n\n"
        f"## Diff 文件（每个变更文件独立一个 diff）\n{diff_list}\n\n"
        f"请逐一阅读上述 diff 文件，分析代码变更并生成变更分析报告。"
    )
    config = ChainConfig(
        steps=steps,
        task=task,
        project_path=project_path,
        chain_dir=chain_dir,
        vars={
            "diffs_dir": diffs_dir,
            "commit_message": commit_message,
            "changed_files": "\n".join(f"- {f}" for f in changed_files),
            "affected_sections": affected_text,
        },
    )

    result = await execute_chain(config, on_progress=on_progress, session_factory=session_factory)

    # ── Cleanup ─────────────────────────────────────────────────────────────
    try:
        for f in diff_files:
            os.remove(os.path.join(diffs_dir, f))
        os.rmdir(diffs_dir)
        if not os.listdir(chain_dir):
            os.rmdir(chain_dir)
    except OSError:
        pass

    return result


def _format_affected_sections(affected: dict[str, list]) -> str:
    """Format affected wiki sections for use in an agent prompt.

    Mirrors the formatting in build_commit_prompt().
    """
    if not affected:
        return "没有找到与此提交相关的 wiki 章节。"

    lines: list[str] = []
    for wiki_page, entries in affected.items():
        sections = [e.section_id for e in entries]
        files = sorted({e.file for e in entries})
        lines.append(f"- **{wiki_page}** → 章节: {', '.join(sections)}（关联文件: {', '.join(files)}）")

    return "\n".join(lines)
