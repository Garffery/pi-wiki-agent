# pi-wiki-agent 实验评价完整方案

---

## 第一章：评价目标

| 问题 | 对应的实验 |
|------|-----------|
| 新版 DAG 工作流比旧版单 agent 更好吗？ | 实验 1 |
| LLM 修复比确定性修复器更好吗？ | 实验 2 |
| 哪个模型最适合这个任务？ | 实验 3 |
| 并发度多大最优？ | 实验 4 |

---

## 第二章：评价框架 — 三层金字塔

```
        ┌──────────────┐
        │  Layer 3     │  人工评审 — 月度 1% 样本，校准 Judge
        │  人工校准     │
       ┌┴──────────────┴┐
       │  Layer 2       │  LLM-as-Judge — 10% 样本，5 维 Likert 评分
       │  内容质量       │
      ┌┴────────────────┴┐
      │  Layer 1          │  自动化 — 每次运行必采集
      │  结构 + 效率      │
      └───────────────────┘
```

### Layer 1：自动化指标（每次运行必采集）

| 指标 | 采集方式 | 说明 |
|------|---------|------|
| `errors_before` / `errors_after` | `WikiQualityChecker.run_checks()` | 运行前/后的错误数 |
| `warnings_before` / `warnings_after` | 同上 | 运行前/后的警告数 |
| `errors_fixed` | `before.errors - after.errors` | 修复了多少错误 |
| `fix_rate` | `errors_fixed / max(before.errors, 1)` | 修复率 |
| `is_success` | 6 条件 AND（详见 4.1） | 单次运行是否完全成功 |
| `duration_ms` | `WorkflowRunResult.duration_ms` | 端到端延迟 |
| `agent_count` | `WorkflowRunResult.agent_count` | 调用了多少个 agent |
| `agent_fail_rate` | `logs` 中 FAILED 行数 / 总 agent 调用数 | agent 执行失败率 |

### Layer 2：LLM-as-Judge（10% 采样）

| 维度 | 权重 | 1 分 | 5 分 |
|------|------|------|------|
| 准确性 | 30% | wiki 内容与 diff 矛盾，有明显幻觉 | 完全准确，每个修改都有 diff 依据 |
| 有据性 | 25% | `**source**` 链接缺失或错误 | 所有修改有正确的 source 引用 |
| 完整性 | 20% | 遗漏了 diff 中的关键变更 | 覆盖了 diff 影响的所有方面 |
| 连贯性 | 15% | 风格混乱，与上下文格格不入 | 与原有 wiki 浑然一体 |
| 可操作性 | 10% | 描述模糊，读者无法理解 | 具体、可执行、带示例 |

Judge prompt 模板：

```
你是 wiki 文档质量评审专家。请对以下 AI 修改的 wiki 页面逐维度评分（1-5 分）。

## 代码变更 (diff)
{diff}

## AI 修改前的 wiki 内容
{original}

## AI 修改后的 wiki 内容
{modified}

请逐维度评分并给出理由：
1. 准确性 — 修改是否与 diff 一致？有无幻觉？
2. 有据性 — **source** 引用是否保留且正确？
3. 完整性 — 是否覆盖了 diff 的所有影响？
4. 连贯性 — 是否与原有风格一致？
5. 可操作性 — 描述是否具体可执行？

按 JSON 格式输出：
{"accuracy": N, "groundedness": N, "completeness": N,
 "coherence": N, "actionability": N, "rationale": "..."}
```

**实施规则**：
- Judge 模型与待评估模型必须不同（例如用 Claude 评 Gemini 的输出）
- 每个样本跑两次 pairwise（交换 A/B 位置），消除 position bias
- 每月用 1% 样本做人工评审，计算 Cohen's kappa 校准

### Layer 3：人工评审（月度校准）

| 动作 | 频率 | 样本量 |
|------|------|--------|
| 校准 Judge | 月度 | 1%（~5-10 页） |
| 发现新维度 | 季度 | 5%（~25-50 页） |

计算 Cohen's kappa 评估 LLM Judge 与人工评分的一致性。目标 > 0.7。持续下降时需要调整 Judge prompt。

---

## 第三章：测试用例构造

### 3.1 核心原理

sync 工作流的输入不是 git 操作，而是 3 个字符串参数：

```python
result = await execute_workflow_sync(
    project_path=...,
    changed_files=["src/taskman/cli.py"],
    commit_message="feat: add export command",
    diff="""
diff --git a/src/taskman/cli.py b/src/taskman/cli.py
...
""",
    revision="test-001",
)
```

