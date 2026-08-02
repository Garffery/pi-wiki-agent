# pi-wiki-agent 实验评价方案

## 项目现状

- **demo 项目**：`D:\project\wiki-demo-taskman` — 含 `.wiki/`（8 页面）、源码、git 历史、已有的 checkpoint 运行产物
- **确定性质量检查器**：`WikiQualityChecker` — 9 项检查（P0 可追溯性 5 项 + P1 新鲜度 4 项），输出结构化 `QualityReport`
- **确定性修复器**：`WikiFixer` — 非 LLM 的 rule-based 修复，可作为基线对照
- **运行时埋点**：`WorkflowRunResult`（logs / duration_ms / agent_count / phases）、progress callbacks（on_agent_start/end）
- **现有 test**：`test_dag.py` 用 `FakeAgent` mock LLM；`wiki_test.py` 用 `dry_run=True` 跳过 LLM 调用

---

## 评估框架：三层金字塔

```
        ┌──────────────┐
        │  Layer 3     │  ← 人工抽检（1% 样本，月度校准）
        │  人工评审     │
       ┌┴──────────────┴┐
       │  Layer 2       │  ← LLM-as-Judge（10% 采样，每轮必跑）
       │  内容质量评分   │
      ┌┴────────────────┴┐
      │  Layer 1          │  ← 自动化指标（100% 样本，秒级反馈）
      │  结构正确性+效率   │
      └───────────────────┘
```

---

## Layer 1：自动化指标（每次运行必采集）

### 1.1 结构正确性 — WikiQualityChecker before/after

```python
# 核心指标
baseline = checker.run_checks()          # 实验前
result   = await execute_workflow_sync(...)  # 执行同步
after    = checker.run_checks()          # 实验后

metrics = {
    "errors_before":     baseline.errors,
    "errors_after":      after.errors,
    "warnings_before":   baseline.warnings,
    "warnings_after":    after.warnings,
    "issues_fixed":      baseline.total_issues - after.total_issues,
    "fix_rate":          (baseline.total_issues - after.total_issues) / max(baseline.total_issues, 1),

    # 按 check 类型细分
    "by_check": {
        check_name: {
            "before": count_before,
            "after":  count_after,
        }
        for check_name in ["source_link_missing", "orphan_page", ...]
    }
}
```

### 1.2 任务完成率 — SWE-bench 风格 pass@k

```python
# 定义"成功"：Plan 阶段产出的 file_tasks 中，
# 每条 task 对应的 wiki 页面在 Write 后质量检查通过

def is_successful(result: WorkflowRunResult) -> bool:
    """Write 阶段后，新增质量问题为 0"""
    before = run_quality_check()
    after  = run_quality_check()
    return after.errors == 0 and after.total_issues <= before.total_issues

# pass@k 计算（k=1,3,5）
# 同一提交重复执行 k 次，统计至少 1 次成功的比例
def pass_at_k(results_per_task: list[list[bool]], k: int) -> float:
    """每次任务有 k 个独立尝试，统计成功概率"""
    n = len(results_per_task)
    successes = sum(
        1 - math.comb(k - sum(attempts), k) / math.comb(k, k)
        if sum(attempts) > 0 else 0
        for attempts in results_per_task
    )
    return successes / n
```

### 1.3 效率指标

```python
efficiency = {
    "duration_ms":         result.duration_ms,
    "agent_count":         result.agent_count,
    "phases":              result.phases,
    "tokens_spent":        budget.spent(),           # 沙箱内 token 估算
    "cost_per_sync":       estimate_cost(tokens),    # 按模型定价估算
    "cost_per_page":       estimate_cost(tokens) / len(wiki_pages_modified),
    "checkpoint_hit_rate": sum(1 for p in phases if checkpoint_hit) / len(phases),
}
```

### 1.4 可靠性 — pass^k（连续 k 次全部成功）

```python
def pass_power_k(results_per_task: list[list[bool]], k: int) -> float:
    """每次任务 k 次尝试全部成功的比例"""
    return sum(all(attempts) for attempts in results_per_task) / len(results_per_task)
```

---

## Layer 2：LLM-as-Judge 内容质量评分

### 2.1 评分维度（5 维 Likert 1-5）

