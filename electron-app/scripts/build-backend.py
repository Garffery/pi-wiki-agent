"""Build the Python backend into a standalone executable using PyInstaller.

Usage:
    uv run python scripts/build-backend.py

Requires pyinstaller (installed in uv env)
Output: electron-app/build/dist/backend/backend.exe
"""

import shutil
import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
ELECTRON_DIR = SCRIPT_DIR.parent
ROOT = ELECTRON_DIR.parent
BUILD_DIR = ELECTRON_DIR / "build"
DIST_DIR = BUILD_DIR / "dist"                    # PyInstaller --distpath
WORK_DIR = BUILD_DIR / ".pyinstaller"            # PyInstaller --workpath
SPEC_DIR = BUILD_DIR                             # PyInstaller --specpath
ENTRY_POINT = SCRIPT_DIR / "backend_entry.py"
FRONTEND_DIR = ROOT / "frontend"
OUTPUT_DIR = DIST_DIR / "backend"                # Final: build/dist/backend/

# Monorepo packages that need to be importable
PACKAGE_DIRS = [
    ROOT / "desktop" / "src",
    ROOT / "packages" / "wiki-agent" / "src",
    ROOT / "packages" / "ai" / "src",
    ROOT / "packages" / "agent" / "src",
    ROOT / "packages" / "coding-agent" / "src",
]

HIDDEN_IMPORTS = [
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan.auto",
    "fastapi",
    "starlette",
    "pydantic",
    "pydantic.deprecated.decorator",
    "pi_wiki_agent",
    "pi_wiki_agent.core",
    "pi_wiki_agent.cron",
    "pi_wiki_desktop",
    "pi_wiki_desktop.api",
    "pi_wiki_desktop.api.v1",
    "pi_wiki_desktop.api.v1.endpoints",
    "pi_wiki_desktop.wiki_model_registry",
]


def clean():
    for d in [DIST_DIR, WORK_DIR]:
        if d.exists():
            shutil.rmtree(d)
    # Clean old spec files from BUILD_DIR
    for f in BUILD_DIR.glob("*.spec"):
        f.unlink()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def build_pythonpath():
    return ";".join(str(d) for d in PACKAGE_DIRS)


def run_pyinstaller():
    pyi_args = [
        sys.executable, "-m", "PyInstaller",
        str(ENTRY_POINT),
        "--onedir",
        "--name", "backend",
        "--distpath", str(DIST_DIR),
        "--workpath", str(WORK_DIR),
        "--specpath", str(SPEC_DIR),
        "--clean",
        "--noconfirm",
    ]

    if FRONTEND_DIR.exists():
        sep = ";" if sys.platform == "win32" else ":"
        pyi_args += ["--add-data", f"{FRONTEND_DIR}{sep}frontend"]

    for imp in HIDDEN_IMPORTS:
        pyi_args += ["--hidden-import", imp]

    pyi_args += [
        "--collect-submodules", "pi_wiki_agent",
        "--collect-submodules", "pi_wiki_desktop",
        "--collect-submodules", "pi_ai",
        "--collect-submodules", "pi_agent",
        "--collect-submodules", "pi_coding_agent",
    ]

    env = {**__import__("os").environ, "PYTHONPATH": build_pythonpath()}
    print(f"[build-backend] PYTHONPATH={env['PYTHONPATH']}")
    print(f"[build-backend] Running PyInstaller...")

    result = subprocess.run(pyi_args, env=env, cwd=str(ROOT))
    if result.returncode != 0:
        print("[build-backend] PyInstaller failed", file=sys.stderr)
        sys.exit(result.returncode)

    backend_exe = OUTPUT_DIR / "backend.exe"
    if backend_exe.exists():
        print(f"[build-backend] Done! Executable: {backend_exe}")
    else:
        print(f"[build-backend] ERROR: backend.exe not found at {backend_exe}", file=sys.stderr)
        print(f"[build-backend] Contents of {OUTPUT_DIR}:")
        for f in OUTPUT_DIR.rglob("*"):
            print(f"  {f}")
        sys.exit(1)


if __name__ == "__main__":
    clean()
    run_pyinstaller()