Agent 从 `.wiki/chain/diffs/<revision>/` 读 per-file diff。因此**不需要真实 git commit**，直接用 Python 的 `difflib.unified_diff()` 构造 diff 文本即可模拟任何提交。

### 3.2 前置准备：确认反向索引覆盖

```bash
cd D:\project\wiki-demo-taskman
python -c "
import json
idx = json.load(open('.wiki/repowiki-metadata.json'))
for e in idx['entries']:
    print(f\"{e['file']} → {e['wiki_page']}#{e['section_id']}\")
"
```

输出示例：
```
src/taskman/cli.py      → api-reference.md#cli-commands
src/taskman/models.py   → architecture.md#data-model
src/taskman/storage.py  → configuration.md#storage-config
```

**只有反向索引中的源文件修改才会触发 wiki 更新**。构造 diff 时，`changed_files` 必须包含索引中的文件。

### 3.3 测试用例目录结构

```
eval/test_cases/
├── case_01_new_feature/
│   ├── diff.txt           ← git diff 文本（手写）
│   ├── args.json          ← {changed_files, commit_message, revision}
│   └── expected.json      ← 人工标注的预期结果
├── case_02_modify_behavior/
│   └── ...
├── ...
├── case_06_multi_file/
├── case_07_large_diff/
└── case_08_empty_wiki/
```

### 3.4 类型 1：新增功能

**场景**：在 `cli.py` 中新增一个 `export` 命令。

**diff.txt**：

```diff
diff --git a/src/taskman/cli.py b/src/taskman/cli.py
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

<details>
<summary><b>args.json</b></summary>

```json
{
  "changed_files": ["src/taskman/cli.py"],
  "commit_message": "feat: add export command to CLI",
  "revision": "case-01"
}
```
</details>

<details>
<summary><b>expected.json</b></summary>

```json
{
  "should_modify_pages": ["api-reference.md"],
  "should_not_modify_pages": ["architecture.md", "configuration.md"],
  "expected_section_changes": {
    "api-reference.md": {
      "cli-commands": {
        "action": "add_new_command",
        "command_name": "export",
        "must_contain": ["export", "output", "json"]
      }
    }
  },
  "quality_should_improve": true
}
```
</details>

### 3.5 类型 2：修改行为

**场景**：`Task.status` 枚举值从 `"pending"/"done"` 改为 `"todo"/"in_progress"/"done"`，同时 `to_dict()` 新增两个字段。

**diff.txt**：

```diff
diff --git a/src/taskman/models.py b/src/taskman/models.py
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

<details>
<summary><b>args.json</b></summary>

```json
{
  "changed_files": ["src/taskman/models.py"],
  "commit_message": "refactor: change Task status enum and extend to_dict",
  "revision": "case-02"
}
```
</details>

<details>
<summary><b>expected.json</b></summary>

```json
{
  "should_modify_pages": ["architecture.md"],
  "expected_section_changes": {
    "architecture.md": {
      "data-model": {
        "action": "update",
        "must_disappear": ["PENDING", "pending"],
        "must_appear": ["TODO", "IN_PROGRESS", "todo", "in_progress"]
      }
    }
  }
}
```
</details>

### 3.6 类型 3：删除/重构

**场景**：删除废弃的 `sync_legacy()` 命令。

**diff.txt**：

```diff
diff --git a/src/taskman/cli.py b/src/taskman/cli.py
--- a/src/taskman/cli.py
+++ b/src/taskman/cli.py
@@ -60,12 +60,0 @@ def export_tasks(output: str = "tasks.json"):

-@app.command()
-def sync_legacy():
-    """[DEPRECATED] Legacy sync command, use 'sync' instead."""
-    print("This command is deprecated. Use 'taskman sync' instead.")
-    return sync_v2()
```

<details>
<summary><b>args.json</b></summary>

```json
{
  "changed_files": ["src/taskman/cli.py"],
  "commit_message": "chore: remove deprecated sync_legacy command",
  "revision": "case-03"
}
```
</details>

<details>
<summary><b>expected.json</b></summary>

```json
{
  "should_modify_pages": ["api-reference.md"],
  "expected_section_changes": {
    "api-reference.md": {
      "cli-commands": {
        "action": "remove",
        "must_disappear": ["sync_legacy", "DEPRECATED"]
      }
    }
  }
}
```
</details>

