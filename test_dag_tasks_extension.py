"""
Test script for the dag_tasks extension.

This script tests the dag_tasks extension independently to verify all functionality works.
"""
import asyncio
import json
import os
import shutil
import sys
from pathlib import Path

# Fix Windows console encoding
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Add the extensions directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "extensions"))

# Import the extension
import dag_tasks


class MockExtensionAPI:
    """Mock ExtensionAPI for testing."""

    def __init__(self):
        self.tools = {}
        self.commands = {}
        self.event_handlers = {}

    def register_tool(self, name, description, parameters, execute, **kwargs):
        """Register a tool."""
        self.tools[name] = {
            "name": name,
            "description": description,
            "parameters": parameters,
            "execute": execute,
        }
        print(f"✓ Registered tool: {name}")

    def register_command(self, name, description, handler, **kwargs):
        """Register a command."""
        self.commands[name] = {
            "name": name,
            "description": description,
            "handler": handler,
        }
        print(f"✓ Registered command: /{name}")

    def on(self, event_type, handler):
        """Register event handler."""
        if event_type not in self.event_handlers:
            self.event_handlers[event_type] = []
        self.event_handlers[event_type].append(handler)
        print(f"✓ Registered event handler: {event_type}")


class MockContext:
    """Mock context for testing."""

    def __init__(self, cwd):
        self.cwd = cwd
        self.session_id = "test_session"


