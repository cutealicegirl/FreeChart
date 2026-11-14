@echo off
REM ───────────────────────────────────────────────────────────────────────
REM 生成 Free Chart 的 Windows 安装包（.exe 安装程序）
REM
REM 前置：先打包出 dist\Free Chart.exe（见仓库 README「打包」一节），
REM      再安装 Inno Setup 并把 iscc.exe 加入 PATH：
REM      winget install InnoSetup.InnoSetup   （或从 https://jrsoftware.org 下载）
REM ───────────────────────────────────────────────────────────────────────
cd /d "%~dp0"

if not exist "..\dist\Free Chart.exe" (
    echo [错误] 找不到 ..\dist\Free Chart.exe，请先运行 PyInstaller 打包。
    exit /b 1
)

where iscc >nul 2>nul
if errorlevel 1 (
    echo [错误] 未找到 iscc.exe（Inno Setup 编译器）。
    echo         请先安装 Inno Setup：winget install InnoSetup.InnoSetup
    echo         并把安装目录（含 iscc.exe）加入系统 PATH，然后重跑本脚本。
    exit /b 1
)

iscc "FreeChart.iss"
if errorlevel 1 (
    echo [错误] 安装包编译失败，请查看上面的输出。
    exit /b 1
)

echo [完成] 安装包已生成到 installer\out\FreeChart-Setup-*.exe
