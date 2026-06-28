# 扩展加载的真实流程

## 🔍 问题分析

你在 `main.py:305` 看到的 `ext_paths` 是空的，这是**正常的**！

```python
# main.py:305
ext_paths = first_pass.extensions or []  # 这里通常是空的 []
extensions_result = await load_extensions(ext_paths, os.getcwd(), event_bus)
```

这个加载只是为了获取**命令行指定的扩展**（使用 `-e` 参数）。

## ✅ 真正的扩展加载位置

扩展的**自动发现和加载**发生在 `create_agent_session()` 里面！

### 关键代码位置

#### 1. **sdk.py:116-125** - 创建 ResourceLoader
```python
packages/coding-agent/src/pi_coding_agent/core/sdk.py

第 116-125 行：
resource_loader = options.resource_loader
if not resource_loader:
    from .resource_loader import DefaultResourceLoader, DefaultResourceLoaderOptions
    loader_opts = DefaultResourceLoaderOptions(
        cwd=cwd,
        agent_dir=agent_dir,
        settings_manager=settings_manager,
    )
    resource_loader = DefaultResourceLoader(loader_opts)
    await resource_loader.reload()  # ← 这里加载扩展！
```

#### 2. **resource_loader.py:233** - reload() 方法
```python
packages/coding-agent/src/pi_coding_agent/core/resource_loader.py

第 233 行：
async def reload(self) -> None:
    # Load extensions (from package manager + additional paths)
    if not self._no_extensions:
        await self._load_extensions()  # ← 自动发现和加载扩展
```

#### 3. **resource_loader.py:308-317** - 扩展自动发现
```python
第 308-317 行：
async def _load_extensions(self) -> None:
    # 从三个位置自动发现扩展：
    
    # 1. 项目本地：<cwd>/.pi/extensions/
    local_dir = os.path.join(self._cwd, ".pi", "extensions")
    ext_paths.extend(discover_extensions_in_dir(local_dir))
    
    # 2. 项目根目录：<cwd>/extensions/  ← dag_tasks 在这里被发现！
    root_dir = os.path.join(self._cwd, "extensions")
    ext_paths.extend(discover_extensions_in_dir(root_dir))
    
    # 3. 全局：~/.pi/agent/extensions/
    global_dir = os.path.join(self._agent_dir, "extensions")
    ext_paths.extend(discover_extensions_in_dir(global_dir))
```

#### 4. **sdk.py:194-195** - 获取扩展结果
```python
第 194-195 行：
extensions_result = resource_loader.get_extensions()
print(f"拓展的结果: {extensions_result}")
```

## 📊 完整加载流程

```
启动 pi
    ↓
main.py:306 - load_extensions(ext_paths, ...)
    ├─ ext_paths = [] (命令行参数，通常为空)
    └─ 只加载通过 -e 参数指定的扩展
    ↓
main.py:373 - create_agent_session(opts)
    ↓
sdk.py:116-125 - 创建 DefaultResourceLoader
    ↓
sdk.py:125 - resource_loader.reload()
    ↓
resource_loader.py:233 - _load_extensions()
    ↓
resource_loader.py:308-317 - 自动发现扩展
    ├─ .pi/extensions/
    ├─ extensions/           ← dag_tasks 在这里被发现！
    └─ ~/.pi/agent/extensions/
    ↓
loader.py:311 - discover_extensions_in_dir()
    ├─ 发现 extensions/dag_tasks/__init__.py
    └─ 添加到 ext_paths
    ↓
loader.py:323-328 - load_extensions(ext_paths)
    ├─ 加载 dag_tasks.extension_factory
    ├─ 调用 extension_factory(api)
    └─ 注册 task_manage, task_next, /tasks
    ↓
sdk.py:194-195 - extensions_result = resource_loader.get_extensions()
    ↓
sdk.py:196-199 - 返回 CreateAgentSessionResult
    └─ extensions_result 包含所有加载的扩展
    ↓
main.py:376 - session_extensions_result = result.extensions_result
    ↓
main.py:445 - run_interactive_mode(..., extensions_result=session_extensions_result)
    ↓
扩展加载完成 ✅
```

## 🎯 关键点

### 两次加载

1. **main.py:306** - 第一次加载
   - 目的：加载命令行指定的扩展（`-e` 参数）
   - `ext_paths = first_pass.extensions or []` 通常为空
   - 这是**正常的**

2. **sdk.py:125 → resource_loader.reload()** - 第二次加载（真正的自动发现）
   - 目的：自动发现和加载所有扩展
   - 扫描 3 个目录：`.pi/extensions/`, `extensions/`, `~/.pi/agent/extensions/`
   - **dag_tasks 在这里被加载**

### 为什么有两次？

- **第一次**：获取扩展定义的命令行参数（extension flags）
- **第二次**：真正加载扩展并注册工具和命令

## 🔍 验证你的扩展是否被加载

### 方法 1：查看日志
启动 pi 时，你应该看到：
```
拓展的结果: {...}
```

### 方法 2：添加调试输出

在 `resource_loader.py:314` 添加：
```python
root_dir = os.path.join(self._cwd, "extensions")
discovered = discover_extensions_in_dir(root_dir)
print(f"从 {root_dir} 发现的扩展: {discovered}")
ext_paths.extend(discovered)
```

### 方法 3：检查扩展结果

在 `sdk.py:195` 后面，你已经有：
```python
print(f"拓展的结果: {extensions_result}")
```

这应该显示 dag_tasks 扩展。

## 📝 总结

| 位置 | 代码行 | 作用 | ext_paths |
|------|--------|------|-----------|
| main.py:306 | `load_extensions(ext_paths, ...)` | 加载 `-e` 参数指定的扩展 | 通常为空 `[]` |
| sdk.py:125 | `resource_loader.reload()` | 自动发现和加载扩展 | **dag_tasks 在这里** |
| resource_loader.py:314 | `discover_extensions_in_dir(root_dir)` | 扫描 `extensions/` 目录 | **发现 dag_tasks** |

## ✅ 你的扩展状态

- ✅ 位置正确：`extensions/dag_tasks/`
- ✅ 结构正确：有 `__init__.py` 和 `extension_factory`
- ✅ 会被发现：在 `resource_loader.reload()` 中
- ✅ 会被加载：通过 `load_extensions()` 
- ✅ 已验证：`verify_dag_tasks_loading.py` 测试通过

**main.py:305 的 ext_paths 为空是正常的！真正的扩展加载在 create_agent_session 里面。**

---

**关键加载位置**：
- 🎯 **sdk.py:125** - `await resource_loader.reload()`
- 🎯 **resource_loader.py:314** - `discover_extensions_in_dir(root_dir)`
- 🎯 **sdk.py:194** - `extensions_result = resource_loader.get_extensions()`
