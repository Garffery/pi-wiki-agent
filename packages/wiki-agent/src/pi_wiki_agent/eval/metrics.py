"""
指标计算 — pass@k, pass^k, 以及 per-type 细分。

pass@k 使用 SWE-bench 标准的无偏估计：对每个 case 独立计算后取平均。
"""
from __future__ import annotations

import math
from collections import defaultdict
from typing import Sequence

from .types import CaseResult, SuiteResult


def pass_at_k(n: int, c: int, k: int) -> float:
    """
    SWE-bench 标准的 pass@k 无偏估计（单题级别）。

    Args:
        n: 该题的总生成样本数
        c: 该题的正确样本数
        k: 随机抽取数

    Returns:
        从 n 个样本中随机抽 k 个，至少有一个正确的概率的无偏估计
    """
    if n < 1 or k < 1:
        return 0.0
    if c <= 0:
        return 0.0
    if n - c < k:
        return 1.0
    return 1.0 - math.comb(n - c, k) / math.comb(n, k)


def _group_by_case(results: Sequence[CaseResult]) -> dict[str, list[CaseResult]]:
    groups: dict[str, list[CaseResult]] = defaultdict(list)
    for r in results:
        groups[r.case_id].append(r)
    return dict(groups)


def compute_pass_at_k(suite: SuiteResult, k: int = 1) -> float:
    """
    从 SuiteResult 计算 pass@k。

    对每个 case 独立计算 pass@k，然后取所有 case 的平均值。
    这是 SWE-bench 论文使用的聚合方式。
    """
    groups = _group_by_case(suite.cases)
    if not groups:
        return 0.0

    per_case: list[float] = []
    for runs in groups.values():
        n_i = len(runs)
        if n_i == 0:
            continue
        c_i = sum(1 for r in runs if r.is_ok)
        actual_k = min(k, n_i)
        per_case.append(pass_at_k(n_i, c_i, actual_k))

    if not per_case:
        return 0.0
    return sum(per_case) / len(per_case)


def compute_pass_power_k(suite: SuiteResult, k: int | None = None) -> float:
    """
    计算 pass^k — 所有 k 次尝试全部成功的 case 占比。

    pass^k 衡量稳定性：一个 case 在 k 次重复中每次都成功才算通过。
    当 k 未指定时，默认使用 suite.repeats。
    """
    groups = _group_by_case(suite.cases)
    if not groups:
        return 0.0

    actual_k = k if k is not None else suite.repeats
    if actual_k < 1:
        return 0.0

    strict_pass = 0
    for runs in groups.values():
        if len(runs) >= actual_k and all(r.is_ok for r in runs[:actual_k]):
            strict_pass += 1

    return strict_pass / len(groups)


def compute_all(suite: SuiteResult) -> dict:
    """
    一站式计算所有指标。

    Returns a dict with:
      - n_cases, n_runs, repeats, total_successes
      - pass@1, pass@3 (if repeats >= 3), pass^k (if repeats > 1)
      - overall_pass_rate
      - mean_duration_ms
      - by_type: {type_name: {n, successes, pass@1, pass_rate}}
    """
    groups = _group_by_case(suite.cases)
    n_cases = len(groups)
    total_runs = len(suite.cases)

    if n_cases == 0:
        return {"error": "no cases"}

    metrics: dict = {
        "n_cases": n_cases,
        "n_runs": total_runs,
        "repeats": suite.repeats,
        "total_successes": sum(1 for r in suite.cases if r.is_ok),
        "pass@1": compute_pass_at_k(suite, k=1),
        "overall_pass_rate": suite.overall_pass_rate,
    }

    if suite.repeats >= 3:
        metrics["pass@3"] = compute_pass_at_k(suite, k=3)

    if suite.repeats > 1:
        metrics["pass^k"] = compute_pass_power_k(suite)

    durations = [r.duration_ms for r in suite.cases
                 if r.status.value not in ("SKIPPED", "ERROR")]
    if durations:
        metrics["mean_duration_ms"] = sum(durations) / len(durations)

    # Per-type breakdown
    by_type: dict[str, dict] = {}
    type_map: dict[str, list[list[CaseResult]]] = defaultdict(list)
    for runs in groups.values():
        if runs:
            type_map[runs[0].case_type].append(runs)

    for ctype, case_runs_list in sorted(type_map.items()):
        type_n = len(case_runs_list)
        if type_n == 0:
            continue
        type_c = sum(sum(1 for r in runs if r.is_ok) for runs in case_runs_list)
        type_total = sum(len(runs) for runs in case_runs_list)
        # per-case averaged pass@1 for this type
        per_case_p1 = []
        for runs in case_runs_list:
            n_i = len(runs)
            c_i = sum(1 for r in runs if r.is_ok)
            per_case_p1.append(pass_at_k(n_i, c_i, 1))
        by_type[ctype] = {
            "n": type_n,
            "total_runs": type_total,
            "successes": type_c,
            "pass@1": sum(per_case_p1) / len(per_case_p1) if per_case_p1 else 0.0,
            "pass_rate": sum(1 for runs in case_runs_list
                             if any(r.is_ok for r in runs)) / type_n,
        }

    metrics["by_type"] = by_type
    return metrics
