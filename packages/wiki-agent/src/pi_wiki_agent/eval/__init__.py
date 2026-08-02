"""
pi-wiki-agent 同步 Agent 测试框架

用法::

    from pi_wiki_agent.eval import TestRunner

    runner = TestRunner(dry_run=True)
    suite = runner.run_all(Path("cases/"))
"""

from .types import SuiteResult, CaseResult, Assertion, Verdict, RunStatus
from .loader import discover_cases, load_case
from .runner import TestRunner
from .checker import check
from .reporter import (
    print_header, print_case_result, print_summary,
    write_markdown_report,
)

__all__ = [
    "SuiteResult", "CaseResult", "Assertion", "Verdict", "RunStatus",
    "discover_cases", "load_case",
    "TestRunner",
    "check",
    "print_header", "print_case_result", "print_summary",
    "write_markdown_report",
]