### 3.7 类型 4：纯文档（No-op）

**场景**：只修改 README 标题，不涉及任何被索引的源文件。

**diff.txt**：

```diff
diff --git a/README.md b/README.md
--- a/README.md
+++ b/README.md
@@ -1,5 +1,5 @@
-# TaskMan CLI
+# TaskMan CLI - A Simple Task Manager
```

<details>
<summary><b>args.json</b></summary>

```json
{
  "changed_files": ["README.md"],
  "commit_message": "docs: update README title",
  "revision": "case-04"
}
```
</details>

<details>
<summary><b>expected.json</b></summary>

```json
{
  "should_modify_pages": [],
  "plan_no_change_files_should_include": ["README.md"],
  "plan_file_tasks_should_be_empty": true,
  "quality_should_improve": false
}
```
</details>

### 3.8 类型 5：多文件混合

**场景**：一次提交同时修改 `cli.py` 和 `storage.py`。

从类型 1 和以下 storage.py diff 拼接：

**storage.py 部分**：

```diff
diff --git a/src/taskman/storage.py b/src/taskman/storage.py
--- a/src/taskman/storage.py
+++ b/src/taskman/storage.py
@@ -20,7 +20,7 @@ class JSONStorage:
     def save(self, task: Task) -> None:
         data = self._read_all()
-        data[task.id] = {"status": task.status}
+        data[task.id] = task.to_dict()
         self._write_all(data)
```

<details>
<summary><b>args.json</b></summary>

```json
{
  "changed_files": ["src/taskman/cli.py", "src/taskman/storage.py"],
  "commit_message": "feat: add export command and update storage format",
  "revision": "case-05"
}
```
</details>

<details>
<summary><b>expected.json</b></summary>

```json
{
  "should_modify_pages": ["api-reference.md", "configuration.md"],
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
</details>

### 3.9 边界用例

**边界 1 — 大 diff**：用脚本生成 500+ 行的 diff（如在 `models.py` 新增含 50 种类型的枚举）。验证 agent 不崩溃。

**边界 2 — 空 wiki**：在无 `.wiki/` 目录的项目中运行。预期返回清晰错误信息而非崩溃。

### 3.10 测试用例构造工具

```python
# eval/make_test_cases.py

import difflib
import json
from pathlib import Path

def make_diff(file_path: str, old: str, new: str) -> str:
    """用 Python 生成标准 unified diff 格式"""
    diff = difflib.unified_diff(
        old.splitlines(keepends=True),
        new.splitlines(keepends=True),
        fromfile=f"a/{file_path}",
        tofile=f"b/{file_path}",
    )
    return "".join(diff)

def write_test_case(case_dir: Path, diff: str, args: dict,
                    expected: dict) -> Path:
    """将一个测试用例写入磁盘"""
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "diff.txt").write_text(diff, encoding="utf-8")
    (case_dir / "args.json").write_text(
        json.dumps(args, indent=2, ensure_ascii=False), encoding="utf-8")
    (case_dir / "expected.json").write_text(
        json.dumps(expected, indent=2, ensure_ascii=False), encoding="utf-8")
    return case_dir

def load_test_case(case_dir: Path) -> tuple[str, dict, dict]:
    """从磁盘加载一个测试用例"""
    diff     = (case_dir / "diff.txt").read_text(encoding="utf-8")
    args     = json.loads((case_dir / "args.json").read_text())
    expected = json.loads((case_dir / "expected.json").read_text())
    return diff, args, expected
```

---

## 第四章：实验设计

### 4.1 统一的成功判定标准

单次运行视为"完全成功"需满足**全部 6 个条件**：

```
✅ 条件 1（完成性）
   工作流 3 个阶段全部执行完毕，未抛出异常
   判定: len(result.phases) == 3

✅ 条件 2（无新增错误）
   运行后 WikiQualityChecker.errors == 0
   判定: after.errors == 0

✅ 条件 3（无倒退）
   运行后质量不差于运行前
   判定: after.total_issues <= before.total_issues

✅ 条件 4（覆盖正确）
   Plan 产出的 file_tasks 中每条 task 的 wiki_page 确实存在
   判定: all(task.wiki_page in existing_pages for task in plan.file_tasks)

✅ 条件 5（标记完整）
   所有 wiki 页面的 <!-- WIKI_SECTION:... --> 标记未被破坏
   判定: 无 duplicate_section 新增，无 section 丢失

