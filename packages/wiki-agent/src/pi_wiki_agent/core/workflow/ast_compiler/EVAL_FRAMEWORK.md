# 评测脚本框架架构

## 文件结构

```
packages/wiki-agent/
├── eval/                          # 新建评测目录
│   ├── __init__.py
│   ├── harness.py                 # 核心评测引擎
│   ├── metrics.py                 # 指标计算（pass@k, CLEAR...）
│   ├── fixtures.py                # 测试集构建 + 故障注入
│   ├── judge.py                   # LLM-as-Judge 评分
│   ├── report.py                  # 结果汇总 + 统计检验 + 图表
│   ├── run_experiments.py         # CLI 入口
│   └── configs/                   # 实验配置文件
│       ├── exp1_sync.yaml
│       ├── exp2_fix.yaml
│       ├── exp3_models.yaml
│       └── exp4_concurrency.yaml
```

---

## 核心模块设计

### 1. `harness.py` — 评测引擎

```python
@dataclass
class Commit:
    """测试提交"""
    hash: str
    message: str
    files: list[str]
    diff: str

@dataclass
class EvalConfig:
    """一次实验的配置"""
    name: str
    workflow_script: str        # YAML 文本 或脚本路径
    model: str | None
    concurrency: int
    repeats: int                # 每个提交重复次数
    commits: list[Commit]       # 测试提交列表
    keep_checkpoint: bool = False

@dataclass
class EvalRun:
    """单次运行的结果"""
    config_name: str
    commit_hash: str
    run_index: int              # 第几次重复
    # ── 质量 ──
    quality_before: QualityReport
    quality_after: QualityReport
    errors_fixed: int
    # ── 效率 ──
    duration_ms: float
    agent_count: int
    phases: list[str]
    # ── 任务完成 ──
    task_total: int             # Plan 阶段产出的任务数
    task_succeeded: int         # 成功完成的任务数
    # ── 日志 ──
    logs: list[str]
    # ── 元信息 ──
    timestamp: str

class EvalHarness:
    """评测主循环"""

    def __init__(self, project_path: Path, model_provider=None):
        self.project_path = project_path
        self.checker = WikiQualityChecker(project_path)
        self.model_provider = model_provider

    async def run_single(
        self, commit: Commit, workflow_script: str, **kwargs
    ) -> EvalRun:
        """
        单次评测运行：
          1. 检出 commit 代码状态
          2. 跑 quality check → before
          3. 执行 workflow → result
          4. 跑 quality check → after
          5. 组装 EvalRun
        """

    async def run_batch(
        self, config: EvalConfig, progress_callback=None
    ) -> list[EvalRun]:
        """
        批量运行：
          for commit in config.commits:
              for i in range(config.repeats):
                  run = await self.run_single(commit, ...)
                  results.append(run)
        """

    async def run_experiment(
        self, conditions: list[EvalConfig]
    ) -> dict[str, list[EvalRun]]:
        """
        多条件对比实验：
          results = {}
          for cfg in conditions:
              results[cfg.name] = await self.run_batch(cfg)
          return results
        """
```

**关键设计点**：`run_single` 需要在每次运行前**恢复项目到干净状态**——checkout 到目标 commit、清理上次运行产生的 wiki 修改和 checkpoint 文件。这是整个框架最复杂的部分。

---

### 2. `fixtures.py` — 测试集构建

