# DAG Tasks Extension for Pi-Coding-Agent

TypeScript `pi-dag-tasks` 扩展的 Python 实现版本。

## 快速开始

扩展已安装在 `extensions/dag_tasks/` 目录，将在下次启动时自动加载。

### 验证安装

```bash
# 快速检查
.venv/Scripts/python.exe check_dag_tasks.py

# 完整测试
.venv/Scripts/python.exe test_dag_tasks_extension.py
```

### 基本使用

```python
# 创建任务
{
  "action": "create",
  "create": {
    "title": "实现功能 X",
    "context": "参考现有模式"
  }
}

# 查看就绪任务
task_next()

# 完成任务
{
  "action": "complete",
  "id": "1"
}
```

## 文档

- 📖 [完整文档](extensions/dag_tasks/README.md) - API 参考和详细说明
- 🚀 [快速入门](extensions/dag_tasks/QUICKSTART.md) - 常见场景和示例（中文）
- 📋 [迁移说明](extensions/dag_tasks/MIGRATION.md) - 转换详情和测试结果（中文）
- 📊 [总结](extensions/dag_tasks/SUMMARY.md) - 项目概览（中文）

## 核心功能

✅ **任务管理** - 创建、更新、完成、删除任务  
✅ **DAG 依赖** - 任务依赖关系和自动解锁  
✅ **持久化** - 文件存储，支持内存/会话/项目模式  
✅ **归档系统** - 历史记录和搜索  
✅ **批量操作** - 高效的批量创建和更新  
✅ **验证检测** - 自动识别测试/验证任务  

## 测试状态

✅ 所有测试通过 (6/6)
- 扩展加载
- 任务创建
- 任务依赖
- 任务更新
- 归档和历史
- 文件持久化

## 工具

- `task_manage` - 主要任务管理工具
- `task_next` - 获取就绪任务
- `/tasks` - 命令行查看任务

## 原始文档

TypeScript 原始实现文档：[docs/pi-dag-tasks/README.md](docs/pi-dag-tasks/README.md)

---

**状态**: ✅ 就绪  
**版本**: 1.0.0 (Python)  
**测试**: 通过  
