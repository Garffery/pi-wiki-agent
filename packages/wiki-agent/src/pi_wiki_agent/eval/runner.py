"""
测试执行器 — 遍历用例，逐个执行，收集结果。
"""
from __future__ import annotations

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
    ):
        """
        Args:
            workflow_fn: 接收 {**args, "diff": str}，返回 workflow 运行结果 dict。
                         为 None 时使用内置 dry-run 模拟。
            checker_fn: 接收 (expected, actual)，返回 Assertion 列表。
                        为 None 时使用默认检查器。
            dry_run: True 时强制使用内置模拟，不调 LLM。
        """
        self.workflow_fn = workflow_fn or self._dry_run
        self.checker_fn = checker_fn or default_checker
        self.dry_run = dry_run

    # ═══════════════════════════════════════════════════════════
    # 主入口
    # ═══════════════════════════════════════════════════════════

    def run_all(
        self,
        cases_dir: Path,
        repeats: int = 1,
        on_progress: Callable[[int, int, str], None] | None = None,
    ) -> SuiteResult:
        """
        遍历 cases_dir 下所有用例，逐个执行。

        Args:
            cases_dir: 测试用例根目录
            repeats: 每个用例重复次数
            on_progress: 进度回调 (current, total, case_id)
        """
        case_dirs = discover_cases(cases_dir)
        if not case_dirs:
            raise FileNotFoundError(f"未找到测试用例: {cases_dir}")

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

            # 1. 执行 workflow
            workflow_input = {**case_data["args"], "diff": case_data["diff"]}
            output = self.workflow_fn(workflow_input)

            result.duration_ms = (time.time() - t0) * 1000

            # 2. 校验
            assertions = self.checker_fn(case_data["expected"], output)
            result.assertions = assertions

            # 3. 判定
            if all(a.ok for a in assertions):
                result.status = RunStatus.SUCCESS
            else:
                result.status = RunStatus.PARTIAL

        except Exception as e:
            result.status = RunStatus.ERROR
            result.error_message = str(e)
            result.error_traceback = traceback.format_exc()

        return result

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
