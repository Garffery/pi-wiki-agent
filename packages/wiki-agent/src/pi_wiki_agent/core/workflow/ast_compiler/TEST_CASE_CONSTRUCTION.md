# 测试用例构造方法

## 核心思路

sync 工作流的输入不是 git 操作，而是 3 个字符串参数：
- `changed_files` — 变更的文件列表
- `commit_message` — 提交信息
- `diff` — 完整的 git diff 文本

agent 从 `.wiki/chain/diffs/<revision>/` 目录读 per-file diff 文件。因此**不需要真实的 git commit**，直接构造 diff 文本即可模拟任何提交场景。

---

## 构造方法

### 前置准备

```bash
# 1. 确保 wiki-demo-taskman 处于稳定基线状态
cd D:\project\wiki-demo-taskman
git checkout main
git checkout HEAD -- .wiki/         # 丢弃之前的 wiki 修改
rm -rf .wiki/checkpoints .wiki/chain  # 清理运行产物

# 2. 确认反向索引覆盖哪些源文件
cat .wiki/repowiki-metadata.json | python -c "
import json, sys
idx = json.load(sys.stdin)
for entry in idx['entries']:
    print(f\"{entry['file']} → {entry['wiki_page']}#{entry['section_id']}\")
"
# 输出示例:
# src/taskman/cli.py      → api-reference.md#cli-commands
# src/taskman/models.py   → architecture.md#data-model
# src/taskman/storage.py  → configuration.md#storage-config
```

这一步确认了**哪些源文件的修改会触发 wiki 更新**。

### 测试用例的 3 个组件

每个测试用例由 3 个文件/字符串组成：

```
test_cases/
├── case_01_new_feature/
│   ├── diff.txt              ← git diff 文本
│   ├── args.json             ← {changed_files, commit_message}
│   └── expected.json         ← 预期结果
├── case_02_modify_behavior/
│   ├── diff.txt
│   ├── args.json
│   └── expected.json
├── ...
```

---

## 5 种类型的具体构造

### 类型 1：新增功能

**场景**：在 `cli.py` 中新增一个 `export` 命令。

**diff.txt**（手工编写）：
```diff
diff --git a/src/taskman/cli.py b/src/taskman/cli.py
index abc123..def456 100644
--- a/src/taskman/cli.py
+++ b/src/taskman/cli.py
@@ -45,6 +45,15 @@ def delete_task(task_id: str) -> bool:
     storage.remove(task_id)
     return True
 
+@app.command()
+def export_tasks(output: str = "tasks.json"):
+    """Export all tasks to a JSON file.
+
+    Args:
+        output: Path to the output file. Defaults to tasks.json.
+    """
+    tasks = storage.list_all()
+    with open(output, "w") as f:
+        json.dump([t.to_dict() for t in tasks], f, indent=2)
 
 if __name__ == "__main__":
     app()
```

**args.json**：
```json
{
  "changed_files": ["src/taskman/cli.py"],
  "commit_message": "feat: add export command to CLI",
  "revision": "test-case-01"
}
```

**expected.json**（人工标注的期望结果）：
```json
{
  "should_modify_pages": ["api-reference.md"],
  "should_not_modify_pages": ["architecture.md", "configuration.md", "faq.md"],
  "expected_section_changes": {
    "api-reference.md": {
      "cli-commands": {
        "action": "add_new_command",
        "command_name": "export",
        "description_includes": ["export", "output", "json"]
      }
    }
  },
  "quality_should_improve": true
}
```

**构造要点**：
- diff 添加了新函数/类 — 需要 wiki 描述这个新功能
- `changed_files` 中的文件必须在反向索引中（否则不会触发 wiki 更新）
- `expected` 标注了应该修改哪个页面的哪个章节

---

### 类型 2：修改行为

**场景**：修改 `Task.status` 字段，把 `"pending"/"done"` 改成 `"todo"/"in_progress"/"done"`。

