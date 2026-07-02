#!/bin/bash
# Full packaging pipeline: backend -> frontend -> electron bundle
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== Pi Desktop Full Build Pipeline ==="

echo ""
echo "Step 1/3: Building Python backend..."
bash "$SCRIPT_DIR/build-backend.sh"

echo ""
echo "Step 2/3: Building React frontend..."
bash "$SCRIPT_DIR/build-frontend.sh"

echo ""
echo "Step 3/3: Packaging with electron-builder..."
cd "$SCRIPT_DIR/../electron"
npm install
npx electron-builder --config

echo ""
echo "=== Packaging complete ==="
echo "Check electron/release/ for the installer."
