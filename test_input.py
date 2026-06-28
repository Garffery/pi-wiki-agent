"""Simple input test to diagnose Windows terminal issues."""
import asyncio
import sys

async def test_input():
    print("Testing input functionality...")
    print("Python version:", sys.version)
    print("Platform:", sys.platform)
    print("stdin.isatty():", sys.stdin.isatty())
    print("stdout.isatty():", sys.stdout.isatty())
    print("\nPlease type something and press Enter:")

    loop = asyncio.get_event_loop()
    try:
        user_input = await loop.run_in_executor(None, input, "> ")
        print(f"You entered: {user_input}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_input())
