# AST 编译器重构设计方案

## 一、目标

将现有的**字符串拼接生成 Python 脚本**改为**使用 `ast` 模块构建 AST 树**，提升代码生成的安全性、可维护性和可扩展性。

## 二、架构分层

```
YAML 文本
  → yaml.safe_load()
  → IR 层 (dataclasses, 纯数据结构)
  → 变量解析器 (返回 ast.expr 节点)
  → AST Builder (构建完整 ast.Module)
  → ast.unparse() 生成脚本字符串
  → 交给现有 run_workflow() 执行
```

**设计决策：输出仍然是脚本字符串**

理由：
- `run_workflow()` 中的 `parse_workflow_script()` 负责 meta 提取 + 安全审计（`_DeterminismVisitor`），这是安全边界，不应绕过
- 使用 `ast.unparse()` 生成脚本 → 喂给 `run_workflow()`，保持现有沙箱完整
- 后续如果 `run_workflow()` 也需要重构，AST 方案可以直接 `compile()` 执行，无需再改编译器

## 三、IR 层设计

所有 YAML 解析后的中间表示，纯数据，与 AST 无关。

```python
# ir.py

@dataclass
class VariableDef:
    name: str
    prompt: str          # 原始模板文本，包含 ${...}

@dataclass
class SchemaField:
    name: str
    type: str            # "str", "str?", "int", "float", "bool", "[str]", "{enum: [...]}", nested dict
    optional: bool

@dataclass
class StepDef:
    agent: str           # agent 名称
    label: str | None    # 可能含 ${...}
    prompt: str | None   # 可能含 ${...}
    output_schema: dict | None  # 已编译的 JSON Schema
    id: str | None       # dag 模式用
    depends_on: list[str] | None  # dag 模式用

@dataclass  
class PhaseDef:
    title: str
    mode: Literal["serial", "parallel", "dag", "pipeline"]
    for_each: str | None  # 原始 ${...} 表达式
    steps: list[StepDef]

@dataclass
class WorkflowDef:
    name: str
    description: str
    concurrency: int
    variables: list[VariableDef]
    phases: list[PhaseDef]
```

解析函数：`parse_workflow_yaml(yaml_text: str) -> WorkflowDef`

职责：
- `yaml.safe_load()` 解析
- 校验顶层结构（必须有 name/phases，phases 非空）
- 编译 schema 简写 → JSON Schema（复用现有的 `compile_schema` 逻辑，移入 IR 层）
- 产出纯数据的 `WorkflowDef`

---

## 四、变量解析器设计

**核心变化**：不再返回拼接的 Python 代码字符串，而是返回 `ast.expr` 节点。

```python
# resolver.py

class ResolveContext:
    """变量解析上下文，记录作用域中的变量名映射"""
    prev_var: str = "_prev"       # ${previous} 对应的变量名
    item_var: str = "_item"       # ${item.xxx} 对应的变量名
    outputs_var: str = "_outputs" # ${outputs.xxx} 对应的 dict 名

def resolve_expr(raw: str, ctx: ResolveContext) -> ast.expr:
    """将 YAML 中的 ${...} 模板解析为 AST 表达式节点"""
    ...

def resolve_prompt(raw: str, ctx: ResolveContext) -> ast.expr:
    """将含 ${...} 的 prompt 文本解析为 f-string AST (ast.JoinedStr)"""
    ...
```

### 各语法 → AST 节点映射

| YAML 模板 | 生成的 AST |
|-----------|-----------|
| `${name}` | `ast.Subscript(ast.Subscript(ast.Name('args'), ast.Constant('name')))` |
| `${name.sub}` | `ast.Call(ast.Attribute(...), ...)` 链式 `.get()` |
| `${item.field}` | `ast.Call(ast.Attribute(ast.Name('_item'), 'get'), [ast.Constant('field')])` |
| `${previous}` | `ast.Name('_prev')` |
| `${outputs.Plan.X}` | 带 `isinstance` 守卫的 `.get()` 链 |
| `${join(arr, tpl)}` | `ast.Call(ast.Name('chr'), ast.Constant(10)), ast.Call(ast.Name('join'), ...)` — 生成生成器表达式 AST |
| 纯文本 | `ast.Constant("text")` |
| 混合文本+变量 | `ast.JoinedStr([...])` |

### 与旧方案的对比

**旧方案**（字符串拼接）：
```python
f"(({outputs_var}.get('{parts[0]}') or {{}}).get('{parts[1]}')"
f" if isinstance({outputs_var}.get('{parts[0]}'), dict) else [])"
```

**新方案**（AST 构建）：
```python
# 直接构建 ast.IfExp / ast.Call / ast.Subscript 节点
# 类型安全，不会出现引号/括号不匹配的 bug
```

---

## 五、AST Builder 设计

```python
# builder.py

class WorkflowASTBuilder:
    """将 WorkflowDef IR 构建为完整的 ast.Module"""
    
    def __init__(self, wf: WorkflowDef):
        self.wf = wf
        self._counter = 0  # 唯一变量名计数器
    
    def build(self) -> ast.Module:
        """构建完整 AST 模块，返回 ast.Module"""
        body = []
        body.append(self._build_meta())
        body.append(self._build_init())     # _outputs = {}, _prev = None
        body.append(self._build_checkpoint_meta())
        for phase in self.wf.phases:
            body.extend(self._build_phase(phase))
        body.extend(self._build_return())
        ast.fix_missing_locations(module)
        return ast.Module(body=body, type_ignores=[])
```

### 各 Phase 模式的 AST 构建

#### serial 模式

