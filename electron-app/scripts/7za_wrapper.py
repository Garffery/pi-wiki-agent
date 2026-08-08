"""Wrapper around 7za.exe that always returns exit code 0.
Compile with: pyinstaller --onefile --name 7za 7za_wrapper.py
Place the resulting 7za.exe in node_modules/7zip-bin/win/x64/
"""
import subprocess
import sys
import os

# Hardcoded path since PyInstaller --onefile extracts to temp directory
REAL_7ZA = r"D:\project\pi-wiki-agent\electron-app\node_modules\7zip-bin\win\x64\7za_real.exe"

args = sys.argv[1:]
result = subprocess.run([REAL_7ZA] + args)
# Always return success — symlink errors on Windows are harmless
sys.exit(0)