```python
@dataclass
class FaultSpec:
    """注入的缺陷规格"""
    type: str           # broken_source_link / empty_section / ...
    page: str           # 目标 wiki 页面
    section: str | None # 目标章节
    params: dict        # 注入参数

class TestSetBuilder:
    """从 git 仓库构建测试集"""

    @staticmethod
    def extract_commits(repo_path: Path, count: int = 10) -> list[Commit]:
        """从 git 历史提取提交"""
        # git log --oneline -N → 取最近 N 个提交
        # git diff-tree → files
        # git diff → diff text
        ...

    @staticmethod
    def filter_representative(commits: list[Commit]) -> list[Commit]:
        """筛选代表性提交：覆盖不同变更类型"""
        # 新增文件 / 修改文件 / 删除文件 / 多文件 / 纯文档
        ...

class FaultInjector:
    """向 wiki 页面注入已知缺陷"""

    def inject(self, specs: list[FaultSpec]) -> Path:
        """
        1. 备份原始 wiki 到临时目录
        2. 按 spec 修改 wiki 文件
        3. 返回备份路径（供恢复用）
        """

    def restore(self, backup: Path):
        """恢复原始 wiki"""

    @staticmethod
    def verify(faults: list[FaultSpec], report: QualityReport) -> dict:
        """
        验证缺陷修复情况：
          {fault_id: "fixed" | "unfixed" | "partial"}
        """
```

**`extract_commits` 的具体实现**：

```python
@staticmethod
def extract_commits(repo_path: Path, count: int = 10) -> list[Commit]:
    commits = []
    # 取最近 N 个非 merge 提交
    output = subprocess.run(
        ["git", "-C", str(repo_path), "log", "--oneline",
         "--no-merges", f"-{count}"],
        capture_output=True, text=True
    ).stdout

    for line in output.strip().split("\n"):
        hash_short, *msg = line.split(" ", 1)
        message = msg[0] if msg else ""
        hash_full = subprocess.run(
            ["git", "-C", str(repo_path), "rev-parse", hash_short],
            capture_output=True, text=True
        ).stdout.strip()

        # 获取变更文件
        files = subprocess.run(
            ["git", "-C", str(repo_path), "diff-tree",
             "--no-commit-id", "--name-only", "-r", hash_full],
            capture_output=True, text=True
        ).stdout.strip().split("\n")

        # 获取完整 diff
        diff = subprocess.run(
            ["git", "-C", str(repo_path), "diff",
             f"{hash_full}^..{hash_full}"],
            capture_output=True, text=True
        ).stdout

        commits.append(Commit(
            hash=hash_full, message=message,
            files=files, diff=diff,
        ))
    return commits
```

---

### 3. `metrics.py` — 指标计算

