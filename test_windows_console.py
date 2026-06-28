"""Test Windows console mode setup."""
import sys
import platform

print(f"Platform: {platform.system()}")
print(f"Python version: {sys.version}")

if platform.system() == "Windows":
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32

        # Get console handles
        h_stdin = kernel32.GetStdHandle(-10)  # STD_INPUT_HANDLE
        h_stdout = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE

        print(f"stdin handle: {h_stdin}")
        print(f"stdout handle: {h_stdout}")

        # Get current console modes
        stdin_mode = ctypes.c_ulong()
        stdout_mode = ctypes.c_ulong()

        result1 = kernel32.GetConsoleMode(h_stdin, ctypes.byref(stdin_mode))
        result2 = kernel32.GetConsoleMode(h_stdout, ctypes.byref(stdout_mode))

        print(f"GetConsoleMode stdin result: {result1}, mode: {hex(stdin_mode.value)}")
        print(f"GetConsoleMode stdout result: {result2}, mode: {hex(stdout_mode.value)}")

        # Try to set virtual terminal mode
        new_stdin_mode = 0x0200  # ENABLE_VIRTUAL_TERMINAL_INPUT
        new_stdout_mode = stdout_mode.value | 0x0004 | 0x0008  # ENABLE_VIRTUAL_TERMINAL_PROCESSING | DISABLE_NEWLINE_AUTO_RETURN

        result3 = kernel32.SetConsoleMode(h_stdin, new_stdin_mode)
        result4 = kernel32.SetConsoleMode(h_stdout, new_stdout_mode)

        print(f"SetConsoleMode stdin result: {result3}")
        print(f"SetConsoleMode stdout result: {result4}")

        # Verify the modes were set
        new_mode1 = ctypes.c_ulong()
        new_mode2 = ctypes.c_ulong()
        kernel32.GetConsoleMode(h_stdin, ctypes.byref(new_mode1))
        kernel32.GetConsoleMode(h_stdout, ctypes.byref(new_mode2))

        print(f"Verified stdin mode: {hex(new_mode1.value)}")
        print(f"Verified stdout mode: {hex(new_mode2.value)}")

        print("\nConsole mode test PASSED")
    except Exception as e:
        print(f"Console mode test FAILED: {e}")
        import traceback
        traceback.print_exc()
else:
    print("Not Windows, skipping test")