✅ 条件 6（来源完整）
   所有 **source**:[...](file://...) 链接保留且格式正确
   判定: 无 source_link_missing 新增
```

不满足条件 1 标记为**失败**。满足条件 1 但不满足 2-6 任意一条标记为**部分成功**。全部满足标记为**完全成功**。

### 4.2 实验 1：工作流范式对比

| | 基线 | 实验 |
|------|------|------|
| 名称 | `single` | `workflow` |
| 配置 | `WikiSession.sync_from_commit` | `sync.yaml` via `run_workflow` |
| 并发 | N/A（单 agent 串行） | 8 |
| 模型 | claude-sonnet-4-6 | claude-sonnet-4-6 |
| 重复次数 | 5 | 5 |
| 测试提交数 | 8 | 8 |

**总运行次数**：2 × 5 × 8 = 80 次

**主要假设**：DAG 并行工作流在质量不降的前提下延迟更低。

**观测指标**：
- 主要：pass@1、mean_errors_fixed、mean_duration_ms
- 次要：pass@3、pass^3、agent_fail_rate

**统计方法**：
- Mann-Whitney U test 检验两组差异显著性
- Cohen's d 衡量效应量（> 0.8 为大效应）
- Bootstrap 95% CI 估计指标置信区间

**预期报告**：

```
┌────────────┬──────────┬──────────┬───────────┬──────────┬──────────┐
│ 条件       │ pass@1   │ pass^3   │ errors_fix│ duration │ agent_fail│
├────────────┼──────────┼──────────┼───────────┼──────────┼──────────┤
│ single     │ 0.60±.15 │ 0.40±.12 │  2.8±1.1  │ 45s±5s   │    8%    │
│ workflow   │ 0.70±.12 │ 0.55±.10 │  3.5±0.9  │ 28s±4s   │    3%    │
├────────────┼──────────┼──────────┼───────────┼──────────┼──────────┤
│ Δ          │  +0.10   │  +0.15   │  +0.7     │  -17s    │   -5%    │
│ p-value    │   0.03   │   0.02   │   0.12    │  <0.01   │   0.08   │
│ Cohen's d  │   0.8    │   1.1    │   0.5     │   1.9    │   0.7    │
└────────────┴──────────┴──────────┴───────────┴──────────┴──────────┘
```

按提交类型细分：

```
┌──────────────┬─────────────────────┬─────────────────────┐
│ 提交类型     │ single pass@1       │ workflow pass@1      │
├──────────────┼─────────────────────┼─────────────────────┤
│ 新增功能 (×2)│      40%            │      60%            │
│ 修改行为 (×2)│      50%            │      70%            │
│ 删除重构 (×2)│      40%            │      50%            │
│ 纯文档   (×1)│     100%            │     100%            │
│ 多文件   (×1)│      40%            │      60%            │
└──────────────┴─────────────────────┴─────────────────────┘
```

**失败案例分析**（每次失败自动输出）：
- commit hash / message
- 不满足哪个成功条件
- 相关 log 片段（最后 20 行）
- Plan 阶段产出的 file_tasks 结构

---

### 4.3 实验 2：修复能力对比

| | 基线 | 实验 |
|------|------|------|
| 名称 | `rule_fix` | `llm_fix` |
| 配置 | `WikiFixer.fix_all()`（确定性规则） | `fix_quality.yaml` via `run_workflow` |
| 模型 | 无 | claude-sonnet-4-6 |
| 重复次数 | 1（确定性） | 5 |
| 注入缺陷数 | 20 | 20 |

**总运行次数**：1 + 5 = 6 次

**缺陷注入规格**：

```
断链 (broken_source_link)   ×5  → 把 **source** 路径改为不存在的文件
空章节 (empty_section)      ×5  → 清空 WIKI_SECTION 的正文
重复章节 (duplicate_section) ×3  → 复制一个 WIKI_SECTION 标记
HTML 实体 (html_entities)   ×4  → 插入 &lt; &gt; &amp; 等
过期内容 (outdated_content)  ×3  → touch 源文件使 mtime > wiki mtime
```

**指标**：

| 指标 | 定义 |
|------|------|
| **精确率** | `(修复成功的缺陷数) / (agent 声称修复的缺陷数)` |
| **召回率** | `(修复成功的缺陷数) / (注入的总缺陷数)` |
| **副作用率** | `(修复 A 时破坏 B 的次数) / (agent 修改的页面数)` |

**预期报告**：

```
┌──────────────┬──────────┬──────────┬──────────┐
│ 缺陷类型     │ rule 修复率 │ llm 修复率 │ llm 副作用率 │
├──────────────┼──────────┼──────────┼──────────┤
│ 断链         │   0%     │  80%     │    5%    │
│ 空章节       │   0%     │  60%     │   10%    │
│ 重复章节     │   0%     │  70%     │    5%    │
│ HTML 实体    │ 100%     │  90%     │    0%    │
│ 过期内容     │   0%     │  50%     │   15%    │
├──────────────┼──────────┼──────────┼──────────┤
│ 总精确率     │  20%     │  70%     │    7%    │
│ 总召回率     │  20%     │  70%     │    -     │
└──────────────┴──────────┴──────────┴──────────┘
```

**说明**：`WikiFixer` 是 rule-based 的确定性修复器。P0 修复已实现，P1 修复大多是 stub。HTML 实体是唯一已实现的 P1 修复，因此 rule 能处理它。

---

### 4.4 实验 3：模型对比

| 条件 | 模型 |
|------|------|
| `wf-claude` | claude-sonnet-4-6 |
| `wf-gemini` | gemini-2.5-pro |
| `wf-gpt` | gpt-4o |

**固定参数**：sync.yaml workflow, concurrency=8, repeats=3, 测试提交 8 个

**总运行次数**：3 × 3 × 8 = 72 次

**指标**：CLEAR 综合得分

```
CLEAR = 0.25×Cost_norm + 0.20×Latency_norm + 0.20×Efficacy
       + 0.20×Assurance + 0.15×Reliability
```

| 维度 | 计算 |
|------|------|
| Cost_norm | `基准成本($0.50) / max(实际成本, $0.01)`，上限 1.0 |
| Latency_norm | `基准延迟(60s) / max(实际延迟, 1ms)`，上限 1.0 |
| Efficacy | `errors_fixed / max(before.errors, 1)` |
| Assurance | `1 - agent_fail_rate - 越界编辑率` |
| Reliability | `pass^3` |

**预期报告**：

```
┌──────────┬────────┬────────┬──────────┬──────────┬─────────┐
│ 模型     │ pass@1 │ errors │ duration │ cost/sync│ CLEAR   │
├──────────┼────────┼────────┼──────────┼──────────┼─────────┤
│ claude   │  0.70  │  3.5   │   28s    │  $0.35   │  0.72   │
│ gemini   │  0.55  │  2.8   │   22s    │  $0.12   │  0.68   │
│ gpt      │  0.65  │  3.2   │   35s    │  $0.45   │  0.61   │
└──────────┴────────┴────────┴──────────┴──────────┴─────────┘
```

---

### 4.5 实验 4：并发度消融

| 条件 | concurrency |
|------|------------|
| `wf-c1` | 1 |
| `wf-c4` | 4 |
| `wf-c8` | 8 |
| `wf-c16` | 16 |

**固定参数**：sync.yaml workflow, claude-sonnet-4-6, repeats=3, 测试提交 8 个

**总运行次数**：4 × 3 × 8 = 96 次

**关键问题**：
- 并发度的边际收益递减点在哪儿？
- 更高并发是否导致更高 agent 失败率（速率限制）？

**预期报告**：

```
┌──────┬──────────┬──────────┬──────────┬──────────┐
│ conc │ duration │ agent_fail│ pass@1  │ pass^3   │
├──────┼──────────┼──────────┼──────────┼──────────┤
│  1   │   52s    │    2%    │  0.65    │  0.50    │
│  4   │   35s    │    3%    │  0.68    │  0.52    │
│  8   │   28s    │    3%    │  0.70    │  0.55    │
│ 16   │   26s    │    8%    │  0.62    │  0.45    │  ← 收益递减
└──────┴──────────┴──────────┴──────────┴──────────┘
```

---

## 第五章：指标计算

### 5.1 pass@k（SWE-bench 标准，无偏估计）

```python
import math

def pass_at_k(n: int, c: int, k: int) -> float:
    """
    n: 总样本数
    c: 总成功次数（所有样本所有尝试的成功次数之和）
    k: 每个样本的尝试次数
    """
    if n - c < k:
        return 1.0
    return 1.0 - math.comb(n - c, k) / math.comb(n, k)
```

### 5.2 稳定性指标

```python
import numpy as np
from scipy import stats

def compute_metrics(runs: list[EvalRun]) -> dict:
    errors_fixed = [r.errors_before - r.errors_after for r in runs]
    durations    = [r.duration_ms for r in runs]

    # Mann-Whitney U test vs baseline
    # Cohen's d 效应量
    # Bootstrap 95% CI

    return {
        "pass_at_1":        pass_at_k(len(runs), sum(r.is_success for r in runs), 1),
        "pass_at_3":        pass_at_k(len(runs), sum(r.is_success for r in runs), 3),
        "pass_power_3":     sum(1 for g in group_by_commit(runs)
                                if all(r.is_success for r in g)) / len(groups),
        "mean_errors_fixed": np.mean(errors_fixed),
        "std_errors_fixed":  np.std(errors_fixed, ddof=1),
        "mean_duration_ms":  np.mean(durations),
        "p50_duration_ms":   np.median(durations),
        "p95_duration_ms":   np.percentile(durations, 95),
        "ci_95":             bootstrap_ci(errors_fixed),
    }
```

### 5.3 统计检验

| 场景 | 方法 | 说明 |
|------|------|------|
| 两组连续指标对比（errors/duration） | Mann-Whitney U | 不假设正态分布 |
| 效应量 | Cohen's d | > 0.5 中等，> 0.8 大 |
| 置信区间 | Bootstrap 95% CI | 10000 次重采样 |
| 显著性水平 | p < 0.05 | 多组对比用 Bonferroni 校正 |

---

## 第六章：实施计划

### 第一步：Dry Run 验证管道（不调 LLM）

```python
class FakeAgent:
    """Mock agent，返回固定响应用于管道验证"""
    async def run(self, prompt, **kwargs):
        schema = kwargs.get("schema")
        if schema:
            return {"file_tasks": [], "no_change_files": []}
        return "mock analysis result"

# 验证:
# 1. compile_workflow_yaml() 不报错
# 2. run_workflow() 3 阶段全部跑通
# 3. _outputs 结构正确
# 4. checkpoint 文件正确写入
# 5. 返回 WorkflowRunResult
```

### 第二步：搭建评测脚本

实现 `eval/` 目录下的核心模块：
- `harness.py` — `EvalHarness` 主循环
- `fixtures.py` — 测试用例构造和注入
- `metrics.py` — pass@k、CLEAR、统计检验
- `run_experiments.py` — CLI 入口

### 第三步：构造 8 个测试用例

按照第三章的方案，手写 8 组 `diff.txt` / `args.json` / `expected.json`。

### 第四步：运行实验 1

```
python -m eval.run_experiments --config eval/configs/exp1_sync.yaml
```

### 第五步：分析结果 + 迭代

根据实验 1 的结果调整参数，然后依次运行实验 2-4。

---

## 第七章：评测脚本架构

```
packages/wiki-agent/eval/
├── __init__.py
├── harness.py           # EvalHarness — 评测主循环
├── fixtures.py          # 测试用例构造 + 故障注入
├── metrics.py           # pass@k, CLEAR, 统计检验
├── judge.py             # LLM-as-Judge 评分
├── report.py            # 报告生成（Markdown + CSV + 图表）
├── run_experiments.py   # CLI 入口
├── test_cases/          # 测试用例目录
│   ├── case_01_new_feature/
│   │   ├── diff.txt
│   │   ├── args.json
│   │   └── expected.json
│   ├── case_02_modify_behavior/
│   ├── ...
│   └── case_08_empty_wiki/
└── configs/             # 实验配置 YAML
    ├── exp1_sync.yaml
    ├── exp2_fix.yaml
    ├── exp3_models.yaml
    └── exp4_concurrency.yaml
```

---

## 附录：风险与应对

| 风险 | 影响 | 应对 |
|------|------|------|
| LLM 输出不稳定，指标波动大 | 结论不可靠 | 增加 repeats（5→10）；报告 CI 而非点估计 |
| API 速率限制 | 高并发条件跑不完 | 降低 concurrency 上限；加 backoff 重试 |
| 测试用例构造偏差 | diff 不反映真实场景 | 定期从真实仓库抽取 diff 补充测试集 |
| Judge 评分漂移 | Layer 2 分数系统性偏移 | 月度人工校准；版本控制 Judge prompt |
| 成本过高 | 跑不完所有实验 | 先 Dry Run 验证；减少 repeats；用更便宜模型做预实验 |
