import os
import sys
import subprocess
import time
import urllib.request
from pathlib import Path

def main():
    root_dir = Path(__file__).resolve().parent
    backend_dir = root_dir / "ps01-sketch" / "backend"
    frontend_dir = root_dir / "ps01-sketch" / "ps01-sketch"

    python_exe = backend_dir / ".venv" / "Scripts" / "python.exe"
    if not python_exe.exists():
        python_exe = Path(sys.executable)

    npm_cmd = "npm.cmd" if sys.platform == "win32" else "npm"

    print("=" * 60)
    print("Starting AI Forensic Sketch Application Services")
    print(f"Root:     {root_dir}")
    print(f"Backend:  {backend_dir}")
    print(f"Frontend: {frontend_dir}")
    print("=" * 60)

    # 1. Start Backend
    backend_cmd = [
        str(python_exe),
        "-m",
        "uvicorn",
        "main:app",
        "--reload",
        "--host",
        "127.0.0.1",
        "--port",
        "8000",
    ]
    print("[1/2] Launching FastAPI Backend on http://127.0.0.1:8000 ...")
    backend_proc = subprocess.Popen(
        backend_cmd,
        cwd=str(backend_dir),
    )

    # 2. Start Frontend
    frontend_cmd = [
        npm_cmd,
        "run",
        "dev",
        "--",
        "--host",
        "127.0.0.1",
        "--port",
        "5173",
    ]
    print("[2/2] Launching Vite Frontend on http://127.0.0.1:5173 ...")
    frontend_proc = subprocess.Popen(
        frontend_cmd,
        cwd=str(frontend_dir),
    )

    # 3. Wait and verify health
    print("\nWaiting for services to become ready...")
    backend_ready = False
    frontend_ready = False

    for attempt in range(1, 31):
        if not backend_ready:
            try:
                with urllib.request.urlopen("http://127.0.0.1:8000/healthz", timeout=1) as resp:
                    if resp.status == 200:
                        backend_ready = True
                        print(f"✓ Backend is LIVE at http://127.0.0.1:8000 (attempt {attempt})")
            except Exception:
                pass

        if not frontend_ready:
            try:
                with urllib.request.urlopen("http://127.0.0.1:5173/", timeout=1) as resp:
                    if resp.status == 200:
                        frontend_ready = True
                        print(f"✓ Frontend is LIVE at http://127.0.0.1:5173 (attempt {attempt})")
            except Exception:
                pass

        if backend_ready and frontend_ready:
            break
        time.sleep(1)

    if backend_ready and frontend_ready:
        print("\nAll services are active and reachable!")
        print("  - Frontend UI: http://127.0.0.1:5173")
        print("  - Backend API: http://127.0.0.1:8000/docs")
    else:
        print(f"\nStartup check status: backend={backend_ready}, frontend={frontend_ready}")

    # Keep running
    try:
        while True:
            time.sleep(2)
            if backend_proc.poll() is not None:
                print("Backend process terminated unexpectedly.")
                break
            if frontend_proc.poll() is not None:
                print("Frontend process terminated unexpectedly.")
                break
    except KeyboardInterrupt:
        print("\nShutting down services...")
    finally:
        for proc in [backend_proc, frontend_proc]:
            try:
                proc.terminate()
            except Exception:
                pass

if __name__ == "__main__":
    main()
