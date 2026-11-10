@echo off
title AI Forensic Sketch Launcher
echo ========================================================
echo Starting AI Forensic Sketch Application Services
echo ========================================================
start "FastAPI Backend" cmd /k "cd /d "%~dp0ps01-sketch\backend" && .venv\Scripts\python.exe -m uvicorn main:app --reload --host 127.0.0.1 --port 8000"
start "Vite Frontend" cmd /k "cd /d "%~dp0ps01-sketch\ps01-sketch" && npm run dev -- --host 127.0.0.1 --port 5173"
echo Both servers launched in interactive terminal windows.
echo Frontend: http://127.0.0.1:5173
echo Backend:  http://127.0.0.1:8000/docs
