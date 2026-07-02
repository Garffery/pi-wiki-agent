#!/bin/bash
# Build the React frontend for production.
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
FRONTEND_DIR="$SCRIPT_DIR/../frontend"

echo "=== Building Pi Desktop Frontend ==="

cd "$FRONTEND_DIR"
npm ci
npm run build

echo "=== Frontend build complete ==="
echo "Output: $FRONTEND_DIR/dist/"