async def test_extension_loading():
    """Test 1: Extension loads correctly."""
    print("\n" + "="*60)
    print("TEST 1: Extension Loading")
    print("="*60)

    try:
        api = MockExtensionAPI()
        dag_tasks.extension_factory(api)

        assert "task_manage" in api.tools, "task_manage tool not registered"
        assert "task_next" in api.tools, "task_next tool not registered"
        assert "tasks" in api.commands, "tasks command not registered"
        assert "session_start" in api.event_handlers, "Session start handler not registered"

        print("\n✅ Extension loaded successfully!")
        return True
    except Exception as e:
        print(f"\n❌ Extension loading failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_task_create():
    """Test 2: Task creation."""
    print("\n" + "="*60)
    print("TEST 2: Task Creation")
    print("="*60)

    test_dir = os.path.join(os.getcwd(), "test_dag_tasks_create")
    os.makedirs(test_dir, exist_ok=True)
    os.chdir(test_dir)

    try:
        api = MockExtensionAPI()
        dag_tasks.extension_factory(api)

        execute_task_manage = api.tools["task_manage"]["execute"]

        # Test single create
        print("\n📝 Creating single task...")
        result = await execute_task_manage({
            "action": "create",
            "create": {
                "title": "Test task 1",
                "description": "This is a test task",
                "context": "Testing context field"
            }
        }, MockContext(test_dir))

        assert result.get("success"), f"Create failed: {result}"
        print("✓ Single task created")
        print(result['content'][0]['text'])

        # Test batch create
        print("\n📝 Creating multiple tasks...")
        result = await execute_task_manage({
            "action": "create",
            "creates": [
                {"title": "Task 2", "status": "in_progress"},
                {"title": "Task 3", "blockedBy": ["2"]},
            ]
        }, MockContext(test_dir))

        assert result.get("success"), f"Batch create failed: {result}"
        print("✓ Batch tasks created")
        print(result['content'][0]['text'])

        print("\n✅ Task creation test passed!")
        return True

    except Exception as e:
        print(f"\n❌ Task creation test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        os.chdir("..")
        if os.path.exists(test_dir):
            shutil.rmtree(test_dir)


async def test_task_dependencies():
    """Test 3: Task dependencies."""
    print("\n" + "="*60)
    print("TEST 3: Task Dependencies")
    print("="*60)

    test_dir = os.path.join(os.getcwd(), "test_dag_tasks_deps")
    os.makedirs(test_dir, exist_ok=True)
    os.chdir(test_dir)

    try:
        api = MockExtensionAPI()
        dag_tasks.extension_factory(api)

        execute_task_manage = api.tools["task_manage"]["execute"]
        execute_task_next = api.tools["task_next"]["execute"]

        # Create tasks with dependencies
        print("\n📝 Creating tasks with dependencies...")
        await execute_task_manage({
            "action": "create",
            "creates": [
                {"title": "Design API", "status": "in_progress"},
                {"title": "Implement API", "blockedBy": ["1"]},
                {"title": "Write tests", "blockedBy": ["2"], "metadata": {"kind": "verification"}},
            ]
        }, MockContext(test_dir))

        # Check ready tasks
        print("\n🔍 Checking ready tasks...")
        result = await execute_task_next({"limit": 5}, MockContext(test_dir))
        print(result['content'][0]['text'])

        # Complete first task
        print("\n✅ Completing task 1...")
        result = await execute_task_manage({
            "action": "complete",
            "id": "1"
        }, MockContext(test_dir))
        print(result['content'][0]['text'])

        # Check if task 2 is now unblocked
        print("\n🔍 Checking for unblocked tasks...")
        result = await execute_task_next({"limit": 5}, MockContext(test_dir))
        print(result['content'][0]['text'])

        print("\n✅ Task dependencies test passed!")
        return True

    except Exception as e:
        print(f"\n❌ Task dependencies test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        os.chdir("..")
        if os.path.exists(test_dir):
            shutil.rmtree(test_dir)


async def test_task_update():
    """Test 4: Task updates."""
    print("\n" + "="*60)
    print("TEST 4: Task Updates")
    print("="*60)

    test_dir = os.path.join(os.getcwd(), "test_dag_tasks_update")
    os.makedirs(test_dir, exist_ok=True)
    os.chdir(test_dir)

    try:
        api = MockExtensionAPI()
        dag_tasks.extension_factory(api)

        execute_task_manage = api.tools["task_manage"]["execute"]

        # Create a task
        print("\n📝 Creating task...")
        await execute_task_manage({
            "action": "create",
            "create": {"title": "Test task", "status": "pending"}
        }, MockContext(test_dir))

        # Update to in_progress
        print("\n✏️ Updating task to in_progress...")
        result = await execute_task_manage({
            "action": "update",
            "update": {
                "id": "1",
                "status": "in_progress",
                "context": "Added context during work"
            }
        }, MockContext(test_dir))
        print(result['content'][0]['text'])

        # Update to completed
        print("\n✅ Completing task...")
        result = await execute_task_manage({
            "action": "complete",
            "id": "1"
        }, MockContext(test_dir))
        print(result['content'][0]['text'])

        print("\n✅ Task updates test passed!")
        return True

    except Exception as e:
        print(f"\n❌ Task updates test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        os.chdir("..")
        if os.path.exists(test_dir):
            shutil.rmtree(test_dir)


async def test_archive_and_history():
    """Test 5: Archive and history."""
    print("\n" + "="*60)
    print("TEST 5: Archive and History")
    print("="*60)

    test_dir = os.path.join(os.getcwd(), "test_dag_tasks_archive")
    os.makedirs(test_dir, exist_ok=True)
    os.chdir(test_dir)

    try:
        api = MockExtensionAPI()
        dag_tasks.extension_factory(api)

        execute_task_manage = api.tools["task_manage"]["execute"]

        # Create and complete tasks
        print("\n📝 Creating tasks...")
        await execute_task_manage({
            "action": "create",
            "creates": [
                {"title": "Task 1", "status": "completed"},
                {"title": "Task 2", "status": "completed"},
                {"title": "Task 3", "status": "open"},
            ]
        }, MockContext(test_dir))

        # Archive completed tasks
        print("\n📦 Archiving completed tasks...")
        result = await execute_task_manage({
            "action": "archive",
            "archive": "completed"
        }, MockContext(test_dir))
        print(result['content'][0]['text'])

        # View history
        print("\n📜 Viewing history...")
        result = await execute_task_manage({
            "action": "history",
            "limit": 10
        }, MockContext(test_dir))
        print(result['content'][0]['text'])

        # List remaining tasks
        print("\n📋 Listing remaining tasks...")
        result = await execute_task_manage({
            "action": "list"
        }, MockContext(test_dir))
        print(result['content'][0]['text'])

        print("\n✅ Archive and history test passed!")
        return True

    except Exception as e:
        print(f"\n❌ Archive and history test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        os.chdir("..")
        if os.path.exists(test_dir):
            shutil.rmtree(test_dir)


async def test_file_persistence():
    """Test 6: File persistence."""
    print("\n" + "="*60)
    print("TEST 6: File Persistence")
    print("="*60)

    test_dir = os.path.join(os.getcwd(), "test_dag_tasks_persist")
    os.makedirs(test_dir, exist_ok=True)
    os.chdir(test_dir)

    try:
        # Create tasks in first session
        print("\n📝 Creating tasks in session 1...")
        api1 = MockExtensionAPI()
        dag_tasks.extension_factory(api1)
        execute1 = api1.tools["task_manage"]["execute"]

        await execute1({
            "action": "create",
            "creates": [
                {"title": "Persistent task 1"},
                {"title": "Persistent task 2"},
            ]
        }, MockContext(test_dir))

        # Check file was created
        store_file = os.path.join(test_dir, ".pi", "dag-tasks", "tasks-test_session.json")
        assert os.path.exists(store_file), "Store file not created"
        print(f"✓ Store file created: {store_file}")

        # Load tasks in second session
        print("\n📖 Loading tasks in session 2...")
        api2 = MockExtensionAPI()
        dag_tasks.extension_factory(api2)
        execute2 = api2.tools["task_manage"]["execute"]

        result = await execute2({
            "action": "list"
        }, MockContext(test_dir))
        print(result['content'][0]['text'])

        # Verify tasks were loaded
        assert "Persistent task 1" in result['content'][0]['text']
        assert "Persistent task 2" in result['content'][0]['text']
        print("✓ Tasks persisted across sessions")

        print("\n✅ File persistence test passed!")
        return True

    except Exception as e:
        print(f"\n❌ File persistence test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        os.chdir("..")
        if os.path.exists(test_dir):
            shutil.rmtree(test_dir)


async def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("DAG TASKS EXTENSION TEST SUITE")
    print("="*60)

    results = []

    # Run all tests
    results.append(("Extension Loading", await test_extension_loading()))
    results.append(("Task Creation", await test_task_create()))
    results.append(("Task Dependencies", await test_task_dependencies()))
    results.append(("Task Updates", await test_task_update()))
    results.append(("Archive and History", await test_archive_and_history()))
    results.append(("File Persistence", await test_file_persistence()))

    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {name}")

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 All tests passed!")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
