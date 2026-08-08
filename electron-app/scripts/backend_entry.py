"""PyInstaller entry point for the wiki desktop backend.

Used by PyInstaller to build a standalone executable.
This is separate from the normal CLI entry point to avoid hatchling
entry-point registration issues in frozen builds.
"""

import uvicorn

from pi_wiki_desktop.app import create_app

app = create_app()

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8899)
