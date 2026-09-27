@echo off
chcp 65001 >nul
REM ============================================================
REM  NCL 启动器 · 一键发布到 GitHub
REM  用法：在本文件夹内双击运行（需已安装 Git，并已完成 gh 登录）
REM  仓库：https://github.com/doujiao-Studio/Minecraft-Launcher
REM  注意：源码在本目录，但线上仓库统一放在 MC启动器/ 子目录下；
REM        更新时先克隆远端，把本目录源码拷进 MC启动器/ 再提交推送。
REM ============================================================

setlocal
cd /d "%~dp0"

set REPO=doujiao-Studio/Minecraft-Launcher
set REPO_URL=https://github.com/doujiao-Studio/Minecraft-Launcher.git

echo [1/3] 检查 Git / gh ...
where git >nul 2>nul || (echo 错误：未安装 Git，请先到 https://git-scm.com 安装 && pause && exit /b 1)
git --version

where gh >nul 2>nul
if errorlevel 1 (
  echo 错误：未检测到 GitHub CLI(gh)。
  echo   请安装 gh 后运行 "gh auth login" 再执行本脚本。
  echo   若要修改 .github/workflows 下的工作流文件，还需要：
  echo       gh auth refresh -s workflow
  goto :eof
)

echo [2/3] 检查 gh 登录状态 ...
gh auth status >nul 2>nul
if errorlevel 1 (
  echo 尚未登录 GitHub，正在打开登录流程...
  gh auth login
  if errorlevel 1 (echo 登录失败，请手动 gh auth login 后重试 && pause && exit /b 1)
)

echo [3/3] 更新远端仓库 ...
echo   步骤：
echo     a) git clone --depth 1 %REPO_URL% %TEMP%\ncl-repo
echo     b) 用本目录的 main.py / mcl / tests / assets / README.md /
echo        LICENSE / MCL-Launcher.spec / CHANGELOG.md 覆盖 %TEMP%\ncl-repo\MC启动器\
echo     c) 在 %TEMP%\ncl-repo 提交并推送 main
echo     d) 打 tag 触发 CI 自动构建并发布 Release：
echo          git tag vX.Y.Z ^&^& git push origin vX.Y.Z
echo   （详见仓库 README 与 CHANGELOG.md）
echo.
echo 仓库地址： %REPO_URL%
pause