生成的逻辑结构：
```python
_p0_prev = checkpoint.load('Analyze') or {}
if _p0_prev.get('value') is not None:
    log('...')
    _s_result = _p0_prev['value']
else:
    _s1 = await agent(f'...', {'label': '...', 'agent': '...'})
    _s_result = _s1
    checkpoint.save('Analyze', {'value': _s_result, 'session_path': agent_session_path()})
_outputs['Analyze'] = _s_result
```

AST 构建要点：
- `ast.If` 节点表达 checkpoint 检查分支
- `ast.Await(ast.Call(ast.Name('agent'), ...))` 表达 agent 调用
- `ast.Assign` 链实现 `${previous}` 传递

#### parallel 模式

```python
_p1_results = await parallel([
    (lambda: agent(f'...', {'label': '...', 'agent': '...'})),
    (lambda: agent(f'...', {'label': '...', 'agent': '...'})),
])
```

AST 构建要点：
- `ast.Lambda` 包装每个 agent 调用
- `ast.ListComp` 表达 `for_each` 展开

#### dag 模式（最复杂）

```python
_p2_dag_tasks = []
for idx, it in enumerate(_p2_items):
    tid = it.get('id', f'task-{idx}')
    pe = _p2_prev_tasks.get(tid) or {}
    if pe.get('value') is not None:
        _p2_dag_tasks.append({'id': tid, 'fn': lambda v=pe['value']: v, ...})
    elif pe.get('session_path'):
        _p2_dag_tasks.append({...lambda with resume_from...})
    else:
        _p2_dag_tasks.append({...lambda fresh...})
_p2_seed = {tid: v['value'] for tid, v in _p2_prev_tasks.items() if v.get('value') is not None}
_p2_results_dict = await dag(_p2_dag_tasks, seed=_p2_seed)
```

AST 构建要点：
- `ast.For` + 内部 `ast.If` 三分支（cached / resume / fresh）
- 每个 lambda 需要闭包捕获 `it`（`lambda it2=it: ...`）
- `ast.DictComp` 构建 seed 字典
- 结果按原始顺序重排

#### pipeline 模式

```python
_p3_results = await pipeline(
    _p3_items,
    lambda _prev, _orig, _idx: agent(...),
    lambda _prev, _orig, _idx: agent(...),
)
```

AST 构建要点：
- `ast.Lambda` 接受 `_prev`, `_orig`, `_idx` 三个参数
- 链式调用 `pipeline(items, stage1, stage2, ...)`

### 辅助 AST 节点工厂

```python
# ast_helpers.py — 避免 builder.py 过于臃肿

def make_call(func_name: str, args: list[ast.expr], keywords: list[ast.keyword] = None) -> ast.Call:
    """构建函数调用节点: func_name(arg1, arg2, ...)"""

def make_await(call: ast.Call) -> ast.Await:
    """构建 await 表达式"""

def make_dict(keys: list[str], values: list[ast.expr]) -> ast.Dict:
    """构建字典字面量"""

def make_get(dict_expr: ast.expr, key: str, default: ast.expr = None) -> ast.expr:
    """构建 .get(key) 或 .get(key, default) 调用"""

def make_lambda(body: ast.expr, args: list[str]) -> ast.Lambda:
    """构建 lambda 表达式"""

def make_fstring(parts: list[tuple[bool, str]], ctx: ResolveContext) -> ast.JoinedStr:
    """构建 f-string 节点"""
```

---

## 六、模块结构

```
workflow/
├── ast_compiler/          # 新编译器（独立于现有代码）
│   ├── __init__.py        # 公开 compile_workflow_yaml()
│   ├── DESIGN.md          # 本设计文档
│   ├── ir.py              # IR 数据类 + parse_workflow_yaml()
│   ├── resolver.py        # 变量解析器 (→ ast.expr)
│   ├── schema.py          # schema 简写编译器 (从 compiler.py 提取)
│   ├── ast_helpers.py     # AST 节点构建辅助函数
│   └── builder.py         # AST Builder (WorkflowASTBuilder)
├── compiler.py            # [待删除] 旧字符串拼接编译器
├── workflow.py            # [保留] 运行时
├── workflow_agent.py      # [保留]
├── checkpoint.py          # [保留]
└── ...
```

---

## 七、与现有代码的关系

- **零耦合**：新模块 `ast_compiler/` 完全不 import 旧的 `compiler.py`
- **相同接口**：对外暴露 `compile_workflow_yaml(yaml_text, agent_defs=None) -> str`
- **相同输出**：生成的脚本字符串语义与旧编译器完全相同，`run_workflow()` 无需任何修改
- **删除计划**：验证通过后删除 `compiler.py`，修改 `workflow_sync.py` 的 import 路径

---

## 八、核心优势

| 维度 | 旧方案（字符串拼接） | 新方案（AST 构建） |
|------|---------------------|-------------------|
| 安全性 | 引号/括号/缩进易出错 | `ast` 模块保证语法正确 |
| 可维护性 | 嵌套模板难以阅读 | AST 节点结构清晰 |
| 可扩展性 | 新语法需手写字符串 | 组合 AST 节点即可 |
| 变量解析 | 返回字符串再嵌入 | 返回 ast.expr，类型安全 |
| 调试 | 只能看生成的文本 | 可用 `ast.dump()` 检查树 |
| 后续优化 | 无法分析 | 可在 AST 上做静态分析/优化 |

---

## 九、实现顺序

1. **`ir.py`** — 数据模型 + YAML 解析
2. **`schema.py`** — schema 简写编译器（迁移自 `compiler.py:compile_schema`）
3. **`ast_helpers.py`** — AST 节点工厂函数
4. **`resolver.py`** — 变量解析器
5. **`builder.py`** — 核心 AST Builder
6. **`__init__.py`** — 对外接口
7. **验证** — 用现有 `sync.yaml` / `fix_quality.yaml` 对比新旧输出