**diff.txt**：
```diff
diff --git a/src/taskman/models.py b/src/taskman/models.py
index def456..ghi789 100644
--- a/src/taskman/models.py
+++ b/src/taskman/models.py
@@ -10,9 +10,9 @@ class TaskStatus(Enum):
-    PENDING = "pending"
+    TODO = "todo"
+    IN_PROGRESS = "in_progress"
     DONE = "done"
 
 @dataclass
 class Task:
-    status: str = TaskStatus.PENDING.value
+    status: str = TaskStatus.TODO.value
     title: str = ""
     description: str = ""
@@ -30,7 +31,9 @@ class Task:
     def to_dict(self) -> dict:
         return {
-            "status": self.status,
+            "status": self.status,
+            "title": self.title,
+            "description": self.description,
             "created_at": self.created_at.isoformat(),
         }
```

**args.json**：
```json
{
  "changed_files": ["src/taskman/models.py"],
  "commit_message": "refactor: change Task status enum and add fields to to_dict",
  "revision": "test-case-02"
}
```

**expected.json**：
```json
{
  "should_modify_pages": ["architecture.md"],
  "should_not_modify_pages": ["api-reference.md", "faq.md"],
  "expected_section_changes": {
    "architecture.md": {
      "data-model": {
        "action": "update",
        "old_content_contains": ["PENDING", "pending"],
        "new_content_contains": ["TODO", "IN_PROGRESS", "todo", "in_progress"]
      }
    }
  },
  "quality_should_improve": true
}
```

**构造要点**：
- diff 修改了枚举值和数据结构 — 需要更新 wiki 中对应的描述
- `expected` 同时检查"旧内容应该消失"和"新内容应该出现"

---

### 类型 3：删除/重构

**场景**：删除废弃的 `sync_legacy()` 函数。

**diff.txt**：
```diff
diff --git a/src/taskman/cli.py b/src/taskman/cli.py
index ghi789..jkl012 100644
--- a/src/taskman/cli.py
+++ b/src/taskman/cli.py
@@ -60,12 +60,0 @@ def export_tasks(output: str = "tasks.json"):
-
-@app.command()
-def sync_legacy():
-    """[DEPRECATED] Legacy sync command, use 'sync' instead."""
-    print("This command is deprecated. Use 'taskman sync' instead.")
-    return sync_v2()
```

**args.json**：
```json
{
  "changed_files": ["src/taskman/cli.py"],
  "commit_message": "chore: remove deprecated sync_legacy command",
  "revision": "test-case-03"
}
```

**expected.json**：
```json
{
  "should_modify_pages": ["api-reference.md"],
  "expected_section_changes": {
    "api-reference.md": {
      "cli-commands": {
        "action": "remove",
        "must_remove_text": ["sync_legacy", "DEPRECATED"]
      }
    }
  }
}
```

**构造要点**：
- 纯删除 diff — 对应 wiki 内容应被移除
- `must_remove_text` 验证删除是否彻底

---

### 类型 4：纯文档（No-op）

**场景**：只修改了 README，不影响任何源码。

**diff.txt**：
```diff
diff --git a/README.md b/README.md
index jkl012..mno345 100644
--- a/README.md
+++ b/README.md
@@ -1,5 +1,5 @@
-# TaskMan CLI
+# TaskMan CLI - A Simple Task Manager
```

**args.json**：
```json
{
  "changed_files": ["README.md"],
  "commit_message": "docs: update README title",
  "revision": "test-case-04"
}
```

**expected.json**：
```json
{
  "should_modify_pages": [],
  "should_not_modify_pages": ["api-reference.md", "architecture.md", "faq.md"],
  "plan_no_change_files_should_include": ["README.md"],
  "plan_file_tasks_should_be_empty": true,
  "quality_should_improve": false
}
```

**构造要点**：
- `README.md` 不在反向索引中 → 不应该触发任何 wiki 修改
- Plan 阶段的 `no_change_files` 应包含此文件
- 验证 agent 不会对无关变更"画蛇添足"

---

### 类型 5：多文件混合

**场景**：一次提交同时修改了 `cli.py`（新增参数）、`storage.py`（修改存储格式）。

把类型 1 和类型 2 的 diff 合并到一个 diff 中：

**diff.txt**：就是上面 type1 + type2 的两个 diff 拼接。

**args.json**：
```json
{
  "changed_files": ["src/taskman/cli.py", "src/taskman/storage.py"],
  "commit_message": "feat: add export command and update storage format",
  "revision": "test-case-05"
}
```

