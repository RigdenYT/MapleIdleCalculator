@echo off
cd /d "%~dp0"
py -3 maplestory_idle_companion_optimizer.py
if errorlevel 1 pause
