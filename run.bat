@echo off
title GitHub PDF and EPUB Viewer

:: Check if dependencies are already installed (takes 0.05s). Only installs on first run.
python -c "import flask, requests" >nul 2>&1
if errorlevel 1 (
    echo First time setup: Installing Flask and Requests...
    python -m pip install flask requests -q
)

python "%~dp0viewer.py" %*
if errorlevel 1 pause
