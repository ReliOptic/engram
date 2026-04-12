"""Engram server entry point for PyInstaller packaging.

Starts uvicorn serving the FastAPI app on port 8000.
Opens the browser automatically.
"""

import sys
import os
import webbrowser
import threading

# Ensure the project root is on sys.path for imports
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


def open_browser():
    """Open browser after a short delay to let the server start."""
    import time
    time.sleep(2)
    webbrowser.open("http://localhost:8000")


def main():
    import uvicorn

    print("=" * 50)
    print("  Engram — Multi-Agent Support System")
    print("  Starting server on http://localhost:8000")
    print("  Press Ctrl+C to stop")
    print("=" * 50)
    print()

    # Open browser in background
    threading.Thread(target=open_browser, daemon=True).start()

    uvicorn.run(
        "backend.main:app",
        host="127.0.0.1",
        port=8000,
        log_level="info",
    )


if __name__ == "__main__":
    main()
