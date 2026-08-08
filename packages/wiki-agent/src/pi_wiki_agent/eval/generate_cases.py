"""
从版本历史批量生成测试 case。支持 git 和 SVN。

用法:
  python -m pi_wiki_agent.eval.generate_cases \
    --vcs git \
    --project D:/project/wiki-demo-taskman \
    --count 10 \
    --out cases/
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path


# ── VCS 适配层 ─────────────────────────────────────────────────────────────────

def _git_log(project: str, count: int) -> list[dict]:
    """git: 获取最近 N 个 commit 的元信息。"""
    result = subprocess.run(
        ["git", "-C", project, "log", "--first-parent", "--no-merges",
         f"-{count}", "--format=%H|%s"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    commits = []
    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        parts = line.split("|", 1)
        rev = parts[0]
        msg = parts[1] if len(parts) > 1 else ""
        # 获取变更文件列表
        files_result = subprocess.run(
            ["git", "-C", project, "diff-tree", "--no-commit-id",
             "--name-only", "-r", rev],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        files = [f for f in files_result.stdout.strip().split("\n") if f]
        commits.append({"revision": rev, "message": msg, "files": files})
    return commits


def _svn_log(project: str, count: int) -> list[dict]:
    """SVN: 获取最近 N 个 commit 的元信息。"""
    result = subprocess.run(
        ["svn", "log", "-l", str(count), "--xml", project],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    import xml.etree.ElementTree as ET
    root = ET.fromstring(result.stdout)
    commits = []
    for entry in root.findall("logentry"):
        rev = entry.get("revision")
        msg_elem = entry.find("msg")
        msg = msg_elem.text.strip() if msg_elem is not None and msg_elem.text else ""

        paths_elem = entry.find("paths")
        files = []
        if paths_elem is not None:
            for p in paths_elem.findall("path"):
                path = p.text or ""
                # SVN paths are absolute from repo root
                if path.startswith("/"):
                    path = path[1:]
                files.append(path)

        commits.append({"revision": rev, "message": msg, "files": files})
    return commits


def _git_diff(project: str, revision: str) -> str:
    """git: 获取指定 revision 的 unified diff。"""
    result = subprocess.run(
        ["git", "-C", project, "diff", f"{revision}~1..{revision}"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return result.stdout


def _svn_diff(project: str, revision: str) -> str:
    """SVN: 获取指定 revision 的 unified diff。"""
    result = subprocess.run(
        ["svn", "diff", "-c", revision, project],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return result.stdout


# ── 单 commit 元信息获取 ────────────────────────────────────────────────────────

def _git_commit_info(project: str, revision: str) -> dict | None:
    """git: 获取单个 commit 的元信息。"""
    # commit message
    result = subprocess.run(
        ["git", "-C", project, "log", "-1", "--format=%H|%s", revision],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if not result.stdout.strip():
        return None
    parts = result.stdout.strip().split("|", 1)
    rev = parts[0]
    msg = parts[1] if len(parts) > 1 else ""
    # 变更文件列表
    files_result = subprocess.run(
        ["git", "-C", project, "diff-tree", "--no-commit-id",
         "--name-only", "-r", rev],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    files = [f for f in files_result.stdout.strip().split("\n") if f]
    return {"revision": rev, "message": msg, "files": files}


def _svn_commit_info(project: str, revision: str) -> dict | None:
    """SVN: 获取单个 revision 的元信息。"""
    result = subprocess.run(
        ["svn", "log", "-r", revision, "--xml", project],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    import xml.etree.ElementTree as ET
    root = ET.fromstring(result.stdout)
    entry = root.find("logentry")
    if entry is None:
        return None
    rev = entry.get("revision")
    msg_elem = entry.find("msg")
    msg = msg_elem.text.strip() if msg_elem is not None and msg_elem.text else ""
    paths_elem = entry.find("paths")
    files = []
    if paths_elem is not None:
        for p in paths_elem.findall("path"):
            path = p.text or ""
            if path.startswith("/"):
                path = path[1:]
            files.append(path)
    return {"revision": rev, "message": msg, "files": files}


# ── 类型推断 ───────────────────────────────────────────────────────────────────

def _infer_type(files: list[str], message: str) -> str:
    has_py = any(f.endswith(".py") for f in files)
    only_docs = all(f.endswith((".md", ".txt", ".rst", ".adoc")) for f in files)
    many_files = len(files) > 5

    if not files:
        return "empty"
    if only_docs:
        return "doc_only"
    if many_files:
        return "multi_file"
    if "refactor" in message.lower() or "remove" in message.lower() or "删除" in message:
        return "remove_refactor"
    if has_py:
        return "modify_behavior"
    return "unknown"


# ── 生成入口 ───────────────────────────────────────────────────────────────────

def generate_cases(
    project: str,
    out_dir: Path,
    count: int = 10,
    vcs: str = "git",
    revisions: list[str] | None = None,
):
    """
    从版本历史批量生成测试 case。

    Args:
        project: 目标项目路径
        out_dir: 输出目录
        count: 提取的 commit 数量（revisions 为空时有效）
        vcs: "git" 或 "svn"
        revisions: 指定 revision 列表。非空时忽略 count，只用指定版本。
                   git: commit hash 或短 hash
                   svn: revision 数字（字符串形式）
    """
    log_fn = _git_log if vcs == "git" else _svn_log
    diff_fn = _git_diff if vcs == "git" else _svn_diff
    info_fn = _git_commit_info if vcs == "git" else _svn_commit_info

    if revisions:
        # 指定版本模式
        commits = []
        for rev in revisions:
            info = info_fn(project, rev.strip())
            if info:
                commits.append(info)
            else:
                print(f"  警告: 未找到 revision '{rev}'，已跳过")
        if not commits:
            print(f"没有找到任何有效的 revision: {revisions}")
            return
    else:
        # 最近 N 个模式
        commits = log_fn(project, count)
        if not commits:
            print(f"没有找到任何 commit: {project}")
            return

    total = len(commits)
    os.makedirs(out_dir, exist_ok=True)

    for i, commit in enumerate(commits):
        rev = commit["revision"]
        msg = commit["message"]
        files = commit["files"]
        case_type = _infer_type(files, msg)

        # 目录名
        short_rev = rev[:8] if vcs == "git" else f"r{rev}"
        case_dir = out_dir / f"case_{i+1:02d}_{case_type}"
        case_dir.mkdir(parents=True, exist_ok=True)

        # diff
        diff = diff_fn(project, rev)
        (case_dir / "diff.txt").write_text(diff, encoding="utf-8")

        # args
        (case_dir / "args.json").write_text(json.dumps({
            "vcs": vcs,
            "changed_files": files,
            "commit_message": msg,
            "revision": rev,
        }, indent=2, ensure_ascii=False), encoding="utf-8")

        # expected（结构断言留空，三指标不依赖）
        (case_dir / "expected.json").write_text(json.dumps({
            "should_modify_pages": [],
            "should_not_modify_pages": [],
        }, indent=2, ensure_ascii=False), encoding="utf-8")

        print(f"  [{i+1:02d}/{total}] {case_dir.name}  ({rev[:12]})  {msg[:60]}")


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="从版本历史批量生成测试 case",
    )
    parser.add_argument("--vcs", choices=["git", "svn"], default="git",
                        help="版本控制类型")
    parser.add_argument("--project", required=True,
                        help="目标项目路径")
    parser.add_argument("--count", type=int, default=10,
                        help="提取最近 N 个 commit（与 --revisions 互斥，默认 10）")
    parser.add_argument("--revisions", type=str, default=None,
                        help="指定 revision 列表，逗号分隔。如 'f764ab2,9126b6c' 或 '101,102,105'")
    parser.add_argument("--out", type=Path, default=Path("cases"),
                        help="输出目录")
    args = parser.parse_args()

    project_path = os.path.abspath(args.project)
    out_dir = args.out.resolve()

    revisions = None
    if args.revisions:
        revisions = [r.strip() for r in args.revisions.split(",") if r.strip()]

    if revisions:
        print(f"VCS: {args.vcs}, 项目: {project_path}, 指定版本: {len(revisions)} 个, 输出: {out_dir}")
    else:
        print(f"VCS: {args.vcs}, 项目: {project_path}, 数量: {args.count}, 输出: {out_dir}")
    print()
    generate_cases(project_path, out_dir, args.count, args.vcs, revisions)
    print()
    total = len(revisions) if revisions else args.count
    print(f"完成，共生成 {total} 个 case → {out_dir}")


if __name__ == "__main__":
    main()
