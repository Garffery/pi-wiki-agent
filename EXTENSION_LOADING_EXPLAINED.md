# 项目中扩展加载的详细说明

## 📍 扩展加载位置

### 主要加载点

#### 1. **main.py** - 主入口
**文件**: `packages/coding-agent/src/pi_coding_agent/main.py`

```python
# 第 17 行：导入 load_extensions
from .core.extensions.loader import load_extensions

# 第 306 行：加载扩展系统
extensions_result = await load_extensions(ext_paths, os.getcwd(), event_bus)
print(f"拓展系统添加结果:{extensions_result}")
```

#### 2. **resource_loader.py** - 资源加载器
**文件**: `packages/coding-agent/src/pi_coding_agent/core/resource_loader.py`

```python
# 第 233 行：加载扩展
if not self._no_extensions:
    await self._load_extensions()

# 第 298-332 行：_load_extensions 方法
async def _load_extensions(self) -> None:
    """加载扩展"""
    # 从设置中获取扩展路径
    ext_paths = self._resolve_resource_paths_from_settings("extensions")
    
    # 自动发现扩展的三个位置：
    # 1. 项目本地：<cwd>/.pi/extensions/
    local_dir = os.path.join(self._cwd, ".pi", "extensions")
    ext_paths.extend(discover_extensions_in_dir(local_dir))
    
    # 2. 项目根目录：<cwd>/extensions/  ← 你的扩展在这里！
    root_dir = os.path.join(self._cwd, "extensions")
    ext_paths.extend(discover_extensions_in_dir(root_dir))
    
    # 3. 全局：~/.pi/agent/extensions/
    global_dir = os.path.join(self._agent_dir, "extensions")
    ext_paths.extend(discover_extensions_in_dir(global_dir))
    
    # 加载所有发现的扩展
    base_result = await load_extensions(ext_paths, self._cwd, event_bus)
```

#### 3. **loader.py** - 扩展加载器
**文件**: `packages/coding-agent/src/pi_coding_agent/core/extensions/loader.py`

```python
# 第 61 行：discover_extensions_in_dir - 发现扩展
def discover_extensions_in_dir(directory: str) -> list[str]:
    """在目录中发现扩展路径"""
    if not os.path.isdir(directory):
        return []
    
    paths: list[str] = []
    for entry in sorted(os.listdir(directory)):
        full = os.path.join(directory, entry)
        
        # 发现 .py 文件
        if os.path.isfile(full) and entry.endswith(".py") and not entry.startswith("_"):
            paths.append(full)
        
        # 发现目录（包）
        elif os.path.isdir(full):
            index = os.path.join(full, "__init__.py")
            if os.path.exists(index):
                paths.append(full)  # ← dag_tasks 在这里被发现！
    
    return paths

# 第 159 行：load_extensions - 加载扩展
async def load_extensions(
    paths: list[str],
    cwd: str = "",
    event_bus: Any = None,
) -> LoadExtensionsResult:
    """从路径加载扩展"""
    result = LoadExtensionsResult()
    
    for path in paths:
        resolved = os.path.abspath(path)
        factory = _load_extension_module(resolved)
        
        ext = Extension(path=path, resolved_path=resolved)
        api = ExtensionAPI(ext)
        
        # 调用 extension_factory
        ret = factory(api)
        if inspect.isawaitable(ret):
            await ret
        
        result.extensions.append(ext)
    
    return result
```

## 🔄 加载流程

```
启动 pi-coding-agent
    ↓
main.py (主入口)
    ↓
resource_loader.py (_load_extensions)
    ↓
发现扩展目录：
  1. ~/.pi/agent/extensions/          (全局)
  2. <project>/.pi/extensions/        (项目本地)
  3. <project>/extensions/            (项目根目录) ← dag_tasks 在这里
    ↓
loader.py (discover_extensions_in_dir)
    ↓
发现 extensions/dag_tasks/__init__.py
    ↓
loader.py (load_extensions)
    ↓
加载 dag_tasks.extension_factory
    ↓
调用 extension_factory(api)
    ↓
注册工具和命令：
  - task_manage 工具
  - task_next 工具
  - /tasks 命令
    ↓
扩展加载完成 ✅
```

