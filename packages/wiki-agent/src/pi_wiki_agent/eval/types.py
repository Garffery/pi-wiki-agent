"""
测试框架数据类型 — 纯数据，零项目依赖。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Verdict(str, Enum):
    """单条断言判定"""
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"

    def symbol(self) -> str:
        return {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}[self.value]


class RunStatus(str, Enum):
    """用例运行状态"""
    SUCCESS = "SUCCESS"    # 全部断言通过
    PARTIAL = "PARTIAL"    # 至少一条断言失败，但工作流未崩溃
    ERROR   = "ERROR"      # 工作流抛出异常
    SKIPPED = "SKIPPED"    # 未运行

    def symbol(self) -> str:
        return {
            "SUCCESS": "✅",
            "PARTIAL": "❌",
            "ERROR":   "\U0001F4A5",
            "SKIPPED": "⏭",
        }[self.value]


@dataclass
class Assertion:
    """单条检查结果"""
    name: str          # 断言名称，如 "phases_complete"
    expected: Any      # 期望值
    actual: Any        # 实际值
    verdict: Verdict
    detail: str = ""   # 失败时的补充说明

    @property
    def ok(self) -> bool:
        return self.verdict == Verdict.PASS


@dataclass
class CaseResult:
    """一个测试用例的完整运行结果"""
    case_id: str       # 用例 ID，如 "case_01_new_feature"
    case_name: str     # 显示名称，如 "新增功能"
    case_type: str     # 类型标签，如 "new_feature"
    status: RunStatus
    assertions: list[Assertion] = field(default_factory=list)
    content_metrics: dict = field(default_factory=dict)
    # {"correctness": {"score": 0.50, "reason": "..."},
    #  "completeness": {"score": 0.60, "reason": "..."},
    #  "precision": {"score": 0.67, "reason": "..."},
    #  "claims": [{statement, verdict, evidence}, ...]}
    # 空 dict = 未执行 Judge（dry-run 或出错）
    duration_ms: float = 0.0
    error_message: str = ""
    error_traceback: str = ""

    @property
    def passed(self) -> int:
        return sum(1 for a in self.assertions if a.ok)

    @property
    def failed(self) -> int:
        return sum(1 for a in self.assertions if a.verdict == Verdict.FAIL)

    @property
    def total(self) -> int:
        return len(self.assertions)

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 0.0

    @property
    def is_ok(self) -> bool:
        return self.status == RunStatus.SUCCESS


@dataclass
class SuiteResult:
    """一次完整测试套件的汇总结果"""
    suite_name: str
    cases: list[CaseResult] = field(default_factory=list)
    total_duration_ms: float = 0.0
    repeats: int = 1

    @property
    def by_status(self) -> dict[str, int]:
        counts: dict[str, int] = {s.value: 0 for s in RunStatus}
        for c in self.cases:
            counts[c.status.value] += 1
        return counts

    @property
    def overall_pass_rate(self) -> float:
        if not self.cases:
            return 0.0
        return sum(1 for c in self.cases if c.is_ok) / len(self.cases)

    @property
    def assertion_pass_rate(self) -> float:
        total_a = sum(c.total for c in self.cases)
        if total_a == 0:
            return 0.0
        return sum(c.passed for c in self.cases) / total_a

    def failures(self) -> list[CaseResult]:
        return [c for c in self.cases
                if c.status in (RunStatus.PARTIAL, RunStatus.ERROR)]
