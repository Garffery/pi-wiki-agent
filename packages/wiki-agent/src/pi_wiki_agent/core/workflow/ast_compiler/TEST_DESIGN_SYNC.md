# 同步 Agent 测试设计

## 一、被测对象

`sync.yaml` 工作流，3 阶段：Analyze → Plan → Write。输入是一个 VCS 提交（changed_files + commit_message + diff），输出是 wiki 页面的修改。

## 二、测试用例设计

### 2.1 测试提交的选取原则

从 `wiki-demo-taskman` 的 git 历史中选取提交，覆盖 5 种典型变更类型：

| 类型 | 说明 | 影响范围 | 选取数量 |
|------|------|---------|---------|
| **新增功能** | 新增一个命令/模块，涉及新文件 | 需在多个 wiki 页面新增内容 | 2 |
| **修改行为** | 修改已有函数的逻辑/参数 | 需更新已有章节的描述 | 2 |
| **删除/重构** | 删除废弃代码、重命名 | 需删除/重写 wiki 中相关描述 | 2 |
| **纯文档** | 只改了 README/docstring | wiki 无影响，验证 No-op 行为 | 1 |
| **多文件混合** | 一次提交改了 3+ 文件不同类型 | 需综合协调 | 1 |

另外补 2 个边界用例：

| 边界类型 | 说明 |
|---------|------|
| **空 wiki 项目** | 一个没有任何 `.wiki/` 的新项目（应报错或跳过） |
| **大 diff 提交** | diff 超过 500 行，测试 prompt 截断和 agent 处理能力 |

> 总计每个条件 **10 个测试提交**。

### 2.2 具体提交示例（从 wiki-demo-taskman 提取）

```bash
cd D:\project\wiki-demo-taskman
git log --oneline -20
```

假设提取到以下提交（示例，实际根据 repo 情况调整）：

```
1. abc1234  feat: add export command to CLI           ← 新增功能
2. def5678  refactor: rename Task.status to Task.state ← 修改行为
3. ghi9012  fix: handle empty storage on startup       ← 修改行为
4. jkl3456  feat: add priority field to Task model     ← 新增功能
5. mno7890  chore: remove deprecated sync_legacy()     ← 删除/重构
6. pqr1234  docs: update installation guide            ← 纯文档
7. stu5678  feat: add batch-delete, update formatter   ← 多文件混合
8. vwx9012  refactor: extract Storage interface        ← 删除/重构
9. yza3456  fix: correct date format in list output    ← 修改行为
10. bcd7890  perf: optimize file I/O in storage layer  ← 修改行为
```

---

## 三、评测条件矩阵

### 3.1 实验 1-A：工作流范式对比

| 条件 ID | 配置 | 说明 |
|---------|------|------|
| `single` | `WikiSession.sync_from_commit` | 旧版单 agent 串行 |
| `workflow` | `sync.yaml` via `run_workflow` | 新版 3 阶段 DAG 工作流 |

**固定参数**：model=claude-sonnet-4-6, concurrency=8, thinking=medium, repeats=5

### 3.2 实验 1-B：并发度消融（仅 workflow 条件）

| 条件 ID | concurrency | 说明 |
|---------|------------|------|
| `wf-c1` | 1 | 完全串行 |
| `wf-c4` | 4 | |
| `wf-c8` | 8 | 当前默认 |
| `wf-c16` | 16 | 上限 |

**固定参数**：model=claude-sonnet-4-6, thinking=medium, repeats=3

### 3.3 实验 1-C：模型对比（仅 workflow 条件）

| 条件 ID | model |
|---------|-------|
| `wf-claude` | claude-sonnet-4-6 |
| `wf-gemini` | gemini-2.5-pro |
| `wf-gpt` | gpt-4o |

**固定参数**：concurrency=8, repeats=3

---

## 四、成功/失败判定标准

### 4.1 单次运行的"成功"定义

一次运行视为成功，需同时满足以下条件：

```
✅ 条件 1（完成性）：工作流 3 个阶段全部执行完毕
✅ 条件 2（无新增错误）：运行后 WikiQualityChecker.errors == 0
✅ 条件 3（无倒退）：运行后 total_issues ≤ 运行前 total_issues
✅ 条件 4（覆盖正确）：Plan 产出的 file_tasks 中，
    每条 task 对应的 wiki 页面确实存在
✅ 条件 5（标记完整）：所有 wiki 页面的 WIKI_SECTION 标记未被破坏
✅ 条件 6（来源完整）：所有 **source** 链接保留且格式正确
```

### 4.2 按提交类型的补充判定

| 提交类型 | 补充判定 |
|---------|---------|
| 纯文档 | Plan 产出的 `no_change_files` 包含该文件，`file_tasks` 为空 |
| 新增功能 | Write 后的 wiki 新增了对应章节/页面 |
| 删除/重构 | Write 后相关的旧描述已被移除或更新 |
| 多文件混合 | 每个受影响文件的 wiki 对应页面都有修改 |

### 4.3 部分成功

如果某次运行不满足全部条件但满足条件 1-3，标记为 **部分成功**。报告时区分"完全成功"和"部分成功"。

---

## 五、测试执行流程

### 5.1 单次测试运行流程

