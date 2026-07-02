#!/bin/bash
# Build the Python backend into a standalone executable using PyInstaller.
# Requires: pip install pyinstaller
# Output: scripts/dist/pi-desktop-backend/

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
BACKEND_DIR="$SCRIPT_DIR/../backend"
OUTPUT_DIR="$SCRIPT_DIR/dist"

echo "=== Building Pi Desktop Backend ==="
echo "Project root: $PROJECT_ROOT"
echo "Backend dir:  $BACKEND_DIR"
echo "Output dir:   $OUTPUT_DIR"

# Clean previous build
rm -rf "$OUTPUT_DIR"
mkdir -p "$OUTPUT_DIR"

cd "$PROJECT_ROOT"

# Install pyinstaller if not present
pip install pyinstaller 2>/dev/null || true

# Build with PyInstaller
pyinstaller \
  --onedir \
  --name pi-desktop-backend \
  --distpath "$OUTPUT_DIR" \
  --workpath "$OUTPUT_DIR/build" \
  --specpath "$OUTPUT_DIR" \
  --add-data "$PROJECT_ROOT/packages/ai/src/pi_ai:pi_ai" \
  --add-data "$PROJECT_ROOT/packages/agent/src/pi_agent:pi_agent" \
  --add-data "$PROJECT_ROOT/packages/coding-agent/src/pi_coding_agent:pi_coding_agent" \
  --add-data "$PROJECT_ROOT/packages/tui/src/pi_tui:pi_tui" \
  --hidden-import pi_agent \
  --hidden-import pi_ai \
  --hidden-import pi_coding_agent \
  --hidden-import pi_tui \
  --hidden-import pi_ai.providers.anthropic \
  --hidden-import pi_ai.providers.openai_responses \
  --hidden-import pi_ai.providers.google \
  "$BACKEND_DIR/src/pi_desktop_backend/main.py"

echo "=== Backend build complete ==="
echo "Output: $OUTPUT_DIR/pi-desktop-backend/"
