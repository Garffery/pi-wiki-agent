"""
结果报告器 — 终端彩色输出 + Markdown 文件报告。
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import TextIO

from .types import SuiteResult, CaseResult, Assertion, Verdict, RunStatus
from .metrics import compute_all

# ═══════════════════════════════════════════════════════════
# ANSI 颜色
# ═══════════════════════════════════════════════════════════

class _C:
    GRAY  = "\033[90m"
    RED   = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    CYAN  = "\033[96m"
    BOLD  = "\033[1m"
    RESET = "\033[0m"


def _c(text: str, *colors: str) -> str:
    if not sys.stdout.isatty():
        return text
    prefix = "".join(colors)
    return f"{prefix}{text}{_C.RESET}"


_STATUS_ICONS: dict[str, str] = {
    "SUCCESS": "PASS",
    "PARTIAL": "FAIL",
    "ERROR":   "ERR!",
    "SKIPPED": "SKIP",
}

_STATUS_COLORS: dict[str, tuple] = {
    "SUCCESS": (_C.GREEN,),
    "PARTIAL": (_C.RED,),
    "ERROR":   (_C.RED, _C.BOLD),
    "SKIPPED": (_C.GRAY,),
}


# ═══════════════════════════════════════════════════════════
# 控制台输出
# ═══════════════════════════════════════════════════════════

def print_header(suite: SuiteResult, file: TextIO = sys.stdout):
    """打印测试套件头部"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print("=" * 52, file=file)
    print("  pi-wiki-agent 同步 Agent 测试", file=file)
    print("-" * 52, file=file)
    print(f"  套件: {suite.suite_name}", file=file)
    print(f"  用例: {len(suite.cases)} 个  重复: {suite.repeats} 次", file=file)
    print(f"  时间: {now}", file=file)
    print("=" * 52, file=file)
    print(file=file)


def print_case_result(result: CaseResult, file: TextIO = sys.stdout):
    """打印单个用例结果"""
    icon = _STATUS_ICONS.get(result.status.value, "?")
    colors = _STATUS_COLORS.get(result.status.value, (_C.RESET,))

    # 用例标题行
    tag = result.case_type
    print(f"  {_c(icon, *colors)} [{tag}] {result.case_name}", file=file)

    # 断言列表
    for a in result.assertions:
        sym = a.verdict.symbol()
        if a.verdict == Verdict.PASS:
            print(f"    {_c(sym, _C.GREEN)} {a.name}", file=file)
        elif a.verdict == Verdict.FAIL:
            print(f"    {_c(sym, _C.RED)} {a.name}", file=file)
            print(f"      {_c('期望:', _C.GRAY)} {_trunc(str(a.expected), 80)}", file=file)
            print(f"      {_c('实际:', _C.GRAY)} {_trunc(str(a.actual), 80)}", file=file)
            if a.detail:
                print(f"      {_c(a.detail, _C.GRAY)}", file=file)
        else:
            print(f"    {_c(sym, _C.GRAY)} {a.name} (跳过)", file=file)

    # 错误
    if result.status == RunStatus.ERROR:
        print(f"    {_c('错误:', _C.RED)} {result.error_message}", file=file)
        for line in result.error_traceback.split("\n")[-4:]:
            if line.strip():
                print(f"      {_c(line, _C.GRAY)}", file=file)

    # 耗时和通过率
    tag_color = _C.GREEN if result.is_ok else _C.RED
    print(f"    {_c(f'{result.duration_ms:.0f}ms', _C.GRAY)}  "
          f"{_c(f'{result.passed}/{result.total}', tag_color)} 通过", file=file)
    print(file=file)


def print_summary(suite: SuiteResult, file: TextIO = sys.stdout):
    """打印汇总统计"""
    counts = suite.by_status
    total = max(len(suite.cases), 1)

    print("-" * 50, file=file)
    print("  [Summary]", file=file)
    print(file=file)

    # 条形图
    for status, label, color in [
        (RunStatus.SUCCESS, "完全通过", _C.GREEN),
        (RunStatus.PARTIAL, "部分失败", _C.RED),
        (RunStatus.ERROR,   "执行错误", _C.RED),
    ]:
        n = counts[status.value]
        bar_w = int(30 * n / total)
        bar = "█" * bar_w
        print(f"  {_c('●', color)} {label}: {n:3d}/{total}  {_c(bar, color)}", file=file)
    print(file=file)

    # 统计数字
    print(f"  断言通过率: {suite.assertion_pass_rate*100:.1f}%", file=file)
    print(f"  用例通过率: {suite.overall_pass_rate*100:.1f}%", file=file)
    print(f"  总耗时:     {suite.total_duration_ms:.0f}ms", file=file)

    # pass@k 指标
    m = compute_all(suite)
    if "pass@1" in m:
        print(f"  pass@1:     {m['pass@1']*100:.1f}%", file=file)
    if "pass@3" in m:
        print(f"  pass@3:     {m['pass@3']*100:.1f}%", file=file)
    if "pass^k" in m:
        print(f"  pass^{suite.repeats}:    {m['pass^k']*100:.1f}%", file=file)
    if "mean_duration_ms" in m:
        print(f"  平均耗时:   {m['mean_duration_ms']:.0f}ms", file=file)
    print(file=file)

    # 按类型细分 pass@1
    by_type = m.get("by_type") or {}
    if by_type:
        print("  ── 按类型 pass@1 ──", file=file)
        for ctype, tm in by_type.items():
            print(f"  {ctype:20s}  {tm['pass@1']*100:5.1f}%  ({tm['pass_rate']*100:.0f}% cases 有过成功)", file=file)
        print(file=file)

    # 失败列表
    failures = suite.failures()
    if failures:
        print(_c("  失败用例:", _C.RED), file=file)
        for f in failures:
            print(f"    - [{f.case_type}] {f.case_name}", file=file)
        print(file=file)


