@echo off
chcp 65001 >nul
REM ============================================================
REM  NCL 启动器 · 一键发布到 GitHub
REM  用法：在本文件夹内双击运行（需已安装 Git，并已完成 gh 登录）
REM ============================================================

setlocal
cd /d "%~dp0"

echo [1/4] 检查 Git / gh ...
where git >nul 2>nul || (echo 错误：未安装 Git，请先到 https://git-scm.com 安装 && pause && exit /b 1)
git --version

where gh >nul 2>nul
if errorlevel 1 (
  echo 警告：未检测到 GitHub CLI(gh)。
  echo   方式A（推荐）：安装 gh 后运行 "gh auth login" 再执行本脚本。
  echo   方式B（手动）：按文末说明手动添加 remote 并 push。
  goto :manual
)

echo [2/4] 检查 gh 登录状态 ...
gh auth status >nul 2>nul
if errorlevel 1 (
  echo 尚未登录 GitHub，正在打开登录流程...
  gh auth login
  if errorlevel 1 (echo 登录失败，请手动 gh auth login 后重试 && pause && exit /b 1)
)

echo [3/4] 设置本地提交身份（如已设置可忽略）...
git config user.name >nul 2>nul || git config user.name "NCL"
git config user.email >nul 2>nul || git config user.email "ncl@example.com"
echo   （请将其替换为你的 GitHub 用户名和邮箱，提交才会正确归属）

echo [4/4] 创建仓库并推送 ...
gh repo create NCL-Launcher --public --source=. --push --description "NCL 启动器 - 整合启动/版本/下载中心/服务器/内网穿透的一站式 Minecraft 工具（纯 Python + Tkinter）"
if errorlevel 1 (
  echo 创建/推送失败，可能是仓库名已存在或网络问题。
  goto :manual
)
echo.
echo 发布成功！仓库地址： https://github.com/%USERNAME%/NCL-Launcher
goto :eof

:manual
echo.
echo ============ 手动发布步骤 ============
echo 1) 打开 https://github.com/new
echo    仓库名填 NCL-Launcher，设为 Public，不要勾选初始化 README/.gitignore（我们已有）
echo 2) 在本文件夹执行：
echo       git init
echo       git add -A
echo       git commit -m "Initial commit: NCL Launcher"
echo       git branch -M main
echo       git remote add origin https://github.com/你的用户名/NCL-Launcher.git
echo       git push -u origin main
echo 3) 打版本标签并推送以触发自动构建 Release：
echo       git tag v1.0.0
echo       git push origin v1.0.0
pause