```python
import math
import numpy as np
from dataclasses import dataclass

@dataclass
class ExperimentMetrics:
    """一个实验条件的所有指标汇总"""
    condition: str
    num_runs: int

    # ── 成功率 (SWE-bench 风格) ──
    pass_at_1: float          # 单次成功率
    pass_at_1_std: float      # 标准差
    pass_at_3: float
    pass_at_5: float
    pass_power_3: float       # 连续 3 次全部成功

    # ── 质量改进 ──
    mean_errors_fixed: float
    mean_warnings_fixed: float
    fix_rate: float           # issues_fixed / total_issues_before

    # ── 效率 ──
    mean_duration_ms: float
    mean_agent_count: float
    mean_tokens: float
    cost_per_sync_usd: float

    # ── 可靠性 ──
    agent_failure_rate: float  # agent 调用失败/异常的比例

    # ── CLEAR 综合得分 ──
    clear_score: float

# ═══════════════════════════════════════════════════════════
# pass@k 计算
# ═══════════════════════════════════════════════════════════

def pass_at_k(results: list[list[bool]], k: int) -> float:
    """
    SWE-bench 标准公式（无偏估计）

    results: 每条任务 k 次尝试的成功/失败列表
             例: [[True, False, True], [False, False, False], ...]
    """
    n = len(results)          # 任务数
    c = sum(sum(r) for r in results)  # 总成功次数
    if n - c < k:
        return 1.0
    return 1.0 - math.comb(n - c, k) / math.comb(n, k)


def pass_power_k(results: list[list[bool]], k: int) -> float:
    """连续 k 次全部成功的任务比例（可靠性）"""
    successes = sum(1 for r in results if sum(r) == k)
    return successes / len(results)


# ═══════════════════════════════════════════════════════════
# CLEAR 综合得分
# ═══════════════════════════════════════════════════════════

def clear_score(
    efficacy: float,        # 质量改进幅度 (0-1 归一化)
    cost: float,            # 每次同步成本 ($)
    latency: float,         # 延迟 (ms)
    reliability: float,     # pass^3
    assurance: float,       # 1 - 越界率
    cost_baseline: float = 0.50,   # 参考基准
    latency_baseline: float = 60000,
    w: tuple = (0.25, 0.20, 0.20, 0.20, 0.15),
) -> float:
    """归一化加权综合得分"""
    cost_norm    = min(cost_baseline / max(cost, 0.01), 1.0)
    latency_norm = min(latency_baseline / max(latency, 1), 1.0)
    return (
        w[0] * cost_norm +
        w[1] * latency_norm +
        w[2] * efficacy +
        w[3] * assurance +
        w[4] * reliability
    )


# ═══════════════════════════════════════════════════════════
# 统计检验
# ═══════════════════════════════════════════════════════════

def mann_whitney(a: list[float], b: list[float]) -> tuple[float, float]:
    """Mann-Whitney U test, 返回 (U_statistic, p_value)"""
    from scipy.stats import mannwhitneyu
    result = mannwhitneyu(a, b, alternative="two-sided")
    return result.statistic, result.pvalue


def cohens_d(a: list[float], b: list[float]) -> float:
    """效应量 Cohen's d"""
    mean_diff = np.mean(a) - np.mean(b)
    pooled_std = np.sqrt((np.std(a)**2 + np.std(b)**2) / 2)
    return mean_diff / pooled_std


def bootstrap_ci(data: list[float], n_bootstrap: int = 10000,
                 ci: float = 0.95) -> tuple[float, float]:
    """Bootstrap 置信区间"""
    means = [np.mean(np.random.choice(data, len(data), replace=True))
             for _ in range(n_bootstrap)]
    lower = np.percentile(means, (1 - ci) / 2 * 100)
    upper = np.percentile(means, (1 + ci) / 2 * 100)
    return lower, upper
```

---

### 4. `judge.py` — LLM 内容质量评分

```python
JUDGE_PROMPT = """你是 wiki 文档质量评审专家。
请对以下 AI 修改的 wiki 页面逐维度评分（1-5 分）。

## 代码变更 (diff)
{diff}

## AI 修改后的 wiki 内容
{modified}

请逐维度评分并给出理由：
1. 准确性 — 与 diff 一致？无幻觉？
2. 有据性 — **source** 引用保留且正确？
3. 完整性 — 覆盖了 diff 的所有影响？
4. 连贯性 — 与原有风格一致？
5. 可操作性 — 描述具体可执行？

返回 JSON:
{{"accuracy": N, "groundedness": N, "completeness": N,
  "coherence": N, "actionability": N, "rationale": "..."}}
"""

async def judge_wiki_page(
    diff: str, modified_wiki: str,
    judge_model: str = "claude-sonnet-4-6",
) -> dict:
    """用独立模型给一次 wiki 修改打分"""
    response = await call_llm(
        model=judge_model,
        prompt=JUDGE_PROMPT.format(diff=diff, modified=modified_wiki),
        response_format="json",
    )
    return json.loads(response)


async def judge_batch(
    runs: list[EvalRun], sample_rate: float = 0.10,
) -> list[dict]:
    """对 10% 样本做 LLM 评分"""
    sampled = random.sample(runs, int(len(runs) * sample_rate))
    scores = []
    for run in sampled:
        for page_edit in extract_page_edits(run):
            score = await judge_wiki_page(
                diff=run.commit_diff(page_edit),
                modified_wiki=page_edit.modified_content,
            )
            score["run_id"] = run.id
            scores.append(score)
    return scores
```

---

### 5. `report.py` — 结果汇总

