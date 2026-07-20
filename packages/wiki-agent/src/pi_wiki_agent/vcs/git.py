"""Git monitor implementation."""

from __future__ import annotations

import asyncio
from pathlib import Path

from ..logging import logger
from .monitor import CommitInfo, VCSMonitor


class GitMonitor(VCSMonitor):
    """Git VCS monitor using subprocess git commands."""

    async def poll(self) -> list[CommitInfo]:
        last = self.get_last_revision()
        range_spec = f"{last}..HEAD" if last else "HEAD"
        commits: list[CommitInfo] = []

        lines = await self._git("log", "--format=%H %s", range_spec, "--first-parent", "--reverse")
        if not lines:
            return commits

        for line in lines:
            parts = line.strip().split(" ", 1)
            if len(parts) < 2:
                continue
            rev, msg = parts[0], parts[1]
            files = await self._git("diff-tree", "--no-commit-id", "--name-only", "-r", rev)
            if not files:
                files = await self._git("diff-tree", "--no-commit-id", "--name-only", "-r", "--root", rev)
            commits.append(CommitInfo(
                revision=rev,
                message=msg,
                files=[self._norm_path(f) for f in files if f.strip()],
            ))

        logger.info("Git 轮询: {} 个新提交 (范围: {})", len(commits), range_spec)
        return commits

    async def get_commit(self, revision: str) -> CommitInfo:
        # Author + timestamp
        meta = await self._git("show", "--format=%an%n%aI", "--no-patch", revision)
        author = meta[0].strip() if len(meta) > 0 else ""
        timestamp = meta[1].strip() if len(meta) > 1 else ""

        # Message
        msg_lines = await self._git("log", "--format=%s", "-1", revision)
        message = msg_lines[0].strip() if msg_lines else ""

        # Changed files
        files_raw = await self._git("diff-tree", "--no-commit-id", "--name-only", "-r", revision)
        if not files_raw:
            files_raw = await self._git("diff-tree", "--no-commit-id", "--name-only", "-r", "--root", revision)
        files = [self._norm_path(f) for f in files_raw if f.strip()]

        # Diff
        diff_lines = await self._git("diff", f"{revision}~1..{revision}")
        if not diff_lines:
            # Initial commit has no parent
            diff_lines = await self._git("show", "--format=", revision)
        diff = "\n".join(diff_lines)

        return CommitInfo(
            revision=revision,
            message=message,
            author=author,
            timestamp=timestamp,
            files=files,
            diff=diff,
        )

    async def _git(self, *args: str) -> list[str]:
        cmd = ["git", *args]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(self._project_root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            logger.warning("Git 命令失败: {} (code={}) stderr={}", " ".join(cmd), proc.returncode, stderr.decode("utf-8", errors="replace")[:200] if stderr else "")
        if not stdout:
            return []
        return stdout.decode("utf-8", errors="replace").splitlines()

    async def get_file_diff(self, revision: str, file_path: str) -> str:
        """Return the diff for a single file using ``git diff <rev>~1..<rev> -- <file>``."""
        parent = f"{revision}~1..{revision}"
        lines = await self._git("diff", parent, "--", file_path)
        if not lines:
            # Initial commit has no parent — use git show
            lines = await self._git("show", "--format=", revision, "--", file_path)
        return "\n".join(lines)
