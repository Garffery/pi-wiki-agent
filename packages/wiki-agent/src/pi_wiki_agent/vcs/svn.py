"""SVN monitor implementation."""

from __future__ import annotations

import asyncio
import xml.etree.ElementTree as ET
from pathlib import Path

from .monitor import CommitInfo, VCSMonitor


class SVNMonitor(VCSMonitor):
    """SVN VCS monitor using subprocess svn commands."""

    async def poll(self) -> list[CommitInfo]:
        last = self.get_last_revision()
        if last:
            try:
                start = str(int(last) + 1)
            except ValueError:
                start = "1"
        else:
            start = "1"

        xml_out = await self._svn("log", "-r", f"{start}:HEAD", "--xml")
        if not xml_out:
            return []
        return self._parse_log_xml(xml_out)

    async def get_commit(self, revision: str) -> CommitInfo:
        # Metadata
        xml_out = await self._svn("log", "-r", revision, "--xml")
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
            commits.append(CommitInfo(
                revision=rev,
                author=author_el.text or "" if author_el is not None else "",
                timestamp=date_el.text or "" if date_el is not None else "",
                message=msg_el.text.strip() if msg_el is not None and msg_el.text else "",
            ))
        return commits

    @staticmethod
    def _strip_repo_root(path: str) -> str:
        """Remove leading slashes / repo-relative prefix from svn paths."""
        p = path.strip().lstrip("/")
        # SVN diff --summarize may output paths with leading repo-relative segments
        # Strip the common project root prefix if present
        return p
