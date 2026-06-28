# DAG Tasks 快速入门

## 简介

DAG Tasks 是一个为 pi-coding-agent 设计的精简任务管理扩展，支持任务依赖（DAG）、持久化存储和归档系统。

## 快速开始

### 1. 创建第一个任务

```python
{
  "action": "create",
  "create": {
    "title": "实现用户登录功能",
    "description": "添加邮箱和密码登录",
    "context": "使用 JWT 认证，参考现有的注册流程"
  }
}
```

### 2. 创建带依赖的任务

```python
{
  "action": "create",
  "creates": [
    {
      "title": "设计数据库 schema",
      "status": "in_progress"
    },
    {
      "title": "编写 API 端点",
      "blockedBy": ["1"]
    },
    {
      "title": "添加单元测试",
      "blockedBy": ["2"],
      "metadata": {"kind": "verification"}
    }
  ]
}
```

### 3. 查看就绪任务

```python
{
  "action": "task_next"
}
```

或使用命令：
```
/tasks
```

### 4. 更新任务状态

开始任务：
```python
{
  "action": "update",
  "update": {
    "id": "1",
    "status": "in_progress"
  }
}
```

完成任务：
```python
{
  "action": "complete",
  "id": "1"
}
```

### 5. 批量操作

批量完成：
```python
{
  "action": "complete",
  "ids": ["1", "2", "3"]
}
```

完成并归档：
```python
{
  "action": "done_archive",
  "ids": ["1", "2"]
}
```

### 6. 归档和历史

归档所有完成的任务：
```python
{
  "action": "archive",
  "archive": "completed"
}
```

查看归档历史：
```python
{
  "action": "history",
  "limit": 20,
  "query": "登录"
}
```

## 常见场景

### 场景 1：多步骤功能开发

```python
{
  "action": "create",
  "creates": [
    {"title": "设计功能", "status": "in_progress"},
    {"title": "实现后端", "blockedBy": ["1"]},
    {"title": "实现前端", "blockedBy": ["1"]},
    {"title": "集成测试", "blockedBy": ["2", "3"], "metadata": {"kind": "verification"}},
    {"title": "更新文档", "blockedBy": ["4"]}
  ]
}
```

### 场景 2：Bug 修复流程

```python
{
  "action": "create",
  "creates": [
    {
      "title": "定位 bug 原因",
      "status": "in_progress",
      "context": "用户报告：点击提交按钮无响应"
    },
    {
      "title": "修复 bug",
      "blockedBy": ["1"]
    },
    {
      "title": "添加回归测试",
      "blockedBy": ["2"],
      "metadata": {"kind": "verification"}
    }
  ]
}
```

### 场景 3：代码审查准备

```python
{
  "action": "create",
  "creates": [
    {"title": "运行所有测试", "metadata": {"kind": "verification"}},
    {"title": "代码格式化和 lint", "metadata": {"kind": "verification"}},
    {"title": "更新 CHANGELOG"},
    {"title": "创建 Pull Request", "blockedBy": ["1", "2", "3"]}
  ]
}
```

## 任务状态流转

```
pending (待处理)
    ↓
in_progress (进行中)
    ↓
completed (已完成)
    ↓
archived (已归档)
```

## 依赖关系

- `blockedBy`: 此任务被哪些任务阻塞（必须先完成这些任务）
- `blocks`: 此任务阻塞哪些任务（完成后会解锁这些任务）

**示例**：
- 任务 2 `blockedBy: ["1"]` → 任务 1 必须先完成
- 任务 1 完成后 → 任务 2 自动解锁

## 任务上下文 (Context)

`context` 字段用于存储持久化的执行说明：

```python
{
  "title": "实现支付功能",
  "context": "使用 Stripe API。密钥在 .env 文件中。参考 /docs/payment-flow.md 的流程图。注意要处理失败重试。"
}
```

**何时使用 context**：
- 约束和需求
- 相关发现和决策
- 预期的输入/输出
- 完成定义

## 验证任务

