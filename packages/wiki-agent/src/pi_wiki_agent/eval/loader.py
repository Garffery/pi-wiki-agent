"""
测试用例加载器 — 遍历 cases/ 目录，加载 diff.txt + args.json + expected.json
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# 目录名 → 中文类型标签
_TYPE_LABELS: dict[str, str] = {
    "new_feature":      "新增功能",
    "modify_behavior":  "修改行为",
    "remove_refactor":  "删除/重构",
    "doc_only":         "纯文档 (No-op)",
    "multi_file":       "多文件混合",
    "large_diff":       "大 diff",
    "empty_wiki":       "空 wiki",
}


def discover_cases(cases_dir: Path) -> list[Path]:
    """发现 cases/ 下所有子目录，按名称排序（保证遍历顺序确定）。"""
    if not cases_dir.exists():
        return []
    dirs = [d for d in cases_dir.iterdir() if d.is_dir()]
    dirs.sort(key=lambda d: d.name)
    return dirs


def load_case(case_dir: Path) -> dict[str, Any]:
    """
    从目录加载一个测试用例。

    目录结构::

        case_01_new_feature/
        ├── diff.txt        — git diff 文本
        ├── args.json       — {changed_files, commit_message, revision}
        └── expected.json   — 预期结果

    返回::

        {
            "id":       "case_01_new_feature",
            "name":     "新增功能",
            "type":     "new_feature",
            "diff":     "...",
            "args":     {...},
            "expected": {...},
        }
    """
    case_id = case_dir.name

    diff_path     = case_dir / "diff.txt"
    args_path     = case_dir / "args.json"
    expected_path = case_dir / "expected.json"

    # 校验文件完整性
    missing = []
    for p, name in [(diff_path, "diff.txt"), (args_path, "args.json"),
                    (expected_path, "expected.json")]:
        if not p.exists():
            missing.append(name)
    if missing:
        raise FileNotFoundError(
            f"用例 '{case_id}' 缺少文件: {', '.join(missing)}"
        )

    diff     = diff_path.read_text(encoding="utf-8")
    args     = json.loads(args_path.read_text(encoding="utf-8"))
    expected = json.loads(expected_path.read_text(encoding="utf-8"))

    # 类型标签
    type_label = _infer_type(case_id)

    # 名称：优先用 expected.json 中的 name 字段
    name = expected.get("name", _TYPE_LABELS.get(type_label, case_id))

    return {
        "id":       case_id,
        "name":     name,
        "type":     type_label,
        "diff":     diff,
        "args":     args,
        "expected": expected,
    }


def _infer_type(case_id: str) -> str:
    for key in _TYPE_LABELS:
        if key in case_id:
            return key
    return "unknown"