**expected.json**：
```json
{
  "should_modify_pages": ["api-reference.md", "configuration.md"],
  "should_not_modify_pages": ["faq.md"],
  "expected_section_changes": {
    "api-reference.md": {
      "cli-commands": {"action": "add_new_command"}
    },
    "configuration.md": {
      "storage-config": {"action": "update"}
    }
  }
}
```

---

## 两个边界用例

### 边界 1：大 diff

用一个脚本生成超过 500 行的 diff（例如在 `models.py` 中新增一个包含 50 种 TaskType 的枚举）：

```python
# 生成脚本
lines = []
for i in range(50):
    lines.append(f'    TYPE_{i:03d} = "type_{i:03d}"')
diff = f"""...\n+class TaskType(Enum):\n""" + "\n".join(lines)
```

测试：验证 agent 能否在 prompt 超长时正确处理（压缩、截断或报错）。

### 边界 2：空 wiki 项目

在一个**没有任何 `.wiki/` 目录**的项目中运行 sync：

```json
{
  "changed_files": ["src/main.py"],
  "commit_message": "feat: initial commit",
  "revision": "test-edge-02"
}
```

预期：应报清晰错误（如 "no wiki index found"），而非崩溃。

---

## 构造与验证工具

### 生成 diff 的辅助脚本

```python
# eval/make_test_cases.py

def make_diff(file_path: str, old_content: str, new_content: str) -> str:
    """用 Python 生成标准 git diff 格式"""
    import difflib
    diff = difflib.unified_diff(
        old_content.splitlines(keepends=True),
        new_content.splitlines(keepends=True),
        fromfile=f"a/{file_path}",
        tofile=f"b/{file_path}",
    )
    return "".join(diff)


def write_test_case(case_dir: Path, diff: str, changed_files: list[str],
                    commit_message: str, revision: str) -> dict:
    """将测试用例写入磁盘并返回 args"""
    case_dir.mkdir(parents=True, exist_ok=True)

    # 写 diff 文件
    (case_dir / "diff.txt").write_text(diff, encoding="utf-8")

    # 写每个文件的 per-file diff（模拟 monitor.write_file_diffs 的行为）
    diffs_dir = case_dir / "diffs" / revision
    diffs_dir.mkdir(parents=True, exist_ok=True)
    # 从完整 diff 中提取每个文件的 diff
    per_file = split_diff_by_file(diff)
    for fname, fdiff in per_file.items():
        safe_name = fname.replace("/", "_").replace("\\", "_")
        (diffs_dir / f"{safe_name}.diff").write_text(fdiff, encoding="utf-8")

    args = {
        "changed_files": changed_files,
        "commit_message": commit_message,
        "revision": revision,
    }
    (case_dir / "args.json").write_text(json.dumps(args, indent=2), encoding="utf-8")
    return args
```

### 注入 diff 到项目

```python
async def run_test_case(harness, project_path: Path, case_dir: Path):
    """将测试用例的 diff 注入项目目录，然后运行 sync"""
    args = json.loads((case_dir / "args.json").read_text())

    # 把 per-file diffs 复制到项目的 .wiki/chain/diffs/
    src_diffs = case_dir / "diffs" / args["revision"]
    dst_diffs = project_path / ".wiki" / "chain" / "diffs" / args["revision"]
    shutil.copytree(src_diffs, dst_diffs)

    # 运行
    return await harness.run_single(
        changed_files=args["changed_files"],
        commit_message=args["commit_message"],
        diff=(case_dir / "diff.txt").read_text(),
        revision=args["revision"],
    )
```

---

## 总结

| 测试用例 | diff 来源 | 关键验证点 |
|---------|----------|-----------|
| type1 新增功能 | 手写 diff（新增函数） | 对应 wiki 章节新增内容 |
| type2 修改行为 | 手写 diff（修改枚举+结构） | 旧内容消失，新内容出现 |
| type3 删除重构 | 手写 diff（删除函数） | 相关描述被移除 |
| type4 纯文档 | 手写 diff（改 README） | No-op，无 wiki 修改 |
| type5 多文件混合 | type1 + type2 拼接 | 多个 wiki 页面都被修改 |
| edge1 大 diff | 脚本生成 500+ 行 | 不崩溃，正确处理 |
| edge2 空 wiki | 无 .wiki 目录 | 清晰错误而非崩溃 |

所有 diff 都是**构造的字符串**，不依赖真实 git 提交。