```
┌─────────────────────────────────────────┐
│ 1. 准备                                 │
│    git checkout <commit>~1   (变更前代码) │
│    git checkout <commit>     (变更后代码) │
│    git checkout <commit>~1 -- .wiki/     │
│        ↑ 保持 wiki 不变                  │
│    删除 .wiki/checkpoints/               │
│    删除 .wiki/chain/                     │
├─────────────────────────────────────────┤
│ 2. Before 测量                          │
│    report_before = WikiQualityChecker    │
│        .run_checks().to_dict()           │
│    记录 wiki 页面的快照（文件内容 hash）  │
├─────────────────────────────────────────┤
│ 3. 执行                                 │
│    result = await run_workflow(script)   │
│    记录: duration_ms, logs, phases       │
├─────────────────────────────────────────┤
│ 4. After 测量                           │
│    report_after = WikiQualityChecker     │
│        .run_checks().to_dict()           │
│    对比 wiki 页面 hash → 找出被修改的页面 │
│    提取每个被修改页面的 diff             │
├─────────────────────────────────────────┤
│ 5. 组装 EvalRun                         │
│    计算: errors_fixed, is_success, ...   │
└─────────────────────────────────────────┘
```

### 5.2 状态隔离

每次运行后需要恢复到干净状态。两种策略：

**策略 A（推荐）**：每次运行前从 git 恢复
```bash
git checkout <commit>  # 恢复到目标提交
git checkout HEAD -- .wiki/  # 丢弃 wiki 修改
rm -rf .wiki/checkpoints .wiki/chain  # 清理运行产物
```

**策略 B**：用 git worktree 创建隔离副本
```bash
git worktree add /tmp/eval-<uuid> <commit>
# 在 worktree 中执行
# 完成后删除
```

策略 A 更简单，但会丢弃中间产物。策略 B 保留全部产物但开销更大。推荐先用 A，需要保留全量日志时用 B。

---

## 六、测量指标汇总

### 6.1 单次运行指标

```python
@dataclass
class EvalRun:
    # ── 标识 ──
    condition: str          # 条件 ID
    commit_hash: str
    run_index: int          # 第几次重复 (0-based)

    # ── 质量 (Layer 1) ──
    quality_before: dict    # QualityReport 序列化
    quality_after: dict
    errors_before: int
    errors_after: int
    warnings_before: int
    warnings_after: int
    new_issues: list[str]   # 新增问题类型
    is_success: bool        # 完全成功
    is_partial: bool        # 部分成功

    # ── 任务完成 ──
    plan_tasks_count: int   # Plan 阶段产出任务数
    write_success_count: int # Write 阶段成功任务数
    write_fail_count: int

    # ── 效率 ──
    duration_ms: float
    phase_durations: dict   # {"Analyze": N, "Plan": N, "Write": N}
    agent_count: int

    # ── 页面修改 ──
    pages_modified: list[str]
    pages_untouched: list[str]

    # ── 原始数据（供 Layer 2/3 使用） ──
    logs: list[str]
    diff_per_page: dict[str, str]  # page → 修改前后 diff
```

### 6.2 跨条件汇总指标

| 指标 | 计算方式 | 含义 |
|------|---------|------|
| **pass@1** | 单次成功率 | 一次尝试内的成功率 |
| **pass@3** | 3 次中至少 1 次成功 | 重试能弥补多大差距 |
| **pass^3** | 3 次连续全部成功 | 可靠性 |
| **mean_errors_fixed** | errors_before - errors_after 的均值 | 修复了多少错误 |
| **mean_duration_ms** | 平均端到端延迟 | 速度 |
| **std_duration_ms** | 延迟标准差 | 稳定性 |
| **success_rate_by_type** | 按提交类型的成功率 | 哪种场景更难 |
| **agent_fail_rate** | agent 调用异常率 | 健壮性 |
| **page_touch_rate** | 被修改页面 / 总页面 | 修改精确度 |

### 6.3 假阳性/假阴性检查

从 log 中自动识别：
- **假阳性**：Plan 产出了 `file_tasks`，但实际 wiki 不需要修改（no_change_files 判断错误）
- **假阴性**：Plan 产出了空 `file_tasks`，但实际 wiki 需要修改（遗漏）

通过在测试中人工确认的"预期修改页面列表"来对比。

---

## 七、报告输出

### 7.1 总览表

```
实验 1-A: 工作流范式对比
模型: claude-sonnet-4-6 | 重复: 5 次 | 测试提交: 10 个

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

### 7.2 按提交类型细分

```
┌──────────────┬─────────────────────┬─────────────────────┐
│ 提交类型     │ single pass@1       │ workflow pass@1      │
├──────────────┼─────────────────────┼─────────────────────┤
│ 新增功能     │ 3/10 (30%)          │ 6/10 (60%)           │
│ 修改行为     │ 5/10 (50%)          │ 7/10 (70%)           │
│ 删除/重构    │ 4/10 (40%)          │ 5/10 (50%)           │
│ 纯文档       │ 10/10 (100%)        │ 10/10 (100%)         │
│ 多文件混合   │ 2/5 (40%)           │ 3/5 (60%)            │
└──────────────┴─────────────────────┴─────────────────────┘
```

### 7.3 失败案例分析

自动输出每次失败运行的：
- commit hash + message
- 失败条件（不满足哪个判定条件）
- 相关 log 片段（最后 20 行）
- Plan 阶段产出的 file_tasks（是否有结构性错误）

---

## 八、快速验证（Dry Run 模式）

在实际跑 LLM 之前，用 `FakeAgent` 做一遍完整流程验证：

```python
# fake agent 返回固定响应，验证 pipeline 通顺
class EchoAgent:
    async def run(self, prompt, **kwargs):
        return f"[agent output for: {prompt[:50]}...]"

# 验证：
# - compile() 不出错
# - 3 个阶段都执行了
# - _outputs 结构正确
# - checkpoint 文件正确写入
```

这一步不应该调用 LLM，纯验证管道逻辑。`test_dag.py` 已经验证了 DAG 执行器，还需要验证完整的 3 阶段串联。
