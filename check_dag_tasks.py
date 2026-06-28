"""
Simple syntax check for dag_tasks extension
"""
import sys
import os
import io

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "extensions"))

try:
    print("Testing imports...")

    print("1. Importing types...")
    from dag_tasks import types
    print("   [OK] types imported")

    print("2. Importing store...")
    from dag_tasks import store
    print("   [OK] store imported")

    print("3. Importing config...")
    from dag_tasks import config
    print("   [OK] config imported")

    print("4. Importing dag_tasks...")
    from dag_tasks import dag_tasks
    print("   [OK] dag_tasks imported")

    print("5. Importing extension...")
    import dag_tasks
    print("   [OK] dag_tasks package imported")

    print("\n[SUCCESS] All imports successful!")
    print("\nExtension is ready to use.")

except Exception as e:
    print(f"\n[ERROR] Import failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
