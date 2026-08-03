"""
CLI 入口 — 遍历用例，执行测试，输出结果。

用法::

    # dry-run（内置模拟，不调 LLM）
    python -m pi_wiki_agent.eval --cases <cases_dir> --dry-run

    # 真实 LLM 运行
    python -m pi_wiki_agent.eval --cases <cases_dir> --project D:/project/wiki-demo-taskman

    # 只跑特定用例（按目录名过滤）
    python -m pi_wiki_agent.eval --cases <cases_dir> --project <path> --filter case_01
    python -m pi_wiki_agent.eval --cases <cases_dir> --filter new_feature

    # 重复执行（统计 pass@k）
    python -m pi_wiki_agent.eval --cases <cases_dir> --project <path> --repeats 3

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
        "--project", type=str, default=None,
        help="真实 LLM 模式的项目路径 (如 D:/project/wiki-demo-taskman)",
    )
    parser.add_argument(
        "--repeats", type=int, default=1,
        help="每个用例重复执行次数（默认 1）",
    )
    parser.add_argument(
        "--filter", type=str, default=None,
        help="只跑匹配的用例（按目录名过滤，如 case_01 或 new_feature）",
    )
    parser.add_argument(
        "--report", type=Path, default=None,
        help="生成 Markdown 报告的输出路径",
    )
    args = parser.parse_args()

    if args.dry_run:
        runner = TestRunner(dry_run=True)
    elif args.project:
        from .real_runner import make_runner
        runner = make_runner(args.project)
    else:
        parser.error("请指定 --dry-run 或 --project <路径>")

    # 执行
    def _progress(current: int, total: int, case_id: str):
        print(f"  [{current}/{total}] {case_id} ...", flush=True)

    suite = runner.run_all(
        cases_dir=args.cases.resolve(),
        repeats=args.repeats,
        on_progress=_progress,
        case_filter=args.filter,
    )

    # 输出
    print()
    print_header(suite)
    for case in suite.cases:
        print_case_result(case)
    print_summary(suite)

    # 报告
    if args.report:
        path = write_markdown_report(suite, args.report.resolve())
        print(f"  报告已生成: {path}")


if __name__ == "__main__":
    main()
