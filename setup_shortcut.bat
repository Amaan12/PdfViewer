@echo off
title Setup GitHub PDF Viewer Shortcut
cd /d "%~dp0"
echo [*] Creating Desktop Shortcut with Book Icon...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0create_shortcut.ps1"
pause