```python
def generate_summary(
    experiment_results: dict[str, list[EvalRun]],
    llm_scores: list[dict] | None = None,
) -> str:
    """生成 Markdown 格式实验报告"""

def comparison_table(
    metrics_list: list[ExperimentMetrics],
) -> str:
    """生成条件对比表"""

def significance_heatmap(
    conditions: list[str], metrics: dict[str, list[float]],
) -> str:
    """生成显著性矩阵（ASCII heatmap）"""

def plot_latency_distribution(
    runs: dict[str, list[EvalRun]], output: Path,
):
    """延迟分布箱线图 (matplotlib)"""

def plot_radar_chart(
    metrics_list: list[ExperimentMetrics], output: Path,
):
    """CLEAR 五维雷达图"""
```

---

### 6. `run_experiments.py` — CLI 入口

```python
# 用法:
#   python -m pi_wiki_agent.eval.run_experiments \
#       --config eval/configs/exp1_sync.yaml
#
# 或编程调用:
#   result = await run_experiment("exp1_sync")

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--output", default="eval/results/")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    # 1. 加载配置
    configs = load_experiment_config(args.config)

    # 2. 初始化 harness
    harness = EvalHarness(
        project_path=Path(configs["project_path"]),
    )

    # 3. 运行实验
    if args.dry_run:
        print(f"Would run {sum(c.repeats * len(c.commits) for c in configs)} runs")
        return

    results = await harness.run_experiment(configs)

    # 4. 计算指标
    metrics_list = [compute_metrics(runs) for runs in results.values()]

    # 5. 统计检验
    pairwise_tests = []
    for a_name, b_name in itertools.combinations(results.keys(), 2):
        a, b = results[a_name], results[b_name]
        p = mann_whitney(
            [r.errors_fixed for r in a],
            [r.errors_fixed for r in b],
        )
        pairwise_tests.append((a_name, b_name, p))

    # 6. 生成报告
    report = generate_summary(results, metrics_list, pairwise_tests)
    print(report)
```

---

### 7. 实验配置示例 — `configs/exp1_sync.yaml`

```yaml
experiment:
  id: "exp1-sync-comparison"
  hypothesis: "3 阶段 DAG 并行工作流在质量不降的前提下比单 agent 串行更快"

project:
  path: "D:/project/wiki-demo-taskman"
  wiki_dir: ".wiki"
  test_commits_count: 10

conditions:
  - name: "baseline_single_agent"
    description: "旧版 WikiSession.sync_from_commit"
    mode: "legacy_session"       # 特殊模式，走 agent_session 而非 workflow
    model: "claude-sonnet-4-6"
    repeats: 5

  - name: "experiment_dag_workflow"
    description: "新版 sync.yaml DAG 工作流"
    workflow: "sync.yaml"
    model: "claude-sonnet-4-6"
    concurrency: 8
    repeats: 5

metrics:
  primary: ["pass_at_1", "errors_fixed", "duration_ms"]
  secondary: ["pass_at_3", "tokens", "agent_failure_rate"]

output:
  dir: "eval/results/exp1/"
  formats: ["csv", "json", "md"]
```

---

## 数据流总结

```
YAML 配置文件
    │
    ▼
run_experiments.py ──→ EvalHarness.run_experiment()
    │                       │
    │              ┌────────┴────────┐
    │              │  for commit:    │
    │              │    for repeat:  │
    │              │      before = quality_check()
    │              │      result = await run_workflow()
    │              │      after  = quality_check()
    │              │      → EvalRun  │
    │              └────────┬────────┘
    │                       │
    ▼                       ▼
metrics.py ◀── list[EvalRun]
    │
    ├── pass@k, pass^k
    ├── mean/std/bootstrap CI
    ├── Mann-Whitney / Cohen's d
    └── CLEAR score
    │
    ▼
report.py ──→ Markdown 报告 + CSV + PNG 图表
```
