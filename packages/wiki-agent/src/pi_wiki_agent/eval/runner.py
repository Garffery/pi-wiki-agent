"""
测试执行器 — 遍历用例，逐个执行，收集结果。
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import time
import traceback
from pathlib import Path
from typing import Any, Callable

from .types import CaseResult, SuiteResult, RunStatus
from .loader import discover_cases, load_case
from .checker import check as default_checker


class TestRunner:
    """
    测试执行器。

    用法::

        runner = TestRunner(dry_run=True)
        suite = runner.run_all(Path("cases/"), repeats=1)
    """

    def __init__(
        self,
        workflow_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
        checker_fn: Callable[[dict[str, Any], dict[str, Any]], list] | None = None,
        dry_run: bool = False,
        project_path: str | None = None,
        vcs: str = "git",
        enable_judge: bool = True,
    ):
        """
        Args:
            workflow_fn: 接收 {**args, "diff": str}，返回 workflow 运行结果 dict。
                         为 None 时使用内置 dry-run 模拟。
            checker_fn: 接收 (expected, actual)，返回 Assertion 列表。
                        为 None 时使用默认检查器。
            dry_run: True 时强制使用内置模拟，不调 LLM。
            project_path: 目标项目路径，用于 wiki 重置和 Judge 评测。
            vcs: 版本控制类型，"git" 或 "svn"。
            enable_judge: True 时在工作流执行后调用 LLM Judge。
        """
        self.workflow_fn = workflow_fn or self._dry_run
        self.checker_fn = checker_fn or default_checker
        self.dry_run = dry_run
        self.project_path = project_path
        self.vcs = vcs
        self.enable_judge = enable_judge

    # ═══════════════════════════════════════════════════════════
    # 主入口
    # ═══════════════════════════════════════════════════════════

    def run_all(
        self,
        cases_dir: Path,
        repeats: int = 1,
        on_progress: Callable[[int, int, str], None] | None = None,
        case_filter: str | None = None,
    ) -> SuiteResult:
        """
        遍历 cases_dir 下所有用例，逐个执行。

        Args:
            cases_dir: 测试用例根目录
            repeats: 每个用例重复次数
            on_progress: 进度回调 (current, total, case_id)
            case_filter: 可选用例名称过滤（匹配目录名，如 "case_01" 或 "new_feature"）
        """
        case_dirs = discover_cases(cases_dir)

        # 应用过滤器
        if case_filter:
            case_dirs = [d for d in case_dirs if case_filter in d.name]

        if not case_dirs:
            msg = f"未找到测试用例: {cases_dir}"
            if case_filter:
                msg += f" (filter: {case_filter})"
            raise FileNotFoundError(msg)

        suite = SuiteResult(
            suite_name=cases_dir.name,
            repeats=repeats,
        )

        total = len(case_dirs) * repeats
        idx = 0
        t0 = time.time()

        for case_dir in case_dirs:
            case_data = load_case(case_dir)

            for rep in range(repeats):
                idx += 1
                if on_progress:
                    on_progress(idx, total, case_data["id"])

                suffix = f" (run {rep + 1}/{repeats})" if repeats > 1 else ""
                result = self._run_one(case_data, suffix)
                suite.cases.append(result)

        suite.total_duration_ms = (time.time() - t0) * 1000
        return suite

    # ═══════════════════════════════════════════════════════════
    # 单用例执行
    # ═══════════════════════════════════════════════════════════

    def _run_one(self, case_data: dict[str, Any], repeat_label: str = "") -> CaseResult:
        result = CaseResult(
            case_id=case_data["id"],
            case_name=case_data["name"] + repeat_label,
            case_type=case_data["type"],
            status=RunStatus.SKIPPED,
        )

        try:
            t0 = time.time()

            # 0. 重置 wiki
            self._reset_wiki(case_data)

            # 1. 执行 workflow
            workflow_input = {**case_data["args"], "diff": case_data["diff"]}
            output = self.workflow_fn(workflow_input)

            result.duration_ms = (time.time() - t0) * 1000

            # 2. 结构校验
            assertions = self.checker_fn(case_data["expected"], output)
            result.assertions = assertions

            # 3. 判定
            if all(a.ok for a in assertions):
                result.status = RunStatus.SUCCESS
            else:
                result.status = RunStatus.PARTIAL

            # 4. LLM Judge
            if self.project_path and not self.dry_run and self.enable_judge:
                try:
                    cm = self._run_judge_sync(case_data)
                    result.content_metrics = cm
                except Exception as e:
                    def _jd(msg, *args):
                        print(f"  [RUNNER] {msg % args if args else msg}", flush=True)
                    _jd("WARN: LLM Judge failed: %s", str(e))

        except Exception as e:
            result.status = RunStatus.ERROR
            result.error_message = str(e)
            result.error_traceback = traceback.format_exc()

        return result

    # ═══════════════════════════════════════════════════════════
    # Wiki 重置
    # ═══════════════════════════════════════════════════════════

    def _reset_wiki(self, case_data: dict[str, Any]) -> None:
        """重置 wiki 到该 case revision 的父节点状态。"""
        def _jd(msg, *args):
            print(f"  [RUNNER] {msg % args if args else msg}", flush=True)

        if not self.project_path:
            return
        revision = case_data["args"].get("revision")
        if not revision:
            return

        if self.vcs == "git":
            parent = f"{revision}~1"
            _jd("[Runner] reset: git checkout %s -- .wiki/", parent[:12])
            subprocess.run(
                ["git", "-C", self.project_path, "checkout", parent, "--", ".wiki/"],
                capture_output=True, encoding="utf-8", errors="replace",
            )
            subprocess.run(
                ["git", "-C", self.project_path, "clean", "-fd", ".wiki/chain/"],
                capture_output=True, encoding="utf-8", errors="replace",
            )
        elif self.vcs == "svn":
            parent = str(int(revision) - 1)
            wiki_path = os.path.join(self.project_path, ".wiki")
            _jd("[Runner] reset: svn update -r %s %s", parent, wiki_path)
            subprocess.run(
                ["svn", "update", "-r", parent, wiki_path],
                capture_output=True, encoding="utf-8", errors="replace",
            )

    # ═══════════════════════════════════════════════════════════
    # LLM Judge
    # ═══════════════════════════════════════════════════════════

    def _get_wiki_changes(self) -> str:
        """获取 workflow 执行后 .wiki/ 的变更。"""
        if not self.project_path:
            return ""

        if self.vcs == "git":
            result = subprocess.run(
                ["git", "-C", self.project_path, "diff", "--", ".wiki/"],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
            )
            return result.stdout
        elif self.vcs == "svn":
            result = subprocess.run(
                ["svn", "diff", os.path.join(self.project_path, ".wiki")],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
            )
            return result.stdout
        return ""

    def _run_judge_sync(self, case_data: dict[str, Any]) -> dict:
        """同步包装 Judge 调用。"""
        from .llm_judge import judge
        def _jd(msg, *args):
            print(f"  [RUNNER] {msg % args if args else msg}", flush=True)

        wiki_diff = self._get_wiki_changes()
        _jd("[Runner] Judge: wiki diff 长度=%d chars", len(wiki_diff))
        if not wiki_diff.strip():
            _jd("WARN: [Runner] Judge: wiki diff 为空，跳过")
            return {}

        diff_text = case_data["diff"]
        commit_msg = case_data["args"].get("commit_message", "")
        _jd("[Runner] Judge: 源码 diff 长度=%d chars, commit=%s", len(diff_text), commit_msg[:60])
        _jd("[Runner] Judge: 开始执行...")

        try:
            cm = asyncio.run(judge(
                diff_text=diff_text,
                wiki_diff_text=wiki_diff,
                commit_message=commit_msg,
            ))
            _jd("[Runner] Judge: 完成, correctness=%.2f, completeness=%.2f, precision=%.2f, claims=%d",
                     cm.get("correctness", {}).get("score", 0) if isinstance(cm.get("correctness"), dict) else 0,
                     cm.get("completeness", {}).get("score", 0) if isinstance(cm.get("completeness"), dict) else 0,
                     cm.get("precision", {}).get("score", 0) if isinstance(cm.get("precision"), dict) else 0,
                     len(cm.get("claims", [])))
            return cm
        except Exception as e:
            _jd("WARN: [Runner] Judge: 执行失败: %s", e)
            return {}

    # ═══════════════════════════════════════════════════════════
    # Dry-run 模拟（不调 LLM）
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def _dry_run(inputs: dict[str, Any]) -> dict[str, Any]:
        changed_files = inputs.get("changed_files", [])
        commit_message = inputs.get("commit_message", "")
        py_files = [f for f in changed_files if f.endswith(".py")]

        # No-op: 没有 .py 文件变更 → 质量不变
        if not py_files:
            return {
                "phases": ["Analyze", "Plan", "Write"],
                "outputs": {
                    "Analyze": f"[mock] 分析了 {len(changed_files)} 个文件，无代码变更",
                    "Plan": {
                        "file_tasks": [],
                        "no_change_files": changed_files,
                    },
                    "Write": [],
                },
                "agent_count": 1,
                "errors_before": 2,
                "errors_after": 2,
                "warnings_before": 3,
                "warnings_after": 3,
            }

        return {
            "phases": ["Analyze", "Plan", "Write"],
            "outputs": {
                "Analyze": f"[mock] 分析了 {len(changed_files)} 个文件",
                "Plan": {
                    "file_tasks": [
                        {
                            "file": f,
                            "wiki_page": _mock_wiki_page(f),
                            "section": "mock-section",
                            "action": "update",
                            "instructions": f"更新 {f} 的相关描述",
                        }
                        for f in py_files
                    ],
                    "no_change_files": [f for f in changed_files if not f.endswith(".py")],
                },
                "Write": [
                    f"[mock] 已更新 {_mock_wiki_page(f)} 以反映 {commit_message[:40]}"
                    for f in py_files
                ],
            },
            "agent_count": max(1, len(py_files) + 2),
            "errors_before": 2,
            "errors_after": 0,
            "warnings_before": 3,
            "warnings_after": 1,
        }


def _mock_wiki_page(file_path: str) -> str:
    """根据源文件路径推断对应的 wiki 页面（模拟反向索引逻辑）。"""
    if "cli" in file_path:
        return "api-reference.md"
    elif "models" in file_path:
        return "architecture.md"
    elif "storage" in file_path:
        return "configuration.md"
    return "getting-started.md"
