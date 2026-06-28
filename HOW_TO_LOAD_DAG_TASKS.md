# 如何加载和使用 DAG Tasks 扩展

## ✅ 扩展已经就绪！

根据验证结果，`dag_tasks` 扩展已经正确安装并会自动加载。

## 📍 扩展位置

```
D:\project\pi-wiki-agent\extensions\dag_tasks\
```

## 🚀 如何加载

### 自动加载（推荐）

扩展会在 pi-coding-agent 启动时**自动加载**，无需任何额外配置！

扩展自动发现路径：
1. 全局: `~/.pi/agent/extensions/`
2. 项目本地: `<project>/.pi/extensions/`
3. **项目根目录: `<project>/extensions/`** ← 你的扩展在这里

### 手动加载（可选）

如果需要手动加载，可以使用 `-e` 参数：

```bash
pi -e extensions/dag_tasks
```

## 🔍 验证扩展是否加载

### 方法 1：运行验证脚本

```bash
.venv/Scripts/python.exe verify_dag_tasks_loading.py
```

### 方法 2：启动 pi-coding-agent 并查看

启动后，扩展加载的工具应该可用：
- `task_manage` 工具
- `task_next` 工具
- `/tasks` 命令

## 📖 使用扩展

### 1. 启动 pi-coding-agent

```bash
# 在项目根目录
pi
# 或
.venv/Scripts/pi.exe
```

### 2. 创建第一个任务

在 agent 对话中：

```
请使用 task_manage 创建一个任务：
{
  "action": "create",
  "create": {
    "title": "测试 DAG Tasks 扩展",
    "description": "验证扩展是否正常工作",
    "context": "这是第一个测试任务"
  }
}
```

### 3. 查看任务

```
请使用 task_next 查看就绪任务
```

或使用命令：

```
/tasks
```

### 4. 完成任务

```
请使用 task_manage 完成任务：
{
  "action": "complete",
  "id": "1"
}
```

## 🎯 快速示例

### 创建带依赖的任务

```
请创建以下任务：
1. "设计 API" (进行中)
2. "实现端点" (被任务1阻塞)
3. "编写测试" (被任务2阻塞)

使用 task_manage 的批量创建功能
```

Agent 会这样调用：

```json
{
  "action": "create",
  "creates": [
    {
      "title": "设计 API",
      "status": "in_progress"
    },
    {
      "title": "实现端点",
      "blockedBy": ["1"]
    },
    {
      "title": "编写测试",
      "blockedBy": ["2"],
      "metadata": {"kind": "verification"}
    }
  ]
}
```

### 查看就绪任务

```
显示当前可以开始的任务
```

### 完成并归档

```
完成所有任务并归档
```

## 🛠️ 工具说明

### task_manage

主要的任务管理工具，支持：
- `create` - 创建任务
- `update` - 更新任务
- `complete` - 完成任务
- `archive` - 归档任务
- `list` - 列出任务
- `history` - 查看历史

### task_next

查看就绪（未被阻塞）的任务。

### /tasks

命令行查看当前所有任务。

## 📁 数据存储

任务会存储在：

```
.pi/dag-tasks/
├── tasks-<session-id>.json    # 当前任务
├── archive.jsonl               # 归档历史
└── dag-tasks-config.json       # 配置文件
```

## 🔧 配置

如需修改配置，编辑 `.pi/dag-tasks/dag-tasks-config.json`：

```json
{
  "task_scope": "session",
  "auto_archive_completed": "on_list_complete",
  "animate_active_tasks": false
}
```

**配置选项**：
- `task_scope`: `"memory"` | `"session"` | `"project"`
- `auto_archive_completed`: `"never"` | `"on_list_complete"` | `"on_task_complete"`

## 📚 更多文档

- [完整 API 文档](extensions/dag_tasks/README.md)
- [快速入门指南](extensions/dag_tasks/QUICKSTART.md)
- [迁移说明](extensions/dag_tasks/MIGRATION.md)
- [扩展对比](EXTENSIONS.md)

## ❓ 常见问题

### Q: 扩展没有加载？

**A:** 运行验证脚本检查：
```bash
.venv/Scripts/python.exe verify_dag_tasks_loading.py
```

### Q: 如何确认扩展已加载？

**A:** 在 agent 中尝试使用 `/tasks` 命令或请求 agent 使用 `task_manage` 工具。

### Q: 可以同时使用 todos 和 dag_tasks 吗？

**A:** 可以！它们是独立的扩展。dag_tasks 适合复杂的项目管理，todos 适合简单的待办事项。

### Q: 任务存储在哪里？

**A:** 默认存储在 `.pi/dag-tasks/tasks-<session-id>.json`。可以通过配置更改为项目级别或内存模式。

### Q: 如何删除所有任务？

**A:** 使用 `purge` 操作或直接删除 `.pi/dag-tasks/` 目录。

## 🎉 开始使用

扩展已经准备就绪！只需启动 pi-coding-agent，就可以开始使用强大的 DAG 任务管理功能了。

---

**验证状态**: ✅ 通过  
**自动加载**: ✅ 已启用  
**就绪状态**: ✅ 可以使用