| 维度 | 权重 | 评分标准 |
|------|------|---------|
| **准确性** | 30% | wiki 内容与源码 diff 一致，无事实错误或幻觉 |
| **有据性** | 25% | 每个修改有对应的 `**source**` 引用，来源可追溯 |
| **完整性** | 20% | 覆盖了所有受影响的章节，无遗漏 |
| **连贯性** | 15% | 与原有 wiki 风格一致，过渡自然 |
| **可操作性** | 10% | 描述具体可执行，读者能据此理解变更 |

### 2.2 Judge prompt 模板

```
你是一个 wiki 文档质量评审专家。请对以下 AI 修改的 wiki 页面打分。

## 原始 wiki 内容
{original_wiki}

## 代码变更 (diff)
{diff}

## AI 修改后的 wiki 内容
{modified_wiki}

请逐维度评分（1-5 分），并给出理由：

1. 准确性 (Accuracy): 修改是否与代码 diff 一致？有无幻觉？
2. 有据性 (Groundedness): 是否保留了 **source** 引用？引用是否正确？
3. 完整性 (Completeness): 是否覆盖了 diff 影响的所有方面？
4. 连贯性 (Coherence): 修改是否与上下文风格一致？
5. 可操作性 (Actionability): 描述是否具体可执行？

按 JSON 格式输出：
{"accuracy": N, "groundedness": N, "completeness": N, "coherence": N, "actionability": N, "rationale": "..."}
```

### 2.3 实施要点

- 用**不同模型**做 Judge（如用 Claude 评估 Gemini 的输出，避免自评偏差）
- 对 10% 样本做 pairwise（旧 vs 新），跑两遍交换位置消除 position bias
- 每月抽 1% 做人工评审，计算 Cohen's kappa 校准 Judge

---

## Layer 3：人工评审（校准基准）

| 频率 | 样本量 | 目的 |
|------|--------|------|
| 月度 | 1% 输出（~5-10 页） | 校准 LLM-as-Judge 的评分偏差 |
| 季度 | 5% 输出 | 发现新的质量维度、更新评分标准 |

计算指标：
- **Cohen's kappa**：LLM Judge vs 人工评分的一致性（目标 > 0.7）
- **Bias drift**：Judge 评分系统性偏移的月度趋势

---

## 实验设计

### 实验 1：工作流范式对比（单 Agent vs DAG 并行）

| 条件 | 配置 | 重复次数 |
|------|------|---------|
| **基线** | `WikiSession.sync_from_commit`（旧版单 agent） | 10 |
| **实验** | `sync.yaml` 工作流（3 阶段 DAG） | 10 |

**测试集**：从 `wiki-demo-taskman` 的 git 历史中取 10 个代表性提交（覆盖：新增文件、修改文件、删除文件、多文件变更、纯文档变更）。

**指标**：
- pass@1, pass@3 成功率
- duration_ms 对比
- token 消耗对比
- 质量得分（Layer 1）对比

**统计检验**：Mann-Whitney U test（非正态分布），p < 0.05

### 实验 2：质量修复能力（LLM vs 确定性修复器）

| 条件 | 配置 |
|------|------|
| **基线** | `WikiFixer.fix_all()`（rule-based，无 LLM） |
| **实验** | `fix_quality.yaml` 工作流 |

**测试集**：故障注入 — 在 demo wiki 中人为引入 20 个缺陷（断链 × 5、空章节 × 5、重复章节 × 3、HTML 实体 × 4、过期内容 × 3）。

**指标**：
- 按 check 类型的修复率（precision / recall）
- 修复副作用率（修 A 时破坏了 B）

### 实验 3：模型对比

| 条件 | 模型 |
|------|------|
| A | Claude (claude-sonnet-4-6) |
| B | Gemini (gemini-2.5-pro) |
| C | GPT (gpt-4o) |

每种模型 × 10 个提交 × 5 次重复 = 150 次运行。

**指标**：综合 CLEAR 得分（Cost + Latency + Efficacy + Assurance + Reliability）。

### 实验 4：并发度消融

| 条件 | concurrency |
|------|------------|
| A | 1（完全串行） |
| B | 4 |
| C | 8（当前默认） |
| D | 16（上限） |

**指标**：延迟变化、成功率、agent 失败率。

---

## 实施步骤

### 第一步：搭建评测脚本框架

