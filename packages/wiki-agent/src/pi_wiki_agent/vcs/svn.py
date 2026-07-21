"""SVN monitor implementation."""

from __future__ import annotations

import asyncio
import xml.etree.ElementTree as ET
from pathlib import Path

from .monitor import CommitInfo, VCSMonitor


class SVNMonitor(VCSMonitor):
    """SVN VCS monitor using subprocess svn commands."""

    async def poll(self) -> list[CommitInfo]:
        await self._ensure_repo_prefix()
        last = self.get_last_revision()
        if last:
            try:
                start = str(int(last) + 1)
            except ValueError:
                start = "1"
        else:
            start = "1"

        xml_out = await self._svn("log", "-r", f"{start}:HEAD", "--xml", "--verbose")
        if not xml_out:
            return []
        return self._parse_log_xml(xml_out)

    async def get_commit(self, revision: str) -> CommitInfo:
        await self._ensure_repo_prefix()

        xml_out = await self._svn("log", "-r", revision, "--xml", "--verbose")
        commits = self._parse_log_xml(xml_out)
        base = commits[0] if commits else CommitInfo(revision=revision)

        # Changed files: svn diff --summarize -c N
        summary = await self._svn("diff", "--summarize", "-c", revision)
        files: list[str] = []
        for line in summary:
            stripped = line.strip()
            if stripped:
                # Format: "M       path/to/file"
                parts = stripped.split(None, 1)
                if len(parts) >= 2:
                    rel = self._strip_repo_root(parts[1])
                    if rel:
                        files.append(self._norm_path(rel))

        # Diff
        diff_lines = await self._svn("diff", "-c", revision)
        diff = "\n".join(line.rstrip("\r") for line in diff_lines)

        base.files = files
        base.diff = diff
        return base

    # ── Helpers ─────────────────────────────────────────────────────────

    async def _svn(self, *args: str) -> list[str]:
        cmd = ["svn", *args]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(self._project_root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await proc.communicate()
        if not stdout:
            return []
        return stdout.decode("utf-8", errors="replace").splitlines()

    async def _ensure_repo_prefix(self) -> None:
        """Lazily fetch SVN repo-relative path prefix (e.g. /trunk)."""
        if hasattr(self, "_repo_prefix"):
            return
        lines = await self._svn("info", "--show-item", "relative-url")
        prefix = ""
        if lines:
            relative_url = lines[0].strip()
            # relative_url looks like ^/trunk or ^/branches/feature-x
            if relative_url.startswith("^/"):
                prefix = relative_url[1:]  # /trunk
        self._repo_prefix = prefix

    def _strip_repo_root(self, path: str) -> str:
        """Strip the SVN repo-relative prefix (e.g. /trunk/) to get a project-root-relative path."""
        p = path.strip().lstrip("/")
        prefix = getattr(self, "_repo_prefix", "")
        if prefix:
            prefix = prefix.lstrip("/")
            if p.startswith(prefix):
                p = p[len(prefix):].lstrip("/")
        return p

    def _parse_log_xml(self, raw: list[str]) -> list[CommitInfo]:
        text = "\n".join(raw)
        try:
            root = ET.fromstring(text)
        except ET.ParseError:
            return []
        commits: list[CommitInfo] = []
        for entry in root.findall("logentry"):
            rev = entry.get("revision", "")
            author_el = entry.find("author")
            date_el = entry.find("date")
            msg_el = entry.find("msg")
            files: list[str] = []
            paths_el = entry.find("paths")
            if paths_el is not None:
                for p in paths_el.findall("path"):
                    rel = self._strip_repo_root(p.text or "")
                    if rel:
                        files.append(self._norm_path(rel))
            commits.append(CommitInfo(
                revision=rev,
                author=author_el.text or "" if author_el is not None else "",
                timestamp=date_el.text or "" if date_el is not None else "",
                message=msg_el.text.strip() if msg_el is not None and msg_el.text else "",
                files=files,
            ))
        return commits

    async def get_file_diff(self, revision: str, file_path: str) -> str:
        """Return the diff for a single file using ``svn diff -c <rev> <file>``."""
        lines = await self._svn("diff", "-c", revision, file_path)
        return "\n".join(line.rstrip("\r") for line in lines)

    async def get_nth_ancestor(self, n: int) -> str:
        """Return the revision N commits before HEAD (0 = HEAD)."""
        lines = await self._svn("info", "--show-item", "revision")
        if not lines:
            return ""
        try:
            head = int(lines[0].strip())
        except ValueError:
            return ""
        ancestor = max(1, head - n)
        return str(ancestor)