## 📂 扩展发现规则

### 1. Python 文件扩展
```
extensions/
  └── my_extension.py    ← 直接发现
```

### 2. Python 包扩展（dag_tasks 的方式）
```
extensions/
  └── dag_tasks/
      ├── __init__.py    ← 包含 extension_factory
      ├── dag_tasks.py
      ├── store.py
      └── types.py
```

### 3. 带 manifest 的扩展
```
extensions/
  └── my_extension/
      ├── package.json   ← 包含 "pi": {"extensions": [...]}
      └── src/
          └── index.py
```

## 🎯 你的扩展位置

```
D:\project\pi-wiki-agent\extensions\dag_tasks\
  ├── __init__.py          ← 包含 extension_factory，会被自动发现
  ├── dag_tasks.py
  ├── store.py
  ├── types.py
  └── config.py
```

**发现路径**: `<project>/extensions/` (项目根目录)
**加载时机**: pi-coding-agent 启动时自动加载
**加载器**: `resource_loader.py` → `loader.py`

## 🔍 验证加载

### 方法 1：查看启动日志
```bash
pi
# 应该看到：拓展系统添加结果:...
```

### 方法 2：运行验证脚本
```bash
.venv/Scripts/python.exe verify_dag_tasks_loading.py
```

### 方法 3：在 agent 中测试
```
/tasks
```
或
```
请使用 task_manage 创建一个测试任务
```

## 🛠️ 调试加载

如果扩展没有加载，检查以下几点：

### 1. 检查文件结构
```bash
ls extensions/dag_tasks/__init__.py
# 应该存在
```

### 2. 检查 extension_factory
```python
python -c "
import sys
sys.path.insert(0, 'extensions')
import dag_tasks
print('Has extension_factory:', hasattr(dag_tasks, 'extension_factory'))
"
```

### 3. 查看加载日志
启动时应该看到扩展加载的消息。

### 4. 检查导入错误
```bash
python -c "
import sys
sys.path.insert(0, 'extensions')
try:
    import dag_tasks
    print('Import OK')
except Exception as e:
    print('Import Error:', e)
"
```

## 📝 扩展加载的关键代码位置

| 位置 | 文件 | 行号 | 说明 |
|------|------|------|------|
| 主入口 | `main.py` | 306 | `await load_extensions(...)` |
| 资源加载 | `resource_loader.py` | 298-332 | `_load_extensions()` 方法 |
| 扩展发现 | `loader.py` | 61-83 | `discover_extensions_in_dir()` |
| 扩展加载 | `loader.py` | 159-189 | `load_extensions()` |
| 扩展执行 | `loader.py` | 86-115 | `_load_extension_module()` |

## 🎉 总结

你的 `dag_tasks` 扩展：

1. ✅ 位于正确的位置：`extensions/dag_tasks/`
2. ✅ 有正确的结构：`__init__.py` 包含 `extension_factory`
3. ✅ 会被自动发现：通过 `discover_extensions_in_dir()`
4. ✅ 会被自动加载：在 `resource_loader._load_extensions()` 中
5. ✅ 已验证可用：`verify_dag_tasks_loading.py` 测试通过

**无需任何额外配置，启动 pi-coding-agent 即可使用！**

---

**关键文件**：
- 主入口：`packages/coding-agent/src/pi_coding_agent/main.py:306`
- 资源加载：`packages/coding-agent/src/pi_coding_agent/core/resource_loader.py:298-332`
- 扩展发现：`packages/coding-agent/src/pi_coding_agent/core/extensions/loader.py:61-83`
