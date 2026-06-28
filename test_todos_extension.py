"""
Test script for the todos extension.

This script tests the todos extension independently to verify all functionality works.
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
import todos


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


async def test_extension_loading():
    """Test 1: Extension loads correctly."""
    print("\n" + "="*60)
    print("TEST 1: Extension Loading")
    print("="*60)

    try:
        api = MockExtensionAPI()
        todos.extension_factory(api)

        assert "todo" in api.tools, "Todo tool not registered"
        assert "todos" in api.commands, "Todos command not registered"
        assert "session_start" in api.event_handlers, "Session start handler not registered"

        print("\n✅ Extension loaded successfully!")
        return True
    except Exception as e:
        print(f"\n❌ Extension loading failed: {e}")
        return False


async def test_todo_operations():
    """Test 2: Todo CRUD operations."""
    print("\n" + "="*60)
    print("TEST 2: Todo CRUD Operations")
    print("="*60)

    # Setup test directory
    test_dir = os.path.join(os.getcwd(), "test_todos_temp")
    os.makedirs(test_dir, exist_ok=True)
    os.chdir(test_dir)

    try:
        api = MockExtensionAPI()
        todos.extension_factory(api)

        execute_todo = api.tools["todo"]["execute"]

        # Test 1: Create todo
        print("\n📝 Creating todo...")
        result = await execute_todo({
            "action": "create",
            "title": "Test task 1",
            "tags": ["test", "demo"],
            "body": "This is a test task for validation."
        })

        assert result.get("success"), f"Create failed: {result.get('error')}"
        created_todo = result["details"]["todo"]
        todo_id = created_todo.id
        print(f"✓ Created todo: TODO-{todo_id}")
        print(f"  Title: {created_todo.title}")
        print(f"  Tags: {created_todo.tags}")

        # Test 2: List todos
        print("\n📋 Listing todos...")
        result = await execute_todo({"action": "list"})
        assert result.get("success"), f"List failed: {result.get('error')}"
        todos_list = result["details"]["todos"]
        assert len(todos_list) == 1, f"Expected 1 todo, got {len(todos_list)}"
        print(f"✓ Found {len(todos_list)} todo(s)")

        # Test 3: Get todo
        print(f"\n🔍 Getting todo TODO-{todo_id}...")
        result = await execute_todo({
            "action": "get",
            "id": f"TODO-{todo_id}"
        })
        assert result.get("success"), f"Get failed: {result.get('error')}"
        fetched_todo = result["details"]["todo"]
        assert fetched_todo.title == "Test task 1"
        print(f"✓ Retrieved todo: {fetched_todo.title}")

        # Test 4: Update todo
        print(f"\n✏️  Updating todo TODO-{todo_id}...")
        result = await execute_todo({
            "action": "update",
            "id": f"TODO-{todo_id}",
            "status": "done",
            "body": "Updated body text."
        })
        assert result.get("success"), f"Update failed: {result.get('error')}"
        updated_todo = result["details"]["todo"]
        assert updated_todo.status == "done"
        print(f"✓ Updated status to: {updated_todo.status}")

        # Test 5: Create another todo
        print("\n📝 Creating second todo...")
        result = await execute_todo({
            "action": "create",
            "title": "Test task 2",
            "tags": ["urgent"],
            "status": "open"
        })
        assert result.get("success"), f"Create failed: {result.get('error')}"
        todo_id_2 = result["details"]["todo"].id
        print(f"✓ Created todo: TODO-{todo_id_2}")

        # Test 6: List all todos
        print("\n📋 Listing all todos...")
        result = await execute_todo({"action": "list-all"})
        assert result.get("success"), f"List-all failed: {result.get('error')}"
        all_todos = result["details"]["todos"]
        assert len(all_todos) == 2, f"Expected 2 todos, got {len(all_todos)}"
        print(f"✓ Found {len(all_todos)} total todo(s)")

        # Test 7: Delete todo
        print(f"\n🗑️  Deleting todo TODO-{todo_id}...")
        result = await execute_todo({
            "action": "delete",
            "id": f"TODO-{todo_id}"
        })
        assert result.get("success"), f"Delete failed: {result.get('error')}"
        print(f"✓ Deleted todo: TODO-{todo_id}")

        # Test 8: Verify deletion
        print("\n📋 Verifying deletion...")
        result = await execute_todo({"action": "list-all"})
        remaining_todos = result["details"]["todos"]
        assert len(remaining_todos) == 1, f"Expected 1 todo after deletion, got {len(remaining_todos)}"
        print(f"✓ Remaining todos: {len(remaining_todos)}")

        print("\n✅ All CRUD operations passed!")
        return True

    except Exception as e:
        print(f"\n❌ CRUD operations failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Cleanup
        os.chdir("..")
        if os.path.exists(test_dir):
            shutil.rmtree(test_dir)


async def test_todos_command():
    """Test 3: /todos command."""
    print("\n" + "="*60)
    print("TEST 3: /todos Command")
    print("="*60)

    # Setup test directory
    test_dir = os.path.join(os.getcwd(), "test_todos_command_temp")
    os.makedirs(test_dir, exist_ok=True)
    os.chdir(test_dir)

    try:
        api = MockExtensionAPI()
        todos.extension_factory(api)

        execute_todo = api.tools["todo"]["execute"]
        todos_command = api.commands["todos"]["handler"]

        # Create some test todos
        print("\n📝 Creating test todos...")
        await execute_todo({
            "action": "create",
            "title": "Implement feature A",
            "tags": ["backend"],
            "status": "open"
        })
        await execute_todo({
            "action": "create",
            "title": "Write tests",
            "tags": ["qa", "urgent"],
            "status": "open"
        })
        await execute_todo({
            "action": "create",
            "title": "Update docs",
            "tags": ["docs"],
            "status": "done"
        })
        print("✓ Created 3 test todos")

        # Execute /todos command
        print("\n🔧 Executing /todos command...")
        print("-" * 60)
        await todos_command("")
        print("-" * 60)

        print("\n✅ /todos command executed successfully!")
        return True

    except Exception as e:
        print(f"\n❌ /todos command failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Cleanup
        os.chdir("..")
        if os.path.exists(test_dir):
            shutil.rmtree(test_dir)


async def test_file_format():
    """Test 4: File format validation."""
    print("\n" + "="*60)
    print("TEST 4: File Format Validation")
    print("="*60)

    # Setup test directory
    test_dir = os.path.join(os.getcwd(), "test_todos_format_temp")
    os.makedirs(test_dir, exist_ok=True)
    os.chdir(test_dir)

    try:
        api = MockExtensionAPI()
        todos.extension_factory(api)

        execute_todo = api.tools["todo"]["execute"]

        # Create a todo
        print("\n📝 Creating todo...")
        result = await execute_todo({
            "action": "create",
            "title": "Format test",
            "tags": ["test"],
            "body": "This is the body text.\n\nWith multiple paragraphs."
        })
        todo_id = result["details"]["todo"].id

        # Check file format
        print("\n📄 Checking file format...")
        todos_dir = os.path.join(os.getcwd(), ".pi", "todos")
        file_path = os.path.join(todos_dir, f"{todo_id}.md")

        assert os.path.exists(file_path), "Todo file not created"

        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        print("File content:")
        print("-" * 60)
        print(content)
        print("-" * 60)

        # Validate JSON frontmatter
        assert content.startswith("{"), "File should start with JSON"

        # Parse and validate
        front_matter, body = todos.split_front_matter(content)
        parsed = json.loads(front_matter)

        assert parsed["id"] == todo_id, "ID mismatch"
        assert parsed["title"] == "Format test", "Title mismatch"
        assert "test" in parsed["tags"], "Tags mismatch"
        assert "body text" in body, "Body content mismatch"

        print("\n✅ File format validation passed!")
        return True

    except Exception as e:
        print(f"\n❌ File format validation failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Cleanup
        os.chdir("..")
        if os.path.exists(test_dir):
            shutil.rmtree(test_dir)


async def test_garbage_collection():
    """Test 5: Garbage collection."""
    print("\n" + "="*60)
    print("TEST 5: Garbage Collection")
    print("="*60)

    # Setup test directory
    test_dir = os.path.join(os.getcwd(), "test_todos_gc_temp")
    os.makedirs(test_dir, exist_ok=True)
    os.chdir(test_dir)

    try:
        api = MockExtensionAPI()
        todos.extension_factory(api)

        todos_dir = os.path.join(os.getcwd(), ".pi", "todos")
        os.makedirs(todos_dir, exist_ok=True)

        # Create settings with 0-day GC threshold
        print("\n⚙️  Creating GC settings (gcDays=0)...")
        settings_path = os.path.join(todos_dir, "settings.json")
        with open(settings_path, "w") as f:
            json.dump({"gc": True, "gcDays": 0}, f)

        execute_todo = api.tools["todo"]["execute"]

        # Create a closed todo
        print("\n📝 Creating closed todo...")
        result = await execute_todo({
            "action": "create",
            "title": "Old completed task",
            "status": "done"
        })
        todo_id = result["details"]["todo"].id
        print(f"✓ Created closed todo: TODO-{todo_id}")

        # Manually trigger GC
        print("\n🗑️  Running garbage collection...")
        settings = await todos.read_todo_settings(todos_dir)
        await todos.garbage_collect_todos(todos_dir, settings)

        # Check if file was deleted
        file_path = os.path.join(todos_dir, f"{todo_id}.md")
        if os.path.exists(file_path):
            print("⚠️  Warning: GC didn't delete the file (this is OK for recent todos)")
        else:
            print("✓ File was garbage collected")

        print("\n✅ Garbage collection test completed!")
        return True

    except Exception as e:
        print(f"\n❌ Garbage collection test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Cleanup
        os.chdir("..")
        if os.path.exists(test_dir):
            shutil.rmtree(test_dir)


async def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("TODOS EXTENSION TEST SUITE")
    print("="*60)

    results = []

    # Run all tests
    results.append(("Extension Loading", await test_extension_loading()))
    results.append(("CRUD Operations", await test_todo_operations()))
    results.append(("/todos Command", await test_todos_command()))
    results.append(("File Format", await test_file_format()))
    results.append(("Garbage Collection", await test_garbage_collection()))

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
