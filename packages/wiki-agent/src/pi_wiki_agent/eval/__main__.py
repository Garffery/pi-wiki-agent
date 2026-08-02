"""
CLI 入口 — 遍历用例，执行测试，输出结果。

用法::

    python -m pi_wiki_agent.eval --cases <cases_dir>

    # dry-run（内置模拟，不调 LLM）
    python -m pi_wiki_agent.eval --cases <cases_dir> --dry-run

    # 重复执行
    python -m pi_wiki_agent.eval --cases <cases_dir> --repeats 3

    # 生成 Markdown 报告
    python -m pi_wiki_agent.eval --cases <cases_dir> --report report.md
"""
from __future__ import annotations

import argparse
from pathlib import Path

from .runner import TestRunner
from .reporter import print_header, print_case_result, print_summary, write_markdown_report


def main():
    parser = argparse.ArgumentParser(
        description="pi-wiki-agent 同步 Agent 测试框架",
    )
    parser.add_argument(
        "--cases", required=True, type=Path,
        help="测试用例根目录",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="使用内置模拟 agent，不调用 LLM",
    )
    parser.add_argument(
        "--repeats", type=int, default=1,
        help="每个用例重复执行次数（默认 1）",
    )
    parser.add_argument(
        "--report", type=Path, default=None,
        help="生成 Markdown 报告的输出路径",
    )
    args = parser.parse_args()

    # 1. 创建 runner
    runner = TestRunner(dry_run=args.dry_run)

    # 2. 执行
    def _progress(current: int, total: int, case_id: str):
        print(f"  [{current}/{total}] {case_id} ...", flush=True)

    suite = runner.run_all(
        cases_dir=args.cases.resolve(),
        repeats=args.repeats,
        on_progress=_progress,
    )

    # 3. 输出
    print()
    print_header(suite)
    for case in suite.cases:
        print_case_result(case)
    print_summary(suite)

    # 4. 报告
    if args.report:
        path = write_markdown_report(suite, args.report.resolve())
        print(f"  报告已生成: {path}")


if __name__ == "__main__":
    main()
