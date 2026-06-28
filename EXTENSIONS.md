# Pi-Coding-Agent Extensions

本项目包含的扩展列表。

## 已安装的扩展

### 1. todos
**位置**: `extensions/todos.py`  
**状态**: ✅ 可用  
**描述**: 简单的待办事项管理扩展

**功能**:
- 创建、更新、删除待办事项
- 基于文件的存储（Markdown 格式）
- 标签和状态管理
- 垃圾回收机制

**工具**:
- `todo` - 待办事项管理
- `/todos` - 查看待办事项

**存储**: `.pi/todos/*.md`

---

### 2. dag_tasks ⭐ NEW
**位置**: `extensions/dag_tasks/`  
**状态**: ✅ 可用  
**描述**: DAG（有向无环图）任务管理扩展，支持任务依赖

**功能**:
- ✅ 任务创建、更新、完成、删除
- ✅ DAG 依赖系统（blockedBy/blocks）
- ✅ 自动循环检测
- ✅ 批量操作
- ✅ 归档和历史系统
- ✅ 验证任务检测
- ✅ 三种持久化模式（内存/会话/项目）

**工具**:
- `task_manage` - 主要任务管理工具
- `task_next` - 获取就绪任务
- `/tasks` - 查看任务

**存储**: 
- `.pi/dag-tasks/tasks-*.json` - 任务存储
- `.pi/dag-tasks/archive.jsonl` - 归档
- `.pi/dag-tasks/dag-tasks-config.json` - 配置

**文档**:
- [README.md](extensions/dag_tasks/README.md) - 完整文档
- [QUICKSTART.md](extensions/dag_tasks/QUICKSTART.md) - 快速入门（中文）
- [MIGRATION.md](extensions/dag_tasks/MIGRATION.md) - 迁移说明（中文）

**测试**: `test_dag_tasks_extension.py` - ✅ 全部通过 (6/6)

---

## 扩展对比

| 特性 | todos | dag_tasks |
|------|-------|-----------|
| 基本任务管理 | ✅ | ✅ |
| 任务依赖 | ❌ | ✅ |
| 批量操作 | ❌ | ✅ |
| 归档系统 | ❌ | ✅ |
| 历史搜索 | ❌ | ✅ |
| 验证检测 | ❌ | ✅ |
| 存储格式 | Markdown | JSON |
| 配置选项 | 基础 | 高级 |
| 适用场景 | 简单待办 | 复杂项目管理 |

## 选择指南

### 使用 todos 当你需要:
- 简单的待办事项列表
- Markdown 格式存储
- 轻量级管理
- 无依赖关系

### 使用 dag_tasks 当你需要:
- 任务之间有依赖关系
- 批量操作任务
- 归档和历史追踪
- 复杂的项目管理
- 验证任务检测

## 扩展加载

扩展在以下位置自动发现：

1. **全局**: `~/.pi/agent/extensions/`
2. **项目本地**: `<project>/.pi/extensions/`
3. **项目根目录**: `<project>/extensions/`

当前项目扩展位于: `D:\project\pi-wiki-agent\extensions\`

## 开发新扩展

参考现有扩展的结构：

```python
"""
Extension description
"""

def extension_factory(api):
    """Extension factory function."""
    
    # Register tools
    api.register_tool(
        name="tool_name",
        description="Tool description",
        parameters={...},
        execute=async_execute_function
    )
    
    # Register commands
    api.register_command(
        name="command_name",
        description="Command description",
        handler=async_handler
    )
    
    # Register event handlers
    api.on("session_start", on_session_start)
```

## 测试扩展

```bash
# 检查 dag_tasks
.venv/Scripts/python.exe check_dag_tasks.py

# 完整测试 dag_tasks
.venv/Scripts/python.exe test_dag_tasks_extension.py

# 检查 todos
.venv/Scripts/python.exe test_todos_extension.py
```

## 扩展文档

- **dag_tasks**: [extensions/dag_tasks/README.md](extensions/dag_tasks/README.md)
- **todos**: 内置文档在源代码中

## 更多信息

- 扩展加载器: `packages/coding-agent/src/pi_coding_agent/core/extensions/loader.py`
- 扩展类型: `packages/coding-agent/src/pi_coding_agent/core/extensions/types.py`
- 原始 TypeScript 实现: `docs/pi-dag-tasks/`

---

**当前状态**: 2 个扩展可用  
**推荐**: 使用 `dag_tasks` 进行复杂任务管理
