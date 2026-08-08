"""Watch for winCodeSign cache downloads and extract them manually.
Works around 7za symlink errors on Windows by using Python's py7zr.
"""

import time
import subprocess
import sys
from pathlib import Path

CACHE_DIR = Path.home() / "AppData" / "Local" / "electron-builder" / "Cache" / "winCodeSign"
SEVENZ_EXE = Path("D:/project/pi-wiki-agent/electron-app/node_modules/7zip-bin/win/x64/7za.exe")


def main():
    print(f"[cache-helper] Watching: {CACHE_DIR}")
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    seen = set()

    while True:
        try:
            for f in CACHE_DIR.glob("*.7z"):
                if f.name in seen:
                    continue
                seen.add(f.name)
                # Extract into directory named after hash (without .7z extension)
                hash_name = f.stem  # e.g. "919000415"
                out_dir = CACHE_DIR / hash_name

                if out_dir.exists() and (out_dir / "rcedit-x64.exe").exists():
                    print(f"[cache-helper] Already extracted: {hash_name}")
                    continue

                print(f"[cache-helper] Extracting: {f.name} -> {hash_name}")
                # Use 7za; ignore symlink errors
                result = subprocess.run(
                    [str(SEVENZ_EXE), "x", "-y", "-snld", "-bd", str(f), f"-o{out_dir}"],
                    capture_output=True, text=True
                )
                if out_dir.exists() and (out_dir / "rcedit-x64.exe").exists():
                    print(f"[cache-helper] Extraction succeeded (had {len(result.stderr.splitlines())} stderr lines)")
                else:
                    print(f"[cache-helper] Extraction may have failed, checking...")
            time.sleep(0.5)
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"[cache-helper] Error: {e}")
            time.sleep(1)


if __name__ == "__main__":
    main()