# ═══════════════════════════════════════════════════════════
# Markdown 报告
# ═══════════════════════════════════════════════════════════

def write_markdown_report(suite: SuiteResult, output_path: Path) -> Path:
    """生成 Markdown 测试报告"""
    lines: list[str] = []
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines.append("# 同步 Agent 测试报告")
    lines.append("")
    lines.append(f"| 项目 | 值 |")
    lines.append(f"|------|----|")
    lines.append(f"| 生成时间 | {now} |")
    lines.append(f"| 测试套件 | {suite.suite_name} |")
    lines.append(f"| 用例数 | {len(suite.cases)} |")
    lines.append(f"| 重复次数 | {suite.repeats} |")
    lines.append(f"| 总耗时 | {suite.total_duration_ms:.0f}ms |")
    lines.append("")

    # 汇总
    counts = suite.by_status
    m = compute_all(suite)
    lines.append("## 汇总")
    lines.append("")
    lines.append(f"| 指标 | 值 |")
    lines.append(f"|------|----|")
    lines.append(f"| 用例通过率 | {suite.overall_pass_rate*100:.1f}% |")
    lines.append(f"| 断言通过率 | {suite.assertion_pass_rate*100:.1f}% |")
    lines.append(f"| pass@1 | {m.get('pass@1', 0)*100:.1f}% |")
    if "pass@3" in m:
        lines.append(f"| pass@3 | {m['pass@3']*100:.1f}% |")
    if "pass^k" in m:
        lines.append(f"| pass^{suite.repeats} | {m['pass^k']*100:.1f}% |")
    if "mean_duration_ms" in m:
        lines.append(f"| 平均耗时 | {m['mean_duration_ms']:.0f}ms |")
    lines.append(f"| 完全通过 | {counts[RunStatus.SUCCESS.value]} |")
    lines.append(f"| 部分失败 | {counts[RunStatus.PARTIAL.value]} |")
    lines.append(f"| 执行错误 | {counts[RunStatus.ERROR.value]} |")
    lines.append("")

    # 按类型汇总
    by_type: dict[str, list[CaseResult]] = {}
    for c in suite.cases:
        by_type.setdefault(c.case_type, []).append(c)
    if by_type:
        lines.append("### 按类型")
        lines.append("")
        lines.append(f"| 类型 | 用例数 | 通过率 |")
        lines.append(f"|------|--------|--------|")
        for t, cases in sorted(by_type.items()):
            rate = sum(1 for c in cases if c.is_ok) / len(cases)
            lines.append(f"| {t} | {len(cases)} | {rate*100:.0f}% |")
        lines.append("")

    # 每个用例
    lines.append("## 用例详情")
    lines.append("")
    for result in suite.cases:
        icon = _STATUS_ICONS.get(result.status.value, "?")
        lines.append(f"### {icon} [{result.case_type}] {result.case_name}")
        lines.append("")
        lines.append(f"- **状态**: {result.status.value}")
        lines.append(f"- **耗时**: {result.duration_ms:.0f}ms")
        lines.append(f"- **断言**: {result.passed}/{result.total} 通过")
        lines.append("")

        if result.assertions:
            lines.append(f"| 断言 | 期望 | 实际 | |")
            lines.append(f"|------|------|------|--|")
            for a in result.assertions:
                s = "PASS" if a.verdict == Verdict.PASS else "FAIL"
                exp = _trunc(str(a.expected), 50)
                act = _trunc(str(a.actual), 50)
                lines.append(f"| {a.name} | {exp} | {act} | {s} |")
            lines.append("")

        if result.status == RunStatus.ERROR:
            lines.append("```")
            lines.append(result.error_message)
            lines.append("```")
            lines.append("")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


# ═══════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════

def _trunc(s: str, n: int) -> str:
    if len(s) <= n:
        return s
    return s[:n - 3] + "..."
