@echo off
chcp 65001 >nul
title MCL-神启动器
cd /d "%~dp0"
where python.exe >nul 2>nul
if %errorlevel%==0 (
  python main.py
) else (
  "D:\python 3.15.0rc2\python.exe" main.py
)
if errorlevel 1 pause