```python
# eval/harness.py — 评测主循环
class EvalHarness:
    def __init__(self, project_path: Path, model: str):
        self.project_path = project_path
        self.model = model
        self.checker = WikiQualityChecker(project_path)
        self.results: list[EvalRun] = []

    def run_single(self, commit: Commit, workflow: str, condition: str) -> EvalRun:
        """单次评测运行"""
        before = self.checker.run_checks()
        t0 = time.monotonic()
        result = await execute_workflow_sync(
            project_path=self.project_path,
            changed_files=commit.files,
            commit_message=commit.message,
            diff=commit.diff,
            revision=commit.hash,
            script=workflow,
            keep_checkpoint=False,
        )
        elapsed = time.monotonic() - t0
        after = self.checker.run_checks()
        return EvalRun(
            condition=condition,
            commit=commit.hash,
            quality_delta=QualityDelta(before, after),
            duration_ms=elapsed * 1000,
            agent_count=result.agent_count,
            logs=result.logs,
        )

    def run_batch(self, commits: list[Commit], conditions: list[str],
                  repeats: int = 5) -> pd.DataFrame:
        """批量评测，返回 DataFrame"""
        ...
```

### 第二步：构建测试集

```bash
# 从 wiki-demo-taskman 历史中提取提交
cd D:\project\wiki-demo-taskman
git log --oneline -20  # 挑选 10 个代表性提交

# 对每个提交提取：
# - files:    git diff-tree --no-commit-id --name-only -r <hash>
# - diff:     git diff <hash>^..<hash>
# - message:  git log --format=%B -n 1 <hash>
```

### 第三步：故障注入脚本

```python
# eval/fault_injection.py
def inject_faults(project_path: Path, fault_spec: list[FaultSpec]) -> list[FaultSpec]:
    """注入已知缺陷到 wiki 页面，返回注入记录供后续验证"""
    for spec in fault_spec:
        if spec.type == "broken_source_link":
            # 修改 wiki 中的 **source** 链接指向不存在的文件
            ...
        elif spec.type == "empty_section":
            # 清空 WIKI_SECTION 的正文内容
            ...
    return fault_spec

def verify_fixes(project_path: Path, injected: list[FaultSpec]) -> dict:
    """验证注入的缺陷是否被修复"""
    report = WikiQualityChecker(project_path).run_checks()
    ...
```

### 第四步：运行实验 + 生成报告

```bash
python eval/run_experiments.py \
    --project D:\project\wiki-demo-taskman \
    --model claude-sonnet-4-6 \
    --repeats 5 \
    --output eval/results/
```

输出：
- `results/exp1_sync_comparison.csv`
- `results/exp2_fix_quality.csv`
- `results/exp3_model_comparison.csv`
- `results/summary_report.md`（含统计检验、图表）

---

## 实验记录模板

每次实验记录以下信息（参考 ML 论文的 reproducibility checklist）：

```yaml
experiment:
  id: "exp1-001"
  date: "2026-08-02"
  hypothesis: "DAG 并行工作流比单 agent 串行更快且质量不降"

configuration:
  model: "claude-sonnet-4-6"
  concurrency: 8
  thinking: "medium"
  temperature: 0.0

test_set:
  source: "wiki-demo-taskman git history"
  num_commits: 10
  commit_hashes: ["abc123", "def456", ...]

results:
  condition_baseline:
    pass_at_1: 0.60 ± 0.15
    pass_at_3: 0.85 ± 0.08
    mean_duration_ms: 45000 ± 5000
    mean_tokens: 25000 ± 3000
    mean_quality_improvement: 3.2 ± 1.1
  condition_experiment:
    pass_at_1: 0.70 ± 0.12
    pass_at_3: 0.90 ± 0.06
    mean_duration_ms: 28000 ± 4000
    mean_tokens: 22000 ± 2500
    mean_quality_improvement: 3.5 ± 0.9

statistical_test:
    method: "Mann-Whitney U"
    p_value: 0.03
    significant: true
```

---

## 总结：指标体系速览

| 层级 | 指标 | 采集方式 | 频率 |
|------|------|---------|------|
| L1 | errors/warnings Δ | WikiQualityChecker | 每次运行 |
| L1 | pass@1 / pass@3 / pass^k | 多次重复 + 统计 | 每个条件 |
| L1 | duration_ms / cost | WorkflowRunResult + 模型定价 | 每次运行 |
| L1 | agent 失败率 / 重试次数 | logs | 每次运行 |
| L2 | 准确性 / 完整性 / 连贯性 (1-5) | LLM-as-Judge | 10% 采样 |
| L3 | Cohen's kappa vs LLM Judge | 人工评审 | 月度 |
| - | CLEAR 综合得分 | 加权计算 | 每个条件汇总 |
