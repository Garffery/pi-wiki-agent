#!/usr/bin/env python
"""
验证 DAG Tasks 扩展是否能被正确加载

运行方式：
    .venv/Scripts/python.exe verify_dag_tasks_loading.py
"""
import os
import sys
import io

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 模拟 pi-coding-agent 的加载流程
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "packages/coding-agent/src"))

from pi_coding_agent.core.extensions.loader import discover_extensions_in_dir

# 检查扩展发现
print("="*60)
print("验证 DAG Tasks 扩展加载")
print("="*60)

# 1. 检查项目扩展目录
extensions_dir = os.path.join(os.getcwd(), "extensions")
print(f"\n1. 检查扩展目录: {extensions_dir}")
print(f"   目录存在: {os.path.isdir(extensions_dir)}")

# 2. 发现扩展
print("\n2. 发现扩展...")
discovered = discover_extensions_in_dir(extensions_dir)
print(f"   发现 {len(discovered)} 个扩展:")
for ext in discovered:
    ext_name = os.path.basename(ext)
    print(f"   - {ext_name}: {ext}")

# 3. 检查 dag_tasks
dag_tasks_path = os.path.join(extensions_dir, "dag_tasks")
print(f"\n3. 检查 dag_tasks 扩展:")
print(f"   路径: {dag_tasks_path}")
print(f"   存在: {os.path.isdir(dag_tasks_path)}")
print(f"   __init__.py: {os.path.exists(os.path.join(dag_tasks_path, '__init__.py'))}")

# 4. 测试导入
print("\n4. 测试导入...")
try:
    sys.path.insert(0, extensions_dir)
    import dag_tasks
    print("   [OK] dag_tasks 导入成功")

    # 检查 extension_factory
    if hasattr(dag_tasks, 'extension_factory'):
        print("   [OK] extension_factory 函数存在")
    else:
        print("   [ERROR] extension_factory 函数不存在")

except Exception as e:
    print(f"   [ERROR] 导入失败: {e}")
    import traceback
    traceback.print_exc()

# 5. 结论
print("\n" + "="*60)
print("结论:")
print("="*60)

if discovered and any('dag_tasks' in ext for ext in discovered):
    print("[SUCCESS] dag_tasks 扩展将在 pi-coding-agent 启动时自动加载")
    print("\n使用方法:")
    print("  1. 启动 pi-coding-agent")
    print("  2. 扩展会自动加载")
    print("  3. 使用 task_manage 和 task_next 工具")
    print("  4. 使用 /tasks 命令查看任务")
else:
    print("[ERROR] dag_tasks 扩展未被发现")
    print("\n可能的解决方案:")
    print("  1. 确保 extensions/dag_tasks/__init__.py 存在")
    print("  2. 或将扩展移动到 .pi/extensions/")

print("\n" + "="*60)
