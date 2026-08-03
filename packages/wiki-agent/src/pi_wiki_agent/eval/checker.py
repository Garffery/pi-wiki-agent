"""
结果校验器 — 将 workflow 实际输出与 expected.json 对比，逐条生成 Assertion。
"""
from __future__ import annotations

from typing import Any

from .types import Assertion, Verdict


def check(expected: dict[str, Any], actual: dict[str, Any]) -> list[Assertion]:
    """
    根据 expected.json 逐条检查 workflow 的实际输出。

    expected.json 支持的字段见 TEST_CASE_CONSTRUCTION.md 第三章。
    """
    assertions: list[Assertion] = []

    # ── 辅助函数 ──

    def _add(name: str, exp: Any, act: Any, detail: str = ""):
        v = Verdict.PASS if act == exp else Verdict.FAIL
        assertions.append(Assertion(
            name=name, expected=exp, actual=act, verdict=v, detail=detail,
        ))

    def _contains(name: str, container: Any, item: Any, detail: str = ""):
        ok = item in container if container is not None else False
        v = Verdict.PASS if ok else Verdict.FAIL
        assertions.append(Assertion(
            name=name,
            expected=f"...包含 {item!r}",
            actual=list(container) if container else None,
            verdict=v, detail=detail,
        ))

    # ── 1. 结构完整性 ──
    phases = actual.get("phases") or []
    _add("phases_complete", 3, len(phases),
         f"工作流应有 3 个阶段，实际 {len(phases)}: {phases}")
    _contains("phase_analyze", phases, "Analyze")
    _contains("phase_plan",    phases, "Plan")
    _contains("phase_write",   phases, "Write")

    # ── 2. 质量无倒退 ──
    errors_before = actual.get("errors_before", 0)
    errors_after  = actual.get("errors_after", 0)
    worsened = errors_after > errors_before
    _add("no_error_worsen", False, worsened,
         f"errors: {errors_before} → {errors_after}")

    # ── 3. 页面覆盖 ──
    outputs = actual.get("outputs") or {}
    plan_raw: Any = outputs.get("Plan", {}) if isinstance(outputs, dict) else {}
    plan_tasks: list = (plan_raw.get("file_tasks") or []) if isinstance(plan_raw, dict) else []
    actual_pages = set(t.get("wiki_page", "") for t in plan_tasks if isinstance(t, dict))

    expected_pages = set(expected.get("should_modify_pages") or [])
    for page in expected_pages:
        _contains(f"page_modified:{page}", actual_pages, page,
                  f"应修改 {page}，实际修改了 {sorted(actual_pages)}")

    not_expected = set(expected.get("should_not_modify_pages") or [])
    unexpected = actual_pages & not_expected
    _add("no_unexpected_page_modified", set(), unexpected,
         f"不应修改但被修改了: {sorted(unexpected)}" if unexpected else "")

    # ── 4. No-op 专用 ──
    if expected.get("plan_file_tasks_should_be_empty"):
        _add("plan_file_tasks_empty", [], plan_tasks,
             f"Plan 应产出空任务列表，实际 {len(plan_tasks)} 条: {plan_tasks}")

    if "plan_no_change_files_should_include" in expected:
        no_change = plan_raw.get("no_change_files") or [] if isinstance(plan_raw, dict) else []
        for fname in expected["plan_no_change_files_should_include"]:
            _contains(f"no_change_includes:{fname}", no_change, fname)

    # ── 5. 质量变化方向 ──
    if expected.get("quality_should_improve") is True:
        improved = errors_after < errors_before
        _add("quality_improved", True, improved,
             f"errors: {errors_before} → {errors_after}")
    elif expected.get("quality_should_improve") is False:
        unchanged = errors_after == errors_before
        _add("quality_unchanged", True, unchanged,
             f"errors 不应变化: {errors_before} → {errors_after}")

    return assertions