对于测试、验证相关的任务，设置 `metadata.kind = "verification"`：

```python
{
  "title": "运行集成测试",
  "metadata": {"kind": "verification"}
}
```

这有助于系统识别验证步骤，并在所有任务完成时提醒是否已验证。

## 配置选项

编辑 `.pi/dag-tasks/dag-tasks-config.json`：

```json
{
  "task_scope": "session",           // "memory" | "session" | "project"
  "auto_archive_completed": "on_list_complete",  // "never" | "on_list_complete" | "on_task_complete"
  "animate_active_tasks": false
}
```

**task_scope**：
- `memory` - 不持久化（仅内存）
- `session` - 按会话持久化（默认）
- `project` - 项目级别持久化

## 环境变量

设置 `PI_DAG_TASKS` 覆盖存储位置：

```bash
# 内存模式
export PI_DAG_TASKS=off

# 自定义文件名
export PI_DAG_TASKS=my-tasks

# 绝对路径
export PI_DAG_TASKS=/path/to/tasks.json

# 相对路径
export PI_DAG_TASKS=./my-tasks.json
```

## 最佳实践

### ✅ 推荐

1. **早创建，保持更新**
   - 在开始工作前创建任务
   - 完成后立即标记为完成

2. **合理的任务粒度**
   - 任务应该是有意义的成果
   - 避免过于细碎（如"打开文件"）
   - 避免过于宏大（如"完成整个项目"）

3. **使用上下文**
   - 记录关键信息和决策
   - 帮助在会话压缩后恢复上下文

4. **及时归档**
   - 完成的任务应该归档
   - 保持活跃任务列表简洁

### ❌ 避免

1. 不要为简单的单步操作创建任务
2. 不要用任务标题作为依赖（使用 ID）
3. 不要批量延迟状态更新
4. 不要创建循环依赖

## 工具总览

| 工具 | 用途 | 示例 |
|------|------|------|
| `task_manage` | 创建、更新、完成、归档任务 | `{"action": "create", ...}` |
| `task_next` | 查看就绪任务 | `{"limit": 5}` |
| `/tasks` | 命令行查看任务 | `/tasks` |

## 故障排除

### 问题：任务一直被阻塞

**检查**：
```python
{
  "action": "list"
}
```

查看哪些任务阻塞了它，完成那些任务即可自动解锁。

### 问题：任务没有持久化

**检查配置**：
```bash
cat .pi/dag-tasks/dag-tasks-config.json
```

确保 `task_scope` 不是 `memory`。

### 问题：找不到归档的任务

**搜索历史**：
```python
{
  "action": "history",
  "query": "关键词",
  "includeContext": true
}
```

## 完整示例

一个完整的功能开发流程：

```python
# 1. 创建任务
{
  "action": "create",
  "creates": [
    {
      "title": "API 设计评审",
      "status": "in_progress",
      "context": "RESTful API，参考现有模式"
    },
    {
      "title": "实现 API 端点",
      "blockedBy": ["1"]
    },
    {
      "title": "前端集成",
      "blockedBy": ["2"]
    },
    {
      "title": "编写测试",
      "blockedBy": ["2", "3"],
      "metadata": {"kind": "verification"}
    },
    {
      "title": "更新文档",
      "blockedBy": ["4"]
    }
  ]
}

# 2. 完成设计评审
{
  "action": "complete",
  "id": "1"
}
# → 自动解锁任务 2

# 3. 查看就绪任务
{
  "action": "task_next"
}

# 4. 批量完成
{
  "action": "complete",
  "ids": ["2", "3", "4", "5"]
}

# 5. 归档所有完成任务
{
  "action": "archive",
  "archive": "completed"
}
```

## 更多信息

- 详细文档：`extensions/dag_tasks/README.md`
- 迁移说明：`extensions/dag_tasks/MIGRATION.md`
- 测试示例：`test_dag_tasks_extension.py`
- 原始文档：`docs/pi-dag-tasks/README.md`

---

开始使用 DAG Tasks 来管理你的开发任务吧！🚀
